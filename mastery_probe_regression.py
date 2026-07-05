#!/usr/bin/env python3
"""Regression checks for monthly mastery probe capture (Layer C)."""

from __future__ import annotations

import sys

from mastery_probe import (
    probe_capture_payload,
    score_from_counts,
    score_from_diagnostic_progress,
    score_from_scorecard,
    session_probe_score,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return bool(condition)


def main() -> int:
    ok = True

    ok &= check("score_from_counts_ok", score_from_counts(7, 10) == 0.7)
    ok &= check("score_from_counts_min_items", score_from_counts(4, 4) is None)

    progress = {
        "status": "placed",
        "results": [{"correct": True}, {"correct": False}, {"correct": True}, {"correct": True}],
    }
    ok &= check("diagnostic_probe_score", score_from_diagnostic_progress(progress) == 0.75, progress)

    scorecard = {"lesson_global": 12, "questions_correct": 8, "questions_total": 10}
    ok &= check("module_assessment_score", score_from_scorecard(scorecard) == 0.8, scorecard)

    state = {"diagnostic_results": progress}
    score, source = session_probe_score(learning_state=state, scorecard=None)
    ok &= check("session_probe_diagnostic", score == 0.75 and source == "diagnostic_baseline", (score, source))

    student = {}
    payload = probe_capture_payload(student, session_score=0.55, source="diagnostic_baseline")
    ok &= check("baseline_probe_written_once", payload.get("baseline_probe_score") == 0.55 and payload.get("latest_probe_score") == 0.55)
    ok &= check("history_appended", len(payload.get("probe_history") or []) == 1)

    student2 = {"baseline_probe_score": 0.4, "probe_history": [{"score": 0.4}]}
    follow = probe_capture_payload(student2, session_score=0.62, source="module_assessment")
    ok &= check("baseline_not_overwritten", "baseline_probe_score" not in follow)
    ok &= check("latest_updated", follow.get("latest_probe_score") == 0.62)

    ok &= check("invalid_source_skipped", probe_capture_payload({}, session_score=0.5, source="bad") == {})

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
