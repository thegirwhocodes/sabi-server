"""
FastAGI handler for Sabi voice lessons over Asterisk.

Handles the conversation loop when Asterisk connects a callback call:
  1. Play greeting
  2. Record child's response (silence detection or # key)
  3. Play thinking cue
  4. Process: STT → LLM → TTS
  5. Play AI response
  6. Loop until wrap-up

Audio format: Asterisk expects 8kHz mono WAV (ulaw/alaw codec).
TTS outputs MP3 → ffmpeg converts to Asterisk-compatible WAV.
"""

import asyncio
import logging
import os
import random
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger("sabi.asterisk")

SHARED_AUDIO_DIR = Path("/shared/audio")
SHARED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

MAX_TURNS = 12
RECORD_MAX_MS = 15000  # 15 seconds max recording
RECORD_SILENCE_S = 3   # Stop recording after 3s silence
CONFIDENCE_THRESHOLD = 0.5

WRAP_UP_PHRASES = [
    "call me back", "bye", "well done today",
    "great job today", "see you next time",
    "talk to you", "until next time",
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


async def tts_and_convert(tts, text: str, label: str = "resp") -> str:
    """Generate TTS audio and convert to Asterisk WAV format.

    Returns path WITHOUT extension (Asterisk adds .wav/.ulaw automatically).
    """
    audio_id = uuid.uuid4().hex
    mp3_path = str(SHARED_AUDIO_DIR / f"{label}_{audio_id}.mp3")
    wav_path = str(SHARED_AUDIO_DIR / f"{label}_{audio_id}.wav")

    # Run TTS (blocking HTTP call — run in thread)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, tts.synthesize, text, mp3_path)

    # Convert MP3 → 8kHz WAV
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
        module = student.get("current_module", 0)
        logger.info(f"Student: {student_id}, module={module}, new={student.get('is_new')}")

        # 2. Generate greeting
        greeting = await llm.generate(
            messages=[],
            student_id=student_id,
            current_module=module,
            memory=memory,
        )
        logger.info(f"Greeting: {greeting[:80]}...")

        # 3. TTS greeting → Asterisk WAV
        greeting_path = await tts_and_convert(tts, greeting, "greeting")

        # 4. Play greeting
        await agi_command(f'STREAM FILE "{greeting_path}" ""')

        messages = [{"role": "assistant", "content": greeting}]

        # 5. Conversation loop
        for turn in range(MAX_TURNS):
            # Record child's response
            rec_path = str(SHARED_AUDIO_DIR / f"rec_{call_id}_{turn}")
            await agi_command(
                f'RECORD FILE "{rec_path}" "wav" "#" {RECORD_MAX_MS} 0 BEEP s={RECORD_SILENCE_S}'
            )

            rec_file = f"{rec_path}.wav"
            if not os.path.exists(rec_file):
                logger.warning(f"No recording file at {rec_file}")
                break

            # Play a random thinking cue while we process
            cue_idx = random.randint(0, 4)
            thinking_path = str(SHARED_AUDIO_DIR / f"thinking_{cue_idx}")
            await agi_command(f'STREAM FILE "{thinking_path}" ""')

            # STT: transcribe the recording
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(None, stt.transcribe, rec_file)
            logger.info(f"Turn {turn}: '{transcript['text']}' (conf={transcript['confidence']:.2f})")

            # Clean up recording
            try:
                os.unlink(rec_file)
            except OSError:
                pass

            # Handle low confidence
            if transcript["confidence"] < CONFIDENCE_THRESHOLD or not transcript["text"].strip():
                retry_path = await tts_and_convert(
                    tts, "I didn't quite catch that. Can you say it again?", "retry"
                )
                await agi_command(f'STREAM FILE "{retry_path}" ""')
                continue

            # Add user message
            messages.append({"role": "user", "content": transcript["text"]})

            # Check if we should start wrapping up
            user_turns = sum(1 for m in messages if m["role"] == "user")
            if user_turns >= 10:
                messages.append({
                    "role": "system",
                    "content": "The call has been going for a while. Please wrap up the lesson with a summary and encouragement."
                })

            # LLM response
            response = await llm.generate(
                messages=messages,
                student_id=student_id,
                current_module=module,
                memory=memory,
            )
            messages.append({"role": "assistant", "content": response})
            logger.info(f"Sabi: {response[:80]}...")

            # TTS response
            resp_path = await tts_and_convert(tts, response, "resp")
            await agi_command(f'STREAM FILE "{resp_path}" ""')

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
