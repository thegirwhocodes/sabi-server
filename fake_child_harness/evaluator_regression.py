#!/usr/bin/env python3
"""Focused regression checks for fake-child turn evaluation."""

from __future__ import annotations

from .child_simulator import SimulatedTurn
from .evaluator import evaluate_turn


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def _turn(**overrides: object) -> SimulatedTurn:
    data = {
        "child_id": "FC-test",
        "call_index": 1,
        "turn_index": 1,
        "prompt": "What is two plus three?",
        "item_id": "addition_2_3",
        "expected_answers": ("5", "five"),
        "ground_truth_correct": True,
        "child_answer_text": "five",
        "stt_text": "Good luck.",
        "noise_level": "brutal_market",
        "stt_confidence": 0.05,
        "notes": (),
    }
    data.update(overrides)
    return SimulatedTurn(**data)


def main() -> int:
    ok = True

    low_conf = evaluate_turn(_turn(stt_text="Kid.", stt_confidence=0.0))
    ok &= check(
        "low_confidence_correct_nonmatch_is_masked_watch",
        low_conf.failure_type == "no_speech_or_masked" and low_conf.severity == "watch",
        low_conf.to_dict(),
    )

    high_conf = evaluate_turn(
        _turn(
            prompt="Blend sh-ip.",
            item_id="lit_blend_ship",
            expected_answers=("ship",),
            child_answer_text="ship",
            stt_text="chips",
            stt_confidence=0.72,
        )
    )
    ok &= check(
        "high_confidence_correct_nonmatch_still_blocks",
        high_conf.failure_type == "false_wrong_grading" and high_conf.severity == "release_blocking",
        high_conf.to_dict(),
    )

    matched_low_conf = evaluate_turn(_turn(stt_text="fine", stt_confidence=0.08))
    ok &= check(
        "low_confidence_numeric_match_still_counts",
        matched_low_conf.failure_type is None and matched_low_conf.grader_matched,
        matched_low_conf.to_dict(),
    )

    prompt_echo = evaluate_turn(
        _turn(
            prompt="Say smile without the s sound.",
            item_id="lit_delete_smile",
            expected_answers=("mile",),
            child_answer_text="mile",
            stt_text="Smile.",
            stt_confidence=0.32,
        )
    )
    ok &= check(
        "deletion_prompt_echo_is_retry_watch",
        prompt_echo.failure_type == "prompt_echo_or_deletion_masked" and prompt_echo.severity == "watch",
        prompt_echo.to_dict(),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
