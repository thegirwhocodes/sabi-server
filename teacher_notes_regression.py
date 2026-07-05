#!/usr/bin/env python3
"""Regression checks for Sabi end-of-call teacher notes."""

from __future__ import annotations

import asyncio
import sys

from teacher_notes import (
    ENGAGEMENT_VALUES,
    _parse_note,
    generate_teacher_note,
    heuristic_teacher_note,
    should_generate_teacher_note,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    # Cost guard.
    ok &= check("guard_skips_no_turns", should_generate_teacher_note(0, 300) is False)
    ok &= check("guard_skips_short_call", should_generate_teacher_note(3, 10) is False)
    ok &= check("guard_allows_real_call", should_generate_teacher_note(3, 120) is True)

    # Heuristic note is always well-formed and safe.
    note = heuristic_teacher_note(
        correct_count=4,
        wrong_count=2,
        skills={"addition": 0.67, "counting": 0.9},
        summary="Practiced addition with 4 correct and 2 needing support.",
        current_level="intermediate",
        lesson={"module_name": "addition"},
        learning_state={"active_skill": "addition", "next_step": "Continue with one guided example.", "scaffold_depth": 0},
        user_turns=5,
    )
    ok &= check(
        "heuristic_note_shape",
        set(["strengths", "struggles", "engagement", "misconceptions", "recommended_focus", "narrative", "source"]).issubset(note.keys())
        and note["source"] == "heuristic"
        and note["engagement"] in ENGAGEMENT_VALUES
        and isinstance(note["strengths"], list)
        and bool(note["recommended_focus"]),
        note,
    )

    # JSON parsing tolerates surrounding prose and normalizes engagement.
    parsed = _parse_note(
        'Sure! Here is the note: {"strengths":["counts to ten"],"struggles":[],'
        '"engagement":"EAGER","misconceptions":[],"recommended_focus":"Do teens next.",'
        '"narrative":"Ada counts confidently."} Hope that helps.'
    )
    ok &= check(
        "parse_extracts_and_normalizes",
        parsed is not None
        and parsed["engagement"] == "eager"
        and parsed["strengths"] == ["counts to ten"]
        and parsed["recommended_focus"] == "Do teens next.",
        parsed,
    )
    ok &= check("parse_bad_engagement_defaults_mixed", (_parse_note('{"engagement":"weird","narrative":"n"}') or {}).get("engagement") == "mixed")
    ok &= check("parse_rejects_non_json", _parse_note("no json here") is None)
    ok &= check("parse_rejects_empty_note", _parse_note('{"strengths":[]}') is None)

    # generate_teacher_note returns None when the cost guard says skip.
    skipped = asyncio.run(
        generate_teacher_note(
            messages=[{"role": "user", "content": "hi"}],
            correct_count=0,
            wrong_count=0,
            skills={},
            summary="",
            current_level="beginner",
            lesson=None,
            learning_state={},
            user_turns=0,
            duration_seconds=5,
        )
    )
    ok &= check("generate_returns_none_when_guarded", skipped is None)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
