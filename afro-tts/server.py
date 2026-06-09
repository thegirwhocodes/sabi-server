"""
Afro-TTS Server — African-accented English text-to-speech.

Uses intronhealth/afro-tts (XTTS v2 fine-tuned on 86 African accents).
Supports zero-shot voice cloning with a 6-second reference audio clip.

Endpoints:
    POST /tts          — Synthesize speech (JSON body)
    POST /tts/upload   — Synthesize with uploaded reference audio (multipart form)
    GET  /health       — Health check
    GET  /voices       — List available default reference voices
"""

import io
import os
import uuid
import time
import logging
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

import torch
import torchaudio
import numpy as np
from scipy.io.wavfile import write as wav_write
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, JSONResponse, StreamingResponse
from huggingface_hub import snapshot_download

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("afro-tts")

# ----- Configuration -----
MODEL_REPO = os.getenv("AFRO_TTS_MODEL_REPO", "intronhealth/afro-tts")
MODEL_DIR = os.getenv("AFRO_TTS_MODEL_DIR", "/app/models/afro-tts")
REFERENCE_DIR = os.getenv("AFRO_TTS_REFERENCE_DIR", "/app/reference_audio")
DEFAULT_SPEAKER = os.getenv("AFRO_TTS_DEFAULT_SPEAKER", "default")
MAX_TEXT_LENGTH = int(os.getenv("AFRO_TTS_MAX_TEXT_LENGTH", "2000"))
SAMPLE_RATE = 24000

# Global model reference
model: Optional[Xtts] = None
config: Optional[XttsConfig] = None
default_conditioning: dict = {}


def download_model():
    """Download the Afro-TTS model from HuggingFace Hub."""
    model_path = Path(MODEL_DIR)

    # Check if model is already downloaded
    if (model_path / "model.pth").exists() and (model_path / "config.json").exists():
        logger.info(f"Model already cached at {MODEL_DIR}")
        return str(model_path)

    logger.info(f"Downloading {MODEL_REPO} from HuggingFace Hub...")
    downloaded_path = snapshot_download(
        repo_id=MODEL_REPO,
        local_dir=str(model_path),
        allow_patterns=["*.pth", "*.json", "audios/*"],
    )
    logger.info(f"Model downloaded to {downloaded_path}")
    return downloaded_path


def load_model():
    """Load the Afro-TTS XTTS model onto GPU."""
    global model, config

    model_path = download_model()

    logger.info("Loading Afro-TTS model configuration...")
    config = XttsConfig()
    config.load_json(os.path.join(model_path, "config.json"))

    logger.info("Initializing Afro-TTS model...")
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=model_path, eval=True)
    model.cuda()

    logger.info("Afro-TTS model loaded on GPU.")

    # Log GPU memory usage
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        logger.info(f"GPU memory — allocated: {allocated:.2f} GB, reserved: {reserved:.2f} GB")


