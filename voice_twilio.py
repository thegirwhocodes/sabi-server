"""
Twilio voice webhook handlers for Sabi.
Same AI pipeline as Africa's Talking (Whisper → Claude → ElevenLabs/Chatterbox),
just wrapped in TwiML instead of AT XML.
"""

import os
import uuid
import random
import logging
import httpx

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("sabi.voice.twilio")

router = APIRouter()

SERVER_URL = os.getenv("SERVER_URL", "https://api.eduforequality.org")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
THINKING_CUE_COUNT = 5

# Chatterbox TTS server (fallback)
CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "http://localhost:8001")

# ElevenLabs — same model/voice_settings as curriculum-app/lib/voice/tts-client.ts (website demo parity)
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "oC2pCZZWEDRe6lmZpaaw")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "").strip() or "eleven_flash_v2_5"


def twiml_response(twiml: str) -> Response:
    """Return TwiML response."""
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>{twiml}</Response>',
        media_type="application/xml",
    )


def detect_exaggeration(text: str) -> float:
    """Detect emotion from LLM response for Chatterbox exaggeration."""
    import re
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{CHATTERBOX_URL}/tts",
                json={"text": text[:2000], "format": "mp3", "exaggeration": exaggeration},
            )
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"Chatterbox TTS: {len(text)} chars, exag={exaggeration}")
            return True
    except Exception as e:
        logger.warning(f"Chatterbox TTS failed: {e}")
        return False


async def synthesize_elevenlabs(text: str, output_path: str) -> bool:
    """Generate speech via ElevenLabs with Bukola voice (or ELEVENLABS_VOICE_ID)."""
    if not ELEVENLABS_API_KEY:
        return False
    try:
        spoken_text = text.replace("₦", "naira ")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={
                    "Content-Type": "application/json",
                    "xi-api-key": ELEVENLABS_API_KEY,
                },
                json={
                    "text": spoken_text,
                    "model_id": ELEVENLABS_MODEL_ID,
                    "voice_settings": {
                        "stability": 0.28,
                        "similarity_boost": 0.7,
                        "speed": 1.0,
                        "use_speaker_boost": True,
                    },
                },
            )
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"ElevenLabs TTS ({ELEVENLABS_VOICE_ID[:8]}…): {len(text)} chars")
            return True
    except Exception as e:
        logger.warning(f"ElevenLabs TTS failed: {e}")
        return False


async def synthesize_tts(text: str, output_path: str, request) -> None:
    """Try ElevenLabs → Chatterbox → YarnGPT fallback chain."""
    if await synthesize_elevenlabs(text, output_path):
        return
    if await synthesize_chatterbox(text, output_path):
        return
    request.app.state.tts.synthesize(text, output_path)


@router.post("/incoming")
async def twilio_incoming(request: Request):
    """
    Handle incoming Twilio voice call.
    Greets the student, then records their speech.
    """
    form = await request.form()
    caller = form.get("From", "")
    call_sid = form.get("CallSid", "")

    logger.info(f"Twilio incoming call from {caller} (CallSid={call_sid})")

    # Find or create student by phone number
    memory = request.app.state.memory
    student = await memory.find_or_create_student(caller)

    # Generate greeting via LLM
    llm = request.app.state.llm
    greeting = await llm.generate(
        messages=[],
        student_id=student["id"],
        current_module=student.get("current_module", 0),
        memory=memory,
    )

    # Save greeting to call history
    memory.set_call_messages(call_sid, [
        {"role": "assistant", "content": greeting}
    ])

    # Generate greeting audio (ElevenLabs Bukola → Chatterbox → YarnGPT)
    audio_id = uuid.uuid4().hex
    audio_path = f"audio_cache/greeting_{audio_id}.mp3"
    await synthesize_tts(greeting, audio_path, request)

    logger.info(f"Greeting generated for {caller}: {greeting[:80]}...")

    # TwiML: play greeting, then record student's speech
    return twiml_response(f"""
    <Play>{SERVER_URL}/audio/greeting_{audio_id}.mp3</Play>
    <Record
        action="{SERVER_URL}/voice/twilio/recording?call_sid={call_sid}&amp;student_id={student['id']}&amp;module={student.get('current_module', 0)}"
        maxLength="15"
        playBeep="false"
        trim="trim-silence"
        timeout="3"
    />
    <Say voice="alice">I didn't hear anything. Goodbye!</Say>
    """)


