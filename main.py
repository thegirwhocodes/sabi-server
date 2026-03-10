"""
Sabi Voice AI Server
Self-hosted voice tutoring server for Education for Equality.

Components:
- STT: faster-whisper (Whisper large-v3)
- LLM: Claude Haiku (primary) / Ollama Llama 3.1 8B (fallback) + RAG
- TTS: YarnGPT API (Nigerian voices)
- Telephony: Africa's Talking voice webhooks

Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os
import uuid
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from stt import SpeechToText
from tts import TextToSpeech
from llm import SabiLLM
from memory import StudentMemory
from voice import router as voice_router

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

    logger.info("All models loaded. Sabi is ready.")
    yield

    # Cleanup
    logger.info("Shutting down Sabi server...")


app = FastAPI(
    title="Sabi Voice AI Server",
    description="Self-hosted AI voice tutor for Nigerian children",
    version="0.1.0",
    lifespan=lifespan,
)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
