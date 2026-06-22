"""
Realtime AudioSocket handler for Sabi phone lessons.

This is the full-duplex path that lets the phone caller interrupt Sabi while
she is speaking. Asterisk sends 8 kHz signed-linear PCM over AudioSocket; we
send the same format back while listening for caller speech at the same time.
"""

import asyncio
import logging
import os
import struct
import subprocess
import time
import uuid
import wave
from collections import deque
from pathlib import Path
from typing import Optional

import httpx

from answer_matcher import extract_number
from diagnostic_flow import build_opening_turn
from learning_state import analyze_session
from transcript_normalizer import normalize_lesson_transcript
from voice_asterisk import (
    CONFIDENCE_THRESHOLD,
    MAX_TURNS,
    build_call_control_messages,
    is_premature_wrap_response,
    should_wrap_up,
    tts_and_convert,
)

logger = logging.getLogger("sabi.realtime")

SHARED_AUDIO_DIR = Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"))
SHARED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_TYPE_HANGUP = 0x00
AUDIO_TYPE_UUID = 0x01
AUDIO_TYPE_DTMF = 0x03
AUDIO_TYPE_PCM_8K = 0x10
AUDIO_TYPE_ERROR = 0xFF

SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
CHANNELS = 1
FRAME_MS = 20
FRAME_BYTES = int(SAMPLE_RATE * SAMPLE_WIDTH * FRAME_MS / 1000)

SPEECH_RMS_THRESHOLD = int(os.getenv("SABI_BARGE_RMS", "650"))
START_SPEECH_FRAMES = int(os.getenv("SABI_BARGE_START_FRAMES", "2"))
END_SILENCE_FRAMES = int(os.getenv("SABI_UTTERANCE_END_SILENCE_FRAMES", "8"))
MAX_UTTERANCE_FRAMES = int(os.getenv("SABI_MAX_UTTERANCE_FRAMES", "500"))
PRE_ROLL_FRAMES = int(os.getenv("SABI_UTTERANCE_PREROLL_FRAMES", "10"))
COLLECT_TIMEOUT_MS = int(os.getenv("SABI_COLLECT_TIMEOUT_MS", "80"))
SABI_INTERNAL_URL = os.getenv("SABI_INTERNAL_URL", "http://127.0.0.1:8000")
BARGE_GRACE_MS = int(os.getenv("SABI_BARGE_GRACE_MS", "650"))
FILLER_WORDS = {
    "um", "umm", "uh", "uhh", "erm", "hmm", "mm", "mmm",
    "um...", "uh...", "hmm...", "mm-hmm", "mhm",
}
STT_HALLUCINATION_PHRASES = {
    "subtitles by",
    "amara.org",
    "thanks for watching",
    "thank you for watching",
    "captioning by",
}
CARRIER_FAILURE_PHRASES = {
    "voicemail box",
    "voice mailbox",
    "mailbox has not been set up",
    "not been set up yet",
    "please try your call again later",
    "subscriber you have dialed",
    "person you are trying to reach",
    "number you have dialed",
    "currently unavailable",
    "cannot be reached",
    "switched off",
}
MIN_USABLE_CONFIDENCE = float(os.getenv("SABI_MIN_USABLE_CONFIDENCE", "0.18"))
RETRY_TEXT = os.getenv("SABI_RETRY_TEXT", "I didn't quite hear that. Can you say it again?")
FAST_GREETING_TEXT = os.getenv(
    "SABI_FAST_GREETING_TEXT",
    "Hello! I'm Sabi, your learning friend. Sabi means to know, and together, we're going to know so much! What is your name?",
)
USE_CACHED_GREETING = os.getenv("SABI_USE_CACHED_GREETING", "false").strip().lower() in {"1", "true", "yes"}
MAX_CALL_SECONDS = int(os.getenv("SABI_MAX_CALL_SECONDS", "480"))

