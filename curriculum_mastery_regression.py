#!/usr/bin/env python3
"""Regression checks for Sabi curriculum-aligned mastery classification."""

from __future__ import annotations

import sys

from curriculum_mastery import (
    ADVANCE_THRESHOLD,
    build_call_scorecard,
    classify_mastery,
    classify_session_advance,
    cross_session_signal,
    lesson_mastery_line,
    lesson_passed,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    ok &= check("classify_mastered_at_advance", classify_mastery(ADVANCE_THRESHOLD) == "mastered")
    ok &= check("classify_mastered_high", classify_mastery(0.95) == "mastered")
    ok &= check("classify_near_mid", classify_mastery(0.7) == "near")
    ok &= check("classify_needs_practice_low", classify_mastery(0.4) == "needs_practice")
    ok &= check("classify_insufficient_none", classify_mastery(None) == "insufficient")
    ok &= check("classify_insufficient_no_attempts", classify_mastery(0.9, attempts=0) == "insufficient")

    # Lesson 20 is the hard 70% gate before two-digit addition.
    line20 = lesson_mastery_line("numeracy", 20)
    ok &= check(
        "lesson_20_is_hard_70_gate",
        line20.get("threshold") == 0.70 and line20.get("hard_gate") is True,
        line20,
    )
    ok &= check("lesson_20_below_gate_fails", lesson_passed("numeracy", 20, 3, 5) is False)
    ok &= check("lesson_20_at_gate_passes", lesson_passed("numeracy", 20, 4, 5) is True)

    # Module assessment lesson 12 = 7 of 10 (0.70 ratio).
    line12 = lesson_mastery_line("numeracy", 12)
    ok &= check(
        "lesson_12_module_assessment_7_of_10",
        line12.get("kind") == "module_assessment" and line12.get("correct") == 7 and line12.get("total") == 10,
        line12,
    )
    # Lesson 64 = 12 of 15 (0.80 ratio); 9/12 = 0.75 should fail, 10/12 = 0.833 pass.
    ok &= check("lesson_64_scaled_fail", lesson_passed("numeracy", 64, 9, 12) is False)
    ok &= check("lesson_64_scaled_pass", lesson_passed("numeracy", 64, 10, 12) is True)

    # Regular lesson uses the default 0.70 pass line.
    default_line = lesson_mastery_line("numeracy", 3)
    ok &= check("default_lesson_pass_line_070", default_line.get("threshold") == 0.70 and default_line.get("kind") == "lesson")
    ok &= check("no_evidence_returns_none", lesson_passed("numeracy", 3, 0, 0) is None)

    # Cross-session advance: >= 0.85 for the last 3 sessions.
    ok &= check("advance_three_high", classify_session_advance([0.5, 0.9, 0.86, 0.88]) is True)
    ok &= check("advance_blocked_by_dip", classify_session_advance([0.9, 0.5, 0.88]) is False)
    ok &= check("advance_needs_three", classify_session_advance([0.9, 0.9]) is False)
    ok &= check("cross_session_signal_bands", cross_session_signal(0.9) == "mastered" and cross_session_signal(0.7) == "near" and cross_session_signal(0.3) == "needs_practice")

    scorecard = build_call_scorecard(
        course="numeracy",
        lesson={"module": 2, "module_name": "addition", "global_lesson": 15, "title": "Counting on"},
        correct_count=4,
        wrong_count=2,
        skills={"addition": 0.67},
        learning_state_before={"tarl_level": 2},
        learning_state_after={"tarl_level": 2, "scaffold_depth": 1},
        should_advance=False,
    )
    ok &= check(
        "scorecard_core_fields",
        scorecard["questions_correct"] == 4
        and scorecard["questions_total"] == 6
        and scorecard["accuracy"] == 0.667
        and scorecard["mastery_signal"] == "near"
        and scorecard["lesson_global"] == 15
        and scorecard["per_skill"]["addition"]["mastery"] == "near"
        and scorecard["tarl_level_before"] == 2,
        scorecard,
    )
    empty = build_call_scorecard(
        course="numeracy",
        lesson=None,
        correct_count=0,
        wrong_count=0,
        skills=None,
        learning_state_before=None,
        learning_state_after=None,
        should_advance=False,
    )
    ok &= check(
        "scorecard_no_evidence_is_insufficient",
        empty["questions_total"] == 0 and empty["accuracy"] is None and empty["mastery_signal"] == "insufficient",
        empty,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
