"""Curriculum-aligned mastery classification for Sabi.

The pedagogy math already existed across the project, but only as prose in the
lesson scripts and FOUNDATIONAL_COURSES_PLAN. This module puts the thresholds in
one enforceable place so the backend can label a child's performance against the
actual curriculum ("mastered", "near mastery", "needs practice") instead of just
showing a raw count.

Thresholds (from the original curriculum design):
- Per-lesson pass line: 0.70 accuracy (module-assessment lessons like numeracy
  Lesson 12 = 7/10, Lesson 20 hard gate = 70%, Lesson 28 = 6/7, Lesson 64 = 12/15).
- Cross-session rules (FOUNDATIONAL_COURSES_PLAN Part 8): advance at >= 0.85 held
  for 3+ sessions; reinforce 0.60-0.84; remediate < 0.60; skip a module at >= 0.90
  on the diagnostic.
"""

from __future__ import annotations

from typing import Any

# Single-session mastery bands.
ADVANCE_THRESHOLD = 0.85      # >= this is "mastered" for the session
REINFORCE_THRESHOLD = 0.60    # [0.60, 0.85) is "near" mastery
LESSON_PASS_THRESHOLD = 0.70  # per-lesson pass line (module-assessment default)
DIAGNOSTIC_SKIP_THRESHOLD = 0.90

# Cross-session advance rule: score at/above ADVANCE for this many recent sessions.
ADVANCE_SESSION_COUNT = 3

MASTERY_MASTERED = "mastered"
MASTERY_NEAR = "near"
MASTERY_NEEDS_PRACTICE = "needs_practice"
MASTERY_INSUFFICIENT = "insufficient"

MASTERY_LABELS = {
    MASTERY_MASTERED: "Mastered",
    MASTERY_NEAR: "Near mastery",
    MASTERY_NEEDS_PRACTICE: "Needs practice",
    MASTERY_INSUFFICIENT: "Not enough evidence",
}

# Module-assessment lessons carry their own n-of-m rule from the lesson scripts.
# Keyed by numeracy global lesson number.
NUMERACY_MODULE_ASSESSMENTS: dict[int, dict[str, Any]] = {
    12: {"correct": 7, "total": 10, "note": "Module 1 check: 7 of 10 skills for mastery; 5-6 is near mastery."},
    20: {"threshold": 0.70, "hard_gate": True, "note": "Week 5 gate: do not advance to two-digit addition below 70% accuracy."},
    28: {"correct": 6, "total": 7, "note": "Module 2 assessment: 6 of 7 for full mastery; 4-5 conditional."},
    44: {"threshold": 0.70, "note": "Module 3 subtraction assessment."},
    64: {"correct": 12, "total": 15, "note": "Module 4 assessment: 12 of 15 to complete multiplication."},
}


def classify_mastery(accuracy: float | None, *, attempts: int | None = None) -> str:
    """Classify a single accuracy value (0.0-1.0) into a mastery band."""
    if accuracy is None:
        return MASTERY_INSUFFICIENT
    if attempts is not None and int(attempts) <= 0:
        return MASTERY_INSUFFICIENT
    value = float(accuracy)
    if value >= ADVANCE_THRESHOLD:
        return MASTERY_MASTERED
    if value >= REINFORCE_THRESHOLD:
        return MASTERY_NEAR
    return MASTERY_NEEDS_PRACTICE


def mastery_label(signal: str) -> str:
    return MASTERY_LABELS.get(signal, MASTERY_LABELS[MASTERY_INSUFFICIENT])


def lesson_mastery_line(course: str, lesson_global: int | None) -> dict[str, Any]:
    """Return the mastery pass line for a specific lesson.

    Module-assessment lessons use their n-of-m rule; everything else uses the
    default per-lesson pass line (0.70).
    """
    if str(course or "numeracy") == "numeracy" and lesson_global in NUMERACY_MODULE_ASSESSMENTS:
        spec = dict(NUMERACY_MODULE_ASSESSMENTS[lesson_global])
        if "threshold" not in spec and spec.get("total"):
            spec["threshold"] = round(int(spec["correct"]) / int(spec["total"]), 2)
        spec.setdefault("threshold", LESSON_PASS_THRESHOLD)
        spec["kind"] = "module_assessment"
        return spec
    return {
        "threshold": LESSON_PASS_THRESHOLD,
        "kind": "lesson",
        "note": "Standard lesson pass line (70% correct on the day's skill).",
    }


