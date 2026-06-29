"""
Chatterbox Turbo TTS Server for Sabi Voice AI.

Self-hosted, emotionally expressive Nigerian English TTS.
Uses Chatterbox Turbo (350M params, MIT license) with voice cloning
from a short reference audio clip.

Features:
- Voice cloning from 5-10s reference audio
- Emotion control via `exaggeration` parameter (0.25-2.0)
- Paralinguistic tags: [laugh], [chuckle], [sigh], [cough]
- Pronunciation preprocessing for Nigerian English
- Volume normalization for consistent output
- API-compatible with existing afro-tts endpoints

Run: uvicorn server:app --host 0.0.0.0 --port 8001
"""

import io
import os
import re
import time
import asyncio
import hashlib
import logging
from pathlib import Path

import numpy as np
import torch
import torchaudio
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import Response, JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sabi.chatterbox")

# Configuration
MODEL_DIR = os.getenv("CHATTERBOX_MODEL_DIR", "")
REFERENCE_DIR = os.getenv("CHATTERBOX_REFERENCE_DIR", "/app/reference_audio")
DEFAULT_SPEAKER = os.getenv("CHATTERBOX_DEFAULT_SPEAKER", "bukola")
MAX_TEXT_LENGTH = int(os.getenv("CHATTERBOX_MAX_TEXT_LENGTH", "2000"))
MAX_CONCURRENT_SYNTHESIS = max(1, int(os.getenv("CHATTERBOX_MAX_CONCURRENT", "1")))
MAX_QUEUE_WAITERS = max(0, int(os.getenv("CHATTERBOX_MAX_QUEUE", "12")))
QUEUE_TIMEOUT_SECONDS = max(0.1, float(os.getenv("CHATTERBOX_QUEUE_TIMEOUT_SECONDS", "8")))
CACHE_ENABLED = os.getenv("CHATTERBOX_CACHE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
CACHE_DIR = Path(os.getenv("CHATTERBOX_CACHE_DIR", "/app/tts_cache"))
CACHE_MAX_FILES = max(0, int(os.getenv("CHATTERBOX_CACHE_MAX_FILES", "5000")))

# Pronunciation map for Nigerian English words the model may mispronounce
PRONUNCIATION_MAP = {
    "Sabi": "Sahbee",
    "sabi": "sahbee",
    "SABI": "SAHBEE",
    "Sabi's": "Sahbee's",
    "sabi's": "sahbee's",
}

_NAIRA_then_DIGITS = re.compile(r"\bnaira\s+(\d[\d,]*(?:\.\d+)?)\b", re.I)
_NAIRA_then_TENS_COMPOUND = re.compile(
    r"\bnaira\s+((?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:-(?:one|two|three|four|five|six|seven|eight|nine))?)\b",
    re.I,
)
_NAIRA_then_TEENS = re.compile(
    r"\bnaira\s+(ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b",
    re.I,
)
_NAIRA_then_SINGLE = re.compile(
    r"\bnaira\s+(one|two|three|four|five|six|seven|eight|nine)\b"
    r"(?!\s+hundred)(?!\s+thousand)",
    re.I,
)


def normalize_money_for_speech(raw: str) -> str:
    """Match curriculum-app/lib/voice/normalize-money-for-speech.ts (keep in sync)."""
    s = raw

    def _amount_after_naira_symbol(m: re.Match) -> str:
        return f"{m.group(1).replace(',', '')} naira"

    s = re.sub(r"₦\s*(\d[\d,]*(?:\.\d+)?)\b", _amount_after_naira_symbol, s)
    s = s.replace("₦", "naira")

    def _flip_digits(m: re.Match) -> str:
        return f"{m.group(1).replace(',', '')} naira"

    s = _NAIRA_then_DIGITS.sub(_flip_digits, s)
    s = _NAIRA_then_TENS_COMPOUND.sub(lambda m: f"{m.group(1)} naira", s)
    s = _NAIRA_then_TEENS.sub(lambda m: f"{m.group(1)} naira", s)
    s = _NAIRA_then_SINGLE.sub(lambda m: f"{m.group(1)} naira", s)
    return re.sub(r"\s{2,}", " ", s)


def preprocess_text(text: str) -> str:
    """Apply pronunciation fixes and text cleanup for TTS."""
    text = normalize_money_for_speech(text)
    # Apply pronunciation map (word-boundary-aware)
    for original, replacement in PRONUNCIATION_MAP.items():
        text = re.sub(
            r"\b" + re.escape(original) + r"\b",
            replacement,
            text,
        )
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    # Truncate
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
    return text


def normalize_audio(audio: np.ndarray, target_db: float = -1.0) -> np.ndarray:
    """Peak-normalize audio to target dB level."""
    peak = np.max(np.abs(audio))
    if peak > 0:
        target_amplitude = 10 ** (target_db / 20.0)  # -1dB ≈ 0.891
        audio = audio * (target_amplitude / peak)
    return audio


def audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert float32 numpy array to WAV bytes."""
    # Normalize first
    audio = normalize_audio(audio)
    # Convert to int16
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    import scipy.io.wavfile
    scipy.io.wavfile.write(buf, sample_rate, audio_int16)
    return buf.getvalue()


def audio_to_mp3_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert float32 numpy array to MP3 bytes."""
    # Normalize first
    audio = normalize_audio(audio)
    tensor = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
    buf = io.BytesIO()
    torchaudio.save(buf, tensor, sample_rate, format="mp3")
    return buf.getvalue()


# Global model state
model = None
speaker_audio_cache = {}  # name → audio_prompt_path
tts_semaphore: asyncio.BoundedSemaphore | None = None
queue_waiters = 0
queue_waiters_lock: asyncio.Lock | None = None
stats = {
    "requests": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "syntheses": 0,
    "queue_rejections": 0,
    "queue_timeouts": 0,
    "errors": 0,
}


def load_model():
    """Load Chatterbox Turbo model."""
    global model
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    # Pre-download model without token (it's public, but library defaults to token=True)
    from huggingface_hub import snapshot_download
    snapshot_download("ResembleAI/chatterbox-turbo", token=False)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading Chatterbox Turbo on {device}...")
    # Set HF_TOKEN to a non-empty dummy so the library uses local cache
    os.environ["HF_TOKEN"] = "local"
    model = ChatterboxTurboTTS.from_pretrained(device=device)
    logger.info(f"Chatterbox Turbo loaded. Sample rate: {model.sr}")


def load_speakers():
    """Pre-load reference audio paths for each speaker."""
    global speaker_audio_cache
    ref_dir = Path(REFERENCE_DIR)

    if not ref_dir.exists():
        logger.warning(f"Reference audio directory not found: {ref_dir}")
        return

    for wav_file in sorted(ref_dir.glob("*.wav")):
        name = wav_file.stem
        speaker_audio_cache[name] = str(wav_file)
        logger.info(f"  Speaker loaded: {name} ({wav_file.name})")

    if not speaker_audio_cache:
        logger.warning("No reference audio files found!")
    else:
        logger.info(f"Loaded {len(speaker_audio_cache)} speaker(s)")


def synthesize_speech(
    text: str,
    speaker_name: str = None,
    speaker_wav_path: str = None,
    exaggeration: float = 0.5,
) -> tuple[np.ndarray, int]:
    """
    Synthesize speech using Chatterbox Turbo.

    Args:
        text: Input text (may include [laugh], [sigh] etc.)
        speaker_name: Name of pre-loaded speaker
        speaker_wav_path: Path to reference audio (overrides speaker_name)
        exaggeration: Emotion intensity (0.25=flat, 0.5=neutral, 1.0+=dramatic)

    Returns:
        (audio_array, sample_rate)
    """
    if model is None:
        raise RuntimeError("Model not loaded")

    # Determine reference audio
    audio_prompt = speaker_wav_path
    if not audio_prompt:
        if speaker_name and speaker_name in speaker_audio_cache:
            audio_prompt = speaker_audio_cache[speaker_name]
        elif DEFAULT_SPEAKER in speaker_audio_cache:
            audio_prompt = speaker_audio_cache[DEFAULT_SPEAKER]
        elif speaker_audio_cache:
            audio_prompt = next(iter(speaker_audio_cache.values()))

    if not audio_prompt:
        raise RuntimeError("No reference audio available for voice cloning")

    # Preprocess text (pronunciation fixes)
    processed_text = preprocess_text(text)
    logger.info(f"Synthesizing: '{processed_text[:80]}...' (exag={exaggeration})")

    # Generate audio
    wav_tensor = model.generate(
        processed_text,
        audio_prompt_path=audio_prompt,
        exaggeration=exaggeration,
    )

    # Convert to numpy
    audio = wav_tensor.squeeze().cpu().numpy()
    return audio, model.sr


# --- FastAPI App ---

app = FastAPI(
    title="Sabi Chatterbox TTS",
    description="Emotionally expressive Nigerian English TTS for Sabi voice AI",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    """Load model and speakers on startup."""
    global tts_semaphore, queue_waiters_lock
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tts_semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT_SYNTHESIS)
    queue_waiters_lock = asyncio.Lock()
    load_model()
    load_speakers()
    logger.info(
        "Chatterbox TTS server ready. max_concurrent=%s max_queue=%s queue_timeout=%.1fs cache=%s",
        MAX_CONCURRENT_SYNTHESIS,
        MAX_QUEUE_WAITERS,
        QUEUE_TIMEOUT_SECONDS,
        "on" if CACHE_ENABLED else "off",
    )


@app.get("/health")
async def health():
    """Health check."""
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "gpu": torch.cuda.get_device_name(0),
            "vram_allocated_gb": round(torch.cuda.memory_allocated() / 1e9, 2),
            "vram_reserved_gb": round(torch.cuda.memory_reserved() / 1e9, 2),
        }
    return {
        "status": "ok",
        "model": "chatterbox-turbo",
        "speakers": list(speaker_audio_cache.keys()),
        "gpu": gpu_info,
        "inference": {
            "max_concurrent": MAX_CONCURRENT_SYNTHESIS,
            "max_queue": MAX_QUEUE_WAITERS,
            "queue_timeout_seconds": QUEUE_TIMEOUT_SECONDS,
            "current_waiters": queue_waiters,
        },
        "cache": {
            "enabled": CACHE_ENABLED,
            "dir": str(CACHE_DIR),
            "max_files": CACHE_MAX_FILES,
        },
        "stats": stats,
    }