CALL_REGISTRY: dict[str, dict[str, str]] = {}
HANGUP_EVENTS: dict[str, dict[str, str]] = {}


def register_call(call_uuid: str, phone: str = "unknown", mode: str = "inbound", attempt: str = "1") -> None:
    """Register caller metadata before Asterisk opens the AudioSocket stream."""
    CALL_REGISTRY[call_uuid] = {
        "phone": phone or "unknown",
        "mode": mode or "inbound",
        "attempt": attempt or "1",
    }
    logger.info(
        "Registered AudioSocket call uuid=%s phone=%s mode=%s attempt=%s",
        call_uuid,
        phone,
        mode,
        attempt,
    )


def record_hangup_event(call_uuid: str, **event: str) -> None:
    """Store and log the PBX-side hangup details for post-call debugging."""
    clean_event = {key: str(value or "") for key, value in event.items()}
    clean_event["received_at"] = str(int(time.time()))
    HANGUP_EVENTS[call_uuid] = clean_event
    while len(HANGUP_EVENTS) > 200:
        oldest_key = next(iter(HANGUP_EVENTS))
        HANGUP_EVENTS.pop(oldest_key, None)
    logger.warning(
        "Asterisk hangup uuid=%s phone=%s mode=%s cause=%s dialstatus=%s duration=%s billsec=%s recording=%s",
        call_uuid,
        clean_event.get("phone", ""),
        clean_event.get("mode", ""),
        clean_event.get("hangup_cause", ""),
        clean_event.get("dialstatus", ""),
        clean_event.get("duration", ""),
        clean_event.get("billsec", ""),
        clean_event.get("recording", ""),
    )


def _rms(frame: bytes) -> int:
    if not frame:
        return 0
    sample_count = len(frame) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack("<" + "h" * sample_count, frame[:sample_count * 2])
    return int((sum(sample * sample for sample in samples) / sample_count) ** 0.5)


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


def _read_wav_file_pcm(wav_path: Path) -> bytes:
    with wave.open(str(wav_path), "rb") as wav:
        params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
        if params != (CHANNELS, SAMPLE_WIDTH, SAMPLE_RATE):
            converted = wav_path.with_name(f"{wav_path.stem}_slin8.wav")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
                    "-sample_fmt", "s16", str(converted),
                ],
                capture_output=True,
                check=True,
            )
            wav_path = converted

    with wave.open(str(wav_path), "rb") as wav:
        return wav.readframes(wav.getnframes())


def _read_wav_pcm(path_without_ext: str) -> bytes:
    return _read_wav_file_pcm(Path(f"{path_without_ext}.wav"))


