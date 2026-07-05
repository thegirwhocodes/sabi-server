"""Monthly mastery probe scoring for Sabi pilot evidence (Layer C).

The probe is a short, fixed, comparable oral assessment distinct from adaptive
lessons. Baseline is captured at diagnostic completion; follow-up probes update
`latest_probe_score` on module-assessment calls (curriculum gate lessons) so
cohort effect size (d) can be computed without waiting for a separate probe call
flow. A dedicated probe session kind can extend this later.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from curriculum_mastery import NUMERACY_MODULE_ASSESSMENTS

PROBE_MIN_ITEMS = 5
PROBE_SOURCES = {"diagnostic_baseline", "module_assessment", "monthly_probe"}


def score_from_counts(correct: int, total: int, *, min_items: int = PROBE_MIN_ITEMS) -> float | None:
    """Return accuracy 0.0-1.0 when enough items were attempted."""
    total = int(total or 0)
    if total < min_items:
        return None
    return round(int(correct or 0) / total, 3)


def score_from_diagnostic_progress(progress: dict[str, Any] | None) -> float | None:
    """Score the numeracy diagnostic when placement is complete."""
    if not progress or progress.get("status") not in {"placed", "complete"}:
        return None
    results = progress.get("results") or []
    if not results:
        return None
    correct = sum(1 for row in results if row.get("correct"))
    return score_from_counts(correct, len(results), min_items=3)


def score_from_scorecard(scorecard: dict[str, Any] | None) -> float | None:
    """Score a module-assessment lesson call (fixed n-of-m gate items)."""
    if not scorecard:
        return None
    lesson_global = scorecard.get("lesson_global")
    if lesson_global not in NUMERACY_MODULE_ASSESSMENTS:
        return None
    return score_from_counts(
        int(scorecard.get("questions_correct") or 0),
        int(scorecard.get("questions_total") or 0),
        min_items=PROBE_MIN_ITEMS,
    )


def session_probe_score(
    *,
    learning_state: dict[str, Any] | None,
    scorecard: dict[str, Any] | None,
    correct_count: int = 0,
    wrong_count: int = 0,
) -> tuple[float | None, str | None]:
    """Pick the best probe score for this ended session."""
    state = learning_state or {}
    if str(state.get("session_kind") or "") == "probe":
        score = score_from_counts(correct_count, correct_count + wrong_count)
        return score, "monthly_probe"

    diagnostic = state.get("diagnostic_results")
    if isinstance(diagnostic, dict) and diagnostic.get("status") in {"placed", "complete"}:
        score = score_from_diagnostic_progress(diagnostic)
        if score is not None:
            return score, "diagnostic_baseline"

    assessment_score = score_from_scorecard(scorecard)
    if assessment_score is not None:
        return assessment_score, "module_assessment"
    return None, None


def probe_capture_payload(
    student: dict,
    *,
    session_score: float | None,
    source: str | None,
) -> dict[str, Any]:
    """Merge probe fields into a student update payload.

    Baseline is written once; every valid probe also updates latest and history.
    """
    if session_score is None or source not in PROBE_SOURCES:
        return {}

    now = datetime.now(timezone.utc).isoformat()
    score = round(float(session_score), 3)
    history = student.get("probe_history") if isinstance(student.get("probe_history"), list) else []
    entry = {"score": score, "source": source, "recorded_at": now}
    payload: dict[str, Any] = {
        "latest_probe_score": score,
        "latest_probe_at": now,
        "probe_history": [*history, entry][-24:],
    }
    if student.get("baseline_probe_score") is None:
        payload["baseline_probe_score"] = score
        payload["baseline_probe_at"] = now
        payload["baseline_probe_source"] = source
    return payload
