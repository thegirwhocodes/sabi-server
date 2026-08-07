#!/usr/bin/env python3
"""Regression checks for Sabi phone runtime UX configuration.

Run this inside the deployed container after env/config changes. It catches
deployment drift that normal unit tests miss, like a live .env shortening the
open feedback note window below the product spec.
"""

from __future__ import annotations

import asyncio
import sys
import struct
import types
import os
import inspect
from pathlib import Path

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    # Local lightweight runs may not have container dependencies installed.
    # The constants we verify are loaded at import time and do not need httpx.
    sys.modules["httpx"] = types.SimpleNamespace()

os.environ.setdefault("SABI_SHARED_AUDIO_DIR", str(Path(os.getenv("TMPDIR", "/tmp")) / "sabi-phone-runtime-config"))

import voice_asterisk
import voice_realtime


def check(name: str, ok: bool, detail: object) -> bool:
    if ok:
        print(f"PASS {name} - {detail}")
        return True
    print(f"FAIL {name} - {detail}")
    return False


async def natural_pause_survives_endpointing() -> tuple[bool, dict]:
    """Prove a normal 200 ms pause does not split one spoken response."""
    call = voice_realtime.RealtimeCall(
        "natural-pause-regression",
        None,
        None,
        None,
        None,
        None,
        None,
    )
    first_speech = struct.pack(
        "<" + "h" * (voice_realtime.FRAME_BYTES // 2),
        *([1200] * (voice_realtime.FRAME_BYTES // 2)),
    )
    second_speech = struct.pack(
        "<" + "h" * (voice_realtime.FRAME_BYTES // 2),
        *([2400] * (voice_realtime.FRAME_BYTES // 2)),
    )
    silence = bytes(voice_realtime.FRAME_BYTES)

    # Ten 20 ms quiet frames model the brief pause in the August 6 call.
    # A 160 ms endpoint stops before second_speech; the 360 ms endpoint keeps it.
    queued_frames = (
        [first_speech] * 3
        + [silence] * 10
        + [second_speech] * 3
        + [silence] * voice_realtime.END_SILENCE_FRAMES
    )
    for frame in queued_frames:
        call.audio_queue.put_nowait(frame)

    captured = await call.collect_utterance(
        [first_speech],
        end_silence_frames=voice_realtime.END_SILENCE_FRAMES,
        speech_threshold=voice_realtime.SPEECH_RMS_THRESHOLD,
    )
    second_phrase_kept = second_speech in captured
    return second_phrase_kept, {
        "end_silence_frames": voice_realtime.END_SILENCE_FRAMES,
        "end_silence_ms": voice_realtime.END_SILENCE_FRAMES * voice_realtime.FRAME_MS,
        "natural_pause_ms": 200,
        "captured_seconds": round(
            len(captured) / (voice_realtime.SAMPLE_RATE * voice_realtime.SAMPLE_WIDTH),
            2,
        ),
        "second_phrase_kept": second_phrase_kept,
    }


def main() -> int:
    natural_pause_ok, natural_pause_detail = asyncio.run(natural_pause_survives_endpointing())
    results = [
        check(
            "max_call_window_allows_full_lesson",
            voice_realtime.MAX_CALL_SECONDS >= 420,
            voice_realtime.MAX_CALL_SECONDS,
        ),
        check(
            "target_wrap_keeps_five_to_seven_minute_lesson",
            voice_asterisk.TARGET_WRAP_SECONDS >= 330,
            voice_asterisk.TARGET_WRAP_SECONDS,
        ),
        check(
            "minimum_lesson_before_wrap",
            voice_asterisk.MIN_LESSON_SECONDS >= 300,
            voice_asterisk.MIN_LESSON_SECONDS,
        ),
        check(
            "open_feedback_note_has_room_for_complaints",
            voice_realtime.FEEDBACK_MAX_SECONDS >= 90,
            voice_realtime.FEEDBACK_MAX_SECONDS,
        ),
        check(
            "feedback_wait_is_not_rushed",
            voice_realtime.FEEDBACK_WAIT_SECONDS >= 8,
            voice_realtime.FEEDBACK_WAIT_SECONDS,
        ),
        check(
            "feedback_note_tolerates_natural_pauses",
            voice_realtime.FEEDBACK_END_SILENCE_MS >= 2500,
            voice_realtime.FEEDBACK_END_SILENCE_MS,
        ),
        check(
            "literacy_hears_softer_speech",
            voice_realtime.LITERACY_SPEECH_RMS_THRESHOLD < voice_realtime.SPEECH_RMS_THRESHOLD,
            {
                "literacy": voice_realtime.LITERACY_SPEECH_RMS_THRESHOLD,
                "general": voice_realtime.SPEECH_RMS_THRESHOLD,
            },
        ),
        check(
            "all_lesson_turns_tolerate_natural_pauses",
            voice_realtime.END_SILENCE_FRAMES >= 18
            and voice_realtime.LITERACY_END_SILENCE_FRAMES >= voice_realtime.END_SILENCE_FRAMES,
            {
                "literacy": voice_realtime.LITERACY_END_SILENCE_FRAMES,
                "general": voice_realtime.END_SILENCE_FRAMES,
            },
        ),
        check(
            "natural_pause_does_not_cut_off_second_phrase",
            natural_pause_ok,
            natural_pause_detail,
        ),
        check(
            "barge_in_uses_tunable_literacy_thresholds",
            "speech_threshold" in inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge).parameters
            and "end_silence_frames" in inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge).parameters
            and "barge_grace_ms" in inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge).parameters,
            inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge),
        ),
        check(
            "barge_in_has_production_kill_switch",
            isinstance(voice_realtime.BARGE_IN_ENABLED, bool)
            and "BARGE_IN_ENABLED" in inspect.getsource(
                voice_realtime.RealtimeCall.play_pcm_with_barge
            ),
            voice_realtime.BARGE_IN_ENABLED,
        ),
        check(
            "opening_greeting_ignores_initial_carrier_audio",
            voice_realtime.INITIAL_GREETING_BARGE_GRACE_MS >= 2500
            and voice_realtime.INITIAL_GREETING_BARGE_GRACE_MS > voice_realtime.BARGE_GRACE_MS,
            {
                "opening_ms": voice_realtime.INITIAL_GREETING_BARGE_GRACE_MS,
                "normal_ms": voice_realtime.BARGE_GRACE_MS,
            },
        ),
        check(
            "feedback_mode_known",
            voice_realtime.FEEDBACK_MODE in {
                "off",
                "testers",
                "all",
                "1",
                "true",
                "yes",
                "on",
                "pilot",
                "prepilot",
                "pre-pilot",
            },
            voice_realtime.FEEDBACK_MODE,
        ),
        check(
            "live_greeting_not_forced_to_stale_cache",
            not voice_realtime.USE_CACHED_GREETING,
            voice_realtime.USE_CACHED_GREETING,
        ),
        check(
            "unclear_audio_gets_audibility_coaching",
            voice_realtime.MAX_UNCLEAR_RETRIES >= 2
            and "closer" in voice_realtime.UNCLEAR_AUDIO_RETRY_TEXT.lower()
            and "slowly" in voice_realtime.UNCLEAR_AUDIO_RETRY_TEXT.lower(),
            {
                "MAX_UNCLEAR_RETRIES": voice_realtime.MAX_UNCLEAR_RETRIES,
                "UNCLEAR_AUDIO_RETRY_TEXT": voice_realtime.UNCLEAR_AUDIO_RETRY_TEXT,
            },
        ),
        check(
            "unclear_retry_escalates_after_first_prompt",
            voice_realtime._retry_text_for_unclear_audio(0) == voice_realtime.RETRY_TEXT
            and voice_realtime._retry_text_for_unclear_audio(1) == voice_realtime.UNCLEAR_AUDIO_RETRY_TEXT,
            {
                "first": voice_realtime._retry_text_for_unclear_audio(0),
                "second": voice_realtime._retry_text_for_unclear_audio(1),
            },
        ),
        check(
            "numeric_keypad_fallback_available",
            voice_realtime.KEYPAD_NUMERIC_FALLBACK_ENABLED is True
            and voice_realtime.KEYPAD_NUMERIC_TIMEOUT_SECONDS >= 6
            and voice_realtime.KEYPAD_NUMERIC_MAX_DIGITS >= 3
            and voice_realtime.KEYPAD_NUMERIC_TERMINATORS == {"#", "*"}
            and "keypad" in voice_realtime.KEYPAD_NUMERIC_FALLBACK_TEXT.lower(),
            {
                "enabled": voice_realtime.KEYPAD_NUMERIC_FALLBACK_ENABLED,
                "timeout": voice_realtime.KEYPAD_NUMERIC_TIMEOUT_SECONDS,
                "max_digits": voice_realtime.KEYPAD_NUMERIC_MAX_DIGITS,
                "terminators": voice_realtime.KEYPAD_NUMERIC_TERMINATORS,
                "prompt": voice_realtime.KEYPAD_NUMERIC_FALLBACK_TEXT,
            },
        ),
        check(
            "turn_budget_allows_curriculum_flow",
            voice_asterisk.MAX_TURNS >= 34 and voice_asterisk.WRAP_UP_AFTER_TURNS >= 30,
            {
                "MAX_TURNS": voice_asterisk.MAX_TURNS,
                "WRAP_UP_AFTER_TURNS": voice_asterisk.WRAP_UP_AFTER_TURNS,
            },
        ),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
