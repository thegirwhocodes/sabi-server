"""
Realtime AudioSocket handler for Sabi phone lessons.

This is the full-duplex path that lets the phone caller interrupt Sabi while
she is speaking. Asterisk sends 8 kHz signed-linear PCM over AudioSocket; we
send the same format back while listening for caller speech at the same time.
"""

import asyncio
import json
import logging
import os
import re
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
from call_admin import merge_call_hangup_event, write_call_review_record
from call_admin import append_call_turn_review, call_turn_audio_path, write_call_learning_summary
from curriculum_path import resolve_literacy_lesson, resolve_numeracy_lesson
from diagnostic_flow import build_opening_turn
from learning_state import analyze_session, force_numeracy_course
from numeric_grading import (
    analyze_latest_numeric_turn,
    question_expects_numeric_answer,
    response_accepts_verified_number,
    verified_numeric_control_message,
)
from original_sabi_prompt import ORIGINAL_SABI_FIRST_MESSAGE, original_sabi_prompt_for_phone
from phone_utils import phone_is_numeracy_only
from transcript_normalizer import (
    is_likely_stt_hallucination_transcript,
    is_phone_system_transcript,
    normalize_lesson_transcript,
)
from turn_taking import (
    INTERRUPTION_CANDIDATE_RESET_MS,
    INTERRUPTION_EVAL_INTERVAL_MS,
    INTERRUPTION_MIN_AUDIO_MS,
    INTERRUPTION_PREFILTER_RMS,
    SMART_TURN_MAX_EXTENSION_MS,
    TURN_GATE_ENABLED,
    get_managed_turn_detector,
)
from voice_asterisk import (
    CONFIDENCE_THRESHOLD,
    MAX_TURNS,
    build_call_control_messages,
    clean_text_for_tts,
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
LITERACY_SPEECH_RMS_THRESHOLD = int(os.getenv("SABI_LITERACY_SPEECH_RMS", "420"))
START_SPEECH_FRAMES = int(os.getenv("SABI_BARGE_START_FRAMES", "2"))
END_SILENCE_FRAMES = int(os.getenv("SABI_UTTERANCE_END_SILENCE_FRAMES", "18"))
LITERACY_END_SILENCE_FRAMES = int(os.getenv("SABI_LITERACY_UTTERANCE_END_SILENCE_FRAMES", "18"))
MAX_UTTERANCE_FRAMES = int(os.getenv("SABI_MAX_UTTERANCE_FRAMES", "500"))
PRE_ROLL_FRAMES = int(os.getenv("SABI_UTTERANCE_PREROLL_FRAMES", "10"))
COLLECT_TIMEOUT_MS = int(os.getenv("SABI_COLLECT_TIMEOUT_MS", "80"))
SABI_INTERNAL_URL = os.getenv("SABI_INTERNAL_URL", "http://127.0.0.1:8000")
BARGE_GRACE_MS = int(os.getenv("SABI_BARGE_GRACE_MS", "650"))
# The home-grown energy gate cannot distinguish intentional speech from a
# breath, cough, handset movement, or acoustic playback leakage as reliably as
# a managed conversational turn detector.  Keep a production kill switch so a
# carrier can use the realtime lesson/STT lane without turning those sounds
# into learner answers.  When disabled, caller audio is still drained during
# playback and listening begins only after Sabi finishes speaking.
BARGE_IN_ENABLED = os.getenv("SABI_BARGE_IN_ENABLED", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
# Outbound PSTN legs can deliver a short answer/ringback click or dial tone just
# after Asterisk answers.  Do not let that carrier audio interrupt the opening
# greeting and become turn 0.  Later greeting speech and all normal lesson
# barge-in remain enabled.
INITIAL_GREETING_BARGE_GRACE_MS = max(
    BARGE_GRACE_MS,
    int(os.getenv("SABI_INITIAL_GREETING_BARGE_GRACE_MS", "3000")),
)
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
SHORT_STT_HALLUCINATION_TRANSCRIPTS = {
    "bye",
    "bye bye",
    "goodbye",
    "see you",
    "see you next time",
    "thank you",
    "thanks",
    "got it",
    "end card",
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


def _keypad_terminators_from_env() -> set[str]:
    raw = os.getenv("SABI_KEYPAD_NUMERIC_TERMINATORS", "#*").strip()
    if raw.lower() in {"hash_star", "hash-star", "hash,*", "hash"}:
        return {"#", "*"}
    return set(raw or "#*")


MIN_USABLE_CONFIDENCE = float(os.getenv("SABI_MIN_USABLE_CONFIDENCE", "0.18"))
RETRY_TEXT = os.getenv("SABI_RETRY_TEXT", "I didn't quite hear that. Can you say it again?")
UNCLEAR_AUDIO_RETRY_TEXT = os.getenv(
    "SABI_UNCLEAR_AUDIO_RETRY_TEXT",
    "I still can't hear clearly. Please move the phone closer to your mouth, find a quieter spot if you can, and say just the answer slowly.",
)
MAX_UNCLEAR_RETRIES = max(1, int(os.getenv("SABI_MAX_UNCLEAR_RETRIES", "2")))
KEYPAD_NUMERIC_FALLBACK_ENABLED = os.getenv("SABI_KEYPAD_NUMERIC_FALLBACK_ENABLED", "1").strip().lower() in {
    "1", "true", "yes", "on"
}
KEYPAD_NUMERIC_FALLBACK_TEXT = os.getenv(
    "SABI_KEYPAD_NUMERIC_FALLBACK_TEXT",
    "The phone is still noisy. For this number answer, you can press the digits on your keypad, then press hash.",
)
KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT = os.getenv(
    "SABI_KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT",
    "If I ever mishear a number, you can type it on your keypad and press hash.",
).strip()
NUMERIC_AMBIGUITY_CONFIRMATION_TEXT = os.getenv(
    "SABI_NUMERIC_AMBIGUITY_CONFIRMATION_TEXT",
    "I may not have heard the full amount. Say the naira amount again slowly for me.",
)
KEYPAD_NUMERIC_TIMEOUT_SECONDS = int(os.getenv("SABI_KEYPAD_NUMERIC_TIMEOUT_SECONDS", "8"))
KEYPAD_NUMERIC_MAX_DIGITS = int(os.getenv("SABI_KEYPAD_NUMERIC_MAX_DIGITS", "4"))
KEYPAD_NUMERIC_INTERDIGIT_SECONDS = float(os.getenv("SABI_KEYPAD_NUMERIC_INTERDIGIT_SECONDS", "1.2"))
KEYPAD_NUMERIC_TERMINATORS = _keypad_terminators_from_env()
FAST_GREETING_TEXT = os.getenv(
    "SABI_FAST_GREETING_TEXT",
    "Hello! I'm Sabi, your learning friend. Sabi means to know, and together, we're going to know so much! What is your name?",
)
USE_CACHED_GREETING = os.getenv("SABI_USE_CACHED_GREETING", "false").strip().lower() in {"1", "true", "yes"}
MAX_CALL_SECONDS = int(os.getenv("SABI_MAX_CALL_SECONDS", "480"))
# The pre-pilot consent flow tells testers they will get an optional open
# feedback prompt. Keep it available by default; set SABI_FEEDBACK_MODE=off to
# disable, or testers + SABI_FEEDBACK_TEST_NUMBERS to restrict during trials.
FEEDBACK_MODE = os.getenv("SABI_FEEDBACK_MODE", "all").strip().lower()
FEEDBACK_TEST_NUMBERS = {
    "".join(ch for ch in value if ch.isdigit())
    for value in os.getenv("SABI_FEEDBACK_TEST_NUMBERS", "").split(",")
    if value.strip()
}
FEEDBACK_MAX_SECONDS = int(os.getenv("SABI_FEEDBACK_MAX_SECONDS", "90"))
# Wait window: how long to wait for the caller to START speaking after the prompt.
# Tuned up from 8s after testers reported the call cutting off while they
# gathered their thoughts. Real-world: an adult needs ~10-20s to decide what
# to say; a child needs longer.
FEEDBACK_WAIT_SECONDS = int(os.getenv("SABI_FEEDBACK_WAIT_SECONDS", "25"))
# Mid-note silence: how long the caller can pause inside their note before we
# consider it finished. Tuned up so think-pauses don't truncate the note.
FEEDBACK_END_SILENCE_MS = int(os.getenv("SABI_FEEDBACK_END_SILENCE_MS", "6000"))
FEEDBACK_END_SILENCE_FRAMES = max(1, int(FEEDBACK_END_SILENCE_MS / FRAME_MS))
# RMS floor for "this frame contains speech". Lowered from 320 so softer
# voices on poor PSTN aren't rejected as silence.
FEEDBACK_SPEECH_RMS_THRESHOLD = int(os.getenv("SABI_FEEDBACK_SPEECH_RMS", "220"))
# If the first wait window expires with no speech, repeat a short prompt once
# and try again. Set SABI_FEEDBACK_RETRY_ENABLED=0 to disable.
FEEDBACK_RETRY_ENABLED = os.getenv("SABI_FEEDBACK_RETRY_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
# DTMF digit a caller can press to skip the feedback window immediately.
# Empty string disables.
FEEDBACK_DTMF_SKIP_DIGIT = os.getenv("SABI_FEEDBACK_DTMF_SKIP_DIGIT", "1").strip()
# DTMF "hotkey" a caller can press AT ANY POINT during the lesson to stop the
# call and jump straight to the open feedback space -- so a frustrated child
# (or tester) who would otherwise just hang up has a way to say what went
# wrong. Defaults to the star key, which never collides with numeric answers
# on a numeracy lesson. Empty string disables. Set SABI_FEEDBACK_HOTKEY_DIGIT.
FEEDBACK_HOTKEY_DIGIT = os.getenv("SABI_FEEDBACK_HOTKEY_DIGIT", "*").strip()
# Length of the audible "go" cue beep played right before the recording
# window opens, so the caller knows recording is now live.
FEEDBACK_GO_CUE_MS = int(os.getenv("SABI_FEEDBACK_GO_CUE_MS", "400"))
FEEDBACK_GO_CUE_FREQ_HZ = int(os.getenv("SABI_FEEDBACK_GO_CUE_FREQ_HZ", "880"))
FEEDBACK_PROMPT_TEXT = os.getenv(
    "SABI_FEEDBACK_PROMPT_TEXT",
    (
        "Before you go, this is your space to say anything at all -- what you liked, "
        "what was hard, anything that annoyed you. Just start talking after the beep."
    ),
)
FEEDBACK_REQUESTED_PROMPT_TEXT = os.getenv(
    "SABI_FEEDBACK_REQUESTED_PROMPT_TEXT",
    "Of course, I'm listening. Say anything you like. Go ahead after the beep.",
)
# Warm, de-escalating prompt used when the caller pressed the mid-call feedback
# hotkey -- they interrupted the lesson because something is bothering them, so
# lead with reassurance, not survey framing.
FEEDBACK_HOTKEY_PROMPT_TEXT = os.getenv(
    "SABI_FEEDBACK_HOTKEY_PROMPT_TEXT",
    "Okay, I'm listening. What is wrong? What upset you? Tell me after the beep.",
)
# Short line appended to the greeting so the caller knows the hotkey exists.
# Empty string disables the announcement. Only spoken on the live-synth greeting
# path (not the rarely-used cached greeting).
FEEDBACK_HOTKEY_ANNOUNCE_TEXT = os.getenv(
    "SABI_FEEDBACK_HOTKEY_ANNOUNCE_TEXT",
    (
        "Anytime you want, you can say, I want to leave feedback, or press the star "
        "key on your phone, and I will stop and listen after the beep."
    ),
)
# After the caller leaves a mid-call note, Sabi acknowledges it warmly and then
# asks whether to keep going. Kept deterministic so the model can't wander.
FEEDBACK_CONTINUE_QUESTION_TEXT = os.getenv(
    "SABI_FEEDBACK_CONTINUE_QUESTION_TEXT",
    "Do you want to keep learning, or should we stop here for today?",
)
# Spoken if the empathy model call fails, so the flow never dead-ends silently.
FEEDBACK_EMPATHY_FALLBACK_TEXT = os.getenv(
    "SABI_FEEDBACK_EMPATHY_FALLBACK_TEXT",
    "Thank you for telling me. I hear you, and I am glad you said something.",
)
# Spoken when the caller opened the feedback space but left no note.
FEEDBACK_EMPTY_NOTE_RESUME_TEXT = os.getenv(
    "SABI_FEEDBACK_EMPTY_NOTE_RESUME_TEXT",
    "That is okay. Whenever you are ready, let's keep going.",
)
FEEDBACK_RETRY_PROMPT_TEXT = os.getenv(
    "SABI_FEEDBACK_RETRY_PROMPT_TEXT",
    (
        "I did not hear anything. If you have something to share, start now. "
        "Or press 1 to skip and end the call."
    ),
)

CALL_REGISTRY: dict[str, dict[str, str]] = {}
HANGUP_EVENTS: dict[str, dict[str, str]] = {}


def _build_go_cue_pcm() -> bytes:
    """Generate a short sine-wave beep so the caller knows recording is live.

    Avoids the latency of a TTS round-trip. 8 kHz signed-linear, mono, the
    same format Asterisk AudioSocket expects.
    """
    if FEEDBACK_GO_CUE_MS <= 0:
        return b""
    import math
    num_samples = int(SAMPLE_RATE * FEEDBACK_GO_CUE_MS / 1000)
    amp = 8000
    freq = max(220, min(2000, FEEDBACK_GO_CUE_FREQ_HZ))
    # 20ms fade-in/out so the tone doesn't click.
    fade_samples = min(int(SAMPLE_RATE * 0.02), num_samples // 4)
    samples = []
    for i in range(num_samples):
        envelope = 1.0
        if i < fade_samples:
            envelope = i / fade_samples
        elif i > num_samples - fade_samples:
            envelope = max(0.0, (num_samples - i) / fade_samples)
        value = int(amp * envelope * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        samples.append(value)
    return struct.pack(f"<{num_samples}h", *samples)


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
    merge_call_hangup_event(call_uuid, clean_event, SHARED_AUDIO_DIR)
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
    path.parent.mkdir(parents=True, exist_ok=True)
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
    if is_phone_system_transcript(text):
        return True
    return any(phrase in normalized for phrase in CARRIER_FAILURE_PHRASES)


def _looks_like_stt_hallucination(text: str) -> bool:
    normalized = " ".join(text.lower().strip(" .,!?:;").split())
    if normalized in SHORT_STT_HALLUCINATION_TRANSCRIPTS:
        return True
    if is_likely_stt_hallucination_transcript(text):
        return True
    return any(phrase in normalized for phrase in STT_HALLUCINATION_PHRASES)


def _looks_like_numeric_answer(text: str) -> bool:
    """Allow math answers through even when Whisper confidence is nervous."""
    return extract_number(text) is not None


def _retry_text_for_unclear_audio(retry_streak: int) -> str:
    """Escalate from repeat request to concrete audibility coaching."""
    if retry_streak <= 0:
        return RETRY_TEXT
    return UNCLEAR_AUDIO_RETRY_TEXT


def _is_literacy_state(state: dict | None) -> bool:
    state = state or {}
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    skill_text = " ".join(
        str(value or "")
        for value in (
            state.get("course"),
            state.get("active_skill"),
            literacy.get("active_skill"),
            literacy.get("next_step"),
            state.get("next_step"),
        )
    ).lower()
    return (
        state.get("course") == "literacy"
        or "literacy" in skill_text
        or "phonemic" in skill_text
        or "sound" in skill_text
        or "rhyme" in skill_text
        or "syllable" in skill_text
    )


def _stt_mode_for_state(state: dict | None) -> str:
    return "literacy" if _is_literacy_state(state) else "general"


def _course_state_for_phone(phone: str, state: dict | None) -> dict:
    """Apply reversible, caller-scoped course experiments to runtime state."""
    effective = dict(state or {})
    return force_numeracy_course(effective) if phone_is_numeracy_only(phone) else effective


def _stt_mode_for_turn(state: dict | None, messages: list[dict[str, str]]) -> str:
    # The test lane deliberately keeps Gemini for names and numeracy, where it
    # won the real-call bake-off. Foundational literacy sounds use the much
    # faster Whisper/Groq lane instead. A returning learner can already be in a
    # literacy state while Sabi is still asking their name, so question intent
    # must take precedence over the saved course here.
    if _current_question_asks_for_name(messages):
        return "general"
    if _current_question_expects_numeric(messages):
        return "general"
    return _stt_mode_for_state(state)


def _latest_assistant_turn(messages: list[dict[str, str]]) -> str:
    return next(
        (
            str(message.get("content") or "")
            for message in reversed(messages)
            if message.get("role") == "assistant"
        ),
        "",
    )


def _current_question_expects_numeric(messages: list[dict[str, str]]) -> bool:
    """Keypad/STT numeric gate based only on the question being answered now."""
    return question_expects_numeric_answer(_latest_assistant_turn(messages))


def _current_question_asks_for_name(messages: list[dict[str, str]]) -> bool:
    current = _latest_assistant_turn(messages).lower()
    return bool(
        re.search(
            r"\b(?:what(?:'s| is) your name|tell me your name|say your name|who am i speaking (?:to|with))\b",
            current,
        )
    )


def _recent_assistant_stt_context(
    messages: list[dict[str, str]],
    state: dict | None = None,
) -> str:
    """Give STT the current lesson metadata and exact tutor question.

    This deliberately describes the expected response *type* but never inserts
    the correct answer, which would make a generative audio model hallucinate.
    """
    state = state or {}
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    # The outgoing tutor turn alone defines the response expected now. Older
    # maths wording must not turn a new literacy question into a numeric STT
    # prompt (a failure observed in the Aug 6 callback).
    recent_tutor = _latest_assistant_turn(messages)
    numeric_context = question_expects_numeric_answer(recent_tutor)
    course = "numeracy" if numeric_context else str(state.get("course") or "numeracy")
    if _is_literacy_state(state) and not numeric_context:
        course = "literacy"
    lesson = (
        resolve_literacy_lesson(state)
        if course == "literacy"
        else resolve_numeracy_lesson(state)
    )
    metadata = [
        f"course={course}",
        f"module={literacy.get('current_module') if course == 'literacy' else state.get('current_module')}",
        f"lesson={literacy.get('current_lesson') if course == 'literacy' else state.get('current_lesson')}",
        f"skill={literacy.get('active_skill') if course == 'literacy' else state.get('active_skill')}",
        f"phase={literacy.get('phase') if course == 'literacy' else state.get('phase')}",
        f"lesson_title={(lesson or {}).get('title') or 'current lesson'}",
    ]
    return f"Lesson metadata: {'; '.join(metadata)}. Exact recent tutor prompt: {recent_tutor}"


def _speech_threshold_for_state(state: dict | None) -> int:
    return LITERACY_SPEECH_RMS_THRESHOLD if _is_literacy_state(state) else SPEECH_RMS_THRESHOLD


def _end_silence_frames_for_state(state: dict | None) -> int:
    return LITERACY_END_SILENCE_FRAMES if _is_literacy_state(state) else END_SILENCE_FRAMES


def _looks_like_literacy_answer(text: str, state: dict | None) -> bool:
    if not _is_literacy_state(state):
        return False
    normalized = " ".join((text or "").lower().replace("-", " ").split()).strip(" .,!?:;")
    if not normalized:
        return False
    letters = {chr(code) for code in range(ord("a"), ord("z") + 1)}
    common_short = {
        "yes", "no", "same", "different", "rhyme", "rhymes", "sound", "sounds",
        "cat", "mat", "hat", "bat", "ball", "mango", "moon", "mama", "market",
        "rat", "sat", "fat", "pat", "dog", "log", "fog", "hog", "big", "dig", "pig",
        "mmm", "mm", "sss", "ss", "ah", "at", "am", "ma", "pa", "ta",
    }
    tokens = normalized.split()
    if normalized in letters or normalized in common_short:
        return True
    if len(tokens) <= 3 and any(token in letters or token in common_short for token in tokens):
        return True
    if len(normalized) <= 5 and normalized.replace(" ", "") in common_short:
        return True
    return False


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


def _phone_digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _feedback_enabled_for_phone(phone: str) -> bool:
    if FEEDBACK_MODE in {"", "0", "false", "no", "off"}:
        return False
    if FEEDBACK_MODE in {"1", "true", "yes", "on", "all", "pilot", "prepilot", "pre-pilot"}:
        return True
    if FEEDBACK_MODE == "testers":
        digits = _phone_digits(phone)
        return bool(
            digits
            and any(
                digits == tester_digits
                or digits.endswith(tester_digits)
                or tester_digits.endswith(digits)
                for tester_digits in FEEDBACK_TEST_NUMBERS
            )
        )
    return False


def _drain_dtmf(queue: asyncio.Queue) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return


FEEDBACK_OFFER_END_REASONS = {
    "sabi_wrap_up",
    "max_call_seconds",
    "normal_loop_complete",
    "feedback_requested",
    "feedback_hotkey",
}


def _should_offer_feedback(
    student_id: str | None,
    messages: list[dict[str, str]],
    hungup: bool,
    end_reason: str,
) -> bool:
    del student_id  # Feedback sidecars can still be useful if memory failed.
    return bool(messages) and not hungup and end_reason in FEEDBACK_OFFER_END_REASONS


_STOP_LESSON_MARKERS = (
    "stop", "no more", "not anymore", "i am done", "i'm done", "im done",
    "finished", "that's all", "thats all", "goodbye", "good bye", "bye",
    "end the call", "hang up", "leave", "go now", "tired", "enough",
    "don't want to continue", "do not want to continue", "no thank",
)
_CONTINUE_LESSON_MARKERS = (
    "keep learning", "keep going", "continue", "carry on", "go on", "more",
    "yes", "yeah", "yep", "sure", "okay", "ok", "let's continue", "lets continue",
    "i want to learn", "teach me", "keep teaching", "still learning",
)


def _wants_to_continue_lesson(text: str) -> bool:
    """Decide whether a caller's reply to 'keep going or stop?' means continue.

    Bias: a clear stop word stops; a clear continue word (or any other
    non-empty answer, since they are still engaged and talking) continues;
    an empty/no-answer stops.
    """
    normalized = " ".join((text or "").lower().replace("-", " ").split()).strip(" .,!?:;")
    if not normalized:
        return False
    if any(marker in normalized for marker in _STOP_LESSON_MARKERS):
        # A bare "no" also stops.
        return False
    if normalized in {"no", "nope", "nah"}:
        return False
    if any(marker in normalized for marker in _CONTINUE_LESSON_MARKERS):
        return True
    # They said something else but are still talking/engaged -> keep going.
    return True


def _looks_like_feedback_request(text: str) -> bool:
    normalized = " ".join((text or "").lower().replace("-", " ").split()).strip(" .,!?:;")
    if not normalized:
        return False
    direct_phrases = (
        "leave feedback",
        "give feedback",
        "send feedback",
        "record feedback",
        "feedback note",
        "leave a note",
        "give a note",
        "voice note",
        "make a complaint",
        "make complaint",
        "i want to complain",
        "i want to report",
        "report a problem",
        "say something about the call",
        "talk about the call",
    )
    if any(phrase in normalized for phrase in direct_phrases):
        return True
    return "feedback" in normalized and any(
        marker in normalized
        for marker in ("i want", "can i", "let me", "need to", "want to", "please", "note")
    )


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
                 stt, llm, tts, memory, tts_primary: str = "", conversation_style: str = "current",
                 barge_in_enabled: bool | None = None):
        self.call_uuid = call_uuid
        self.reader = reader
        self.writer = writer
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.memory = memory
        self.conversation_style = (conversation_style or "current").strip().lower()
        # Each listener can canary learned barge-in independently. The public
        # 9019 lane inherits the conservative global default; Twilio's 9020
        # test lane may opt in without changing Africa's Talking traffic.
        self.barge_in_enabled = (
            BARGE_IN_ENABLED if barge_in_enabled is None else bool(barge_in_enabled)
        )
        # Per-lane TTS provider override. Empty = global SABI_TTS_PRIMARY.
        # The isolated test lane (port 9020) sets this from
        # SABI_TTS_TEST_PRIMARY so Chatterbox can be canaried without touching
        # the production chain.
        self.tts_primary = (tts_primary or "").strip().lower()
        self.last_tts_provider = ""
        metadata = CALL_REGISTRY.pop(call_uuid, {})
        self.phone = metadata.get("phone", "unknown")
        self.mode = metadata.get("mode", "inbound")
        try:
            self.attempt = max(1, int(metadata.get("attempt", "1")))
        except ValueError:
            self.attempt = 1
        self.call_id = call_uuid
        self.audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=1200)
        self.dtmf_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
        self.pre_roll: deque[bytes] = deque(maxlen=PRE_ROLL_FRAMES)
        self.hungup = False
        self.end_reason = "unknown"
        # Set True the moment the caller presses the mid-call feedback hotkey.
        self.feedback_hotkey_pressed = False
        # Set True once any feedback note has been captured, so the end-of-call
        # offer does not ask a second time.
        self.feedback_captured = False
        # Shared lazy ONNX runtimes.  The strict gate is used while Sabi talks;
        # the permissive gate and Smart Turn endpoint model are used after the
        # prompt.  Keeping this separate from STT prevents noise from becoming
        # a Gemini request in the first place.
        self.turn_detector = get_managed_turn_detector()

    def set_end_reason(self, reason: str) -> None:
        if self.end_reason == "unknown":
            self.end_reason = reason

    def _consume_feedback_hotkey(self) -> bool:
        """Drain pending DTMF; latch the hotkey if the caller pressed it.

        Non-hotkey digits are re-queued so the numeric keypad fallback still
        works. Returns True the first time the hotkey is seen; the latched
        ``feedback_hotkey_pressed`` flag stays True afterward so callers that
        drained the queue can still detect it.
        """
        if not FEEDBACK_HOTKEY_DIGIT:
            return False
        pressed = False
        leftover: list[str] = []
        while True:
            try:
                digit = self.dtmf_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if digit == FEEDBACK_HOTKEY_DIGIT:
                pressed = True
            else:
                leftover.append(digit)
        for digit in leftover:
            try:
                self.dtmf_queue.put_nowait(digit)
            except asyncio.QueueFull:
                break
        if pressed:
            if not self.feedback_hotkey_pressed:
                logger.info("Feedback hotkey pressed uuid=%s digit=%r", self.call_uuid, FEEDBACK_HOTKEY_DIGIT)
            self.feedback_hotkey_pressed = True
        return pressed

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
                    digit = ""
                    if payload:
                        try:
                            digit = payload.decode("ascii", errors="ignore").strip()
                        except Exception:
                            digit = ""
                    logger.info("DTMF on AudioSocket uuid=%s digit=%r", self.call_uuid, digit or payload)
                    if digit:
                        try:
                            self.dtmf_queue.put_nowait(digit)
                        except asyncio.QueueFull:
                            logger.warning("DTMF queue full; dropping digit uuid=%s digit=%s", self.call_uuid, digit)
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

    async def _listening_pcm_is_speech(self, pcm: bytes) -> bool:
        """Validate a captured post-prompt turn before it reaches Gemini.

        This gate is intentionally much more permissive than interruption
        detection because literacy answers can be a single phoneme.  Detector
        failures fail open here; a broken optional guard must never erase a
        real child's response.
        """
        if not TURN_GATE_ENABLED:
            return True
        loop = asyncio.get_running_loop()
        evidence = await loop.run_in_executor(None, self.turn_detector.listening_speech, pcm)
        logger.info(
            "Listening speech gate uuid=%s accepted=%s reason=%s duration_ms=%s max_prob=%.3f longest_ms=%s ratio=%.3f",
            self.call_uuid,
            evidence.accepted,
            evidence.reason,
            evidence.duration_ms,
            evidence.max_probability,
            evidence.longest_speech_ms,
            evidence.speech_ratio,
        )
        if evidence.reason.startswith("detector_error:"):
            return True
        return evidence.accepted

    async def synthesize_pcm(self, text: str, label: str) -> bytes:
        start = time.monotonic()
        path_without_ext, provider = await tts_and_convert(
            self.tts, text, label, primary=self.tts_primary or None
        )
        self.last_tts_provider = provider
        pcm = _read_wav_pcm(path_without_ext)
        logger.info(
            "%s TTS ready in %.2fs (%d bytes, provider=%s)",
            label, time.monotonic() - start, len(pcm), provider,
        )
        return pcm

    async def play_pcm(self, pcm: bytes) -> None:
        """Play a short prompt without barge-in collection."""
        self.drain_audio()
        if self.hungup:
            self.set_end_reason("channel_closed_before_playback")
            return

        for offset in range(0, len(pcm), FRAME_BYTES):
            if self.hungup:
                self.set_end_reason("channel_closed_during_playback")
                return
            frame_start = time.monotonic()
            await _send_packet(self.writer, AUDIO_TYPE_PCM_8K, pcm[offset:offset + FRAME_BYTES])
            elapsed = time.monotonic() - frame_start
            await asyncio.sleep(max(0, FRAME_MS / 1000 - elapsed))

    async def play_pcm_with_barge(
        self,
        pcm: bytes,
        speech_threshold: int | None = None,
        end_silence_frames: int | None = None,
        barge_grace_ms: int | None = None,
    ) -> Optional[bytes]:
        """Play audio while watching caller audio. Returns interrupted utterance PCM."""
        # Drop audio that accumulated while LLM/TTS was thinking. Otherwise PSTN
        # noise can barge in before Sabi sends her first frame.
        self.drain_audio()
        if self.hungup:
            self.set_end_reason("channel_closed_before_playback")
            return None

        interruption_frames: list[bytes] = []
        interruption_silent_frames = 0
        last_evaluated_frame_count = 0
        last_interruption_decision = None
        outbound_reference: deque[bytes] = deque(maxlen=max(1, int(3000 / FRAME_MS)))
        frame_count = max(1, len(pcm) // FRAME_BYTES)
        playback_start = time.monotonic()
        threshold = speech_threshold or SPEECH_RMS_THRESHOLD
        effective_barge_grace_ms = BARGE_GRACE_MS if barge_grace_ms is None else max(0, barge_grace_ms)
        logger.info(
            "Playback start uuid=%s duration=%.2fs barge_in_enabled=%s barge_grace_ms=%s speech_threshold=%s",
            self.call_uuid,
            len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
            self.barge_in_enabled,
            effective_barge_grace_ms,
            threshold,
        )

        for offset in range(0, len(pcm), FRAME_BYTES):
            if self.hungup:
                self.set_end_reason("channel_closed_during_playback")
                logger.info("Playback stopped because channel closed uuid=%s elapsed=%.2fs", self.call_uuid, time.monotonic() - playback_start)
                return None

            # A frustrated caller can press the hotkey mid-sentence: stop
            # talking immediately and let the main loop open the feedback space.
            if self._consume_feedback_hotkey():
                logger.info("Playback stopped for feedback hotkey uuid=%s elapsed=%.2fs", self.call_uuid, time.monotonic() - playback_start)
                return None

            frame_start = time.monotonic()
            outbound_frame = pcm[offset:offset + FRAME_BYTES]
            await _send_packet(self.writer, AUDIO_TYPE_PCM_8K, outbound_frame)
            outbound_reference.append(outbound_frame)

            drained_frames = 0
            peak_rms = 0
            barge_allowed = (
                self.barge_in_enabled
                and (time.monotonic() - playback_start) >= (effective_barge_grace_ms / 1000)
            )
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
                if not interruption_frames:
                    # Energy is only a cheap candidate prefilter now.  It can
                    # never interrupt playback on its own.
                    if rms < INTERRUPTION_PREFILTER_RMS:
                        continue
                    interruption_frames.extend(self.pre_roll)
                    interruption_frames.append(inbound)
                    interruption_silent_frames = 0
                else:
                    interruption_frames.append(inbound)
                    if rms >= INTERRUPTION_PREFILTER_RMS:
                        interruption_silent_frames = 0
                    else:
                        interruption_silent_frames += 1

                candidate_ms = len(interruption_frames) * FRAME_MS
                since_last_eval_ms = (
                    len(interruption_frames) - last_evaluated_frame_count
                ) * FRAME_MS
                if (
                    candidate_ms >= INTERRUPTION_MIN_AUDIO_MS
                    and since_last_eval_ms >= INTERRUPTION_EVAL_INTERVAL_MS
                ):
                    last_evaluated_frame_count = len(interruption_frames)
                    candidate_pcm = b"".join(interruption_frames)
                    reference_pcm = b"".join(outbound_reference)
                    loop = asyncio.get_running_loop()
                    last_interruption_decision = await loop.run_in_executor(
                        None,
                        self.turn_detector.evaluate_interruption,
                        candidate_pcm,
                        reference_pcm,
                    )
                    decision = last_interruption_decision
                    logger.info(
                        "Interruption gate uuid=%s accepted=%s reason=%s duration_ms=%s max_prob=%.3f longest_ms=%s echo=%.3f",
                        self.call_uuid,
                        decision.accepted,
                        decision.reason,
                        decision.speech.duration_ms,
                        decision.speech.max_probability,
                        decision.speech.longest_speech_ms,
                        decision.echo_similarity,
                    )
                    if decision.accepted:
                        logger.info(
                            "Learned barge-in accepted uuid=%s peak_rms=%d drained=%d frame=%d/%d elapsed=%.2fs",
                            self.call_uuid,
                            peak_rms,
                            drained_frames,
                            offset // FRAME_BYTES,
                            frame_count,
                            time.monotonic() - playback_start,
                        )
                        return await self.collect_utterance(
                            interruption_frames,
                            end_silence_frames=end_silence_frames,
                            speech_threshold=threshold,
                        )

                if interruption_silent_frames * FRAME_MS >= INTERRUPTION_CANDIDATE_RESET_MS:
                    logger.info(
                        "Interruption candidate rejected uuid=%s reason=%s duration_ms=%s peak_rms=%s",
                        self.call_uuid,
                        getattr(last_interruption_decision, "reason", "energy_only"),
                        candidate_ms,
                        peak_rms,
                    )
                    interruption_frames.clear()
                    interruption_silent_frames = 0
                    last_evaluated_frame_count = 0
                    last_interruption_decision = None

            elapsed = time.monotonic() - frame_start
            await asyncio.sleep(max(0, FRAME_MS / 1000 - elapsed))

        if not self.barge_in_enabled:
            # Close the race between the final playback frame and the next
            # wait_for_utterance() call.  Nothing heard while Sabi was talking
            # should be promoted into a learner turn when barge-in is disabled.
            self.drain_audio()
        logger.info("Playback complete uuid=%s elapsed=%.2fs", self.call_uuid, time.monotonic() - playback_start)
        return None

    async def wait_for_utterance(
        self,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
    ) -> Optional[bytes]:
        """Wait until caller starts talking, then return one complete utterance."""
        speech_frames = 0
        threshold = speech_threshold or SPEECH_RMS_THRESHOLD
        while not self.hungup:
            if self.feedback_hotkey_pressed or self._consume_feedback_hotkey():
                return None
            inbound = await self.audio_queue.get()
            if inbound is None:
                self.hungup = True
                self.set_end_reason("channel_closed_waiting_for_speech")
                return None
            if _rms(inbound) >= threshold:
                speech_frames += 1
                if speech_frames >= START_SPEECH_FRAMES:
                    frames = list(self.pre_roll)
                    frames.append(inbound)
                    pcm = await self.collect_utterance(
                        frames,
                        max_frames=max_frames,
                        end_silence_frames=end_silence_frames,
                        speech_threshold=threshold,
                    )
                    if await self._listening_pcm_is_speech(pcm):
                        return pcm
                    logger.info(
                        "Rejected non-speech listening candidate uuid=%s duration=%.2fs",
                        self.call_uuid,
                        len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
                    )
                    speech_frames = 0
            else:
                speech_frames = 0
        return None

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
        dtmf_skip_digit: str | None = None,
        rms_telemetry: dict | None = None,
    ) -> Optional[bytes]:
        """Wait for speech, optionally short-circuited by a DTMF digit.

        rms_telemetry, when passed, is mutated in place with peak_rms,
        mean_rms, frames_observed, frames_above_threshold, ended_reason,
        time_to_first_speech_ms (or None). This lets callers debug why a
        recording window closed without changing the function's return type.
        """
        if timeout_seconds <= 0:
            if rms_telemetry is not None:
                rms_telemetry["ended_reason"] = "timeout_zero"
                rms_telemetry["time_to_first_speech_ms"] = None
            return None

        deadline = time.monotonic() + timeout_seconds
        speech_frames = 0
        threshold = speech_threshold or SPEECH_RMS_THRESHOLD
        peak_rms = 0
        rms_sum = 0
        frames_observed = 0
        frames_above_threshold = 0
        wait_started_at = time.monotonic()

        def _record_metrics(ended_reason: str, time_to_speech_ms: int | None) -> None:
            if rms_telemetry is None:
                return
            rms_telemetry["peak_rms"] = peak_rms
            rms_telemetry["mean_rms"] = int(rms_sum / frames_observed) if frames_observed else 0
            rms_telemetry["frames_observed"] = frames_observed
            rms_telemetry["frames_above_threshold"] = frames_above_threshold
            rms_telemetry["ended_reason"] = ended_reason
            rms_telemetry["time_to_first_speech_ms"] = time_to_speech_ms
            rms_telemetry["wait_seconds_used"] = round(time.monotonic() - wait_started_at, 2)

        while not self.hungup:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _record_metrics("wait_timeout", None)
                return None
            # If a DTMF skip is enabled, drain any digits the caller pressed
            # while the prompt was still playing so we can short-circuit
            # immediately on the first matching digit.
            if dtmf_skip_digit:
                while True:
                    try:
                        digit = self.dtmf_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if digit == dtmf_skip_digit:
                        _record_metrics("dtmf_skipped", None)
                        return None
            try:
                inbound = await asyncio.wait_for(self.audio_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                _record_metrics("wait_timeout", None)
                return None
            if inbound is None:
                self.hungup = True
                self.set_end_reason("channel_closed_waiting_for_optional_speech")
                _record_metrics("channel_closed", None)
                return None
            rms = _rms(inbound)
            frames_observed += 1
            rms_sum += rms
            if rms > peak_rms:
                peak_rms = rms
            if rms >= threshold:
                speech_frames += 1
                frames_above_threshold += 1
                if speech_frames >= START_SPEECH_FRAMES:
                    time_to_speech_ms = int((time.monotonic() - wait_started_at) * 1000)
                    frames = list(self.pre_roll)
                    frames.append(inbound)
                    pcm = await self.collect_utterance(
                        frames,
                        max_frames=max_frames,
                        end_silence_frames=end_silence_frames,
                        speech_threshold=threshold,
                    )
                    if await self._listening_pcm_is_speech(pcm):
                        _record_metrics("speech_captured", time_to_speech_ms)
                        return pcm
                    logger.info(
                        "Rejected non-speech optional candidate uuid=%s duration=%.2fs",
                        self.call_uuid,
                        len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
                    )
                    speech_frames = 0
            else:
                speech_frames = 0
        _record_metrics("channel_closed", None)
        return None

    async def wait_for_keypad_digits(
        self,
        timeout_seconds: float,
        *,
        max_digits: int = KEYPAD_NUMERIC_MAX_DIGITS,
        terminators: set[str] | None = None,
    ) -> str | None:
        """Collect DTMF digits, auto-submitting shortly after the last digit."""
        if timeout_seconds <= 0 or max_digits <= 0:
            return None
        deadline = time.monotonic() + timeout_seconds
        terminators = terminators if terminators is not None else KEYPAD_NUMERIC_TERMINATORS
        digits: list[str] = []
        while not self.hungup:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if digits and KEYPAD_NUMERIC_INTERDIGIT_SECONDS > 0:
                remaining = min(remaining, KEYPAD_NUMERIC_INTERDIGIT_SECONDS)
            try:
                digit = await asyncio.wait_for(self.dtmf_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            digit = str(digit or "").strip()
            if digit in terminators:
                if digit == FEEDBACK_HOTKEY_DIGIT and not digits:
                    self.feedback_hotkey_pressed = True
                break
            if digit.isdigit():
                digits.append(digit)
                if len(digits) >= max_digits:
                    break
        return "".join(digits) if digits else None

    async def wait_for_numeric_or_utterance(
        self,
        *,
        end_silence_frames: int,
        speech_threshold: int,
    ) -> tuple[bytes | None, str | None]:
        """Accept either speech or keypad digits for the current numeric question.

        Both listeners run together. Pressing digits plus hash wins immediately;
        a single digit also auto-submits after the short inter-digit window.
        """
        speech_task = asyncio.create_task(
            self.wait_for_utterance(
                end_silence_frames=end_silence_frames,
                speech_threshold=speech_threshold,
            )
        )
        keypad_task = asyncio.create_task(
            self.wait_for_keypad_digits(
                MAX_CALL_SECONDS,
                max_digits=KEYPAD_NUMERIC_MAX_DIGITS,
                terminators=KEYPAD_NUMERIC_TERMINATORS,
            )
        )
        try:
            done, _pending = await asyncio.wait(
                {speech_task, keypad_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if keypad_task in done:
                digits = keypad_task.result()
                if digits or self.feedback_hotkey_pressed:
                    speech_task.cancel()
                    await asyncio.gather(speech_task, return_exceptions=True)
                    return None, digits
                return await speech_task, None

            utterance = speech_task.result()
            keypad_task.cancel()
            await asyncio.gather(keypad_task, return_exceptions=True)
            return utterance, None
        finally:
            for task in (speech_task, keypad_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(speech_task, keypad_task, return_exceptions=True)

    async def prompt_for_keypad_numeric_answer(
        self,
        *,
        turn: int,
        user_audio_path: Path | None,
        transcript: dict,
        raw_text: str,
        normalized_text: str,
        learning_state_before: dict | None,
        turn_flags: list[str],
        turn_start: float,
    ) -> str | None:
        """Ask for keypad digits after repeated noisy numeric-answer failures."""
        if not KEYPAD_NUMERIC_FALLBACK_ENABLED:
            return None
        _drain_dtmf(self.dtmf_queue)
        prompt_pcm = await self.synthesize_pcm(KEYPAD_NUMERIC_FALLBACK_TEXT, "rt_keypad_retry")
        self.persist_turn_review(
            turn=turn,
            user_audio_path=user_audio_path,
            transcript=transcript,
            raw_text=raw_text,
            normalized_text=normalized_text,
            learning_state_before=learning_state_before,
            learning_state_after=learning_state_before,
            assistant_text=KEYPAD_NUMERIC_FALLBACK_TEXT,
            assistant_pcm=prompt_pcm,
            flags=[*turn_flags, "retry_prompt", "keypad_numeric_fallback_prompt"],
            timings={
                "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                "turn_total_seconds": round(time.monotonic() - turn_start, 3),
            },
        )
        await self.play_pcm(prompt_pcm)
        if self.hungup:
            return None
        digits = await self.wait_for_keypad_digits(
            KEYPAD_NUMERIC_TIMEOUT_SECONDS,
            max_digits=KEYPAD_NUMERIC_MAX_DIGITS,
            terminators=KEYPAD_NUMERIC_TERMINATORS,
        )
        if digits:
            logger.info("Realtime turn %s accepted keypad numeric fallback=%s", turn, digits)
            return digits
        logger.info("Realtime turn %s keypad numeric fallback timed out", turn)
        return None

    async def collect_utterance(
        self,
        initial_frames: list[bytes],
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
    ) -> bytes:
        frames = list(initial_frames)
        silent_frames = 0
        max_frame_count = max_frames or MAX_UTTERANCE_FRAMES
        silence_limit = end_silence_frames or END_SILENCE_FRAMES
        threshold = speech_threshold or SPEECH_RMS_THRESHOLD
        endpoint_extension_deadline: float | None = None

        async def pause_is_endpoint() -> bool:
            """Use prosody/linguistic audio cues before treating silence as final."""
            nonlocal endpoint_extension_deadline
            candidate_pcm = b"".join(frames)
            loop = asyncio.get_running_loop()
            decision = await loop.run_in_executor(
                None,
                self.turn_detector.endpoint_complete,
                candidate_pcm,
            )
            logger.info(
                "Smart Turn endpoint uuid=%s available=%s complete=%s probability=%s reason=%s",
                self.call_uuid,
                decision.available,
                decision.complete,
                decision.probability,
                decision.reason,
            )
            if not decision.available or decision.complete is not False:
                return True
            now = time.monotonic()
            if endpoint_extension_deadline is None:
                endpoint_extension_deadline = now + (SMART_TURN_MAX_EXTENSION_MS / 1000)
            if now >= endpoint_extension_deadline:
                logger.info(
                    "Smart Turn extension exhausted uuid=%s extension_ms=%s",
                    self.call_uuid,
                    SMART_TURN_MAX_EXTENSION_MS,
                )
                return True
            return False

        while len(frames) < max_frame_count and not self.hungup:
            try:
                inbound = await asyncio.wait_for(self.audio_queue.get(), timeout=COLLECT_TIMEOUT_MS / 1000)
            except asyncio.TimeoutError:
                silent_frames += max(1, int(COLLECT_TIMEOUT_MS / FRAME_MS))
                if silent_frames >= silence_limit:
                    if await pause_is_endpoint():
                        break
                    silent_frames = 0
                continue

            if inbound is None:
                self.hungup = True
                self.set_end_reason("channel_closed_collecting_utterance")
                break

            frames.append(inbound)
            if _rms(inbound) >= threshold:
                silent_frames = 0
            else:
                silent_frames += 1
                if silent_frames >= silence_limit:
                    if await pause_is_endpoint():
                        break
                    silent_frames = 0

        pcm = b"".join(frames)
        logger.info(
            "Collected utterance uuid=%s duration=%.2fs silence_limit_frames=%s",
            self.call_uuid,
            len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
            silence_limit,
        )
        return pcm

    async def transcribe_pcm(
        self,
        pcm: bytes,
        turn: int,
        audio_path: Path | None = None,
        mode: str = "general",
        context: str = "",
    ) -> dict:
        path = audio_path or (SHARED_AUDIO_DIR / f"rt_rec_{self.call_uuid}_{turn}.wav")
        keep_audio = audio_path is not None
        _write_wav(path, pcm)
        duration_seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
        try:
            loop = asyncio.get_event_loop()
            start = time.monotonic()
            result = await loop.run_in_executor(None, self.stt.transcribe, str(path), mode, context)
            stt_latency = time.monotonic() - start
            logger.info(
                "Realtime turn %s: '%s' conf=%.2f stt=%.2fs",
                turn, result.get("text", ""), result.get("confidence", 0), stt_latency,
            )
            result["audio_path"] = str(path)
            result["audio_seconds"] = duration_seconds
            result["stt_latency_seconds"] = stt_latency
            result["mode"] = mode
            return result
        finally:
            if not keep_audio:
                try:
                    path.unlink()
                except OSError:
                    pass

    async def record_feedback_note(
        self,
        student_id: str | None,
        learning_state: dict | None,
        *,
        requested_by_caller: bool = False,
        hotkey: bool = False,
        mid_call: bool = False,
    ) -> str:
        """Ask for one optional, open-ended tester note. Returns the transcript.

        Returns the transcribed note text ("" when nothing was captured) so the
        mid-call feedback flow can react to what the caller said. The passive
        end-of-call callers ignore the return value.

        Flow:
          1. Play the long open-ended prompt.
          2. Play a short "go" beep so the caller knows recording is now live.
          3. Wait up to FEEDBACK_WAIT_SECONDS for them to start; allow DTMF
             skip via FEEDBACK_DTMF_SKIP_DIGIT.
          4. If the first window expires with no speech AND
             FEEDBACK_RETRY_ENABLED, play a short re-prompt + beep and try
             one more time.
          5. Always write a sidecar — even when no audio was captured — so an
             admin can see WHY the window closed (timeout vs dtmf_skipped vs
             channel_closed). This was previously a silent return that left
             the call ending mysteriously.
        """
        # The hotkey / a spoken feedback request is an explicit "I want to talk"
        # from the caller, so honor it even when the passive end-of-call offer
        # is restricted by mode.
        explicit = hotkey or requested_by_caller or mid_call
        if self.hungup or (not explicit and not _feedback_enabled_for_phone(self.phone)):
            return ""

        base_tags = ["open_voice_note"]
        if hotkey:
            base_tags.append("hotkey")
        if mid_call:
            base_tags.append("mid_call")

        # Clear old audio/keys before inviting feedback. Do not clear again
        # after the beep: that can erase the first words of the actual note.
        self.drain_audio()
        _drain_dtmf(self.dtmf_queue)
        # The hotkey press itself is now consumed; reset so a leftover latch
        # doesn't abort the recording windows below.
        self.feedback_hotkey_pressed = False

        prompt_played_at = time.monotonic()
        if hotkey:
            prompt_text = FEEDBACK_HOTKEY_PROMPT_TEXT
        elif requested_by_caller:
            prompt_text = FEEDBACK_REQUESTED_PROMPT_TEXT
        else:
            prompt_text = FEEDBACK_PROMPT_TEXT
        prompt_pcm = await self.synthesize_pcm(prompt_text, "rt_feedback_prompt")
        await self.play_pcm(prompt_pcm)
        if self.hungup:
            return ""
        prompt_played_seconds = round(time.monotonic() - prompt_played_at, 2)

        # Audible "you're live" cue right before opening the recording window.
        go_cue = _build_go_cue_pcm()
        if go_cue:
            await self.play_pcm(go_cue)
            if self.hungup:
                return ""

        max_frames = max(1, int(FEEDBACK_MAX_SECONDS * 1000 / FRAME_MS))
        skip_digit = FEEDBACK_DTMF_SKIP_DIGIT or None
        attempts: list[dict] = []

        first_metrics: dict = {}
        feedback_pcm = await self.wait_for_optional_utterance(
            FEEDBACK_WAIT_SECONDS,
            max_frames=max_frames,
            end_silence_frames=FEEDBACK_END_SILENCE_FRAMES,
            speech_threshold=FEEDBACK_SPEECH_RMS_THRESHOLD,
            dtmf_skip_digit=skip_digit,
            rms_telemetry=first_metrics,
        )
        attempts.append({"attempt": 1, "metrics": first_metrics})

        # Retry once if the first window expired with no speech (and they
        # didn't DTMF-skip out, and the channel is still up).
        if (
            not feedback_pcm
            and FEEDBACK_RETRY_ENABLED
            and not self.hungup
            and first_metrics.get("ended_reason") == "wait_timeout"
        ):
            try:
                retry_pcm = await self.synthesize_pcm(FEEDBACK_RETRY_PROMPT_TEXT, "rt_feedback_retry")
                await self.play_pcm(retry_pcm)
                if not self.hungup and go_cue:
                    await self.play_pcm(go_cue)
                if not self.hungup:
                    second_metrics: dict = {}
                    feedback_pcm = await self.wait_for_optional_utterance(
                        FEEDBACK_WAIT_SECONDS,
                        max_frames=max_frames,
                        end_silence_frames=FEEDBACK_END_SILENCE_FRAMES,
                        speech_threshold=FEEDBACK_SPEECH_RMS_THRESHOLD,
                        dtmf_skip_digit=skip_digit,
                        rms_telemetry=second_metrics,
                    )
                    attempts.append({"attempt": 2, "metrics": second_metrics})
            except Exception as exc:
                logger.warning("Feedback retry failed uuid=%s: %s", self.call_uuid, exc)

        final_metrics = attempts[-1]["metrics"] if attempts else {}
        ended_reason = final_metrics.get("ended_reason", "unknown")

        # ALWAYS write a sidecar — even with no audio — so the admin can see
        # whether the caller skipped, timed out, or got cut off by hangup.
        if not feedback_pcm:
            logger.info(
                "No optional feedback captured uuid=%s ended_reason=%s attempts=%d",
                self.call_uuid, ended_reason, len(attempts),
            )
            try:
                feedback_path = SHARED_AUDIO_DIR / f"feedback_{self.call_uuid}.json"
                feedback_path.write_text(
                    json.dumps(
                        {
                            "call_uuid": self.call_uuid,
                            "call_id": self.call_id,
                            "phone_number": self.phone,
                            "student_id": student_id,
                            "channel": "asterisk_audiosocket",
                            "participant_type": "tester",
                            "recording_path": "",
                            "transcript": "",
                            "duration_seconds": 0,
                            "tags": base_tags + [f"no_audio:{ended_reason}"],
                            "feedback_mode": FEEDBACK_MODE,
                            "mode": self.mode,
                            "attempt": self.attempt,
                            "learning_state": learning_state or {},
                            "prompt_played_seconds": prompt_played_seconds,
                            "ended_reason": ended_reason,
                            "wait_attempts": attempts,
                            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        },
                        ensure_ascii=True, indent=2, default=str,
                    )
                )
            except Exception as exc:
                logger.warning("Could not write empty feedback sidecar uuid=%s: %s", self.call_uuid, exc)
            return ""

        duration_seconds = int(len(feedback_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH))
        if duration_seconds <= 0:
            return ""

        feedback_path = SHARED_AUDIO_DIR / f"feedback_{self.call_uuid}.wav"
        _write_wav(feedback_path, feedback_pcm)

        transcript_text = ""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.stt.transcribe, str(feedback_path))
            transcript_text = (result.get("text") or "").strip()
        except Exception as exc:
            logger.warning("Feedback transcription failed uuid=%s: %s", self.call_uuid, exc)

        feedback_metadata = {
            "call_uuid": self.call_uuid,
            "call_id": self.call_id,
            "phone_number": self.phone,
            "student_id": student_id,
            "channel": "asterisk_audiosocket",
            "participant_type": "tester",
            "recording_path": str(feedback_path),
            "transcript": transcript_text,
            "duration_seconds": duration_seconds,
            "tags": list(base_tags),
            "feedback_mode": FEEDBACK_MODE,
            "mode": self.mode,
            "attempt": self.attempt,
            "learning_state": learning_state or {},
            "prompt_played_seconds": prompt_played_seconds,
            "ended_reason": ended_reason,
            "time_to_first_speech_ms": final_metrics.get("time_to_first_speech_ms"),
            "rms_telemetry": {
                "peak": final_metrics.get("peak_rms"),
                "mean": final_metrics.get("mean_rms"),
                "frames_observed": final_metrics.get("frames_observed"),
                "frames_above_threshold": final_metrics.get("frames_above_threshold"),
            },
            "wait_attempts": attempts,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            feedback_path.with_suffix(".json").write_text(
                json.dumps(feedback_metadata, ensure_ascii=True, indent=2, default=str)
            )
        except Exception as exc:
            logger.warning("Could not write feedback sidecar uuid=%s: %s", self.call_uuid, exc)

        await self.memory.save_call_feedback(
            student_id=student_id,
            phone_number=self.phone,
            call_id=self.call_id,
            channel="asterisk_audiosocket",
            participant_type="tester",
            recording_path=str(feedback_path),
            transcript=transcript_text,
            duration_seconds=duration_seconds,
            metadata={
                "mode": self.mode,
                "attempt": self.attempt,
                "feedback_mode": FEEDBACK_MODE,
                "learning_state": learning_state or {},
                "prompt_played_seconds": prompt_played_seconds,
                "ended_reason": ended_reason,
                "time_to_first_speech_ms": final_metrics.get("time_to_first_speech_ms"),
                "rms_telemetry": feedback_metadata["rms_telemetry"],
                "wait_attempts": attempts,
            },
            tags=list(base_tags),
            consent_recorded=True,
            assent_recorded=False,
        )
        self.feedback_captured = True
        return transcript_text

    async def handle_mid_call_feedback(
        self,
        student_id: str | None,
        learning_state: dict | None,
        messages: list[dict],
        *,
        module: int = 0,
        course: str = "numeracy",
        trigger: str = "hotkey",
    ) -> bool:
        """Run the mid-call feedback conversation. Returns True to resume.

        Flow (Naomi's design):
          1. Record + transcribe + save the caller's note.
          2. Warmly acknowledge what they said (LLM, guardrailed; caring
             fallback line on error) -- Sabi decides the words.
          3. Ask whether to keep learning or stop here.
          4. Return True to resume the lesson from where they left off, or
             False to stop the call.
        """
        hotkey = trigger == "hotkey"
        transcript_text = await self.record_feedback_note(
            student_id,
            learning_state,
            requested_by_caller=True,
            hotkey=hotkey,
            mid_call=True,
        )
        if self.hungup:
            return False

        # They opened the space but left no note -> reassure and resume.
        if not transcript_text:
            resume_pcm = await self.synthesize_pcm(FEEDBACK_EMPTY_NOTE_RESUME_TEXT, "rt_feedback_resume")
            await self.play_pcm_with_barge(resume_pcm)
            return not self.hungup

        # Acknowledge warmly. Reuse the LLM (guardrails + provider fallback) but
        # steer it hard away from teaching; fall back to a fixed caring line.
        ack_text = FEEDBACK_EMPATHY_FALLBACK_TEXT
        try:
            ack_messages = [
                *messages[-6:],
                {
                    "role": "system",
                    "content": (
                        'The child just used the feedback space and said: "'
                        + transcript_text
                        + '". This is NOT a lesson answer. Reply as Sabi, their kind tutor, in '
                        "ONE short spoken sentence: warmly acknowledge how they feel and thank "
                        "them for telling you. Do NOT teach, do NOT ask a lesson question, do "
                        "NOT give advice. Then stop."
                    ),
                },
            ]
            generated = await self.llm.generate(
                messages=ack_messages,
                student_id=student_id,
                current_module=module,
                memory=self.memory,
                course=course,
                learning_state=learning_state or {},
                call_id=self.call_id,
                channel="asterisk_audiosocket",
            )
            generated = (generated or "").strip()
            if generated:
                ack_text = generated
        except Exception as exc:
            logger.warning("Mid-call feedback empathy generation failed uuid=%s: %s", self.call_uuid, exc)

        # One combined utterance: acknowledgement + deterministic continue/stop.
        combined = f"{ack_text} {FEEDBACK_CONTINUE_QUESTION_TEXT}"
        messages.append({"role": "assistant", "content": combined})
        combined_pcm = await self.synthesize_pcm(combined, "rt_feedback_ack")
        await self.play_pcm_with_barge(combined_pcm)
        if self.hungup:
            return False

        # Listen for their yes/no.
        answer_pcm = await self.wait_for_utterance()
        if self.hungup or not answer_pcm:
            return False
        answer = ""
        try:
            result = await self.transcribe_pcm(answer_pcm, 999)
            answer = (result.get("text") or "").strip()
        except Exception as exc:
            logger.warning("Mid-call feedback resume transcription failed uuid=%s: %s", self.call_uuid, exc)
        messages.append({"role": "user", "content": answer})
        wants_continue = _wants_to_continue_lesson(answer)
        logger.info(
            "Mid-call feedback resume decision uuid=%s answer=%r continue=%s",
            self.call_uuid, answer, wants_continue,
        )
        if not wants_continue:
            bye_pcm = await self.synthesize_pcm(
                "Okay. Thank you for talking with me today. Bye for now.", "rt_feedback_bye"
            )
            await self.play_pcm(bye_pcm)
        return wants_continue

    def persist_turn_review(
        self,
        *,
        turn: int,
        user_audio_path: Path | None,
        transcript: dict,
        raw_text: str,
        normalized_text: str,
        learning_state_before: dict | None,
        learning_state_after: dict | None,
        assistant_text: str = "",
        assistant_pcm: bytes = b"",
        timings: dict | None = None,
        flags: list[str] | None = None,
    ) -> None:
        """Write one admin review row for an accepted, retried, or ignored turn."""
        assistant_audio_path = call_turn_audio_path(self.call_uuid, turn, "assistant", SHARED_AUDIO_DIR)
        assistant_seconds = 0.0
        if assistant_pcm and assistant_audio_path:
            _write_wav(assistant_audio_path, assistant_pcm)
            assistant_seconds = len(assistant_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
        try:
            append_call_turn_review(
                call_uuid=self.call_uuid,
                turn_index=turn,
                user_audio_path=str(user_audio_path) if user_audio_path else "",
                user_audio_seconds=float(transcript.get("audio_seconds") or 0),
                stt_transcript=raw_text,
                stt_confidence=float(transcript.get("confidence") or 0),
                normalized_transcript=normalized_text,
                learning_state_before=learning_state_before or {},
                learning_state_after=learning_state_after or learning_state_before or {},
                assistant_text=assistant_text,
                assistant_tts_text=clean_text_for_tts(assistant_text) if assistant_text else "",
                assistant_audio_path=str(assistant_audio_path) if assistant_audio_path and assistant_pcm else "",
                assistant_audio_seconds=assistant_seconds,
                timings=timings or {},
                flags=flags or [],
                directory=SHARED_AUDIO_DIR,
                stt_provider=str(transcript.get("provider") or ""),
                stt_prompt=str(transcript.get("gemini_prompt") or ""),
                stt_prompt_mode=str(transcript.get("gemini_prompt_mode") or ""),
                stt_prompt_label=str(transcript.get("gemini_prompt_label") or ""),
                stt_details={
                    key: transcript.get(key)
                    for key in (
                        "consensus",
                        "consensus_key",
                        "consensus_numeric_value",
                        "selection_reason",
                        "ensemble_results",
                        "ensemble_latency_seconds",
                        "provider_error",
                    )
                    if transcript.get(key) is not None
                },
                tts_provider=self.last_tts_provider if assistant_text else "",
            )
        except Exception as exc:
            logger.warning("Could not append turn review uuid=%s turn=%s: %s", self.call_uuid, turn, exc)

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

    async def run_original_sabi(self) -> None:
        """Run the original hackathon prompt with Gemini STT and no state engine.

        This intentionally bypasses learner lookup, deterministic grading,
        diagnostics, scaffold depth, curriculum-path injection, answer gating,
        transcript normalization, keypad teaching, and session-state writes.
        Audio transport, call review, safety guards, and TTS remain available
        so the comparison can run safely on the same phone infrastructure.
        """
        call_started_at = time.monotonic()
        logger.info(
            "Original Sabi call start uuid=%s phone=%s mode=%s attempt=%s",
            self.call_uuid,
            self.phone,
            self.mode,
            self.attempt,
        )
        reader_task = asyncio.create_task(self.read_loop())
        messages: list[dict[str, str]] = [
            {"role": "assistant", "content": ORIGINAL_SABI_FIRST_MESSAGE}
        ]
        system_prompt = original_sabi_prompt_for_phone(self.phone)

        try:
            greeting_pcm = await self.synthesize_pcm(
                ORIGINAL_SABI_FIRST_MESSAGE,
                "rt_original_greeting",
            )
            interrupted = await self.play_pcm_with_barge(
                greeting_pcm,
                speech_threshold=SPEECH_RMS_THRESHOLD,
                end_silence_frames=END_SILENCE_FRAMES,
                barge_grace_ms=INITIAL_GREETING_BARGE_GRACE_MS,
            )
            if self.hungup:
                self.set_end_reason("channel_closed_during_greeting")
                return

            for turn in range(MAX_TURNS):
                if self.hungup:
                    break
                if time.monotonic() - call_started_at >= MAX_CALL_SECONDS:
                    self.set_end_reason("max_call_seconds")
                    break

                utterance_from_barge = interrupted is not None
                utterance = interrupted or await self.wait_for_utterance(
                    end_silence_frames=END_SILENCE_FRAMES,
                    speech_threshold=SPEECH_RMS_THRESHOLD,
                )
                interrupted = None
                if not utterance:
                    self.set_end_reason(
                        "channel_closed_waiting_for_speech" if self.hungup else "no_utterance"
                    )
                    break

                turn_start = time.monotonic()
                user_audio_path = call_turn_audio_path(
                    self.call_uuid,
                    turn,
                    "user",
                    SHARED_AUDIO_DIR,
                )
                stt_context = _recent_assistant_stt_context(
                    messages,
                    {"course": "numeracy", "active_skill": "market numeracy"},
                )
                transcript = await self.transcribe_pcm(
                    utterance,
                    turn,
                    user_audio_path,
                    mode="general",
                    context=stt_context,
                )
                raw_text = str(transcript.get("text") or "").strip()
                turn_flags = ["original_sabi_lane", "no_deterministic_learning_state"]
                if utterance_from_barge:
                    turn_flags.append("barge_in")

                if _looks_like_carrier_audio(raw_text):
                    turn_flags.append("carrier_or_voicemail_audio")
                    self.persist_turn_review(
                        turn=turn,
                        user_audio_path=user_audio_path,
                        transcript=transcript,
                        raw_text=raw_text,
                        normalized_text=raw_text,
                        learning_state_before={},
                        learning_state_after={},
                        flags=turn_flags,
                        timings={
                            "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                            "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                        },
                    )
                    self.set_end_reason("carrier_or_voicemail_audio")
                    break

                if raw_text:
                    learner_text = raw_text
                else:
                    learner_text = "[The phone audio was unclear.]"
                    turn_flags.append("unclear_audio_passed_to_original_llm")
                messages.append({"role": "user", "content": learner_text})

                llm_start = time.monotonic()
                response = await self.llm.generate_with_system_prompt(
                    system_prompt=system_prompt,
                    messages=messages,
                    call_id=self.call_id,
                    channel="asterisk_audiosocket_original_sabi",
                )
                llm_latency = time.monotonic() - llm_start
                messages.append({"role": "assistant", "content": response})

                tts_start = time.monotonic()
                response_pcm = await self.synthesize_pcm(response, "rt_original_resp")
                tts_latency = time.monotonic() - tts_start
                self.persist_turn_review(
                    turn=turn,
                    user_audio_path=user_audio_path,
                    transcript=transcript,
                    raw_text=raw_text,
                    normalized_text=raw_text,
                    learning_state_before={},
                    learning_state_after={},
                    assistant_text=response,
                    assistant_pcm=response_pcm,
                    flags=turn_flags,
                    timings={
                        "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                        "llm_seconds": round(llm_latency, 3),
                        "tts_seconds": round(tts_latency, 3),
                        "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                    },
                )
                logger.info(
                    "Original Sabi turn=%s transcript=%r llm=%.2fs response=%r",
                    turn,
                    raw_text,
                    llm_latency,
                    response,
                )
                interrupted = await self.play_pcm_with_barge(
                    response_pcm,
                    speech_threshold=SPEECH_RMS_THRESHOLD,
                    end_silence_frames=END_SILENCE_FRAMES,
                )
                if should_wrap_up(
                    messages,
                    response,
                    elapsed_seconds=time.monotonic() - call_started_at,
                ):
                    self.set_end_reason("original_sabi_wrap_up")
                    break
        except Exception as exc:
            self.set_end_reason(f"exception:{type(exc).__name__}")
            logger.error(
                "Original Sabi call error uuid=%s: %s",
                self.call_uuid,
                exc,
                exc_info=True,
            )
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
            user_turns = sum(1 for message in messages if message.get("role") == "user")
            assistant_turns = sum(1 for message in messages if message.get("role") == "assistant")
            write_call_review_record(
                call_uuid=self.call_uuid,
                call_id=self.call_id,
                phone_number=self.phone,
                mode=self.mode,
                attempt=self.attempt,
                student_id=None,
                end_reason=self.end_reason,
                duration_seconds=duration_seconds,
                user_turns=user_turns,
                assistant_turns=assistant_turns,
                hangup_event=HANGUP_EVENTS.get(self.call_uuid),
                directory=SHARED_AUDIO_DIR,
            )
            logger.warning(
                "Original Sabi call complete uuid=%s phone=%s end_reason=%s duration=%ss turns=%s",
                self.call_uuid,
                self.phone,
                self.end_reason,
                duration_seconds,
                user_turns,
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
        keypad_option_announced = False
        student_id: Optional[str] = None
        effective_state: dict | None = None
        starting_learning_state: dict | None = None

        try:
            student = await self.memory.find_or_create_student(self.phone)
            student_id = student["id"]
            effective_state = await self.memory.get_effective_learning_state(student)
            if phone_is_numeracy_only(self.phone):
                previous_course = str(effective_state.get("course") or "numeracy")
                effective_state = _course_state_for_phone(self.phone, effective_state)
                logger.info(
                    "Phone-scoped numeracy-only route uuid=%s phone=%s previous_course=%s",
                    self.call_uuid,
                    self.phone,
                    previous_course,
                )
            starting_learning_state = dict(effective_state)
            identity_confirmed = not student.get("needs_identity_confirmation")
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
                greeting_to_speak = greeting
                if FEEDBACK_HOTKEY_DIGIT and FEEDBACK_HOTKEY_ANNOUNCE_TEXT:
                    greeting_to_speak = f"{greeting} {FEEDBACK_HOTKEY_ANNOUNCE_TEXT}"
                greeting_pcm = await self.synthesize_pcm(greeting_to_speak, "rt_greeting")
            interrupted = await self.play_pcm_with_barge(
                greeting_pcm,
                speech_threshold=_speech_threshold_for_state(effective_state),
                end_silence_frames=_end_silence_frames_for_state(effective_state),
                barge_grace_ms=INITIAL_GREETING_BARGE_GRACE_MS,
            )
            if self.hungup:
                self.set_end_reason("channel_closed_during_greeting")
                return

            for turn in range(MAX_TURNS):
                if self.feedback_hotkey_pressed:
                    self.feedback_hotkey_pressed = False
                    logger.info("Feedback hotkey -> opening mid-call feedback uuid=%s", self.call_uuid)
                    keep_going = await self.handle_mid_call_feedback(
                        student_id, effective_state, messages,
                        module=module, course=str((effective_state or {}).get("course") or "numeracy"),
                        trigger="hotkey",
                    )
                    if not keep_going:
                        self.set_end_reason("feedback_then_stopped")
                        break
                    continue
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

                numeric_stt_context = _current_question_expects_numeric(messages)
                stt_mode = _stt_mode_for_turn(effective_state, messages)
                stt_context = _recent_assistant_stt_context(messages, effective_state)
                speech_threshold = _speech_threshold_for_state(effective_state)
                end_silence_frames = _end_silence_frames_for_state(effective_state)
                utterance_from_barge = interrupted is not None
                keypad_text: str | None = None
                if interrupted is not None:
                    utterance = interrupted
                elif numeric_stt_context and KEYPAD_NUMERIC_FALLBACK_ENABLED:
                    utterance, keypad_text = await self.wait_for_numeric_or_utterance(
                        end_silence_frames=end_silence_frames,
                        speech_threshold=speech_threshold,
                    )
                else:
                    utterance = await self.wait_for_utterance(
                        end_silence_frames=end_silence_frames,
                        speech_threshold=speech_threshold,
                    )
                interrupted = None
                if self.feedback_hotkey_pressed:
                    self.feedback_hotkey_pressed = False
                    logger.info("Feedback hotkey (while listening) -> opening mid-call feedback uuid=%s", self.call_uuid)
                    keep_going = await self.handle_mid_call_feedback(
                        student_id, effective_state, messages,
                        module=module, course=str((effective_state or {}).get("course") or "numeracy"),
                        trigger="hotkey",
                    )
                    if not keep_going:
                        self.set_end_reason("feedback_then_stopped")
                        break
                    continue
                if not utterance and not keypad_text:
                    if self.hungup:
                        self.set_end_reason("channel_closed_waiting_for_speech")
                    else:
                        self.set_end_reason("no_utterance")
                    break

                turn_start = time.monotonic()
                user_audio_path = None
                if keypad_text:
                    transcript = {
                        "text": keypad_text,
                        "confidence": 1.0,
                        "language": "dtmf",
                        "duration_seconds": 0.0,
                        "stt_latency_seconds": 0.0,
                        "provider": "dtmf",
                        "keypad_answer": keypad_text,
                    }
                else:
                    user_audio_path = call_turn_audio_path(self.call_uuid, turn, "user", SHARED_AUDIO_DIR)
                    transcript = await self.transcribe_pcm(
                        utterance,
                        turn,
                        user_audio_path,
                        mode=stt_mode,
                        context=stt_context,
                    )
                text = transcript.get("text", "").strip()
                raw_stt_text = text
                confidence = float(transcript.get("confidence", 0))
                turn_flags: list[str] = []
                if stt_mode == "literacy":
                    turn_flags.append("literacy_stt")
                elif numeric_stt_context:
                    turn_flags.append("numeric_stt")
                if keypad_text:
                    turn_flags.extend(["keypad_numeric_answer", "dtmf_answer"])
                if utterance_from_barge:
                    turn_flags.append("barge_in")
                learning_state_before_turn = dict(effective_state or {})
                normalized_text = text.lower().strip(" .,!?:;")
                if _looks_like_carrier_audio(text):
                    logger.warning(
                        "Realtime turn %s: carrier/voicemail audio detected; ending callback. text=%r attempt=%s",
                        turn,
                        text,
                        self.attempt,
                    )
                    self.persist_turn_review(
                        turn=turn,
                        user_audio_path=user_audio_path,
                        transcript=transcript,
                        raw_text=raw_stt_text,
                        normalized_text=text,
                        learning_state_before=learning_state_before_turn,
                        learning_state_after=learning_state_before_turn,
                        flags=[*turn_flags, "carrier_or_voicemail_audio"],
                        timings={
                            "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                            "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                        },
                    )
                    await self.request_callback_retry(text)
                    self.set_end_reason("carrier_or_voicemail_audio")
                    break
                if normalized_text in FILLER_WORDS:
                    logger.info("Realtime turn %s: ignoring filler '%s'", turn, text)
                    self.persist_turn_review(
                        turn=turn,
                        user_audio_path=user_audio_path,
                        transcript=transcript,
                        raw_text=raw_stt_text,
                        normalized_text=text,
                        learning_state_before=learning_state_before_turn,
                        learning_state_after=learning_state_before_turn,
                        flags=[*turn_flags, "ignored_filler"],
                        timings={
                            "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                            "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                        },
                    )
                    continue
                if not text or _looks_like_stt_hallucination(text):
                    if _looks_like_stt_hallucination(text):
                        logger.info("Realtime turn %s: ignoring STT hallucination %r", turn, text)
                    if retry_streak >= MAX_UNCLEAR_RETRIES:
                        keypad_text = None
                        if numeric_stt_context:
                            keypad_text = await self.prompt_for_keypad_numeric_answer(
                                turn=turn,
                                user_audio_path=user_audio_path,
                                transcript=transcript,
                                raw_text=raw_stt_text,
                                normalized_text=text,
                                learning_state_before=learning_state_before_turn,
                                turn_flags=turn_flags,
                                turn_start=turn_start,
                            )
                        if keypad_text:
                            text = keypad_text
                            confidence = 1.0
                            transcript["confidence"] = 1.0
                            transcript["keypad_answer"] = keypad_text
                            turn_flags.extend(["keypad_numeric_fallback", "dtmf_answer"])
                        else:
                            text = "I answered, but the phone transcript was unclear."
                    else:
                        retry_text = _retry_text_for_unclear_audio(retry_streak)
                        retry_streak += 1
                        retry_pcm = await self.synthesize_pcm(retry_text, "rt_retry")
                        self.persist_turn_review(
                            turn=turn,
                            user_audio_path=user_audio_path,
                            transcript=transcript,
                            raw_text=raw_stt_text,
                            normalized_text=text,
                            learning_state_before=learning_state_before_turn,
                            learning_state_after=learning_state_before_turn,
                            assistant_text=retry_text,
                            assistant_pcm=retry_pcm,
                            flags=[*turn_flags, "retry_prompt", "empty_or_hallucinated_transcript"],
                            timings={
                                "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                                "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                            },
                        )
                        logger.info("Realtime turn %s retry pipeline=%.2fs", turn, time.monotonic() - turn_start)
                        interrupted = await self.play_pcm_with_barge(
                            retry_pcm,
                            speech_threshold=speech_threshold,
                            end_silence_frames=end_silence_frames,
                        )
                        continue
                if _looks_like_feedback_request(text):
                    logger.info(
                        "Realtime turn %s: caller requested feedback note uuid=%s text=%r",
                        turn,
                        self.call_uuid,
                        text,
                    )
                    messages.append({"role": "user", "content": text})
                    self.persist_turn_review(
                        turn=turn,
                        user_audio_path=user_audio_path,
                        transcript=transcript,
                        raw_text=raw_stt_text,
                        normalized_text=text,
                        learning_state_before=learning_state_before_turn,
                        learning_state_after=learning_state_before_turn,
                        flags=[*turn_flags, "feedback_requested"],
                        timings={
                            "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                            "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                        },
                    )
                    keep_going = await self.handle_mid_call_feedback(
                        student_id, effective_state, messages,
                        module=module, course=str((effective_state or {}).get("course") or "numeracy"),
                        trigger="spoken",
                    )
                    if not keep_going:
                        self.set_end_reason("feedback_then_stopped")
                        break
                    continue
                literacy_answer = _looks_like_literacy_answer(text, effective_state)
                if confidence < CONFIDENCE_THRESHOLD and not _looks_like_numeric_answer(text) and not literacy_answer:
                    if confidence >= MIN_USABLE_CONFIDENCE and len(normalized_text) >= 3:
                        logger.info(
                            "Realtime turn %s: accepting usable low-confidence transcript %r conf=%.2f",
                            turn,
                            text,
                            confidence,
                        )
                        turn_flags.append("usable_low_confidence")
                    elif retry_streak >= MAX_UNCLEAR_RETRIES:
                        logger.info(
                            "Realtime turn %s: passing unclear transcript after retry %r conf=%.2f",
                            turn,
                            text,
                            confidence,
                        )
                        if numeric_stt_context:
                            keypad_text = await self.prompt_for_keypad_numeric_answer(
                                turn=turn,
                                user_audio_path=user_audio_path,
                                transcript=transcript,
                                raw_text=raw_stt_text,
                                normalized_text=text,
                                learning_state_before=learning_state_before_turn,
                                turn_flags=turn_flags,
                                turn_start=turn_start,
                            )
                            if keypad_text:
                                text = keypad_text
                                confidence = 1.0
                                transcript["confidence"] = 1.0
                                transcript["keypad_answer"] = keypad_text
                                turn_flags.extend(["keypad_numeric_fallback", "dtmf_answer"])
                    else:
                        retry_text = _retry_text_for_unclear_audio(retry_streak)
                        retry_streak += 1
                        retry_pcm = await self.synthesize_pcm(retry_text, "rt_retry")
                        self.persist_turn_review(
                            turn=turn,
                            user_audio_path=user_audio_path,
                            transcript=transcript,
                            raw_text=raw_stt_text,
                            normalized_text=text,
                            learning_state_before=learning_state_before_turn,
                            learning_state_after=learning_state_before_turn,
                            assistant_text=retry_text,
                            assistant_pcm=retry_pcm,
                            flags=[*turn_flags, "retry_prompt", "low_confidence_rejected"],
                            timings={
                                "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                                "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                            },
                        )
                        logger.info("Realtime turn %s retry pipeline=%.2fs", turn, time.monotonic() - turn_start)
                        interrupted = await self.play_pcm_with_barge(
                            retry_pcm,
                            speech_threshold=speech_threshold,
                            end_silence_frames=end_silence_frames,
                        )
                        continue
                else:
                    retry_streak = 0
                    if literacy_answer and confidence < CONFIDENCE_THRESHOLD:
                        logger.info(
                            "Realtime turn %s: accepting short literacy answer %r conf=%.2f",
                            turn,
                            text,
                            confidence,
                        )
                        turn_flags.append("literacy_short_answer")
                if confidence < CONFIDENCE_THRESHOLD:
                    logger.info(
                        "Realtime turn %s: accepting low-confidence answer %r conf=%.2f",
                        turn,
                        text,
                        confidence,
                    )
                    turn_flags.append("low_confidence")

                retry_streak = 0
                asked_for_name = _current_question_asks_for_name(messages)
                latest_question = _latest_assistant_turn(messages)
                assessment_start = time.monotonic()
                if keypad_text:
                    turn_is_answer = True
                    assessed_name = None
                    assessment_output = "keypad"
                else:
                    assessment = await self.llm.assess_turn(
                        latest_question=latest_question,
                        transcript=text,
                        asked_for_name=asked_for_name,
                    )
                    turn_is_answer = assessment.is_answer
                    assessed_name = assessment.name
                    assessment_output = assessment.model_output
                assessment_latency = time.monotonic() - assessment_start
                turn_flags.append("llm_turn_assessed")
                turn_flags.append("answer" if turn_is_answer else "not_answer")
                if not assessment_output:
                    turn_flags.append("turn_assessment_failed_closed")

                if asked_for_name and turn_is_answer and assessed_name:
                    text_for_lesson = f"My name is {assessed_name}"
                    turn_flags.append("name_validated_by_llm")
                elif asked_for_name and not turn_is_answer:
                    # Preserve the raw STT in the call-review record, but keep
                    # non-name speech out of deterministic name extraction.
                    text_for_lesson = "[The caller did not answer the name question.]"
                else:
                    text_for_lesson = _normalize_transcript_for_lesson(text, messages)
                if text_for_lesson != text:
                    turn_flags.append("transcript_normalized")
                messages.append({"role": "user", "content": text_for_lesson})
                if turn_is_answer and not identity_confirmed:
                    resolved_student = await self.memory.resolve_student_for_spoken_identity(
                        student,
                        self.phone,
                        messages,
                    )
                    if resolved_student:
                        old_student_id = student_id
                        student = resolved_student
                        student_id = resolved_student.get("id") or student_id
                        effective_state = await self.memory.get_effective_learning_state(student)
                        effective_state = _course_state_for_phone(self.phone, effective_state)
                        starting_learning_state = dict(effective_state)
                        module = int(effective_state.get("current_module") or student.get("current_module") or module or 0)
                        identity_confirmed = True
                        logger.info(
                            "Realtime resolved shared-phone identity old_student=%s new_student=%s child=%s module=%s",
                            old_student_id,
                            student_id,
                            resolved_student.get("spoken_child_name") or resolved_student.get("name"),
                            module,
                        )
                if turn_is_answer:
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
                else:
                    turn_flags.append("not_graded")
                user_turns = sum(1 for message in messages if message["role"] == "user")
                elapsed_seconds = time.monotonic() - call_started_at
                llm_messages = [
                    *messages,
                    *build_call_control_messages(user_turns, elapsed_seconds, MAX_CALL_SECONDS),
                ]
                if not turn_is_answer:
                    llm_messages.append(
                        {
                            "role": "system",
                            "content": (
                                "The latest caller turn is not a direct answer to your current question. "
                                "Do not grade it, lower the learner's level, increase scaffolding, or advance "
                                "the lesson as though it were wrong. Respond naturally to what they said. "
                                "If they could not hear or asked for repetition, repeat the current question "
                                "clearly. If the current question asks for the learner's name and this is not "
                                "a plausible name, ask them to say their name again; if it is a complaint, "
                                "address it briefly and then repeat the name question. "
                                f"Exact caller transcript: {text!r}."
                            ),
                        }
                    )

                llm_start = time.monotonic()
                latest_numeric_check = analyze_latest_numeric_turn(messages) if turn_is_answer else None
                numeric_ambiguous = (
                    latest_numeric_check is not None
                    and latest_numeric_check.expected is not None
                    and bool(latest_numeric_check.child_numbers)
                    and latest_numeric_check.is_correct is None
                )
                verified_numeric_control = (
                    verified_numeric_control_message(latest_numeric_check)
                    if latest_numeric_check is not None
                    else ""
                )
                if verified_numeric_control:
                    llm_messages.append({"role": "system", "content": verified_numeric_control})
                    turn_flags.append("deterministic_numeric_correct")
                if numeric_ambiguous:
                    response = NUMERIC_AMBIGUITY_CONFIRMATION_TEXT
                    turn_flags.append("numeric_ambiguous_confirmation")
                else:
                    response = await self.llm.generate(
                        messages=llm_messages,
                        student_id=student_id,
                        current_module=module,
                        memory=self.memory,
                        course=str(effective_state.get("course") or "numeracy"),
                        learning_state=effective_state,
                        call_id=self.call_id,
                        channel="asterisk_audiosocket",
                    )
                if (
                    not numeric_ambiguous
                    and is_premature_wrap_response(response, user_turns, elapsed_seconds, MAX_CALL_SECONDS)
                ):
                    logger.warning(
                        "Realtime turn %s produced premature wrap at %.0fs/%s turns; regenerating",
                        turn,
                        elapsed_seconds,
                        user_turns,
                    )
                    repair_messages = [
                        *llm_messages,
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
                        learning_state=effective_state,
                        call_id=self.call_id,
                        channel="asterisk_audiosocket",
                    )
                if (
                    verified_numeric_control
                    and latest_numeric_check is not None
                    and not response_accepts_verified_number(response)
                ):
                    logger.warning(
                        "Realtime turn %s failed to accept verified numeric answer=%s; repairing",
                        turn,
                        latest_numeric_check.expected,
                    )
                    numeric_repair_messages = [
                        *llm_messages,
                        {
                            "role": "system",
                            "content": (
                                "Your previous draft failed the verified numeric-answer rule. "
                                f"Rewrite it now. The learner's answer {latest_numeric_check.expected} "
                                "is correct regardless of the object noun in the transcript. The first "
                                "sentence must explicitly say it is correct. Then ask a genuinely new "
                                "question; do not recount or repeat the solved problem."
                            ),
                        },
                    ]
                    response = await self.llm.generate(
                        messages=numeric_repair_messages,
                        student_id=student_id,
                        current_module=module,
                        memory=self.memory,
                        course=str(effective_state.get("course") or "numeracy"),
                        learning_state=effective_state,
                        call_id=self.call_id,
                        channel="asterisk_audiosocket_numeric_repair",
                    )
                    turn_flags.append("numeric_correct_response_repaired")
                    if not response_accepts_verified_number(response):
                        expected = latest_numeric_check.expected
                        response = (
                            f"Yes, {expected} is correct! Well done. "
                            f"Now, what is {expected} plus one?"
                        )
                        turn_flags.append("numeric_correct_response_forced")
                logger.info("Realtime turn %s llm=%.2fs response=%s", turn, time.monotonic() - llm_start, response)
                llm_latency = time.monotonic() - llm_start
                if (
                    KEYPAD_NUMERIC_FALLBACK_ENABLED
                    and not keypad_option_announced
                    and KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT
                    and question_expects_numeric_answer(response)
                ):
                    response = f"{response} {KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT}"
                    keypad_option_announced = True
                messages.append({"role": "assistant", "content": response})

                tts_start = time.monotonic()
                response_pcm = await self.synthesize_pcm(response, "rt_resp")
                tts_latency = time.monotonic() - tts_start
                self.persist_turn_review(
                    turn=turn,
                    user_audio_path=user_audio_path,
                    transcript=transcript,
                    raw_text=raw_stt_text,
                    normalized_text=text_for_lesson,
                    learning_state_before=learning_state_before_turn,
                    learning_state_after=dict(effective_state or {}),
                    assistant_text=response,
                    assistant_pcm=response_pcm,
                    timings={
                        "stt_seconds": round(float(transcript.get("stt_latency_seconds") or 0), 3),
                        "turn_assessment_seconds": round(assessment_latency, 3),
                        "llm_seconds": round(llm_latency, 3),
                        "tts_seconds": round(tts_latency, 3),
                        "turn_total_seconds": round(time.monotonic() - turn_start, 3),
                    },
                    flags=turn_flags,
                )
                logger.info("Realtime turn %s response pipeline=%.2fs", turn, time.monotonic() - turn_start)
                interrupted = await self.play_pcm_with_barge(
                    response_pcm,
                    speech_threshold=_speech_threshold_for_state(effective_state),
                    end_silence_frames=_end_silence_frames_for_state(effective_state),
                )
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
            if not self.feedback_captured and _should_offer_feedback(student_id, messages, self.hungup, self.end_reason):
                try:
                    await self.record_feedback_note(
                        student_id,
                        effective_state,
                        requested_by_caller=self.end_reason in ("feedback_requested", "feedback_hotkey"),
                        hotkey=self.end_reason == "feedback_hotkey",
                    )
                except Exception as exc:
                    logger.warning("Optional feedback capture failed uuid=%s: %s", self.call_uuid, exc)
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
            learning_result = None
            if student_id and messages:
                learning_result = await self.memory.save_phone_session(
                    student_id=student_id,
                    phone_number=self.phone,
                    call_id=self.call_id,
                    messages=messages,
                    duration_seconds=duration_seconds,
                    channel="asterisk_audiosocket",
                    starting_learning_state=starting_learning_state,
                )
            user_turns = sum(1 for message in messages if message.get("role") == "user")
            assistant_turns = sum(1 for message in messages if message.get("role") == "assistant")
            write_call_review_record(
                call_uuid=self.call_uuid,
                call_id=self.call_id,
                phone_number=self.phone,
                mode=self.mode,
                attempt=self.attempt,
                student_id=student_id,
                end_reason=self.end_reason,
                duration_seconds=duration_seconds,
                user_turns=user_turns,
                assistant_turns=assistant_turns,
                hangup_event=HANGUP_EVENTS.get(self.call_uuid),
                directory=SHARED_AUDIO_DIR,
            )
            if learning_result:
                try:
                    write_call_learning_summary(
                        self.call_uuid,
                        learning_result.get("scorecard"),
                        learning_result.get("teacher_note"),
                        directory=SHARED_AUDIO_DIR,
                    )
                except Exception as exc:
                    logger.warning("Could not write learning summary uuid=%s: %s", self.call_uuid, exc)
            self.memory.clear_call(self.call_id)
            logger.warning(
                "Realtime call complete uuid=%s phone=%s mode=%s attempt=%s end_reason=%s duration=%ss user_turns=%s assistant_turns=%s",
                self.call_uuid,
                self.phone,
                self.mode,
                self.attempt,
                self.end_reason,
                duration_seconds,
                user_turns,
                assistant_turns,
            )


async def handle_audiosocket_call(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                  stt, llm, tts, memory, tts_primary: str = "",
                                  conversation_style: str = "current",
                                  barge_in_enabled: bool | None = None) -> None:
    peer_info = writer.get_extra_info("peername")
    try:
        packet_type, payload = await _read_packet(reader)
        if packet_type != AUDIO_TYPE_UUID or len(payload) != 16:
            logger.warning("AudioSocket %s sent invalid first packet type=%s len=%s", peer_info, packet_type, len(payload))
            writer.close()
            return
        call_uuid = str(uuid.UUID(bytes=payload))
        call = RealtimeCall(
            call_uuid,
            reader,
            writer,
            stt,
            llm,
            tts,
            memory,
            tts_primary=tts_primary,
            conversation_style=conversation_style,
            barge_in_enabled=barge_in_enabled,
        )
        if call.conversation_style == "original":
            await call.run_original_sabi()
        else:
            await call.run()
    except Exception as exc:
        logger.error("AudioSocket connection error from %s: %s", peer_info, exc, exc_info=True)
        writer.close()


async def start_audiosocket_server(stt, llm, tts, memory, host: str = "0.0.0.0", port: int = 9019,
                                   tts_primary: str = "", conversation_style: str = "current",
                                   barge_in_enabled: bool | None = None):
    async def client_handler(reader, writer):
        await handle_audiosocket_call(
            reader,
            writer,
            stt,
            llm,
            tts,
            memory,
            tts_primary=tts_primary,
            conversation_style=conversation_style,
            barge_in_enabled=barge_in_enabled,
        )

    server = await asyncio.start_server(client_handler, host, port)
    logger.info(
        "AudioSocket realtime server listening on %s:%s tts_primary=%s conversation_style=%s barge_in_enabled=%s",
        host,
        port,
        tts_primary or "(global)",
        conversation_style,
        BARGE_IN_ENABLED if barge_in_enabled is None else bool(barge_in_enabled),
    )
    return server