@router.post("/recording")
async def twilio_recording(request: Request):
    """
    Handle Twilio recording callback.
    Download audio → Whisper STT → Claude LLM → Chatterbox TTS → play back.
    """
    form = await request.form()
    recording_url = form.get("RecordingUrl", "")
    recording_sid = form.get("RecordingSid", "")
    call_sid = request.query_params.get("call_sid", "")
    student_id = request.query_params.get("student_id", "")
    current_module = int(request.query_params.get("module", "0"))

    logger.info(f"Twilio recording received: {recording_sid} for call {call_sid}")

    if not recording_url:
        # No recording — ask again
        return twiml_response(f"""
        <Say voice="alice">I didn't hear that. Can you try again?</Say>
        <Record
            action="{SERVER_URL}/voice/twilio/recording?call_sid={call_sid}&amp;student_id={student_id}&amp;module={current_module}"
            maxLength="15"
            playBeep="false"
            trim="trim-silence"
            timeout="3"
        />
        """)

    # 1. Download recording from Twilio (needs auth)
    download_url = f"{recording_url}.mp3"
    temp_path = f"audio_cache/input_{uuid.uuid4().hex}.mp3"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                download_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                follow_redirects=True,
            )
            resp.raise_for_status()
            with open(temp_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"Downloaded recording: {len(resp.content)} bytes")
    except Exception as e:
        logger.error(f"Failed to download recording: {e}")
        return twiml_response(f"""
        <Say voice="alice">Sorry, I had trouble hearing you. Can you say that again?</Say>
        <Record
            action="{SERVER_URL}/voice/twilio/recording?call_sid={call_sid}&amp;student_id={student_id}&amp;module={current_module}"
            maxLength="15"
            playBeep="false"
            trim="trim-silence"
            timeout="3"
        />
        """)

    # 2. STT via Whisper
    stt = request.app.state.stt
    try:
        result = stt.transcribe(temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    logger.info(f"STT: '{result['text']}' (confidence={result['confidence']:.2f})")

    # 3. Low confidence — ask to repeat
    if result["confidence"] < 0.4 or not result["text"].strip():
        repeat_id = uuid.uuid4().hex
        repeat_text = "I didn't quite catch that. Can you say it again?"
        repeat_path = f"audio_cache/repeat_{repeat_id}.mp3"
        await synthesize_tts(repeat_text, repeat_path, request)

        return twiml_response(f"""
        <Play>{SERVER_URL}/audio/repeat_{repeat_id}.mp3</Play>
        <Record
            action="{SERVER_URL}/voice/twilio/recording?call_sid={call_sid}&amp;student_id={student_id}&amp;module={current_module}"
            maxLength="15"
            playBeep="false"
            trim="trim-silence"
            timeout="3"
        />
        """)

    # 4. Get conversation history & add user message
    memory = request.app.state.memory
    messages = memory.get_call_messages(call_sid)
    messages.append({"role": "user", "content": result["text"]})

    # 5. Check if wrapping up (after ~10 exchanges)
    user_turns = sum(1 for m in messages if m["role"] == "user")
    if user_turns >= 10:
        messages.append({
            "role": "system",
            "content": "The call has been going for a while. Please wrap up the lesson with a summary and encouragement.",
        })

    # 6. LLM response
    llm = request.app.state.llm
    response_text = await llm.generate(
        messages=messages,
        student_id=student_id,
        current_module=current_module,
        memory=memory,
    )

    # Save to history
    messages.append({"role": "assistant", "content": response_text})
    memory.set_call_messages(call_sid, messages)

    logger.info(f"LLM response ({user_turns} turns): {response_text[:80]}...")

    # 7. TTS (ElevenLabs Bukola → Chatterbox → YarnGPT)
    response_id = uuid.uuid4().hex
    response_path = f"audio_cache/response_{response_id}.mp3"
    await synthesize_tts(response_text, response_path, request)

    # 8. Check for wrap-up
    wrap_phrases = ["call me back", "bye", "well done today", "great job today", "see you next time"]
    is_wrapping = any(p in response_text.lower() for p in wrap_phrases)

    if is_wrapping or user_turns >= 12:
        logger.info(f"Wrapping up call {call_sid} after {user_turns} turns")
        return twiml_response(f"""
        <Play>{SERVER_URL}/audio/response_{response_id}.mp3</Play>
        <Say voice="alice">Goodbye!</Say>
        <Hangup/>
        """)

    # 9. Continue — play response then record next turn
    return twiml_response(f"""
    <Play>{SERVER_URL}/audio/response_{response_id}.mp3</Play>
    <Record
        action="{SERVER_URL}/voice/twilio/recording?call_sid={call_sid}&amp;student_id={student_id}&amp;module={current_module}"
        maxLength="15"
        playBeep="false"
        trim="trim-silence"
        timeout="3"
    />
    <Say voice="alice">I didn't hear anything. Goodbye!</Say>
    """)


@router.post("/status")
async def twilio_status(request: Request):
    """Handle Twilio call status callbacks."""
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    logger.info(f"Twilio call status: {call_sid} → {status}")

    if status in ("completed", "failed", "busy", "no-answer", "canceled"):
        memory = request.app.state.memory
        memory.clear_call(call_sid)

    return Response(status_code=200)
