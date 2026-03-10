"""
Africa's Talking voice webhook handlers.
Handles incoming calls, processes speech, and plays AI responses.
"""

import os
import uuid
import random
import logging
import xml.etree.ElementTree as ET

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
        # Call ended
        logger.info(f"Call ended: {session_id}")
        # Cleanup call state
        if hasattr(request.app.state, "memory"):
            request.app.state.memory.clear_call(session_id)
        return xml_response("<Response><Reject/></Response>")

    # Find or create student
    memory = request.app.state.memory
    student = await memory.find_or_create_student(caller_number)

    # Generate greeting via LLM
    llm = request.app.state.llm
    greeting = await llm.generate(
        messages=[],
        student_id=student["id"],
        current_module=student.get("current_module", 0),
        memory=memory,
    )

    # Save greeting to conversation history
    memory.set_call_messages(session_id, [
        {"role": "assistant", "content": greeting}
    ])

    # Generate greeting audio
    tts = request.app.state.tts
    audio_id = uuid.uuid4().hex
    audio_path = f"audio_cache/greeting_{audio_id}.mp3"
    tts.synthesize(greeting, audio_path)

    # Build Africa's Talking response XML
    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/greeting_{audio_id}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callbackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student['id']}&module={student.get('current_module', 0)}"
            playBeep="false"/>
</Response>"""

    return xml_response(response_xml)


@router.post("/recording")
async def handle_recording(request: Request):
    """
    Handle recorded speech from Africa's Talking.
    Process: download audio → STT → LLM → TTS → play response.
    """
    form = await request.form()
    recording_url = form.get("recordingUrl", "")
    session_id = request.query_params.get("session", "")
    student_id = request.query_params.get("student", "")
    current_module = int(request.query_params.get("module", "0"))

    logger.info(f"Recording received for session {session_id}")

    if not recording_url:
        # No speech detected — play thinking cue and re-record
        cue_idx = random.randint(0, THINKING_CUE_COUNT - 1)
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/thinking_{cue_idx}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callbackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student_id}&module={current_module}"
            playBeep="false"/>
</Response>""")

    # 1. Play thinking cue immediately while processing
    cue_idx = random.randint(0, THINKING_CUE_COUNT - 1)

    # 2. Download recording from Africa's Talking
    import httpx
    async with httpx.AsyncClient() as client:
        audio_response = await client.get(recording_url)
        temp_path = f"audio_cache/input_{uuid.uuid4().hex}.mp3"
        with open(temp_path, "wb") as f:
            f.write(audio_response.content)

    # 3. STT
    stt = request.app.state.stt
    try:
        result = stt.transcribe(temp_path)
    finally:
        import os as _os
        _os.unlink(temp_path)

    logger.info(f"STT: '{result['text']}' (confidence={result['confidence']:.2f})")

    # 4. Handle low confidence
    if result["confidence"] < 0.5 or not result["text"].strip():
        repeat_audio_id = uuid.uuid4().hex
        request.app.state.tts.synthesize(
            "I didn't quite hear that. Can you say it again?",
            f"audio_cache/repeat_{repeat_audio_id}.mp3"
        )
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/repeat_{repeat_audio_id}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callbackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student_id}&module={current_module}"
            playBeep="false"/>
</Response>""")

    # 5. Get conversation history & add user message
    memory = request.app.state.memory
    messages = memory.get_call_messages(session_id)
    messages.append({"role": "user", "content": result["text"]})

    # 6. Check if we should wrap up (after ~10 exchanges)
    user_turns = sum(1 for m in messages if m["role"] == "user")
    if user_turns >= 10:
        messages.append({
            "role": "system",
            "content": "The call has been going for a while. Please wrap up the lesson with a summary and encouragement."
        })

    # 7. LLM response
    llm = request.app.state.llm
    response_text = await llm.generate(
        messages=messages,
        student_id=student_id,
        current_module=current_module,
        memory=memory,
    )

    # Save to conversation history
    messages.append({"role": "assistant", "content": response_text})
    memory.set_call_messages(session_id, messages)

    # 8. TTS
    response_audio_id = uuid.uuid4().hex
    request.app.state.tts.synthesize(
        response_text,
        f"audio_cache/response_{response_audio_id}.mp3"
    )

    # 9. Check for wrap-up signals
    wrap_up_phrases = ["call me back", "bye", "well done today", "great job today", "see you next time"]
    is_wrapping_up = any(phrase in response_text.lower() for phrase in wrap_up_phrases)

    if is_wrapping_up or user_turns >= 12:
        # End the call
        logger.info(f"Wrapping up call {session_id} after {user_turns} turns")
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/response_{response_audio_id}.mp3"/>
</Response>""")

    # Continue conversation
    return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play url="{SERVER_URL}/audio/response_{response_audio_id}.mp3"/>
    <Record finishOnKey="#" maxLength="10" trimSilence="true"
            callbackUrl="{SERVER_URL}/voice/recording?session={session_id}&student={student_id}&module={current_module}"
            playBeep="false"/>
</Response>""")


@router.post("/events")
async def call_events(request: Request):
    """Handle Africa's Talking call events (status updates)."""
    form = await request.form()
    logger.info(f"Call event: {dict(form)}")
    return Response(status_code=200)