def precompute_default_conditioning():
    """Pre-compute speaker conditioning from reference audio for faster inference."""
    global default_conditioning

    ref_dir = Path(REFERENCE_DIR)
    ref_dir.mkdir(parents=True, exist_ok=True)

    # Check for the bundled reference audio from the model repo
    model_ref = Path(MODEL_DIR) / "audios" / "reference_accent.wav"
    default_ref = ref_dir / "default.wav"

    if model_ref.exists() and not default_ref.exists():
        import shutil
        shutil.copy2(model_ref, default_ref)
        logger.info(f"Copied bundled reference audio to {default_ref}")

    # Pre-compute conditioning for all .wav files in reference_audio/
    for wav_file in sorted(ref_dir.glob("*.wav")):
        speaker_name = wav_file.stem
        try:
            logger.info(f"Pre-computing conditioning for speaker '{speaker_name}'...")
            gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                audio_path=[str(wav_file)]
            )
            default_conditioning[speaker_name] = {
                "gpt_cond_latent": gpt_cond_latent,
                "speaker_embedding": speaker_embedding,
            }
            logger.info(f"Speaker '{speaker_name}' ready.")
        except Exception as e:
            logger.error(f"Failed to compute conditioning for '{speaker_name}': {e}")

    if not default_conditioning:
        logger.warning(
            "No reference audio found. Place .wav files in "
            f"{REFERENCE_DIR} or provide speaker_wav in requests."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    logger.info("=" * 60)
    logger.info("Starting Afro-TTS Server")
    logger.info("=" * 60)

    load_model()
    precompute_default_conditioning()

    logger.info("Afro-TTS server ready.")
    yield

    logger.info("Shutting down Afro-TTS server...")
    # Free GPU memory
    global model
    if model is not None:
        del model
        torch.cuda.empty_cache()


app = FastAPI(
    title="Afro-TTS Server",
    description="African-accented English text-to-speech using intronhealth/afro-tts",
    version="1.0.0",
    lifespan=lifespan,
)


def synthesize_speech(
    text: str,
    speaker_wav_path: Optional[str] = None,
    speaker_name: Optional[str] = None,
    language: str = "en",
    temperature: float = 0.85,
    speed: float = 1.0,
) -> np.ndarray:
    """
    Synthesize speech from text.

    Args:
        text: Input text to synthesize.
        speaker_wav_path: Path to a reference .wav for zero-shot cloning.
        speaker_name: Name of a pre-loaded speaker (from reference_audio/).
        language: Language code (only "en" supported currently).
        temperature: Sampling temperature (0.1-1.0, lower = more stable).
        speed: Playback speed multiplier.

    Returns:
        NumPy array of audio samples (float32, 24kHz).
    """
    if model is None:
        raise RuntimeError("Model not loaded")

    # Determine speaker conditioning
    if speaker_wav_path:
        # Zero-shot cloning from provided audio
        logger.info(f"Computing conditioning from provided audio: {speaker_wav_path}")
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[speaker_wav_path]
        )
    elif speaker_name and speaker_name in default_conditioning:
        gpt_cond_latent = default_conditioning[speaker_name]["gpt_cond_latent"]
        speaker_embedding = default_conditioning[speaker_name]["speaker_embedding"]
    elif "default" in default_conditioning:
        gpt_cond_latent = default_conditioning["default"]["gpt_cond_latent"]
        speaker_embedding = default_conditioning["default"]["speaker_embedding"]
    else:
        # Fallback: use the first available speaker
        if default_conditioning:
            first_speaker = next(iter(default_conditioning))
            gpt_cond_latent = default_conditioning[first_speaker]["gpt_cond_latent"]
            speaker_embedding = default_conditioning[first_speaker]["speaker_embedding"]
        else:
            raise HTTPException(
                status_code=400,
                detail="No speaker reference available. Provide speaker_wav or "
                       "place a .wav file in the reference_audio/ directory.",
            )

    # Synthesize
    out = model.inference(
        text=text,
        language=language,
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=temperature,
        speed=speed,
    )

    return np.array(out["wav"], dtype=np.float32)


def audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert float32 audio array to WAV bytes."""
    # Normalize to int16
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    wav_write(buf, sample_rate, audio_int16)
    buf.seek(0)
    return buf.read()


def audio_to_mp3_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert float32 audio array to MP3 bytes using torchaudio."""
    tensor = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
    buf = io.BytesIO()
    # Use torchaudio to save as MP3 (requires ffmpeg in container)
    torchaudio.save(buf, tensor, sample_rate, format="mp3")
    buf.seek(0)
    return buf.read()


# ----- API Endpoints -----

@app.get("/health")
async def health():
    """Health check."""
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "gpu": torch.cuda.get_device_name(0),
            "vram_allocated_gb": round(torch.cuda.memory_allocated() / 1024**3, 2),
            "vram_reserved_gb": round(torch.cuda.memory_reserved() / 1024**3, 2),
        }

    return {
        "status": "ok" if model is not None else "loading",
        "model": MODEL_REPO,
        "speakers": list(default_conditioning.keys()),
        "gpu": gpu_info,
    }


@app.get("/voices")
async def list_voices():
    """List available pre-loaded speaker voices."""
    return {
        "voices": list(default_conditioning.keys()),
        "default": DEFAULT_SPEAKER,
        "note": "You can also provide any .wav file for zero-shot voice cloning.",
    }


