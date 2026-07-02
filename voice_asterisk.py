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

SHARED_AUDIO_DIR = Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"))
SHARED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
ELEVENLABS_API_KEY = get_secret("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = get_secret("ELEVENLABS_VOICE_ID", "oC2pCZZWEDRe6lmZpaaw")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "").strip() or "eleven_flash_v2_5"
TTS_PRIMARY = os.getenv("SABI_TTS_PRIMARY", "elevenlabs").strip().lower()
# Self-hosted Chatterbox Turbo (per pilot/budget/Sabi Costs.md the phone path
# should be Chatterbox at $0; ElevenLabs stays as paid fallback/last resort).
# `chatterbox` resolves on the sabi-server_default docker network.
CHATTERBOX_URL = os.getenv("SABI_CHATTERBOX_URL", "http://chatterbox:8001/tts").strip()
CHATTERBOX_SPEAKER = os.getenv("SABI_CHATTERBOX_SPEAKER", "naomi").strip()
CHATTERBOX_TIMEOUT_SECONDS = float(os.getenv("SABI_CHATTERBOX_TIMEOUT_SECONDS", "12"))

MAX_TURNS = int(os.getenv("SABI_MAX_TURNS", "40"))
WRAP_UP_AFTER_TURNS = int(os.getenv("SABI_WRAP_UP_AFTER_TURNS", "34"))
MIN_WRAP_USER_TURNS = int(os.getenv("SABI_MIN_WRAP_USER_TURNS", "10"))
MIN_LESSON_SECONDS = int(os.getenv("SABI_MIN_LESSON_SECONDS", "300"))
TARGET_WRAP_SECONDS = int(os.getenv("SABI_TARGET_WRAP_SECONDS", "360"))
RECORD_MAX_MS = 10000  # 10 seconds max recording
RECORD_SILENCE_S = 2   # Stop recording after 2s silence
# SIP/PSTN audio is narrowband and short child answers often score around 0.35
# even when Whisper gets the words right. Keep this lower than web/Twilio.
CONFIDENCE_THRESHOLD = 0.3

WRAP_UP_PHRASES = [
    "call me back", "bye", "well done today",
    "great job today", "see you next time",
    "talk to you", "until next time",
    "next time", "today you learned", "we learned today",
    "you have done really well", "you've done really well",
    "we'll try", "we will try", "finished for today",
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


async def synthesize_chatterbox(text: str, output_path: str) -> bool:
    """Generate speech via the self-hosted Chatterbox Turbo container ($0/call)."""
    if not CHATTERBOX_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=CHATTERBOX_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                CHATTERBOX_URL,
                json={
                    "text": text[:2000],
                    "speaker_name": CHATTERBOX_SPEAKER,
                    "format": "mp3",
                },
            )
            resp.raise_for_status()
            if len(resp.content) < 1024:
                raise RuntimeError(f"suspiciously small audio ({len(resp.content)} bytes)")
            with open(output_path, "wb") as f:
                f.write(resp.content)
            logger.info("Chatterbox TTS (%s): %d chars", CHATTERBOX_SPEAKER, len(text))
            return True
    except Exception as e:
        logger.warning(f"Chatterbox TTS failed: {e}")
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


async def synthesize_phone_tts(tts, text: str, output_path: str, primary: str | None = None) -> str | None:
    """Generate phone audio with the configured provider chain.

    Returns the provider name that produced the audio ("chatterbox",
    "elevenlabs", "yarngpt") or None if every provider failed — truthy/falsy
    compatible with the old bool return.

    `primary` overrides the global SABI_TTS_PRIMARY for one call. The isolated
    AudioSocket test lane uses this (SABI_TTS_TEST_PRIMARY) so Chatterbox can
    be canaried on port 9020 while production keeps its known-good chain.
    """
    effective_primary = (primary or TTS_PRIMARY).strip().lower()

    if effective_primary == "chatterbox":
        if await synthesize_chatterbox(text, output_path):
            return "chatterbox"
        if await synthesize_elevenlabs(text, output_path):
            return "elevenlabs"
        if await synthesize_yarngpt(tts, text, output_path):
            return "yarngpt"
        return None

    if effective_primary == "yarngpt":
        if await synthesize_yarngpt(tts, text, output_path):
            return "yarngpt"
        if await synthesize_elevenlabs(text, output_path):
            return "elevenlabs"
        return None

    if effective_primary not in {"elevenlabs", "yarngpt", "chatterbox"}:
        logger.warning("Unsupported SABI_TTS_PRIMARY=%s; using ElevenLabs then YarnGPT", effective_primary)
    if await synthesize_elevenlabs(text, output_path):
        return "elevenlabs"
    if await synthesize_yarngpt(tts, text, output_path):
        return "yarngpt"
    return None


async def tts_and_convert(tts, text: str, label: str = "resp", primary: str | None = None) -> tuple[str, str]:
    """Generate TTS audio and convert to Asterisk WAV format.

    Returns (path WITHOUT extension, provider name). Asterisk adds .wav/.ulaw
    to the path automatically; the provider feeds per-turn admin evidence.
    """
    audio_id = uuid.uuid4().hex
    mp3_path = str(SHARED_AUDIO_DIR / f"{label}_{audio_id}.mp3")
    wav_path = str(SHARED_AUDIO_DIR / f"{label}_{audio_id}.wav")
    clean_text = clean_text_for_tts(text)

    provider = await synthesize_phone_tts(tts, clean_text, mp3_path, primary=primary)

    if not provider:
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
    return wav_path.rsplit(".", 1)[0], provider


def _latest_user_message(messages: list[dict]) -> str:
    return next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")


def _caller_asked_to_end(messages: list[dict]) -> bool:
    latest_user_lower = _latest_user_message(messages).lower()
    return any(phrase in latest_user_lower for phrase in CALLER_END_PHRASES)


def _response_wants_wrap(response: str) -> bool:
    response_lower = response.lower()
    return any(phrase in response_lower for phrase in WRAP_UP_PHRASES)


def _in_planned_wrap_window(
    user_turns: int,
    elapsed_seconds: float,
    max_call_seconds: int | None = None,
) -> bool:
    """Return true when closing the lesson is intentional instead of early."""
    if max_call_seconds is not None and elapsed_seconds >= max_call_seconds - 60:
        return True
    if elapsed_seconds >= TARGET_WRAP_SECONDS and user_turns >= MIN_WRAP_USER_TURNS:
        return True
    if elapsed_seconds >= MIN_LESSON_SECONDS and user_turns >= WRAP_UP_AFTER_TURNS:
        return True
    return False


def should_prompt_wrap_up(user_turns: int, elapsed_seconds: float, max_call_seconds: int | None = None) -> bool:
    """Return true when Sabi should start closing the current lesson."""
    return _in_planned_wrap_window(user_turns, elapsed_seconds, max_call_seconds)


def build_call_control_messages(
    user_turns: int,
    elapsed_seconds: float,
    max_call_seconds: int | None = None,
) -> list[dict[str, str]]:
    """Transient system instructions for the current turn."""
    if should_prompt_wrap_up(user_turns, elapsed_seconds, max_call_seconds):
        return [{
            "role": "system",
            "content": (
                "The call is now in the planned wrap-up window. Finish the current idea, "
                "summarize the skill the child practiced, give encouragement, and end warmly."
            ),
        }]

    if elapsed_seconds < TARGET_WRAP_SECONDS or user_turns < MIN_WRAP_USER_TURNS:
        return [{
            "role": "system",
            "content": (
                "Do not wrap up or end the lesson yet. This call is still before the planned wrap window "
                f"({int(elapsed_seconds)} seconds, {user_turns} user turns). Continue teaching "
                "one small step and ask the next clear question. Do not say 'next time', "
                "'today you learned', 'well done today', 'bye', or any closing phrase."
            ),
        }]

    return []


def is_premature_wrap_response(
    response: str,
    user_turns: int,
    elapsed_seconds: float,
    max_call_seconds: int | None = None,
) -> bool:
    """Detect an early closing draft before the 5-7 minute lesson window."""
    if not _response_wants_wrap(response):
        return False
    return not _in_planned_wrap_window(user_turns, elapsed_seconds, max_call_seconds)


def should_wrap_up(messages: list[dict], response: str, elapsed_seconds: float | None = None) -> bool:
    """Check if the lesson should end."""
    user_turns = sum(1 for m in messages if m["role"] == "user")
    if user_turns >= MAX_TURNS:
        return True
    if _caller_asked_to_end(messages):
        return True
    # In the original hackathon-style flow, Sabi did not cut the child off just
    # because she used a closing-sounding encouragement. Keep the line open
    # until the planned wrap-up band unless the caller explicitly ends.
    if not _response_wants_wrap(response):
        return False
    if elapsed_seconds is None:
        return False
    if not _in_planned_wrap_window(user_turns, elapsed_seconds):
        return False
    return True


async def handle_agi_call(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                          stt, llm, tts, memory):
    """
    Handle a single Sabi lesson call via AGI protocol.

    Called when Asterisk connects an outbound callback to our FastAGI server.
    The child has already answered the phone.
    """
    call_id = uuid.uuid4().hex
    call_started_at = time.monotonic()
    peer_info = writer.get_extra_info("peername")
    logger.info(f"AGI connection from {peer_info} (call_id={call_id})")
    phone = "unknown"
    student_id = None
    starting_learning_state = None
    messages: list[dict[str, str]] = []

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
        starting_learning_state = dict(effective_state)
        identity_confirmed = not student.get("needs_identity_confirmation")
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
        greeting_path, _tts_provider = await tts_and_convert(tts, greeting, "greeting")

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
                retry_path, _tts_provider = await tts_and_convert(
                    tts, "I didn't quite hear that. Can you say it again?", "retry"
                )
                await agi_command(f'STREAM FILE "{retry_path}" "#"')
                continue

            # Add user message
            messages.append({"role": "user", "content": transcript["text"]})
            if not identity_confirmed:
                resolved_student = await memory.resolve_student_for_spoken_identity(
                    student,
                    phone,
                    messages,
                )
                if resolved_student:
                    old_student_id = student_id
                    student = resolved_student
                    student_id = resolved_student.get("id") or student_id
                    effective_state = await memory.get_effective_learning_state(student)
                    starting_learning_state = dict(effective_state)
                    module = int(effective_state.get("current_module") or student.get("current_module") or module or 0)
                    identity_confirmed = True
                    logger.info(
                        "AGI resolved shared-phone identity old_student=%s new_student=%s child=%s module=%s",
                        old_student_id,
                        student_id,
                        resolved_student.get("spoken_child_name") or resolved_student.get("name"),
                        module,
                    )
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

            user_turns = sum(1 for m in messages if m["role"] == "user")
            elapsed_seconds = time.monotonic() - call_started_at
            llm_messages = [
                *messages,
                *build_call_control_messages(user_turns, elapsed_seconds),
            ]

            # LLM response
            llm_start = time.monotonic()
            response = await llm.generate(
                messages=llm_messages,
                student_id=student_id,
                current_module=module,
                memory=memory,
                course=str(effective_state.get("course") or "numeracy"),
                learning_state=effective_state,
                call_id=call_id,
                channel="asterisk_fastagi",
            )
            if is_premature_wrap_response(response, user_turns, elapsed_seconds):
                logger.warning(
                    "AGI turn %s produced premature wrap at %.0fs/%s turns; regenerating",
                    turn,
                    elapsed_seconds,
                    user_turns,
                )
                response = await llm.generate(
                    messages=[
                        *messages,
                        {
                            "role": "system",
                            "content": (
                                "Your previous draft ended the lesson too early. Rewrite it as an "
                                "active teaching turn: acknowledge the child, continue the same skill, "
                                "and ask one next question. Do not summarize or mention next time."
                            ),
                        },
                    ],
                    student_id=student_id,
                    current_module=module,
                    memory=memory,
                    course=str(effective_state.get("course") or "numeracy"),
                    learning_state=effective_state,
                    call_id=call_id,
                    channel="asterisk_fastagi",
                )
            logger.info(f"Turn {turn}: llm={time.monotonic() - llm_start:.2f}s")
            messages.append({"role": "assistant", "content": response})
            logger.info(f"Sabi turn {turn}: {response}")

            # TTS response
            tts_start = time.monotonic()
            resp_path, _tts_provider = await tts_and_convert(tts, response, "resp")
            logger.info(f"Turn {turn}: tts={time.monotonic() - tts_start:.2f}s")
            await agi_command(f'STREAM FILE "{resp_path}" "#"')

            # Check wrap-up
            if should_wrap_up(messages, response, elapsed_seconds=time.monotonic() - call_started_at):
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
        duration_seconds = int(time.monotonic() - call_started_at)
        if student_id and messages:
            await memory.save_phone_session(
                student_id=student_id,
                phone_number=phone,
                call_id=call_id,
                messages=messages,
                duration_seconds=duration_seconds,
                channel="asterisk_fastagi",
                starting_learning_state=starting_learning_state,
            )
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
