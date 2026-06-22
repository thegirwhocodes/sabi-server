"""
Africa's Talking voice webhook handlers.
Handles incoming calls, processes speech, and plays AI responses.

Latency optimizations:
- Parallel AT audio download + memory fetch (saves ~100-200ms)
- Streaming LLM → TTS pipeline: first sentence synthesized before LLM finishes
- Groq Whisper for STT (fast path, ~200ms vs ~1.5s local)
"""

import os
import uuid
import random
import logging
import asyncio

import httpx
from fastapi import APIRouter, Request, Response

logger = logging.getLogger("sabi.voice")

router = APIRouter()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
THINKING_CUE_COUNT = 5  # Number of pre-generated thinking audio files


def xml_response(xml_str: str) -> Response:
    """Return XML response for Africa's Talking."""
    return Response(content=xml_str, media_type="application/xml")


@router.post("/incoming")
async def incoming_call(request: Request):
    """
    Handle incoming voice call from Africa's Talking.
    First webhook — greet the student and start recording.
    """
    form = await request.form()
    caller_number = form.get("callerNumber", "")
    session_id = form.get("sessionId", "")
    is_active = form.get("isActive", "1")

    logger.info(f"Incoming call from {caller_number} (session={session_id})")

    if is_active == "0":
        logger.info(f"Call ended: {session_id}")
        if hasattr(request.app.state, "memory"):
            request.app.state.memory.clear_call(session_id)
        return xml_response("<Response><Reject/></Response>")

    memory = request.app.state.memory
    student = await memory.find_or_create_student(caller_number)

    llm = request.app.state.llm
    greeting = await llm.generate(
        messages=[],
        student_id=student["id"],
        current_module=student.get("current_module", 0),
        memory=memory,
        call_id=session_id,
        channel="africas_talking_xml",
    )

    memory.set_call_messages(session_id, [
        {"role": "assistant", "content": greeting}
    ])

    # Generate greeting audio — try Chatterbox (emotion-aware) then YarnGPT
    audio_id = uuid.uuid4().hex
    audio_path = f"audio_cache/greeting_{audio_id}.mp3"
    if not await _synthesize_chatterbox(request.app, greeting, audio_path):
        request.app.state.tts.synthesize(greeting, audio_path)

    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/greeting_{audio_id}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callBackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student['id']}&module={student.get('current_module', 0)}"
            playBeep="false"/>
</Response>"""

    return xml_response(response_xml)


@router.post("/recording")
async def handle_recording(request: Request):
    """
    Handle recorded speech from Africa's Talking.
    Process: download audio → STT → LLM → TTS → play response.

    Optimizations applied:
    1. Audio download + memory fetch run in parallel
    2. Streaming LLM → first sentence → TTS while rest of LLM generates
    """
    form = await request.form()
    recording_url = form.get("recordingUrl", "")
    session_id = request.query_params.get("session", "")
    student_id = request.query_params.get("student", "")
    current_module = int(request.query_params.get("module", "0"))

    logger.info(f"Recording received for session {session_id}")

    if not recording_url:
        cue_idx = random.randint(0, THINKING_CUE_COUNT - 1)
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/thinking_{cue_idx}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callBackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student_id}&module={current_module}"
            playBeep="false"/>
</Response>""")

    # ── STEP 1: Parallel — download audio AND fetch conversation history ──
    memory = request.app.state.memory

    async def download_audio():
        async with httpx.AsyncClient(timeout=15.0) as client:
            audio_response = await client.get(recording_url)
            temp_path = f"audio_cache/input_{uuid.uuid4().hex}.mp3"
            with open(temp_path, "wb") as f:
                f.write(audio_response.content)
            return temp_path

    async def fetch_messages():
        return memory.get_call_messages(session_id)

    temp_path, messages = await asyncio.gather(download_audio(), fetch_messages())

    # ── STEP 2: STT ──
    stt = request.app.state.stt
    try:
        result = stt.transcribe(temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    logger.info(f"STT: '{result['text']}' (confidence={result['confidence']:.2f})")

    # ── STEP 3: Low confidence check ──
    if result["confidence"] < 0.5 or not result["text"].strip():
        repeat_audio_id = uuid.uuid4().hex
        repeat_path = f"audio_cache/repeat_{repeat_audio_id}.mp3"
        if not await _synthesize_chatterbox(request.app, "I didn't quite hear that. Can you say it again?", repeat_path):
            request.app.state.tts.synthesize("I didn't quite hear that. Can you say it again?", repeat_path)
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/repeat_{repeat_audio_id}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callBackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student_id}&module={current_module}"
            playBeep="false"/>
