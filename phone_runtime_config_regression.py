#!/usr/bin/env python3
"""Regression checks for Sabi phone runtime UX configuration.

Run this inside the deployed container after env/config changes. It catches
deployment drift that normal unit tests miss, like a live .env shortening the
open feedback note window below the product spec.
"""

from __future__ import annotations

import sys
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


def main() -> int:
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
            "literacy_waits_longer_for_short_sounds",
            voice_realtime.LITERACY_END_SILENCE_FRAMES > voice_realtime.END_SILENCE_FRAMES,
            {
                "literacy": voice_realtime.LITERACY_END_SILENCE_FRAMES,
                "general": voice_realtime.END_SILENCE_FRAMES,
            },
        ),
        check(
            "barge_in_uses_tunable_literacy_thresholds",
            "speech_threshold" in inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge).parameters
            and "end_silence_frames" in inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge).parameters,
            inspect.signature(voice_realtime.RealtimeCall.play_pcm_with_barge),
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