@app.get("/voices")
async def list_voices():
    """List available voices."""
    return {
        "voices": list(speaker_audio_cache.keys()),
        "default": DEFAULT_SPEAKER,
    }


def _cache_path(
    text: str,
    speaker_name: str,
    exaggeration: float,
    output_format: str,
) -> Path:
    key_material = "\n".join(
        [
            "chatterbox-turbo-v1",
            speaker_name or "",
            f"{exaggeration:.2f}",
            output_format,
            preprocess_text(text),
        ]
    )
    digest = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    suffix = "mp3" if output_format == "mp3" else "wav"
    return CACHE_DIR / f"{digest}.{suffix}"


async def _acquire_tts_slot() -> tuple[bool, str]:
    global queue_waiters
    if tts_semaphore is None or queue_waiters_lock is None:
        return False, "not_ready"

    counted_waiter = False
    async with queue_waiters_lock:
        if tts_semaphore.locked():
            if queue_waiters >= MAX_QUEUE_WAITERS:
                stats["queue_rejections"] += 1
                return False, "queue_full"
            queue_waiters += 1
            counted_waiter = True

    try:
        await asyncio.wait_for(tts_semaphore.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
        return True, "ok"
    except asyncio.TimeoutError:
        stats["queue_timeouts"] += 1
        return False, "queue_timeout"
    finally:
        if counted_waiter:
            async with queue_waiters_lock:
                queue_waiters = max(0, queue_waiters - 1)


def _release_tts_slot() -> None:
    if tts_semaphore is not None:
        tts_semaphore.release()


def _synthesize_and_encode(
    text: str,
    speaker_name: str,
    exaggeration: float,
    output_format: str,
) -> tuple[bytes, str, float, float]:
    start = time.time()
    audio, sr = synthesize_speech(
        text=text,
        speaker_name=speaker_name,
        exaggeration=exaggeration,
    )
    elapsed = time.time() - start
    duration = len(audio) / sr

    if output_format == "mp3":
        audio_bytes = audio_to_mp3_bytes(audio, sr)
        media_type = "audio/mpeg"
    else:
        audio_bytes = audio_to_wav_bytes(audio, sr)
        media_type = "audio/wav"

    return audio_bytes, media_type, elapsed, duration


def _write_cache(cache_path: Path, audio_bytes: bytes) -> None:
    if not CACHE_ENABLED:
        return
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_bytes(audio_bytes)
    tmp_path.replace(cache_path)


def _prune_cache_if_needed() -> None:
    if not CACHE_ENABLED or CACHE_MAX_FILES <= 0:
        return
    try:
        files = [path for path in CACHE_DIR.iterdir() if path.is_file()]
    except OSError:
        return
    overflow = len(files) - CACHE_MAX_FILES
    if overflow <= 0:
        return
    for path in sorted(files, key=lambda item: item.stat().st_mtime)[:overflow]:
        try:
            path.unlink()
        except OSError:
            pass


@app.post("/tts")
async def tts_endpoint(request: Request):
    """
    Synthesize speech from text.

    JSON body:
    {
        "text": "Hello! [laugh] Great job!",
        "speaker_name": "bukola",
        "speaker_wav": null,
        "exaggeration": 0.5,
        "format": "wav",
        "temperature": 0.85,
        "speed": 1.0
    }
    """
    stats["requests"] += 1
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    text = data.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    speaker_name = data.get("speaker_name", DEFAULT_SPEAKER)
    exaggeration = float(data.get("exaggeration", 0.5))
    output_format = data.get("format", "wav").lower()
    if output_format not in {"mp3", "wav"}:
        return JSONResponse({"error": "Unsupported format"}, status_code=400)

    # Clamp exaggeration
    exaggeration = max(0.25, min(2.0, exaggeration))

    cache_path = _cache_path(text, speaker_name, exaggeration, output_format)
    if CACHE_ENABLED and cache_path.exists():
        stats["cache_hits"] += 1
        audio_bytes = cache_path.read_bytes()
        media_type = "audio/mpeg" if output_format == "mp3" else "audio/wav"
        logger.info("TTS cache hit: %s chars exag=%.2f", len(text), exaggeration)
        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={
                "X-Cache": "HIT",
                "X-Exaggeration": f"{exaggeration:.2f}",
            },
        )

    stats["cache_misses"] += 1
    acquired, reason = await _acquire_tts_slot()
    if not acquired:
        status = 503 if reason in {"queue_full", "queue_timeout"} else 500
        return JSONResponse(
            {"error": reason},
            status_code=status,
            headers={"Retry-After": str(int(QUEUE_TIMEOUT_SECONDS))},
        )

    try:
        audio_bytes, media_type, elapsed, duration = await asyncio.to_thread(
            _synthesize_and_encode,
            text,
            speaker_name,
            exaggeration,
            output_format,
        )
        stats["syntheses"] += 1
        _write_cache(cache_path, audio_bytes)
        if stats["syntheses"] % 100 == 0:
            _prune_cache_if_needed()
    except Exception as e:
        stats["errors"] += 1
        logger.error(f"Synthesis error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        _release_tts_slot()

    logger.info(f"TTS: {len(text)} chars → {duration:.1f}s audio ({elapsed:.1f}s, exag={exaggeration})")

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "X-Cache": "MISS",
            "X-Inference-Time": f"{elapsed:.3f}",
            "X-Audio-Duration": f"{duration:.3f}",
            "X-Exaggeration": f"{exaggeration:.2f}",
        },
    )


@app.post("/tts/upload")
async def tts_upload(
    text: str = Form(...),
    speaker_wav: UploadFile = File(...),
    exaggeration: float = Form(0.5),
    output_format: str = Form("wav"),
):
    """Synthesize speech with an uploaded reference audio file."""
    # Save uploaded file temporarily
    import tempfile
    suffix = Path(speaker_wav.filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await speaker_wav.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        exaggeration = max(0.25, min(2.0, exaggeration))

        start = time.time()
        audio, sr = synthesize_speech(
            text=text,
            speaker_wav_path=tmp_path,
            exaggeration=exaggeration,
        )
        elapsed = time.time() - start
        duration = len(audio) / sr

        if output_format == "mp3":
            audio_bytes = audio_to_mp3_bytes(audio, sr)
            media_type = "audio/mpeg"
        else:
            audio_bytes = audio_to_wav_bytes(audio, sr)
            media_type = "audio/wav"

        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={
                "X-Inference-Time": f"{elapsed:.3f}",
                "X-Audio-Duration": f"{duration:.3f}",
            },
        )
    finally:
        os.unlink(tmp_path)