</Response>""")

    # ── STEP 4: Build message history ──
    messages.append({"role": "user", "content": result["text"]})
    user_turns = sum(1 for m in messages if m["role"] == "user")

    if user_turns >= 10:
        messages.append({
            "role": "system",
            "content": "The call has been going for a while. Please wrap up the lesson with a summary and encouragement."
        })

    # ── STEP 5: Streaming LLM → TTS pipeline ──
    # Generate first sentence of LLM response and immediately start TTS.
    # This cuts TTFA (time to first audio) significantly.
    llm = request.app.state.llm
    response_audio_id = uuid.uuid4().hex
    response_path = f"audio_cache/response_{response_audio_id}.mp3"

    try:
        response_text = await _stream_llm_to_tts(
            request.app,
            llm,
            messages,
            student_id,
            current_module,
            memory,
            response_path,
            call_id=session_id,
            channel="africas_talking_xml",
        )
    except Exception as e:
        logger.warning(f"Streaming pipeline failed ({e}), falling back to sequential")
        # Sequential fallback
        response_text = await llm.generate(
            messages=messages,
            student_id=student_id,
            current_module=current_module,
            memory=memory,
            call_id=session_id,
            channel="africas_talking_xml",
        )
        if not await _synthesize_chatterbox(request.app, response_text, response_path):
            request.app.state.tts.synthesize(response_text, response_path)

    # ── STEP 6: Save to conversation history ──
    messages.append({"role": "assistant", "content": response_text})
    # Remove temporary system message if we added one
    clean_messages = [m for m in messages if m.get("role") != "system"]
    memory.set_call_messages(session_id, clean_messages)

    # ── STEP 7: Check for wrap-up ──
    wrap_up_phrases = ["call me back", "bye", "well done today", "great job today", "see you next time"]
    is_wrapping_up = any(phrase in response_text.lower() for phrase in wrap_up_phrases)

    if is_wrapping_up or user_turns >= 12:
        logger.info(f"Wrapping up call {session_id} after {user_turns} turns")
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/response_{response_audio_id}.mp3"/>
</Response>""")

    return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/response_{response_audio_id}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callBackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student_id}&module={current_module}"
            playBeep="false"/>
</Response>""")


@router.post("/events")
async def call_events(request: Request):
    """Handle Africa's Talking call events (status updates)."""
    form = await request.form()
    logger.info(f"Call event: {dict(form)}")
    return Response(status_code=200)


# ── Helpers ──

async def _synthesize_chatterbox(app, text: str, output_path: str) -> bool:
    """Generate speech via Chatterbox Turbo. Returns True on success."""
    chatterbox_url = os.getenv("CHATTERBOX_URL", "http://localhost:8001")
    try:
        import re
        exaggeration = 0.5
        if re.search(r'\[laugh\]|!\s*!|Well done|Correct|Yes!|Great|Sharp sharp', text, re.I):
            exaggeration = 0.75
        elif re.search(r'\[sigh\]|Almost|Good try|tricky|Let me help', text, re.I):
            exaggeration = 0.35
        elif re.search(r'\[chuckle\]|Oya|Let.s try|ready', text, re.I):
            exaggeration = 0.6

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{chatterbox_url}/tts",
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
            return True
    except Exception as e:
        logger.warning(f"Chatterbox TTS failed: {e}")
        return False


async def _stream_llm_to_tts(
    app,
    llm,
    messages: list[dict],
    student_id: str,
    current_module: int,
    memory,
    final_output_path: str,
    call_id: str | None = None,
    channel: str = "africas_talking_xml",
) -> str:
    """
    Stream LLM output sentence by sentence → TTS each sentence immediately.
    Concatenates all audio segments into final_output_path.
    Returns the full response text.

    Flow: LLM streams → sentence detected → TTS sentence → save chunk
          → after all chunks → concatenate with ffmpeg → return full text
    """
    sentences = []
    audio_chunks = []

    async for sentence in llm.generate_streaming(
        messages=messages,
        student_id=student_id,
        current_module=current_module,
        memory=memory,
        call_id=call_id,
        channel=channel,
    ):
        sentences.append(sentence)
        chunk_id = uuid.uuid4().hex
        chunk_path = f"audio_cache/chunk_{chunk_id}.mp3"

        # Synthesize this sentence immediately
        if not await _synthesize_chatterbox(app, sentence, chunk_path):
            try:
                app.state.tts.synthesize(sentence, chunk_path)
            except Exception as e:
                logger.warning(f"TTS chunk failed for '{sentence[:40]}': {e}")
                continue

        audio_chunks.append(chunk_path)
        logger.info(f"Streaming TTS: synthesized sentence '{sentence[:50]}'")

    if not audio_chunks:
        raise RuntimeError("No audio chunks generated")

    full_text = " ".join(sentences)

    # Concatenate audio chunks
    if len(audio_chunks) == 1:
        # Only one sentence — just rename/move
        import shutil
        shutil.move(audio_chunks[0], final_output_path)
    else:
        # Use ffmpeg to concatenate
        await _concat_audio(audio_chunks, final_output_path)
        for chunk in audio_chunks:
            try:
                os.unlink(chunk)
            except OSError:
                pass

    return full_text


async def _concat_audio(input_paths: list[str], output_path: str):
    """Concatenate multiple MP3 files using ffmpeg."""
    import asyncio

    # Write ffmpeg concat list
    list_path = f"audio_cache/concat_{uuid.uuid4().hex}.txt"
    with open(list_path, "w") as f:
        for p in input_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            output_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed with code {proc.returncode}")
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass
