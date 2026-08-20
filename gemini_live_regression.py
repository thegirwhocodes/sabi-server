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

    # The lane is promoted to production: default on for everyone, with a
    # per-number opt-out. An explicit list argument keeps allowlist semantics
    # so a caller can still test one specific configuration.
    import os as _os

    def _with_env(**pairs):
        previous = {key: _os.environ.get(key) for key in pairs}
        for key, value in pairs.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value
        return previous

    def _restore(previous):
        for key, value in previous.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value

    saved = _with_env(
        SABI_GEMINI_LIVE_ALL=None,
        SABI_GEMINI_LIVE_PHONES=None,
        SABI_GEMINI_LIVE_EXCLUDE_PHONES=None,
    )
    ok &= check(
        "live_lane_is_default_for_every_caller",
        phone_uses_gemini_live("+2348000000000")
        and phone_uses_gemini_live("+18605550199"),
    )

    _with_env(SABI_GEMINI_LIVE_EXCLUDE_PHONES="+1 (860) 555-0199")
    ok &= check(
        "excluded_number_stays_on_the_established_pipeline",
        not phone_uses_gemini_live("+18605550199")
        and phone_uses_gemini_live("+2348000000000"),
    )

    _with_env(
        SABI_GEMINI_LIVE_ALL="0",
        SABI_GEMINI_LIVE_PHONES="+18604367048",
        SABI_GEMINI_LIVE_EXCLUDE_PHONES=None,
    )
    ok &= check(
        "canary_mode_can_be_restored_without_a_code_change",
        phone_uses_gemini_live("+18604367048")
        and not phone_uses_gemini_live("+2348000000000"),
    )
    _restore(saved)

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
        "five to seven minutes" in compact_prompt
        and compact_prompt.count("## CURRENT NUMERACY CURRICULUM PATH") == 1
        and "do not merely quiz" in compact_prompt
        and len(compact_prompt) < 12000,
        len(compact_prompt),
    )
    learner_context = gemini_live.build_gemini_live_learner_context(
        {"name": "Naomi", "total_sessions": 42, "total_correct": 16, "total_wrong": 72},
        {
            "current_module": 4,
            "current_week": 12,
            "current_lesson": 1,
            "active_skill": "multiplication",
            "research": {"large_private_protocol": "must not enter live prompt"},
        },
    )
    ok &= check(
        "live_learner_context_excludes_stale_scores_and_research_payload",
        "Name: Naomi" in learner_context
        and "16" not in learner_context
        and "72" not in learner_context
        and "large_private_protocol" not in learner_context,
        learner_context,
    )
    compact_state = gemini_live.compact_live_learning_state(
        {"course": "numeracy", "current_module": 4, "research": {"huge": "payload"}}
    )
    ok &= check(
        "live_state_excludes_research_and_raw_event_history",
        compact_state.get("current_module") == 4 and "research" not in compact_state,
        compact_state,
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
        len(products) == len(set(products)),
        products,
    )
    beginner_problems = [
        problem
        for problem in gemini_live.MULTIPLICATION_PROBLEMS
        if problem.difficulty_tier == 1
    ]
    ok &= check(
        "beginner_deck_uses_only_tiny_equal_groups",
        beginner_problems
        and all(problem.expected <= 10 for problem in beginner_problems)
        and all(
            max(problem.groups, problem.per_group) <= 5
            for problem in beginner_problems
        )
        and not any(
            problem.groups == 3 and problem.per_group == 7
            for problem in beginner_problems
        ),
        [(problem.id, problem.groups, problem.per_group) for problem in beginner_problems],
    )
    fresh_openings = [
        gemini_live.GeminiLiveNumeracyTools(f"fresh-call-{index}").next_problem()
        for index in range(20)
    ]
    ok &= check(
        "fresh_beginner_calls_never_hash_into_a_hard_opening",
        all(item.get("difficulty_tier") == 1 for item in fresh_openings)
        and all((item.get("factors") or [99, 99]) == [2, 2] for item in fresh_openings)
        and all(item.get("teaching_intro") for item in fresh_openings),
        fresh_openings,
    )
    secure_beginner = gemini_live.GeminiLiveNumeracyTools(
        "secure-beginner",
        {
            "grading_evidence": {
                "skills": {
                    gemini_live.MULTIPLICATION_MASTERY_SKILL: {"status": "secure"}
                }
            }
        },
    )
    explicit_tier_two = gemini_live.GeminiLiveNumeracyTools(
        "explicit-tier-two",
        {"multiplication_difficulty_tier": 2},
    )
    ok &= check(
        "mastery_does_not_silently_raise_difficulty",
        secure_beginner.difficulty_tier == 1
        and explicit_tier_two.difficulty_tier == 2
        and explicit_tier_two.next_problem().get("difficulty_tier") == 2,
        [secure_beginner.difficulty_tier, explicit_tier_two.difficulty_tier],
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
        "correct_grade_atomically_registers_next_problem",
        (grade.get("next_problem") or {}).get("problem_id") != "object_noun_regression"
        and tools.current_problem is not None
        and tools.current_problem.id == (grade.get("next_problem") or {}).get("problem_id")
        and tools.current_problem_resolved is False,
        grade,
    )
    repeated_next = tools.next_problem()
    ok &= check(
        "registered_followup_cannot_be_replaced_before_answer",
        repeated_next.get("status") == "active_problem"
        and repeated_next.get("problem_id") == (grade.get("next_problem") or {}).get("problem_id")
        and repeated_next.get("question") == (grade.get("next_problem") or {}).get("question"),
        repeated_next,
    )

    grade_event = {"name": "grade_numeric_answer", "result": grade}
    registered_question = (grade.get("next_problem") or {}).get("question") or ""
    mismatch = gemini_live.registered_followup_enforcement(
        [grade_event],
        "Correct! Three bags have five notebooks each. How many notebooks is that?",
        "two fries",
        120,
    )
    ok &= check(
        "controller_replaces_invented_question_with_registered_followup",
        mismatch is not None
        and mismatch.get("unregistered_question_corrected") is True
        and registered_question in str(mismatch.get("instruction") or ""),
        mismatch,
    )
    ok &= check(
        "controller_does_not_duplicate_exact_registered_question",
        gemini_live.registered_followup_enforcement(
            [grade_event],
            f"Correct! {registered_question}",
            "two fries",
            120,
        )
        is None,
    )
    ok &= check(
        "controller_does_not_treat_a_social_check_in_as_an_invented_maths_item",
        not gemini_live.assistant_asked_math_question(
            "Correct! Did that explanation make sense?"
        ),
    )

    resolved_tools = gemini_live.GeminiLiveNumeracyTools("resolved-regression")
    resolved_tools.current_problem = gemini_live.NumeracyProblem(
        "resolved_item",
        "Two bags have four each. How many altogether?",
        8,
    )
    resolved_tools.current_problem_resolved = True
    stale_grade = resolved_tools.grade_answer("eighteen")
    ok &= check(
        "invented_question_answer_cannot_be_graded_against_resolved_item",
        stale_grade.get("status") == "problem_already_resolved"
        and stale_grade.get("is_correct") is None
        and not resolved_tools.call_events,
        stale_grade,
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

    help_tools = gemini_live.GeminiLiveNumeracyTools("help-regression")
    help_tools.current_problem = gemini_live.NumeracyProblem(
        "help_item",
        "Two bags have three oranges each. How many altogether?",
        6,
        conceptual_hint="One bag has three. Count three more: four, five—what comes next?",
    )
    help_request = help_tools.grade_answer("I don't know. Help me.")
    helped_answer = help_tools.grade_answer("six")
    help_score = help_tools.authoritative_session_score()
    ok &= check(
        "clear_help_request_teaches_without_becoming_a_wrong_answer",
        help_request.get("status") == "help_requested"
        and help_request.get("is_correct") is None
        and help_request.get("academic_correctness") == "indeterminate"
        and "One bag has three" in str(help_request.get("instruction") or "")
        and helped_answer.get("is_correct") is True
        and helped_answer.get("independence") == "scaffolded"
        and help_score.get("wrong_count") == 0
        and help_score.get("supported_correct") == 1,
        [help_request, helped_answer, help_score],
    )
    unsure_tools = gemini_live.GeminiLiveNumeracyTools("unsure-number-regression")
    unsure_tools.current_problem = gemini_live.NumeracyProblem(
        "unsure_item",
        "Two bags have three oranges each. How many altogether?",
        6,
    )
    unsure_number = unsure_tools.grade_answer("I'm not sure, is it six?")
    ok &= check(
        "numeric_candidate_is_graded_even_when_learner_sounds_unsure",
        unsure_number.get("status") == "correct"
        and unsure_number.get("is_correct") is True,
        unsure_number,
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
    # The injected contract has to match the mode that is actually running. With
    # the tools off Sabi writes and marks her own naira questions, so the rules
    # that name the tools are wrong to assert - what must hold instead is that
    # she is told to mark the question she really asked.
    if gemini_live.GEMINI_LIVE_TOOLS_ENABLED:
        ok &= check(
            "session_context_is_injected_once_with_tool_requirements",
            "one continuous" in constraints
            and "Call get_next_numeracy_problem at lesson opening" in constraints
            and "I don't know/help me" in constraints
            and "Do not invent" in constraints
            and "object words do not" in constraints
            and "five to seven minutes" in constraints
            and "get_lesson_progress BEFORE" in constraints,
        )
    else:
        ok &= check(
            "session_context_tells_a_toolless_sabi_to_mark_what_she_asked",
            "one continuous" in constraints
            and "Make the questions up as you go" in constraints
            and "no list to work" in constraints
            and "Every question is about money" in constraints
            and "Work in tens" in constraints
            and "five to seven minutes" not in constraints
            and "Mark the answer to the question you actually asked" in constraints
            and "get_next_numeracy_problem" not in constraints
            and "grade_numeric_answer" not in constraints,
        )
    tool_declarations = (
        ((live_setup.get("tools") or [{}])[0]).get("functionDeclarations") or []
    )
    grading_declaration = next(
        (
            declaration
            for declaration in tool_declarations
            if declaration.get("name") == "grade_numeric_answer"
        ),
        {},
    )
    ok &= check(
        "help_gate_is_described_in_the_grading_tool_contract",
        not gemini_live.GEMINI_LIVE_TOOLS_ENABLED
        or "clear request" in str(grading_declaration.get("description") or "")
        and "complete reply" in str(
            (((grading_declaration.get("parameters") or {}).get("properties") or {})
             .get("learner_answer", {}))
            .get("description")
            or ""
        ),
        grading_declaration,
    ) if gemini_live.GEMINI_LIVE_TOOLS_ENABLED else check(
        "grading_tool_is_absent_when_tools_are_off", not tool_declarations
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
