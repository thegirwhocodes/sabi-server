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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from stt import SpeechToText
from tts import TextToSpeech
from llm import SabiLLM
from memory import StudentMemory
from voice import router as voice_router
from voice_asterisk import start_agi_server
from secret_loader import get_secret

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sabi")

# Audio file storage
AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

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

    # Start FastAGI server for Asterisk call handling
    agi_server = await start_agi_server(
        stt=app.state.stt,
        llm=app.state.llm,
        tts=app.state.tts,
        memory=app.state.memory,
    )

    logger.info("All models loaded. Sabi is ready.")
    yield

    # Cleanup
    logger.info("Shutting down Sabi server...")
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
OPEN_PATHS = {"/health", "/docs", "/openapi.json"}
OPEN_PREFIXES = ("/voice/", "/audio/", "/asterisk/")


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
            return await call_next(request)
        if not SABI_API_KEY:
            return await call_next(request)
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if key != SABI_API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)

# Mount audio files directory
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# Voice webhook routes (Africa's Talking)
app.include_router(voice_router, prefix="/voice")


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
    """Generate speech audio from text using YarnGPT."""
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    audio_id = uuid.uuid4().hex
    output_path = AUDIO_DIR / f"tts_{audio_id}.mp3"

    start = time.time()
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

    start = time.time()
    response = await app.state.llm.generate(
        messages=messages,
        student_id=student_id,
        current_module=current_module,
        memory=app.state.memory,
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
        )

        # Save messages
        messages.append({"role": "assistant", "content": response_text})
        app.state.memory.set_call_messages(call_id, messages)

    # 3. TTS
    audio_id = uuid.uuid4().hex
    output_path = AUDIO_DIR / f"response_{audio_id}.mp3"
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


async def ami_originate(phone: str):
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

    # Wait before calling back (so child's phone stops ringing)
    await asyncio.sleep(2)

    # Originate outbound call
    writer.write(
        f"Action: Originate\r\n"
        f"Channel: PJSIP/{phone}@africastalking\r\n"
        f"Context: sabi-callback\r\n"
        f"Exten: {phone}\r\n"
        f"Priority: 1\r\n"
        f"CallerID: Sabi <{phone}>\r\n"
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
    logger.info(f"Flash callback requested for {phone}")

    # Fire and forget — don't block Asterisk's curl
    asyncio.create_task(ami_originate(phone))

    return JSONResponse({"status": "callback_initiated", "phone": phone})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
