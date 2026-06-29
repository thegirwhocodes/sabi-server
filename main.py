"""
Sabi Voice AI Server
Self-hosted voice tutoring server for Education for Equality.

Components:
- STT: faster-whisper (Whisper large-v3)
- LLM: Claude Haiku (primary) / Ollama Llama 3.1 8B (fallback) + RAG
- TTS: YarnGPT API (Nigerian voices)
- Telephony: Africa's Talking voice webhooks + Asterisk SIP (flash callback)

Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os
import uuid
import time
import asyncio
import logging
from pathlib import Path
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from stt import SpeechToText
from tts import TextToSpeech
from llm import SabiLLM
from memory import StudentMemory
from call_admin import (
    call_recording_path,
    call_sidecar_path,
    call_turn_audio_path,
    list_call_records,
    load_call_record,
)
from feedback_admin import (
    feedback_audio_path,
    feedback_sidecar_path,
    list_feedback_records,
    load_feedback_record,
)
from admin_review import render_admin_review_page
from curriculum_review import build_curriculum_review_map
from voice import router as voice_router
from voice_twilio import router as twilio_router
from voice_asterisk import start_agi_server
from voice_realtime import record_hangup_event, register_call, start_audiosocket_server
from secret_loader import get_secret

load_dotenv()

# Chatterbox TTS server (self-hosted, emotion-aware)
CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "http://localhost:8001")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sabi")

# Audio file storage
AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

import re
import httpx

def detect_exaggeration(text: str) -> float:
    """Detect emotion from LLM response and return Chatterbox exaggeration level."""
    if re.search(r'\[laugh\]|!\s*!|Well done|Correct|Yes!|Great|Excellent|Sharp sharp', text, re.I):
        return 0.75
    if re.search(r'\[sigh\]|Almost|Good try|tricky|Let me help', text, re.I):
        return 0.35
    if re.search(r'\[chuckle\]|Oya|Let.s try|ready', text, re.I):
        return 0.6
    return 0.5

async def synthesize_chatterbox(text: str, output_path: str) -> bool:
    """Generate speech via Chatterbox Turbo with emotion-aware exaggeration."""
    try:
        exaggeration = detect_exaggeration(text)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{CHATTERBOX_URL}/tts",
                json={
                    "text": text[:2000],
                    "speaker_name": "naomi",
                    "format": "mp3",
                    "exaggeration": exaggeration,
                },
            )
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"Chatterbox TTS: {len(text)} chars, exag={exaggeration}")
            return True
    except Exception as e:
        logger.warning(f"Chatterbox TTS failed: {e}")
        return False

# Pre-generated thinking cues
THINKING_CUES = [
    "Hmm...",
    "Okay...",
    "Let me see...",
    "Ah...",
    "Right...",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup, cleanup on shutdown."""
    logger.info("Loading Sabi AI models...")

    # Initialize components
    app.state.stt = SpeechToText()
    app.state.tts = TextToSpeech()
    app.state.llm = SabiLLM()
    app.state.memory = StudentMemory()

    # Pre-generate thinking cue audio files
    logger.info("Generating thinking cue audio...")
    for i, cue in enumerate(THINKING_CUES):
        cue_path = AUDIO_DIR / f"thinking_{i}.mp3"
        if not cue_path.exists():
            try:
                app.state.tts.synthesize(cue, str(cue_path))
            except Exception as e:
                logger.warning(f"Could not pre-generate thinking cue {i}: {e}")
    logger.info(f"Thinking cues ready ({len(THINKING_CUES)} files)")

    # Pre-generate thinking cues as WAV for Asterisk playback
    shared_audio = Path("/shared/audio")
    shared_audio.mkdir(parents=True, exist_ok=True)
    for i, cue in enumerate(THINKING_CUES):
        wav_path = shared_audio / f"thinking_{i}.wav"
        if not wav_path.exists():
            try:
                mp3_path = str(shared_audio / f"thinking_{i}.mp3")
                app.state.tts.synthesize(cue, mp3_path)
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-i", mp3_path,
                     "-ar", "8000", "-ac", "1", "-sample_fmt", "s16",
                     str(wav_path)],
                    capture_output=True, check=True,
                )
                os.unlink(mp3_path)
            except Exception as e:
                logger.warning(f"Could not generate Asterisk thinking cue {i}: {e}")
    logger.info("Asterisk thinking cues ready (WAV)")

    # Start FastAGI server as a fallback for older dialplans.
    agi_server = await start_agi_server(
        stt=app.state.stt,
        llm=app.state.llm,
        tts=app.state.tts,
        memory=app.state.memory,
    )
    audiosocket_server = await start_audiosocket_server(
        stt=app.state.stt,
        llm=app.state.llm,
        tts=app.state.tts,
        memory=app.state.memory,
    )

    logger.info("All models loaded. Sabi is ready.")
    yield

    # Cleanup
    logger.info("Shutting down Sabi server...")
    audiosocket_server.close()
    await audiosocket_server.wait_closed()
    agi_server.close()
    await agi_server.wait_closed()


