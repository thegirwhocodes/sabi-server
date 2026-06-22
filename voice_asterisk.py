"""
FastAGI handler for Sabi voice lessons over Asterisk.

Handles the conversation loop when Asterisk connects a callback call:
  1. Play greeting
  2. Record child's response (silence detection or # key)
  3. Process: STT → LLM → TTS
  4. Play AI response
  5. Loop until wrap-up

Audio format: Asterisk expects 8kHz mono WAV (ulaw/alaw codec).
TTS outputs MP3 → ffmpeg converts to Asterisk-compatible WAV.
"""

import asyncio
import logging
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from diagnostic_flow import build_opening_turn
from learning_state import analyze_session
from normalize_money_for_speech import normalize_money_for_speech
from secret_loader import get_secret

logger = logging.getLogger("sabi.asterisk")

SHARED_AUDIO_DIR = Path("/shared/audio")
SHARED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "http://sabi-chatterbox:8001")
ELEVENLABS_API_KEY = get_secret("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = get_secret("ELEVENLABS_VOICE_ID", "oC2pCZZWEDRe6lmZpaaw")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "").strip() or "eleven_flash_v2_5"
TTS_PRIMARY = os.getenv("SABI_TTS_PRIMARY", "elevenlabs").strip().lower()

MAX_TURNS = int(os.getenv("SABI_MAX_TURNS", "40"))
WRAP_UP_AFTER_TURNS = int(os.getenv("SABI_WRAP_UP_AFTER_TURNS", "34"))
MIN_WRAP_USER_TURNS = int(os.getenv("SABI_MIN_WRAP_USER_TURNS", "10"))
RECORD_MAX_MS = 10000  # 10 seconds max recording
RECORD_SILENCE_S = 2   # Stop recording after 2s silence
# SIP/PSTN audio is narrowband and short child answers often score around 0.35
# even when Whisper gets the words right. Keep this lower than web/Twilio.
CONFIDENCE_THRESHOLD = 0.3

WRAP_UP_PHRASES = [
    "call me back", "bye", "well done today",
    "great job today", "see you next time",
    "talk to you", "until next time",
]

CALLER_END_PHRASES = [
    "bye", "goodbye", "i want to stop", "stop the call",
    "end the call", "hang up", "i am done", "i'm done",
]


def mp3_to_asterisk_wav(mp3_path: str, wav_path: str) -> str:
    """Convert MP3 to 8kHz mono WAV (slin) for Asterisk playback."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", mp3_path,
            "-ar", "8000", "-ac", "1", "-sample_fmt", "s16",
            wav_path,
        ],
        capture_output=True,
        check=True,
    )
    return wav_path


def detect_exaggeration(text: str) -> float:
    """Detect emotion from LLM response for Chatterbox exaggeration."""
    if re.search(r'\[laugh\]|!\s*!|Well done|Correct|Yes!|Great|Excellent|Sharp sharp', text, re.I):
        return 0.75
    if re.search(r'\[sigh\]|Almost|Good try|tricky|Let me help', text, re.I):
        return 0.35
    if re.search(r'\[chuckle\]|Oya|Let.s try|ready', text, re.I):
        return 0.6
    return 0.5


def clean_text_for_tts(text: str) -> str:
    """Remove stage directions that voice providers may read out loud."""
    text = normalize_money_for_speech(text).strip()
    text = re.sub(
        r"\s*[\[(]\s*(laughs?|chuckles?|sighs?|giggles?|pauses?|breathes?|clears throat)\s*[\])]\s*",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s*\b(laughs?|chuckles?|sighs?|giggles?)\b[,.!?;:]*", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([.!?])\s+([.!?])", r"\1", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()


async def synthesize_chatterbox(text: str, output_path: str) -> bool:
    """Generate speech via Chatterbox Turbo. Returns True on success."""
    try:
        exaggeration = detect_exaggeration(text)
        async with httpx.AsyncClient(timeout=25.0) as client:
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


async def synthesize_elevenlabs(text: str, output_path: str) -> bool:
    """Generate speech via ElevenLabs. Returns True on success."""
    if not ELEVENLABS_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={
                    "Content-Type": "application/json",
                    "xi-api-key": ELEVENLABS_API_KEY,
                },
                json={
                    "text": text[:2000],
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
            logger.info(f"ElevenLabs TTS ({ELEVENLABS_VOICE_ID[:8]}...): {len(text)} chars")
            return True
    except Exception as e:
        logger.warning(f"ElevenLabs TTS failed: {e}")
        return False


async def synthesize_yarngpt(tts, text: str, output_path: str) -> bool:
    """Generate speech via YarnGPT. Returns True on success."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, tts.synthesize, text, output_path)
        voice = getattr(tts, "voice", "unknown")
        logger.info("YarnGPT TTS (%s): %d chars", voice, len(text))
        return True
    except Exception as e:
        logger.warning(f"YarnGPT TTS failed: {e}")
        return False


async def tts_and_convert(tts, text: str, label: str = "resp") -> str:
    """Generate TTS audio and convert to Asterisk WAV format.

    Returns path WITHOUT extension (Asterisk adds .wav/.ulaw automatically).
    """
    audio_id = uuid.uuid4().hex
    mp3_path = str(SHARED_AUDIO_DIR / f"{label}_{audio_id}.mp3")
    wav_path = str(SHARED_AUDIO_DIR / f"{label}_{audio_id}.wav")
    clean_text = clean_text_for_tts(text)

    if TTS_PRIMARY == "yarngpt":
        ok = (
            await synthesize_yarngpt(tts, clean_text, mp3_path)
            or await synthesize_elevenlabs(clean_text, mp3_path)
            or await synthesize_chatterbox(clean_text, mp3_path)
        )
    elif TTS_PRIMARY == "chatterbox":
        ok = (
            await synthesize_chatterbox(clean_text, mp3_path)
            or await synthesize_elevenlabs(clean_text, mp3_path)
            or await synthesize_yarngpt(tts, clean_text, mp3_path)
        )
    else:
        ok = (
            await synthesize_elevenlabs(clean_text, mp3_path)
            or await synthesize_chatterbox(clean_text, mp3_path)
            or await synthesize_yarngpt(tts, clean_text, mp3_path)
        )

    if not ok:
        raise RuntimeError("All TTS providers failed")

    # Convert MP3 → 8kHz WAV
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, mp3_to_asterisk_wav, mp3_path, wav_path)

    # Clean up MP3
    try:
        os.unlink(mp3_path)
    except OSError:
        pass

    # Return path without extension (Asterisk convention)
    return wav_path.rsplit(".", 1)[0]


