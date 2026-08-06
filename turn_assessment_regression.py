#!/usr/bin/env python3
"""Regression checks for the LLM answer/name gate before lesson grading."""

from __future__ import annotations

import asyncio

import llm as llm_module
from llm import SabiLLM, TURN_ASSESSMENT_PROMPT, parse_turn_assessment


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


async def check_fast_provider_precedes_claude() -> tuple[bool, list[str]]:
    calls: list[str] = []
    original_groq_key = llm_module.GROQ_API_KEY
    original_anthropic_key = llm_module.ANTHROPIC_API_KEY
    original_cerebras_key = llm_module.CEREBRAS_API_KEY
    try:
        llm_module.GROQ_API_KEY = "regression"
        llm_module.ANTHROPIC_API_KEY = "regression"
        llm_module.CEREBRAS_API_KEY = ""
        tutor = SabiLLM.__new__(SabiLLM)
        tutor.primary = "claude"
        tutor.disabled_providers = set()

        async def fake_openai(*args, **kwargs):
            calls.append("groq")
            return '{"is_answer": false, "name": null}'

        async def fake_claude(*args, **kwargs):
            calls.append("claude")
            return '{"is_answer": true, "name": null}'

        tutor._generate_openai_compat = fake_openai
        tutor._generate_claude = fake_claude
        assessment = await tutor.assess_turn(
            latest_question="How many sweets?",
            transcript="Sabi",
        )
        return calls == ["groq"] and not assessment.is_answer, calls
    finally:
        llm_module.GROQ_API_KEY = original_groq_key
        llm_module.ANTHROPIC_API_KEY = original_anthropic_key
        llm_module.CEREBRAS_API_KEY = original_cerebras_key


def main() -> int:
    ok = True

    wrong_lesson_attempt = parse_turn_assessment(
        '{"is_answer": true, "name": null}',
        asked_for_name=False,
    )
    ok &= check(
        "wrong_academic_attempt_still_reaches_grading",
        wrong_lesson_attempt.is_answer and wrong_lesson_attempt.name is None,
        wrong_lesson_attempt,
    )

    complaint = parse_turn_assessment(
        '{"is_answer": false, "name": null}',
        asked_for_name=False,
    )
    ok &= check(
        "complaint_does_not_reach_grading",
        not complaint.is_answer and complaint.name is None,
        complaint,
    )

    valid_name = parse_turn_assessment(
        '```json\n{"is_answer": true, "name": "gideon"}\n```',
        asked_for_name=True,
    )
    ok &= check(
        "plausible_name_is_normalized_and_accepted",
        valid_name.is_answer and valid_name.name == "Gideon",
        valid_name,
    )

    implausible_name = parse_turn_assessment(
        '{"is_answer": false, "name": null}',
        asked_for_name=True,
    )
    ok &= check(
        "learning_to_style_fragment_requires_name_clarification",
        not implausible_name.is_answer and implausible_name.name is None,
        implausible_name,
    )

    name_question_complaint = parse_turn_assessment(
        '{"is_answer": false, "name": null}',
        asked_for_name=True,
    )
    ok &= check(
        "complaint_during_name_question_is_not_mislabeled_as_name_attempt",
        not name_question_complaint.is_answer and name_question_complaint.name is None,
        name_question_complaint,
    )

    invalid = parse_turn_assessment("not json", asked_for_name=False)
    ok &= check(
        "invalid_model_output_fails_closed_without_grading",
        not invalid.is_answer,
        invalid,
    )
    invalid_name = parse_turn_assessment("not json", asked_for_name=True)
    ok &= check(
        "invalid_name_assessment_fails_closed",
        not invalid_name.is_answer and invalid_name.name is None,
        invalid_name,
    )

    ok &= check(
        "assessment_prompt_is_binary_not_correctness_grading",
        "Do not judge whether the academic answer is correct" in TURN_ASSESSMENT_PROMPT
        and "is_answer" in TURN_ASSESSMENT_PROMPT
        and "Learning To" in TURN_ASSESSMENT_PROMPT,
    )

    fast_provider_ok, provider_calls = asyncio.run(check_fast_provider_precedes_claude())
    ok &= check(
        "fast_groq_gate_precedes_full_response_claude",
        fast_provider_ok,
        provider_calls,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