app = FastAPI(
    title="Sabi Voice AI Server",
    description="Self-hosted AI voice tutor for Nigerian children",
    version="0.1.0",
    lifespan=lifespan,
)

# API key authentication — protects AI endpoints from unauthorized use
SABI_API_KEY = get_secret("SABI_API_KEY")
SABI_ADMIN_PIN = get_secret("SABI_ADMIN_PIN", "123")
TRUST_API_KEY_FOR_RATE_LIMIT_BYPASS = os.getenv(
    "SABI_TRUST_API_KEY_FOR_RATE_LIMIT_BYPASS", "1"
).strip().lower() not in {"0", "false", "no"}
OPEN_PATHS = {"/health", "/docs", "/openapi.json"}
OPEN_PREFIXES = ("/voice/", "/audio/", "/asterisk/")
READ_ONLY_ADMIN_METHODS = {"GET", "HEAD", "OPTIONS"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP sliding-window rate limiter for public and AI endpoints."""

    LIMITS = {
        "ai": (30, 60),
        "voice": (120, 60),
        "general": (60, 60),
    }
    AI_PATHS = {"/stt", "/tts", "/llm", "/process-turn"}
    VOICE_PREFIXES = ("/voice/", "/asterisk/")

    def __init__(self, app):
        super().__init__(app)
        self._hits = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self.AI_PATHS:
            tier = "ai"
            if self._is_trusted_ai_request(request):
                return await call_next(request)
        elif path.startswith(self.VOICE_PREFIXES):
            tier = "voice"
        else:
            tier = "general"

        limit, window = self.LIMITS[tier]
        now = time.monotonic()
        ip = self._client_ip(request)
        key = (tier, ip)
        hits = self._hits[key]

        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return JSONResponse(
                {"error": "Too Many Requests"},
                status_code=429,
                headers={"Retry-After": str(window)},
            )

        hits.append(now)
        return await call_next(request)

    @staticmethod
    def _client_ip(request: Request) -> str:
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.rsplit(",", 1)[-1].strip()
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _is_trusted_ai_request(request: Request) -> bool:
        if not TRUST_API_KEY_FOR_RATE_LIMIT_BYPASS or not SABI_API_KEY:
            return False
        supplied_key = (
            request.headers.get("X-API-Key")
            or request.query_params.get("api_key")
            or request.query_params.get("key")
        )
        return supplied_key == SABI_API_KEY


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
            return await call_next(request)
        if not SABI_API_KEY:
            return await call_next(request)
        key = (
            request.headers.get("X-API-Key")
            or request.headers.get("X-Admin-Pin")
            or request.query_params.get("api_key")
            or request.query_params.get("key")
            or request.query_params.get("pin")
        )
        if (
            SABI_ADMIN_PIN
            and request.method in READ_ONLY_ADMIN_METHODS
            and path.startswith("/admin/")
            and key == SABI_ADMIN_PIN
        ):
            return await call_next(request)
        if key != SABI_API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)
app.add_middleware(RateLimitMiddleware)

# Mount audio files directory
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# Voice webhook routes (Africa's Talking)
app.include_router(voice_router, prefix="/voice")

# Twilio voice webhook routes
app.include_router(twilio_router, prefix="/voice/twilio")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "stt": "loaded" if hasattr(app.state, "stt") else "not loaded",
        "tts": "loaded" if hasattr(app.state, "tts") else "not loaded",
        "llm": "loaded" if hasattr(app.state, "llm") else "not loaded",
    }


@app.post("/stt")
async def speech_to_text(request: Request):
    """Transcribe audio to text using Whisper."""
    form = await request.form()
    audio_file = form.get("audio")
    if not audio_file:
        return JSONResponse({"error": "No audio file provided"}, status_code=400)

    # Save uploaded audio temporarily
    temp_path = AUDIO_DIR / f"input_{uuid.uuid4().hex}.wav"
    content = await audio_file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        start = time.time()
        result = app.state.stt.transcribe(str(temp_path))
        elapsed = time.time() - start
        logger.info(f"STT: '{result['text']}' (confidence={result['confidence']:.2f}, {elapsed:.1f}s)")
        return JSONResponse(result)
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/tts")
async def text_to_speech(request: Request):
    """Generate speech audio from text using Chatterbox, falling back to YarnGPT."""
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    audio_id = uuid.uuid4().hex
    output_path = AUDIO_DIR / f"tts_{audio_id}.mp3"

    start = time.time()
    if not await synthesize_chatterbox(text, str(output_path)):
        app.state.tts.synthesize(text, str(output_path))
    elapsed = time.time() - start
    logger.info(f"TTS: {len(text)} chars → {output_path.name} ({elapsed:.1f}s)")

    return FileResponse(
        str(output_path),
        media_type="audio/mpeg",
        filename=f"sabi_{audio_id}.mp3",
    )


@app.post("/llm")
async def llm_response(request: Request):
    """Get teaching response from Claude/Ollama + RAG."""
    data = await request.json()
    messages = data.get("messages", [])
    student_id = data.get("student_id")
    current_module = data.get("current_module", 0)
    call_id = data.get("call_id")
    channel = data.get("channel") or "api"

    start = time.time()
    response = await app.state.llm.generate(
        messages=messages,
        student_id=student_id,
        current_module=current_module,
        memory=app.state.memory,
        call_id=call_id,
        channel=channel,
    )
    elapsed = time.time() - start
    logger.info(f"LLM: {len(response)} chars ({elapsed:.1f}s)")

    return JSONResponse({"response": response})


@app.post("/process-turn")
async def process_turn(request: Request):
    """
    Full turn pipeline: audio → STT → LLM → TTS → audio URL.
    Used by Africa's Talking voice webhook.
    """
    form = await request.form()
    audio_file = form.get("audio")
    student_id = form.get("student_id", "")
    call_id = form.get("call_id", "")
    current_module = int(form.get("current_module", "0"))

    if not audio_file:
        return JSONResponse({"error": "No audio"}, status_code=400)

    total_start = time.time()

    # 1. STT
    temp_path = AUDIO_DIR / f"input_{uuid.uuid4().hex}.wav"
    content = await audio_file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        stt_result = app.state.stt.transcribe(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)

    if stt_result["confidence"] < 0.5:
        # Low confidence — ask to repeat
        response_text = "I didn't quite hear that. Can you say it again?"
    else:
        # 2. LLM
        # Get conversation history for this call
        messages = app.state.memory.get_call_messages(call_id)
        messages.append({"role": "user", "content": stt_result["text"]})

        response_text = await app.state.llm.generate(
            messages=messages,
            student_id=student_id,
            current_module=current_module,
            memory=app.state.memory,
            call_id=call_id,
            channel="process_turn",
        )

        # Save messages
        messages.append({"role": "assistant", "content": response_text})
        app.state.memory.set_call_messages(call_id, messages)

    # 3. TTS — try Chatterbox (emotion-aware) first, fallback to YarnGPT
    audio_id = uuid.uuid4().hex
    output_path = AUDIO_DIR / f"response_{audio_id}.mp3"
    if not await synthesize_chatterbox(response_text, str(output_path)):
        app.state.tts.synthesize(response_text, str(output_path))

    total_elapsed = time.time() - total_start
    logger.info(f"Full turn: {total_elapsed:.1f}s (STT→LLM→TTS)")

    # Return audio URL for Africa's Talking <Play>
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    audio_url = f"{base_url}/audio/response_{audio_id}.mp3"

    return JSONResponse({
        "audio_url": audio_url,
        "transcript": stt_result["text"],
        "response": response_text,
        "confidence": stt_result["confidence"],
        "latency_ms": int(total_elapsed * 1000),
    })


# --- Asterisk Flash Callback ---
# Called by Asterisk dialplan after hanging up on incoming call.
# Triggers outbound callback to child via AMI Originate.

AMI_HOST = os.getenv("AMI_HOST", "asterisk")
AMI_PORT = int(os.getenv("AMI_PORT", "5038"))
AMI_USER = os.getenv("AMI_USER", "sabi")
AMI_SECRET = os.getenv("AMI_SECRET", "sabi_ami_secret_change_me")
SABI_CALLER_ID = os.getenv("SABI_CALLER_ID", "+2342017001459")
FLASH_CALLBACK_DELAY_SECONDS = float(os.getenv("FLASH_CALLBACK_DELAY_SECONDS", "0"))
FLASH_CALLBACK_RETRY_DELAY_SECONDS = float(os.getenv("FLASH_CALLBACK_RETRY_DELAY_SECONDS", "6"))
FLASH_CALLBACK_MAX_ATTEMPTS = int(os.getenv("FLASH_CALLBACK_MAX_ATTEMPTS", "3"))
FLASH_CALLBACK_COOLDOWN_SECONDS = int(os.getenv("FLASH_CALLBACK_COOLDOWN_SECONDS", "20"))
FLASH_CALLBACK_RETRY_ENABLED = os.getenv("FLASH_CALLBACK_RETRY_ENABLED", "0").lower() in {"1", "true", "yes"}
_last_flash_callbacks: dict[str, float] = {}


def normalize_phone(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone or "")


@app.get("/admin/feedback")
async def admin_feedback_index(
    limit: int = 25,
    offset: int = 0,
    phone: str = "",
    call_id: str = "",
    q: str = "",
):
    """
    Protected tester-feedback review index.

    This reads local feedback sidecars written by the AudioSocket path, so
    notes remain reviewable even before the Supabase feedback table exists.
    """
    return JSONResponse(
        list_feedback_records(
            limit=limit,
            offset=offset,
            phone=phone,
            call_id=call_id,
            q=q,
        )
    )


@app.get("/admin/feedback/{call_uuid}")
async def admin_feedback_detail(call_uuid: str, include_raw: bool = False):
    """Return one feedback sidecar. Raw transcript is opt-in."""
    sidecar = feedback_sidecar_path(call_uuid)
    if not sidecar or not sidecar.exists():
        return JSONResponse({"error": "feedback_not_found"}, status_code=404)

    record = load_feedback_record(sidecar, include_raw=include_raw)
    if not record:
        return JSONResponse({"error": "feedback_unreadable"}, status_code=422)
    return JSONResponse(record)


@app.get("/admin/feedback/{call_uuid}/audio")
async def admin_feedback_audio(call_uuid: str):
    """Download the raw feedback WAV for a tester note."""
    audio_path = feedback_audio_path(call_uuid)
    if not audio_path or not audio_path.exists():
        return JSONResponse({"error": "feedback_audio_not_found"}, status_code=404)
    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
        filename=audio_path.name,
    )


@app.get("/admin/calls")
async def admin_call_index(
    limit: int = 25,
    offset: int = 0,
    phone: str = "",
    call_id: str = "",
    flag: str = "",
    q: str = "",
):
    """Protected phone-call QA index for pre-pilot monitoring."""
    return JSONResponse(
        list_call_records(
            limit=limit,
            offset=offset,
            phone=phone,
            call_id=call_id,
            flag=flag,
            q=q,
        )
    )


@app.get("/admin/review", response_class=HTMLResponse)
async def admin_review_console():
    """Protected browser console for learner progress and call QA."""
    return HTMLResponse(render_admin_review_page())


@app.get("/admin/curriculum-map")
async def admin_curriculum_map():
    """Protected structured map of Sabi levels, lessons, and scaffold ladders."""
    return JSONResponse(build_curriculum_review_map())


@app.get("/admin/calls/{call_uuid}")
async def admin_call_detail(call_uuid: str):
    """Return one phone-call QA sidecar."""
    sidecar = call_sidecar_path(call_uuid)
    if not sidecar or not sidecar.exists():
        return JSONResponse({"error": "call_not_found"}, status_code=404)
    record = load_call_record(sidecar)
    if not record:
        return JSONResponse({"error": "call_unreadable"}, status_code=422)
    return JSONResponse(record)


@app.get("/admin/calls/{call_uuid}/audio/{kind}")
async def admin_call_audio(call_uuid: str, kind: str):
    """Download full-call audio. kind=mixed, rx, or tx."""
    audio_path = call_recording_path(call_uuid, kind)
    if not audio_path or not audio_path.exists():
        return JSONResponse({"error": "call_audio_not_found"}, status_code=404)
    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
        filename=audio_path.name,
    )


@app.get("/admin/calls/{call_uuid}/turns/{turn_index}/audio/{role}")
async def admin_call_turn_audio(call_uuid: str, turn_index: int, role: str):
    """Download one per-turn user or assistant WAV clip."""
    audio_path = call_turn_audio_path(call_uuid, turn_index, role)
    if not audio_path or not audio_path.exists():
        return JSONResponse({"error": "turn_audio_not_found"}, status_code=404)
    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
        filename=audio_path.name,
    )


@app.get("/admin/learners")
async def admin_learner_index(
    limit: int = 50,
    offset: int = 0,
    phone: str = "",
    q: str = "",
):
    """Protected roster of children, current level, progression, and calling history."""
    result = await app.state.memory.review_learners(
        limit=limit,
        offset=offset,
        phone=phone,
        q=q,
    )
    return JSONResponse(result)


@app.get("/admin/learners/by-phone")
async def admin_learner_by_phone(phone: str, limit: int = 5):
    """Protected read-only continuity view for all learner profiles on one phone."""
    if not phone.strip():
        return JSONResponse({"error": "phone_required"}, status_code=400)
    result = await app.state.memory.review_phone_continuity(phone, limit=limit)
    return JSONResponse(result)


@app.get("/admin/learners/{student_id}")
async def admin_learner_detail(student_id: str, limit: int = 20):
    """Protected detail view for one child and their recent lesson/call evidence."""
    result = await app.state.memory.review_student(student_id, limit=limit)
    if result.get("status") == "not_found":
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def ami_originate(phone: str, attempt: int = 1, delay_seconds: float | None = None):
    """Send AMI Originate command to Asterisk to call the child back."""
    reader, writer = await asyncio.open_connection(AMI_HOST, AMI_PORT)

    # Read AMI banner
    await reader.readline()

    # Login
    writer.write(
        f"Action: Login\r\n"
        f"Username: {AMI_USER}\r\n"
        f"Secret: {AMI_SECRET}\r\n"
        f"\r\n".encode()
    )
    await writer.drain()

    # Read login response
    while True:
        line = await reader.readline()
        if line.strip() == b"":
            break

    # Wait before calling back so the child's handset/carrier releases the
    # original missed call. Calling back too quickly can land in voicemail or
    # carrier announcements, especially across international test routes.
    if delay_seconds is None:
        delay_seconds = FLASH_CALLBACK_DELAY_SECONDS
    await asyncio.sleep(delay_seconds)

    # Originate outbound call
    writer.write(
        f"Action: Originate\r\n"
        f"Channel: PJSIP/{phone}@africastalking\r\n"
        f"Context: sabi-callback\r\n"
        f"Exten: {phone}\r\n"
        f"Priority: 1\r\n"
        f"CallerID: Sabi <{SABI_CALLER_ID}>\r\n"
        f"Variable: SABI_CALLBACK_ATTEMPT={attempt}\r\n"
        f"Timeout: 30000\r\n"
        f"Async: true\r\n"
        f"\r\n".encode()
    )
    await writer.drain()

    # Read originate response
    while True:
        line = await reader.readline()
        if line.strip() == b"":
            break

    # Logoff
    writer.write(b"Action: Logoff\r\n\r\n")
    await writer.drain()
    writer.close()


@app.post("/asterisk/flash")
async def flash_callback(phone: str = Form(...)):
    """
    Flash callback trigger — called by Asterisk after hanging up on an incoming call.
    Initiates outbound call to the child via AMI Originate.
    Child pays ₦0. We pay ₦3/min SIP outgoing.
    """
    normalized_phone = normalize_phone(phone)
    if not normalized_phone or normalized_phone == "+":
        logger.warning("Flash callback rejected: missing phone number")
        return JSONResponse({"status": "rejected", "reason": "missing_phone"}, status_code=400)

    now = time.monotonic()
    last_requested = _last_flash_callbacks.get(normalized_phone, 0)
    if now - last_requested < FLASH_CALLBACK_COOLDOWN_SECONDS:
        logger.info(
            "Flash callback duplicate suppressed for %s (%.1fs since last request)",
            normalized_phone,
            now - last_requested,
        )
        return JSONResponse({"status": "duplicate_ignored", "phone": normalized_phone})

    _last_flash_callbacks[normalized_phone] = now
    for old_phone, timestamp in list(_last_flash_callbacks.items()):
        if now - timestamp > FLASH_CALLBACK_COOLDOWN_SECONDS * 6:
            _last_flash_callbacks.pop(old_phone, None)

    logger.info(f"Flash callback requested for {normalized_phone}")

    # Fire and forget — don't block Asterisk's curl
    asyncio.create_task(ami_originate(normalized_phone, attempt=1))

    return JSONResponse({"status": "callback_initiated", "phone": normalized_phone, "attempt": 1})


@app.post("/asterisk/flash/retry")
async def retry_flash_callback(
    phone: str = Form(...),
    attempt: int = Form(1),
    reason: str = Form("unknown"),
):
    """
    Retry a callback when the previous outbound leg answered into carrier audio
    or voicemail instead of a real child. This bypasses the public duplicate
    suppression because it is only called from the internal realtime handler.
    """
    normalized_phone = normalize_phone(phone)
    if not normalized_phone or normalized_phone == "+":
        logger.warning("Flash callback retry rejected: missing phone number")
        return JSONResponse({"status": "rejected", "reason": "missing_phone"}, status_code=400)

    if not FLASH_CALLBACK_RETRY_ENABLED:
        logger.info(
            "Flash callback retry disabled for %s after attempt %s reason=%s",
            normalized_phone,
            attempt,
            reason[:160],
        )
        return JSONResponse({
            "status": "retry_disabled",
            "phone": normalized_phone,
            "attempt": attempt,
        })

    next_attempt = attempt + 1
    if next_attempt > FLASH_CALLBACK_MAX_ATTEMPTS:
        logger.warning(
            "Flash callback retry limit reached for %s after attempt %s reason=%s",
            normalized_phone,
            attempt,
            reason[:160],
        )
        return JSONResponse({
            "status": "retry_limit_reached",
            "phone": normalized_phone,
            "attempt": attempt,
            "max_attempts": FLASH_CALLBACK_MAX_ATTEMPTS,
        })

    logger.info(
        "Flash callback retry scheduled for %s attempt=%s/%s reason=%s",
        normalized_phone,
        next_attempt,
        FLASH_CALLBACK_MAX_ATTEMPTS,
        reason[:160],
    )
    _last_flash_callbacks[normalized_phone] = time.monotonic()
    asyncio.create_task(
        ami_originate(
            normalized_phone,
            attempt=next_attempt,
            delay_seconds=FLASH_CALLBACK_RETRY_DELAY_SECONDS,
        )
    )
    return JSONResponse({
        "status": "retry_scheduled",
        "phone": normalized_phone,
        "attempt": next_attempt,
        "delay_seconds": FLASH_CALLBACK_RETRY_DELAY_SECONDS,
    })


@app.post("/admin/asterisk/direct-call")
async def direct_sabi_call(
    phone: str = Form(...),
    attempt: int = Form(1),
    delay_seconds: float = Form(0),
):
    """
    Protected direct test hook for calling a known phone number into the Sabi
    AudioSocket lesson flow without waiting for the AT inbound/flash leg.
    """
    normalized_phone = normalize_phone(phone)
    if not normalized_phone or normalized_phone == "+":
        logger.warning("Direct Sabi call rejected: missing phone number")
        return JSONResponse({"status": "rejected", "reason": "missing_phone"}, status_code=400)

    safe_attempt = max(1, attempt)
    safe_delay = max(0, delay_seconds)
    logger.info(
        "Direct Sabi call requested for %s attempt=%s delay=%.1fs",
        normalized_phone,
        safe_attempt,
        safe_delay,
    )
    asyncio.create_task(
        ami_originate(
            normalized_phone,
            attempt=safe_attempt,
            delay_seconds=safe_delay,
        )
    )
    return JSONResponse({
        "status": "direct_call_initiated",
        "phone": normalized_phone,
        "attempt": safe_attempt,
        "delay_seconds": safe_delay,
    })


@app.post("/asterisk/audiosocket/register")
async def register_audiosocket_call(
    uuid: str = Form(...),
    phone: str = Form("unknown"),
    mode: str = Form("inbound"),
    attempt: str = Form("1"),
):
    """Called by Asterisk immediately before AudioSocket() connects."""
    register_call(uuid, phone, mode, attempt)
    return JSONResponse({"status": "registered", "uuid": uuid, "phone": phone, "mode": mode, "attempt": attempt})


@app.post("/asterisk/hangup")
async def asterisk_hangup(
    uuid: str = Form("unknown"),
    phone: str = Form("unknown"),
    mode: str = Form("unknown"),
    attempt: str = Form(""),
    hangup_cause: str = Form(""),
    dialstatus: str = Form(""),
    duration: str = Form(""),
    billsec: str = Form(""),
    channel: str = Form(""),
    recording: str = Form(""),
    uniqueid: str = Form(""),
):
    """Called from Asterisk's h extension after a call leg hangs up."""
    record_hangup_event(
        uuid,
        phone=phone,
        mode=mode,
        attempt=attempt,
        hangup_cause=hangup_cause,
        dialstatus=dialstatus,
        duration=duration,
        billsec=billsec,
        channel=channel,
        recording=recording,
        uniqueid=uniqueid,
    )
    return JSONResponse({"status": "recorded", "uuid": uuid})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