def _fast_greeting_candidates() -> list[Path]:
    candidates = [
        SHARED_AUDIO_DIR / "sabi_realtime_greeting.wav",
        SHARED_AUDIO_DIR / "sabi_greeting_static.wav",
    ]
    candidates.extend(
        sorted(
            SHARED_AUDIO_DIR.glob("rt_greeting_*.wav"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    )
    candidates.extend(
        sorted(
            SHARED_AUDIO_DIR.glob("greeting_*.wav"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    )
    return candidates


def _load_fast_greeting_pcm() -> bytes | None:
    for wav_path in _fast_greeting_candidates():
        if not wav_path.exists() or wav_path.stat().st_size <= 0:
            continue
        try:
            pcm = _read_wav_file_pcm(wav_path)
            if pcm:
                logger.info(
                    "Using cached fast greeting %s duration=%.2fs",
                    wav_path,
                    len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
                )
                return pcm
        except Exception as exc:
            logger.warning("Could not load cached greeting %s: %s", wav_path, exc)
    return None


def _looks_like_carrier_audio(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(phrase in normalized for phrase in CARRIER_FAILURE_PHRASES)


def _looks_like_stt_hallucination(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(phrase in normalized for phrase in STT_HALLUCINATION_PHRASES)


def _looks_like_numeric_answer(text: str) -> bool:
    """Allow math answers through even when Whisper confidence is nervous."""
    return extract_number(text) is not None


def _normalize_transcript_for_lesson(text: str, messages: list[dict[str, str]]) -> str:
    """
    Clean up common phone-STT confusions before the tutor grades the answer.

    Keep this conservative: only rewrite words when the recent tutor prompt
    establishes the expected object.
    """
    result = normalize_lesson_transcript(text, messages)
    if result.changed:
        logger.info(
            "Normalized STT transcript for lesson: %r -> %r substitutions=%s",
            text,
            result.text,
            result.substitutions,
        )
    return result.text


async def _read_packet(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(3)
    packet_type = header[0]
    length = int.from_bytes(header[1:3], "big")
    payload = await reader.readexactly(length) if length else b""
    return packet_type, payload


async def _send_packet(writer: asyncio.StreamWriter, packet_type: int, payload: bytes = b"") -> None:
    writer.write(bytes([packet_type]) + len(payload).to_bytes(2, "big") + payload)
    await writer.drain()


class RealtimeCall:
    def __init__(self, call_uuid: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 stt, llm, tts, memory):
        self.call_uuid = call_uuid
        self.reader = reader
        self.writer = writer
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.memory = memory
        metadata = CALL_REGISTRY.pop(call_uuid, {})
        self.phone = metadata.get("phone", "unknown")
        self.mode = metadata.get("mode", "inbound")
        try:
            self.attempt = max(1, int(metadata.get("attempt", "1")))
        except ValueError:
            self.attempt = 1
        self.call_id = call_uuid
        self.audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=1200)
        self.pre_roll: deque[bytes] = deque(maxlen=PRE_ROLL_FRAMES)
        self.hungup = False
        self.end_reason = "unknown"

    def set_end_reason(self, reason: str) -> None:
        if self.end_reason == "unknown":
            self.end_reason = reason

    async def read_loop(self) -> None:
        try:
            while True:
                packet_type, payload = await _read_packet(self.reader)
                if packet_type == AUDIO_TYPE_HANGUP:
                    self.set_end_reason("asterisk_sent_hangup")
                    logger.info("AudioSocket hangup uuid=%s", self.call_uuid)
                    break
                if packet_type == AUDIO_TYPE_PCM_8K:
                    self.pre_roll.append(payload)
                    try:
                        self.audio_queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        logger.warning("Audio queue full; dropping caller frame uuid=%s", self.call_uuid)
                elif packet_type == AUDIO_TYPE_DTMF:
                    logger.info("DTMF on AudioSocket uuid=%s digit=%r", self.call_uuid, payload)
                elif packet_type == AUDIO_TYPE_ERROR:
                    logger.warning("AudioSocket error packet uuid=%s payload=%r", self.call_uuid, payload)
                else:
                    logger.debug("Ignoring AudioSocket packet type=%s len=%s", packet_type, len(payload))
        except asyncio.IncompleteReadError:
            self.set_end_reason("audiosocket_closed_by_asterisk_or_network")
            logger.info("AudioSocket closed uuid=%s", self.call_uuid)
        except Exception as exc:
            self.set_end_reason(f"audiosocket_read_error:{type(exc).__name__}")
            logger.error("AudioSocket read loop error uuid=%s: %s", self.call_uuid, exc, exc_info=True)
        finally:
            self.hungup = True
            try:
                self.audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def drain_audio(self) -> None:
        while True:
            try:
                item = self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if item is None:
                self.hungup = True
                return

    async def synthesize_pcm(self, text: str, label: str) -> bytes:
        start = time.monotonic()
        path_without_ext = await tts_and_convert(self.tts, text, label)
        pcm = _read_wav_pcm(path_without_ext)
        logger.info("%s TTS ready in %.2fs (%d bytes)", label, time.monotonic() - start, len(pcm))
        return pcm

    async def play_pcm_with_barge(self, pcm: bytes) -> Optional[bytes]:
        """Play audio while watching caller audio. Returns interrupted utterance PCM."""
        # Drop audio that accumulated while LLM/TTS was thinking. Otherwise PSTN
        # noise can barge in before Sabi sends her first frame.
        self.drain_audio()
        if self.hungup:
            self.set_end_reason("channel_closed_before_playback")
            return None

        speech_frames = 0
        utterance_frames: list[bytes] = []
        frame_count = max(1, len(pcm) // FRAME_BYTES)
        playback_start = time.monotonic()
        logger.info(
            "Playback start uuid=%s duration=%.2fs barge_grace_ms=%s",
            self.call_uuid,
            len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
            BARGE_GRACE_MS,
        )

        for offset in range(0, len(pcm), FRAME_BYTES):
            if self.hungup:
                self.set_end_reason("channel_closed_during_playback")
                logger.info("Playback stopped because channel closed uuid=%s elapsed=%.2fs", self.call_uuid, time.monotonic() - playback_start)
                return None

            frame_start = time.monotonic()
            await _send_packet(self.writer, AUDIO_TYPE_PCM_8K, pcm[offset:offset + FRAME_BYTES])

            drained_frames = 0
            peak_rms = 0
            barge_allowed = (time.monotonic() - playback_start) >= (BARGE_GRACE_MS / 1000)
            while True:
                try:
                    inbound = self.audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                if inbound is None:
                    self.hungup = True
                    self.set_end_reason("channel_closed_during_playback")
                    return None

                if not inbound:
                    continue

                drained_frames += 1
                if not barge_allowed:
                    continue

                rms = _rms(inbound)
                peak_rms = max(peak_rms, rms)
                if rms >= SPEECH_RMS_THRESHOLD:
                    speech_frames += 1
                    if not utterance_frames:
                        utterance_frames.extend(self.pre_roll)
                    utterance_frames.append(inbound)
                else:
                    speech_frames = 0

                if speech_frames >= START_SPEECH_FRAMES:
                    logger.info(
                        "Barge-in detected uuid=%s peak_rms=%d drained=%d frame=%d/%d elapsed=%.2fs",
                        self.call_uuid, peak_rms, drained_frames, offset // FRAME_BYTES,
                        frame_count, time.monotonic() - playback_start,
                    )
                    return await self.collect_utterance(utterance_frames)

            elapsed = time.monotonic() - frame_start
            await asyncio.sleep(max(0, FRAME_MS / 1000 - elapsed))

        logger.info("Playback complete uuid=%s elapsed=%.2fs", self.call_uuid, time.monotonic() - playback_start)
        return None

    async def wait_for_utterance(self) -> Optional[bytes]:
        """Wait until caller starts talking, then return one complete utterance."""
        speech_frames = 0
        while not self.hungup:
            inbound = await self.audio_queue.get()
            if inbound is None:
                self.hungup = True
                self.set_end_reason("channel_closed_waiting_for_speech")
                return None
            if _rms(inbound) >= SPEECH_RMS_THRESHOLD:
                speech_frames += 1
                if speech_frames >= START_SPEECH_FRAMES:
                    frames = list(self.pre_roll)
                    frames.append(inbound)
                    return await self.collect_utterance(frames)
            else:
                speech_frames = 0
        return None

    async def collect_utterance(self, initial_frames: list[bytes]) -> bytes:
        frames = list(initial_frames)
        silent_frames = 0
        while len(frames) < MAX_UTTERANCE_FRAMES and not self.hungup:
            try:
                inbound = await asyncio.wait_for(self.audio_queue.get(), timeout=COLLECT_TIMEOUT_MS / 1000)
            except asyncio.TimeoutError:
                silent_frames += max(1, int(COLLECT_TIMEOUT_MS / FRAME_MS))
                if silent_frames >= END_SILENCE_FRAMES:
                    break
                continue

            if inbound is None:
                self.hungup = True
                self.set_end_reason("channel_closed_collecting_utterance")
                break

            frames.append(inbound)
            if _rms(inbound) >= SPEECH_RMS_THRESHOLD:
                silent_frames = 0
            else:
                silent_frames += 1
                if silent_frames >= END_SILENCE_FRAMES:
                    break

        pcm = b"".join(frames)
        logger.info("Collected utterance uuid=%s duration=%.2fs", self.call_uuid, len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH))
        return pcm

    async def transcribe_pcm(self, pcm: bytes, turn: int) -> dict:
        path = SHARED_AUDIO_DIR / f"rt_rec_{self.call_uuid}_{turn}.wav"
        _write_wav(path, pcm)
        try:
            loop = asyncio.get_event_loop()
            start = time.monotonic()
            result = await loop.run_in_executor(None, self.stt.transcribe, str(path))
            logger.info(
                "Realtime turn %s: '%s' conf=%.2f stt=%.2fs",
                turn, result.get("text", ""), result.get("confidence", 0), time.monotonic() - start,
            )
            return result
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    async def request_callback_retry(self, reason: str) -> None:
        if self.mode != "callback" or not self.phone or self.phone == "unknown":
            return

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(
                    f"{SABI_INTERNAL_URL}/asterisk/flash/retry",
                    data={
                        "phone": self.phone,
                        "attempt": str(self.attempt),
                        "reason": reason[:500],
                    },
                )
            logger.info(
                "Callback retry request uuid=%s phone=%s attempt=%s status=%s body=%s",
                self.call_uuid,
                self.phone,
                self.attempt,
                response.status_code,
                response.text[:300],
            )
        except Exception as exc:
            logger.warning(
                "Callback retry request failed uuid=%s phone=%s attempt=%s: %s",
                self.call_uuid,
                self.phone,
                self.attempt,
                exc,
            )

    async def run(self) -> None:
        call_started_at = time.monotonic()
        logger.info(
            "Realtime call start uuid=%s phone=%s mode=%s attempt=%s",
            self.call_uuid,
            self.phone,
            self.mode,
            self.attempt,
        )
        reader_task = asyncio.create_task(self.read_loop())
        messages: list[dict[str, str]] = []
        retry_streak = 0
        student_id: Optional[str] = None

        try:
            student = await self.memory.find_or_create_student(self.phone)
            student_id = student["id"]
            effective_state = await self.memory.get_effective_learning_state(student)
            starting_learning_state = dict(effective_state)
            module = int(effective_state.get("current_module") or student.get("current_module") or 0)
            logger.info(
                "Realtime student=%s module=%s skill=%s scaffold=%s new=%s",
                student_id,
                module,
                effective_state.get("active_skill"),
                effective_state.get("scaffold_depth"),
                student.get("is_new"),
            )

            greeting = build_opening_turn(student, effective_state)
            messages.append({"role": "assistant", "content": greeting})
            self.drain_audio()
            use_static_greeting = USE_CACHED_GREETING and greeting == FAST_GREETING_TEXT
            greeting_pcm = _load_fast_greeting_pcm() if use_static_greeting else None
            if greeting_pcm is None:
                greeting_pcm = await self.synthesize_pcm(greeting, "rt_greeting")
            interrupted = await self.play_pcm_with_barge(greeting_pcm)
            if self.hungup:
                self.set_end_reason("channel_closed_during_greeting")
                return

            for turn in range(MAX_TURNS):
                if self.hungup:
                    break
                if time.monotonic() - call_started_at >= MAX_CALL_SECONDS:
                    self.set_end_reason("max_call_seconds")
                    logger.info(
                        "Realtime max call duration reached uuid=%s seconds=%s",
                        self.call_uuid,
                        MAX_CALL_SECONDS,
                    )
                    break

                utterance = interrupted if interrupted else await self.wait_for_utterance()
                interrupted = None
                if not utterance:
                    if self.hungup:
                        self.set_end_reason("channel_closed_waiting_for_speech")
                    else:
                        self.set_end_reason("no_utterance")
                    break

                turn_start = time.monotonic()
                transcript = await self.transcribe_pcm(utterance, turn)
                text = transcript.get("text", "").strip()
                confidence = float(transcript.get("confidence", 0))
                normalized_text = text.lower().strip(" .,!?:;")
                if _looks_like_carrier_audio(text):
                    logger.warning(
                        "Realtime turn %s: carrier/voicemail audio detected; ending callback. text=%r attempt=%s",
                        turn,
                        text,
                        self.attempt,
                    )
                    await self.request_callback_retry(text)
                    self.set_end_reason("carrier_or_voicemail_audio")
                    break
                if normalized_text in FILLER_WORDS:
                    logger.info("Realtime turn %s: ignoring filler '%s'", turn, text)
                    continue
                if not text or _looks_like_stt_hallucination(text):
                    if _looks_like_stt_hallucination(text):
                        logger.info("Realtime turn %s: ignoring STT hallucination %r", turn, text)
                    if retry_streak >= 1:
                        text = "I answered, but the phone transcript was unclear."
                    else:
                        retry_streak += 1
                        retry_pcm = await self.synthesize_pcm(RETRY_TEXT, "rt_retry")
                        logger.info("Realtime turn %s retry pipeline=%.2fs", turn, time.monotonic() - turn_start)
                        interrupted = await self.play_pcm_with_barge(retry_pcm)
                        continue
                if confidence < CONFIDENCE_THRESHOLD and not _looks_like_numeric_answer(text):
                    if confidence >= MIN_USABLE_CONFIDENCE and len(normalized_text) >= 3:
                        logger.info(
                            "Realtime turn %s: accepting usable low-confidence transcript %r conf=%.2f",
                            turn,
                            text,
                            confidence,
                        )
                    elif retry_streak >= 1:
                        logger.info(
                            "Realtime turn %s: passing unclear transcript after retry %r conf=%.2f",
                            turn,
                            text,
                            confidence,
                        )
                    else:
                        retry_streak += 1
                        retry_pcm = await self.synthesize_pcm(RETRY_TEXT, "rt_retry")
                        logger.info("Realtime turn %s retry pipeline=%.2fs", turn, time.monotonic() - turn_start)
                        interrupted = await self.play_pcm_with_barge(retry_pcm)
                        continue
                else:
                    retry_streak = 0
                if confidence < CONFIDENCE_THRESHOLD:
                    logger.info(
                        "Realtime turn %s: accepting low-confidence answer %r conf=%.2f",
                        turn,
                        text,
                        confidence,
                    )

                retry_streak = 0
                text_for_lesson = _normalize_transcript_for_lesson(text, messages)
                messages.append({"role": "user", "content": text_for_lesson})
                try:
                    turn_stats = analyze_session(
                        {**student, "learning_state": effective_state, "current_module": module},
                        messages,
                    )
                    effective_state = turn_stats.learning_state
                    module = int(effective_state.get("current_module") or module or 0)
                    logger.info(
                        "Realtime turn %s route module=%s phase=%s diagnostic=%s next=%s",
                        turn,
                        module,
                        effective_state.get("phase"),
                        effective_state.get("diagnostic_status"),
                        effective_state.get("next_step"),
                    )
                except Exception as exc:
                    logger.debug("Could not update in-call learning state: %s", exc)
                user_turns = sum(1 for message in messages if message["role"] == "user")
                elapsed_seconds = time.monotonic() - call_started_at
                llm_messages = [
                    *messages,
                    *build_call_control_messages(user_turns, elapsed_seconds, MAX_CALL_SECONDS),
                ]

                llm_start = time.monotonic()
                response = await self.llm.generate(
                    messages=llm_messages,
                    student_id=student_id,
                    current_module=module,
                    memory=self.memory,
                    course=str(effective_state.get("course") or "numeracy"),
                )
                if is_premature_wrap_response(response, user_turns, elapsed_seconds):
                    logger.warning(
                        "Realtime turn %s produced premature wrap at %.0fs/%s turns; regenerating",
                        turn,
                        elapsed_seconds,
                        user_turns,
                    )
                    repair_messages = [
                        *messages,
                        {
                            "role": "system",
                            "content": (
                                "Your previous draft ended the lesson too early. Rewrite it as an "
                                "active teaching turn: acknowledge the child, continue the same skill, "
                                "and ask one next question. Do not summarize or mention next time."
                            ),
                        },
                    ]
                    response = await self.llm.generate(
                        messages=repair_messages,
                        student_id=student_id,
                        current_module=module,
                        memory=self.memory,
                        course=str(effective_state.get("course") or "numeracy"),
                    )
                logger.info("Realtime turn %s llm=%.2fs response=%s", turn, time.monotonic() - llm_start, response)
                messages.append({"role": "assistant", "content": response})

                response_pcm = await self.synthesize_pcm(response, "rt_resp")
                logger.info("Realtime turn %s response pipeline=%.2fs", turn, time.monotonic() - turn_start)
                interrupted = await self.play_pcm_with_barge(response_pcm)
                if should_wrap_up(messages, response, elapsed_seconds=time.monotonic() - call_started_at):
                    self.set_end_reason("sabi_wrap_up")
                    logger.info("Realtime wrapping up uuid=%s after %s user turns", self.call_uuid, user_turns)
                    break
        except Exception as exc:
            self.set_end_reason(f"exception:{type(exc).__name__}")
            logger.error("Realtime call error uuid=%s: %s", self.call_uuid, exc, exc_info=True)
        finally:
            if self.end_reason == "unknown":
                self.end_reason = "channel_closed" if self.hungup else "normal_loop_complete"
            duration_seconds = int(time.monotonic() - call_started_at)
            self.hungup = True
            reader_task.cancel()
            try:
                await _send_packet(self.writer, AUDIO_TYPE_HANGUP)
            except Exception:
                pass
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            if student_id and messages:
                await self.memory.save_phone_session(
                    student_id=student_id,
                    phone_number=self.phone,
                    call_id=self.call_id,
                    messages=messages,
                    duration_seconds=duration_seconds,
                    channel="asterisk_audiosocket",
                    starting_learning_state=starting_learning_state,
                )
            self.memory.clear_call(self.call_id)
            logger.warning(
                "Realtime call complete uuid=%s phone=%s mode=%s attempt=%s end_reason=%s duration=%ss user_turns=%s assistant_turns=%s",
                self.call_uuid,
                self.phone,
                self.mode,
                self.attempt,
                self.end_reason,
                duration_seconds,
                sum(1 for message in messages if message.get("role") == "user"),
                sum(1 for message in messages if message.get("role") == "assistant"),
            )


async def handle_audiosocket_call(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                  stt, llm, tts, memory) -> None:
    peer_info = writer.get_extra_info("peername")
    try:
        packet_type, payload = await _read_packet(reader)
        if packet_type != AUDIO_TYPE_UUID or len(payload) != 16:
            logger.warning("AudioSocket %s sent invalid first packet type=%s len=%s", peer_info, packet_type, len(payload))
            writer.close()
            return
        call_uuid = str(uuid.UUID(bytes=payload))
        await RealtimeCall(call_uuid, reader, writer, stt, llm, tts, memory).run()
    except Exception as exc:
        logger.error("AudioSocket connection error from %s: %s", peer_info, exc, exc_info=True)
        writer.close()


async def start_audiosocket_server(stt, llm, tts, memory, host: str = "0.0.0.0", port: int = 9019):
    async def client_handler(reader, writer):
        await handle_audiosocket_call(reader, writer, stt, llm, tts, memory)

    server = await asyncio.start_server(client_handler, host, port)
    logger.info("AudioSocket realtime server listening on %s:%s", host, port)
    return server
