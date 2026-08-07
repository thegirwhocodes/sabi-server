#!/usr/bin/env python3
"""Focused regressions for the phone-scoped persistent Gemini Live lane."""

from __future__ import annotations

import inspect
import os
import struct
from pathlib import Path

os.environ.setdefault(
    "SABI_SHARED_AUDIO_DIR",
    str(Path(os.getenv("TMPDIR", "/tmp")) / "sabi-gemini-live-regression"),
)

import gemini_live
import voice_realtime
from phone_utils import phone_uses_gemini_live


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return bool(condition)


def main() -> int:
    ok = True

    ok &= check(
        "live_canary_allowlist_normalizes_caller_id",
        phone_uses_gemini_live(
            "+1 (860) 436-7048",
            "+18604367048,+2348000000000",
        )
        and not phone_uses_gemini_live(
            "+18605550199",
            "+18604367048,+2348000000000",
        ),
    )
    ok &= check(
        "empty_allowlist_fails_to_established_pipeline",
        not phone_uses_gemini_live("+18604367048", ""),
    )

    setup = gemini_live.build_live_setup("Sabi regression prompt")
    live_setup = setup.get("setup") or {}
    generation = live_setup.get("generationConfig") or {}
    ok &= check(
        "raw_protocol_nests_response_modalities_correctly",
        generation.get("responseModalities") == ["AUDIO"]
        and "responseModalities" not in live_setup,
        setup,
    )
    ok &= check(
        "live_session_enables_both_transcripts_and_interruption",
        live_setup.get("inputAudioTranscription") == {}
        and live_setup.get("outputAudioTranscription") == {}
        and (live_setup.get("realtimeInputConfig") or {}).get("activityHandling")
        == "START_OF_ACTIVITY_INTERRUPTS",
        live_setup.get("realtimeInputConfig"),
    )
    ok &= check(
        "live_vad_is_conservative_for_random_sounds",
        (
            (live_setup.get("realtimeInputConfig") or {})
            .get("automaticActivityDetection", {})
            .get("startOfSpeechSensitivity")
            == "START_SENSITIVITY_LOW"
        )
        and (
            (live_setup.get("realtimeInputConfig") or {})
            .get("automaticActivityDetection", {})
            .get("silenceDurationMs")
            >= 500
        ),
        live_setup.get("realtimeInputConfig"),
    )

    source = inspect.getsource(voice_realtime.handle_audiosocket_call)
    ok &= check(
        "only_allowlisted_phone_enters_live_runner",
        "phone_uses_gemini_live(call.phone)" in source
        and "GeminiLiveSetupError" in source
        and "await call.run()" in source,
    )
    ok &= check(
        "live_playback_does_not_drain_caller_audio",
        "drain_audio" not in inspect.getsource(voice_realtime.RealtimeCall.send_pcm_frame),
    )

    converter = gemini_live.Pcm24kTo8k()
    # Two output samples: average(0, 3, 6)=3 and average(9, 12, 15)=12.
    output = converter.feed(struct.pack("<6h", 0, 3, 6, 9, 12, 15))
    ok &= check(
        "native_24k_audio_downsamples_to_telephone_8k",
        struct.unpack("<2h", output) == (3, 12),
        struct.unpack("<2h", output),
    )
    split_converter = gemini_live.Pcm24kTo8k()
    first = split_converter.feed(struct.pack("<2h", 3, 6))
    second = split_converter.feed(struct.pack("<4h", 9, 12, 15, 18))
    ok &= check(
        "downsampler_preserves_partial_groups_across_messages",
        first == b"" and struct.unpack("<2h", second) == (6, 15),
    )

    ok &= check(
        "stream_transcript_merger_handles_deltas",
        gemini_live.merge_stream_text("two", "mangoes") == "two mangoes"
        and gemini_live.merge_stream_text("two", "two mangoes") == "two mangoes"
        and gemini_live.merge_stream_text("two mangoes", "two") == "two mangoes",
    )

    products = [problem.expected for problem in gemini_live.MULTIPLICATION_PROBLEMS]
    ok &= check(
        "multiplication_deck_does_not_repeat_products",
        len(products) == len(set(products)) and products.count(12) == 0,
        products,
    )
    tools = gemini_live.GeminiLiveNumeracyTools("regression-call")
    questions = [tools.next_problem() for _ in range(4)]
    ok &= check(
        "problem_tool_advances_instead_of_repeating",
        len({item["problem_id"] for item in questions}) == 4
        and len({item["expected_answer"] for item in questions}) == 4,
        questions,
    )

    tools.current_problem = gemini_live.NumeracyProblem(
        "object_noun_regression",
        "You have three mangoes and eat one. How many remain?",
        2,
        "subtraction",
    )
    grade = tools.grade_answer("two fries")
    ok &= check(
        "numeric_tool_ignores_object_nouns",
        grade.get("is_correct") is True
        and grade.get("expected_answer") == 2
        and grade.get("object_nouns_ignored") is True,
        grade,
    )

    constraints = gemini_live.build_live_call_constraints(
        "Hello! What is your name?",
        {"course": "numeracy", "active_skill": "multiplication"},
    )
    ok &= check(
        "session_context_is_injected_once_with_tool_requirements",
        "one continuous" in constraints
        and "Call get_next_numeracy_problem before EVERY new maths question" in constraints
        and "grade_numeric_answer BEFORE" in constraints
        and "Object words never change the grade" in constraints,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
