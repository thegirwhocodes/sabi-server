#!/usr/bin/env python3
"""Regression checks for the LLM answer/name gate before lesson grading."""

from __future__ import annotations

from llm import TURN_ASSESSMENT_PROMPT, parse_turn_assessment


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    wrong_lesson_attempt = parse_turn_assessment(
        '{"is_answer": true, "name": null, "name_unclear": false}',
        asked_for_name=False,
    )
    ok &= check(
        "wrong_academic_attempt_still_reaches_grading",
        wrong_lesson_attempt.is_answer and wrong_lesson_attempt.name is None,
        wrong_lesson_attempt,
    )

    complaint = parse_turn_assessment(
        '{"is_answer": false, "name": null, "name_unclear": false}',
        asked_for_name=False,
    )
    ok &= check(
        "complaint_does_not_reach_grading",
        not complaint.is_answer and not complaint.name_unclear,
        complaint,
    )

    valid_name = parse_turn_assessment(
        '```json\n{"is_answer": true, "name": "gideon", "name_unclear": false}\n```',
        asked_for_name=True,
    )
    ok &= check(
        "plausible_name_is_normalized_and_accepted",
        valid_name.is_answer and valid_name.name == "Gideon" and not valid_name.name_unclear,
        valid_name,
    )

    implausible_name = parse_turn_assessment(
        '{"is_answer": false, "name": null, "name_unclear": true}',
        asked_for_name=True,
    )
    ok &= check(
        "learning_to_style_fragment_requires_name_clarification",
        not implausible_name.is_answer and implausible_name.name is None and implausible_name.name_unclear,
        implausible_name,
    )

    name_question_complaint = parse_turn_assessment(
        '{"is_answer": false, "name": null, "name_unclear": false}',
        asked_for_name=True,
    )
    ok &= check(
        "complaint_during_name_question_is_not_mislabeled_as_name_attempt",
        not name_question_complaint.is_answer and not name_question_complaint.name_unclear,
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
        "invalid_name_assessment_asks_for_clarification",
        not invalid_name.is_answer and invalid_name.name_unclear,
        invalid_name,
    )

    ok &= check(
        "assessment_prompt_is_binary_not_correctness_grading",
        "Do not judge whether the academic answer is correct" in TURN_ASSESSMENT_PROMPT
        and "is_answer" in TURN_ASSESSMENT_PROMPT
        and "Learning To" in TURN_ASSESSMENT_PROMPT,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
