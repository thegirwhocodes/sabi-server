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
from gemini_grading import make_evidence_event, summarize_mastery
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
    compact_prompt = gemini_live.build_gemini_live_base_prompt(
        "\n## STUDENT CONTEXT\nReturning learner Naomi.",
        "\n## CURRENT NUMERACY CURRICULUM PATH\nMultiplication groups.",
    )
    ok &= check(
        "live_prompt_is_compact_and_contains_one_curriculum_block",
        "five-to-seven-minute" in compact_prompt
        and compact_prompt.count("## CURRENT NUMERACY CURRICULUM PATH") == 1
        and "do not merely quiz" in compact_prompt
        and len(compact_prompt) < 12000,
        len(compact_prompt),
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
        "unresolved_problem_cannot_be_replaced",
        len({item["problem_id"] for item in questions}) == 1
        and all("expected_answer" not in item for item in questions),
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
    ok &= check(
        "correct_problem_must_resolve_before_deck_advances",
        tools.next_problem().get("problem_id") != "object_noun_regression",
    )

    tools.current_problem = gemini_live.NumeracyProblem(
        "support_regression",
        "Three groups have four each. How many altogether?",
        12,
        "multiplication",
        "equal_groups",
    )
    tools.current_problem_resolved = False
    tools.current_prompt_level = "none"
    tools.current_attempt = 0
    unclear = tools.grade_answer("I did not hear")
    retry_correct = tools.grade_answer("twelve apples")
    ok &= check(
        "technical_retry_is_not_wrong_and_preserves_independence",
        unclear.get("audio_scorability") == "not_scorable"
        and unclear.get("academic_correctness") == "indeterminate"
        and retry_correct.get("is_correct") is True
        and retry_correct.get("independence") == "independent",
        [unclear, retry_correct],
    )

    tools.current_problem = gemini_live.NumeracyProblem(
        "multiple_numbers_regression",
        "Five groups have six each. How many altogether?",
        30,
    )
    tools.current_problem_resolved = False
    tools.current_prompt_level = "none"
    tools.current_attempt = 0
    multiple_numbers = tools.grade_answer("Is it twenty or thirty?")
    ok &= check(
        "multiple_candidate_numbers_are_not_scorable",
        multiple_numbers.get("audio_scorability") == "not_scorable"
        and multiple_numbers.get("is_correct") is None,
        multiple_numbers,
    )

    tools.current_problem = gemini_live.NumeracyProblem(
        "scaffold_regression",
        "Two groups have six each. How many altogether?",
        12,
        "multiplication",
        "equal_groups",
    )
    tools.current_problem_resolved = False
    tools.current_prompt_level = "none"
    tools.current_attempt = 0
    first_wrong = tools.grade_answer("ten")
    supported_correct = tools.grade_answer("twelve")
    ok &= check(
        "correct_after_conceptual_hint_is_supported_not_independent",
        first_wrong.get("independence") == "independent"
        and supported_correct.get("is_correct") is True
        and supported_correct.get("independence") == "scaffolded",
        [first_wrong, supported_correct],
    )

    mastery_events = []
    specs = [
        ("call-a", "item-1", "equal_groups", "correct"),
        ("call-a", "item-2", "array", "correct"),
        ("call-a", "item-3", "equal_groups", "incorrect"),
        ("call-b", "item-4", "rate", "correct"),
        ("call-b", "item-5", "array", "correct"),
    ]
    for index, (call_id, item_id, item_form, correctness) in enumerate(specs, 1):
        mastery_events.append(
            make_evidence_event(
                call_id=call_id,
                item_id=item_id,
                item_form=item_form,
                skill="multiplication",
                expected_answer=index,
                learner_answer=str(index),
                heard_numbers=[index],
                audio_scorability="scorable",
                academic_correctness=correctness,
                independence="independent",
                prompt_level="none",
                attempt_index=1,
            )
        )
    mastery = summarize_mastery(mastery_events, "multiplication")
    ok &= check(
        "mastery_requires_four_of_five_across_two_calls_and_forms",
        mastery.get("status") == "secure"
        and mastery.get("independent_correct") == 4
        and len(mastery.get("evidence_call_ids") or []) == 2,
        mastery,
    )
    one_call_mastery = summarize_mastery(
        [{**event, "call_id": "one-call"} for event in mastery_events],
        "multiplication",
    )
    ok &= check(
        "one_call_cannot_establish_secure_mastery",
        one_call_mastery.get("status") != "secure",
        one_call_mastery,
    )
    duplicate = {**mastery_events[-1], "academic_correctness": "incorrect"}
    duplicate_mastery = summarize_mastery([*mastery_events, duplicate], "multiplication")
    ok &= check(
        "duplicate_item_does_not_create_a_sixth_mastery_vote",
        duplicate_mastery.get("independent_window_size") == 5,
        duplicate_mastery,
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
        and "Object words never change the grade" in constraints
        and "five to seven minutes" in constraints
        and "get_lesson_progress BEFORE" in constraints,
    )
    ok &= check(
        "lesson_clock_blocks_early_wrap_and_opens_after_five_minutes",
        tools.lesson_progress(81).get("may_wrap") is False
        and tools.lesson_progress(81).get("phase") == "today_lesson"
        and gemini_live.is_early_wrap_text("So today, we learned multiplication. Next time...", 81)
        and not gemini_live.is_early_wrap_text("So today, we learned multiplication.", 301),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