@app.post("/tts")
async def tts_endpoint(request: Request):
    """
    Synthesize speech from text.

    JSON body:
        text (str):           Text to synthesize (required, max 2000 chars).
        speaker_wav (str):    Path to reference .wav for voice cloning (optional).
        speaker_name (str):   Name of pre-loaded speaker (optional, default: "default").
        language (str):       Language code (default: "en").
        temperature (float):  Sampling temperature (default: 0.85).
        speed (float):        Speed multiplier (default: 1.0).
        format (str):         Output format: "wav" or "mp3" (default: "wav").

    Returns:
        Audio file (audio/wav or audio/mpeg).
    """
    data = await request.json()
    text = data.get("text", "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds {MAX_TEXT_LENGTH} character limit ({len(text)} chars)",
        )

    speaker_wav = data.get("speaker_wav")
    speaker_name = data.get("speaker_name", DEFAULT_SPEAKER)
    language = data.get("language", "en")
    temperature = float(data.get("temperature", 0.85))
    speed = float(data.get("speed", 1.0))
    output_format = data.get("format", "wav").lower()

    start = time.time()

    try:
        audio = synthesize_speech(
            text=text,
            speaker_wav_path=speaker_wav,
            speaker_name=speaker_name,
            language=language,
            temperature=temperature,
            speed=speed,
        )
    except Exception as e:
        logger.error(f"Synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")

    elapsed = time.time() - start
    duration = len(audio) / SAMPLE_RATE
    logger.info(
        f"TTS: {len(text)} chars -> {duration:.1f}s audio "
        f"(inference: {elapsed:.2f}s, RTF: {elapsed/duration:.2f}x)"
    )

    if output_format == "mp3":
        audio_bytes = audio_to_mp3_bytes(audio)
        media_type = "audio/mpeg"
        filename = f"afro_tts_{uuid.uuid4().hex[:8]}.mp3"
    else:
        audio_bytes = audio_to_wav_bytes(audio)
        media_type = "audio/wav"
        filename = f"afro_tts_{uuid.uuid4().hex[:8]}.wav"

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Inference-Time": f"{elapsed:.3f}",
            "X-Audio-Duration": f"{duration:.3f}",
        },
    )


@app.post("/tts/upload")
async def tts_upload_endpoint(
    text: str = Form(...),
    speaker_wav: UploadFile = File(None),
    speaker_name: str = Form("default"),
    language: str = Form("en"),
    temperature: float = Form(0.85),
    speed: float = Form(1.0),
    format: str = Form("wav"),
):
    """
    Synthesize speech with an uploaded reference audio for voice cloning.

    Multipart form:
        text (str):              Text to synthesize (required).
        speaker_wav (file):      Reference .wav file for voice cloning (optional).
        speaker_name (str):      Pre-loaded speaker name (optional).
        language (str):          Language code (default: "en").
        temperature (float):     Sampling temperature (default: 0.85).
        speed (float):           Speed multiplier (default: 1.0).
        format (str):            Output format: "wav" or "mp3" (default: "wav").
    """
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds {MAX_TEXT_LENGTH} character limit",
        )

    speaker_wav_path = None

    if speaker_wav and speaker_wav.filename:
        # Save uploaded file temporarily
        suffix = Path(speaker_wav.filename).suffix or ".wav"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir="/tmp")
        content = await speaker_wav.read()
        tmp.write(content)
        tmp.close()
        speaker_wav_path = tmp.name

    start = time.time()

    try:
        audio = synthesize_speech(
            text=text,
            speaker_wav_path=speaker_wav_path,
            speaker_name=speaker_name,
            language=language,
            temperature=temperature,
            speed=speed,
        )
    except Exception as e:
        logger.error(f"Synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
    finally:
        # Clean up temp file
        if speaker_wav_path:
            try:
                os.unlink(speaker_wav_path)
            except OSError:
                pass

    elapsed = time.time() - start
    duration = len(audio) / SAMPLE_RATE
    logger.info(
        f"TTS (upload): {len(text)} chars -> {duration:.1f}s audio "
        f"(inference: {elapsed:.2f}s)"
    )

    output_format = format.lower()
    if output_format == "mp3":
        audio_bytes = audio_to_mp3_bytes(audio)
        media_type = "audio/mpeg"
        filename = f"afro_tts_{uuid.uuid4().hex[:8]}.mp3"
    else:
        audio_bytes = audio_to_wav_bytes(audio)
        media_type = "audio/wav"
        filename = f"afro_tts_{uuid.uuid4().hex[:8]}.wav"

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Inference-Time": f"{elapsed:.3f}",
            "X-Audio-Duration": f"{duration:.3f}",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