def lesson_passed(course: str, lesson_global: int | None, questions_correct: int, questions_total: int) -> bool | None:
    """Whether a call's performance clears the lesson's pass line. None if no evidence."""
    if int(questions_total or 0) <= 0:
        return None
    line = lesson_mastery_line(course, lesson_global)
    if line.get("kind") == "module_assessment" and line.get("correct") and line.get("total") and not line.get("hard_gate"):
        # n-of-m style: scale the required correct to however many were actually asked.
        required_ratio = int(line["correct"]) / int(line["total"])
        return (questions_correct / questions_total) >= required_ratio
    accuracy = questions_correct / questions_total
    return accuracy >= float(line.get("threshold", LESSON_PASS_THRESHOLD))


def classify_session_advance(recent_scores: list[float]) -> bool:
    """Cross-session advance rule: >= ADVANCE_THRESHOLD held for the last N sessions."""
    scores = [float(s) for s in (recent_scores or []) if s is not None]
    if len(scores) < ADVANCE_SESSION_COUNT:
        return False
    window = scores[-ADVANCE_SESSION_COUNT:]
    return all(score >= ADVANCE_THRESHOLD for score in window)


def cross_session_signal(score: float | None) -> str:
    """Map a rolling skill score to the FOUNDATIONAL_COURSES_PLAN action band."""
    if score is None:
        return MASTERY_INSUFFICIENT
    value = float(score)
    if value >= ADVANCE_THRESHOLD:
        return MASTERY_MASTERED
    if value >= REINFORCE_THRESHOLD:
        return MASTERY_NEAR
    return MASTERY_NEEDS_PRACTICE


def build_call_scorecard(
    *,
    course: str,
    lesson: dict[str, Any] | None,
    correct_count: int,
    wrong_count: int,
    skills: dict[str, float] | None,
    learning_state_before: dict[str, Any] | None,
    learning_state_after: dict[str, Any] | None,
    should_advance: bool,
) -> dict[str, Any]:
    """Build the per-call learning scorecard tied to the actual curriculum lesson."""
    lesson = lesson or {}
    skills = skills or {}
    before = learning_state_before or {}
    after = learning_state_after or {}

    total = int(correct_count or 0) + int(wrong_count or 0)
    accuracy = round(int(correct_count or 0) / total, 3) if total else None
    lesson_global = lesson.get("global_lesson") or lesson.get("script_lesson")

    per_skill: dict[str, Any] = {}
    for name, score in skills.items():
        score_value = float(score or 0)
        per_skill[name] = {
            "accuracy": round(score_value, 3),
            "mastery": classify_mastery(score_value),
        }

    return {
        "course": str(course or "numeracy"),
        "module": lesson.get("module"),
        "module_name": lesson.get("module_name"),
        "lesson_global": lesson_global,
        "lesson_title": lesson.get("title"),
        "questions_correct": int(correct_count or 0),
        "questions_total": total,
        "accuracy": accuracy,
        "per_skill": per_skill,
        "mastery_signal": classify_mastery(accuracy) if total else MASTERY_INSUFFICIENT,
        "mastery_label": mastery_label(classify_mastery(accuracy) if total else MASTERY_INSUFFICIENT),
        "lesson_passed": lesson_passed(course, lesson_global, int(correct_count or 0), total),
        "lesson_mastery_line": lesson_mastery_line(course, lesson_global),
        "tarl_level_before": before.get("tarl_level"),
        "tarl_level_after": after.get("tarl_level"),
        "scaffold_depth_after": after.get("scaffold_depth"),
        "should_advance": bool(should_advance),
    }