def should_wrap_up(messages: list[dict], response: str) -> bool:
    """Check if the lesson should end."""
    user_turns = sum(1 for m in messages if m["role"] == "user")
    if user_turns >= MAX_TURNS:
        return True
    latest_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    latest_user_lower = latest_user.lower()
    if any(phrase in latest_user_lower for phrase in CALLER_END_PHRASES):
        return True
    # In the original hackathon-style flow, Sabi did not cut the child off just
    # because she used a closing-sounding encouragement. Keep the line open
    # until the planned wrap-up band unless the caller explicitly ends.
    if user_turns < WRAP_UP_AFTER_TURNS:
        return False
    return any(phrase in response.lower() for phrase in WRAP_UP_PHRASES)


async def handle_agi_call(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                          stt, llm, tts, memory):
    """
    Handle a single Sabi lesson call via AGI protocol.

    Called when Asterisk connects an outbound callback to our FastAGI server.
    The child has already answered the phone.
    """
    call_id = uuid.uuid4().hex
    peer_info = writer.get_extra_info("peername")
    logger.info(f"AGI connection from {peer_info} (call_id={call_id})")

    # --- Parse AGI environment variables ---
    env = {}
    while True:
        line = await reader.readline()
        if not line:
            writer.close()
            return
        decoded = line.decode("utf-8").strip()
        if decoded == "":
            break  # Empty line = end of env vars
        if ": " in decoded:
            key, value = decoded.split(": ", 1)
            env[key] = value

    phone = env.get("agi_callerid", "unknown")
    logger.info(f"AGI call from {phone}")

    async def agi_command(cmd: str) -> str:
        """Send AGI command and get response."""
        writer.write(f"{cmd}\n".encode("utf-8"))
        await writer.drain()
        response = await reader.readline()
        decoded = response.decode("utf-8").strip()
        logger.debug(f"AGI: {cmd} → {decoded}")
        return decoded

    try:
        # 1. Find or create student
        student = await memory.find_or_create_student(phone)
        student_id = student["id"]
        effective_state = await memory.get_effective_learning_state(student)
        module = int(effective_state.get("current_module") or student.get("current_module") or 0)
        logger.info(
            "Student: %s, module=%s, skill=%s, scaffold=%s, new=%s",
            student_id,
            module,
            effective_state.get("active_skill"),
            effective_state.get("scaffold_depth"),
            student.get("is_new"),
        )

        # 2. Deterministic opening. This prevents returning callers from
        # being asked their name again before memory is loaded.
        greeting = build_opening_turn(student, effective_state)
        logger.info(f"Greeting: {greeting[:80]}...")

        # 3. TTS greeting → Asterisk WAV
        greeting_path = await tts_and_convert(tts, greeting, "greeting")

        # 4. Play greeting
        await agi_command(f'STREAM FILE "{greeting_path}" "#"')

        messages = [{"role": "assistant", "content": greeting}]

        # 5. Conversation loop
        for turn in range(MAX_TURNS):
            # Record child's response
            rec_path = str(SHARED_AUDIO_DIR / f"rec_{call_id}_{turn}")
            # No BEEP: the phone experience should feel like a live tutor, not voicemail.
            # Stop after short silence so the turn starts processing as soon as the child
            # finishes, instead of waiting for the full max recording window.
            record_start = time.monotonic()
            await agi_command(
                f'RECORD FILE "{rec_path}" "wav" "#" {RECORD_MAX_MS} 0 s={RECORD_SILENCE_S}'
            )
            logger.info(f"Turn {turn}: recording finished in {time.monotonic() - record_start:.2f}s")

            rec_file = f"{rec_path}.wav"
            if not os.path.exists(rec_file):
                logger.warning(f"No recording file at {rec_file}")
                break

            # STT: transcribe the recording
            loop = asyncio.get_event_loop()
            stt_start = time.monotonic()
            transcript = await loop.run_in_executor(None, stt.transcribe, rec_file)
            logger.info(
                f"Turn {turn}: '{transcript['text']}' "
                f"(conf={transcript['confidence']:.2f}, stt={time.monotonic() - stt_start:.2f}s)"
            )

            # Clean up recording
            try:
                os.unlink(rec_file)
            except OSError:
                pass

            # Handle low confidence
            if transcript["confidence"] < CONFIDENCE_THRESHOLD or not transcript["text"].strip():
                retry_path = await tts_and_convert(
                    tts, "I didn't quite hear that. Can you say it again?", "retry"
                )
                await agi_command(f'STREAM FILE "{retry_path}" "#"')
                continue

            # Add user message
            messages.append({"role": "user", "content": transcript["text"]})
            try:
                turn_stats = analyze_session(
                    {**student, "learning_state": effective_state, "current_module": module},
                    messages,
                )
                effective_state = turn_stats.learning_state
                module = int(effective_state.get("current_module") or module or 0)
                logger.info(
                    "AGI turn %s route module=%s phase=%s diagnostic=%s next=%s",
                    turn,
                    module,
                    effective_state.get("phase"),
                    effective_state.get("diagnostic_status"),
                    effective_state.get("next_step"),
                )
            except Exception as exc:
                logger.debug("Could not update AGI learning state: %s", exc)

            # Check if we should start wrapping up
            user_turns = sum(1 for m in messages if m["role"] == "user")
            if user_turns >= WRAP_UP_AFTER_TURNS:
                messages.append({
                    "role": "system",
                    "content": "The call has been going for a while. Please wrap up the lesson with a summary and encouragement."
                })

            # LLM response
            llm_start = time.monotonic()
            response = await llm.generate(
                messages=messages,
                student_id=student_id,
                current_module=module,
                memory=memory,
                course=str(effective_state.get("course") or "numeracy"),
            )
            logger.info(f"Turn {turn}: llm={time.monotonic() - llm_start:.2f}s")
            messages.append({"role": "assistant", "content": response})
            logger.info(f"Sabi turn {turn}: {response}")

            # TTS response
            tts_start = time.monotonic()
            resp_path = await tts_and_convert(tts, response, "resp")
            logger.info(f"Turn {turn}: tts={time.monotonic() - tts_start:.2f}s")
            await agi_command(f'STREAM FILE "{resp_path}" "#"')

            # Check wrap-up
            if should_wrap_up(messages, response):
                logger.info(f"Wrapping up call after {user_turns} turns")
                break

        # 6. Hangup
        await agi_command("HANGUP")
        logger.info(f"Call {call_id} complete ({phone})")

    except Exception as e:
        logger.error(f"AGI handler error: {e}", exc_info=True)
        try:
            await agi_command("HANGUP")
        except Exception:
            pass
    finally:
        writer.close()
        # Clean up call state
        memory.clear_call(call_id)


async def start_agi_server(stt, llm, tts, memory, host="0.0.0.0", port=4573):
    """Start the FastAGI TCP server.

    Asterisk connects to this server when it hits AGI(agi://sabi:4573)
    in the dialplan.
    """

    async def client_handler(reader, writer):
        await handle_agi_call(reader, writer, stt, llm, tts, memory)

    server = await asyncio.start_server(client_handler, host, port)
    logger.info(f"FastAGI server listening on {host}:{port}")
    return server
