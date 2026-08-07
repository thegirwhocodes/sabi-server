"""Authoritative grading evidence for Sabi's Gemini Live numeracy route.

Gemini owns the conversation, but it does not own correctness or mastery.  This
module keeps those decisions deterministic and auditable across phone calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


GRADER_VERSION = "sabi_numeric_v2"
MAX_STORED_EVENTS = 100
MASTERY_WINDOW = 5
MASTERY_CORRECT_REQUIRED = 4
MASTERY_CALLS_REQUIRED = 2
MASTERY_ITEM_FORMS_REQUIRED = 2

SCORABLE = "scorable"
NOT_SCORABLE = "not_scorable"
CORRECT = "correct"
INCORRECT = "incorrect"
INDETERMINATE = "indeterminate"
INDEPENDENT = "independent"
SCAFFOLDED = "scaffolded"
MODELLED = "modelled"


def make_evidence_event(
    *,
    call_id: str,
    item_id: str,
    item_form: str,
    skill: str,
    expected_answer: int,
    learner_answer: str,
    heard_numbers: list[int],
    audio_scorability: str,
    academic_correctness: str,
    independence: str,
    prompt_level: str,
    attempt_index: int,
) -> dict[str, Any]:
    """Create one versioned response event with the full grading rubric."""
    return {
        "event_id": f"{call_id}:{item_id}:{max(1, int(attempt_index))}",
        "call_id": str(call_id),
        "item_id": str(item_id),
        "item_form": str(item_form),
        "skill": str(skill),
        "expected_answer": int(expected_answer),
        "learner_answer": " ".join(str(learner_answer or "").split()),
        "heard_numbers": [int(value) for value in heard_numbers],
        "audio_scorability": str(audio_scorability),
        "academic_correctness": str(academic_correctness),
        "independence": str(independence),
        "prompt_level": str(prompt_level),
        "attempt_index": max(1, int(attempt_index)),
        "grader_version": GRADER_VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def _independent_probe_window(
    events: list[dict[str, Any]], skill: str
) -> list[dict[str, Any]]:
    """Return the last five unique, scorable, independent probes.

    Repeated attempts at the same item are instructional evidence, but they do
    not create extra mastery votes.  The latest eligible attempt for each item
    is retained before the rolling window is selected.
    """
    eligible = [
        event
        for event in events
        if event.get("skill") == skill
        and event.get("audio_scorability") == SCORABLE
        and event.get("academic_correctness") in {CORRECT, INCORRECT}
        and event.get("independence") == INDEPENDENT
        and event.get("item_id")
    ]
    latest_by_item: dict[str, dict[str, Any]] = {}
    item_order: list[str] = []
    for event in eligible:
        item_id = str(event["item_id"])
        if item_id in latest_by_item:
            item_order.remove(item_id)
        latest_by_item[item_id] = event
        item_order.append(item_id)
    return [latest_by_item[item_id] for item_id in item_order[-MASTERY_WINDOW:]]


def summarize_mastery(
    events: list[dict[str, Any]],
    skill: str,
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply Sabi's proposed 4-of-5, two-call mastery rule."""
    window = _independent_probe_window(events, skill)
    correct = sum(event.get("academic_correctness") == CORRECT for event in window)
    calls = sorted({str(event.get("call_id") or "") for event in window if event.get("call_id")})
    forms = sorted({str(event.get("item_form") or "") for event in window if event.get("item_form")})
    criteria = {
        "window_complete": len(window) >= MASTERY_WINDOW,
        "correct_threshold_met": correct >= MASTERY_CORRECT_REQUIRED,
        "two_calls_met": len(calls) >= MASTERY_CALLS_REQUIRED,
        "two_item_forms_met": len(forms) >= MASTERY_ITEM_FORMS_REQUIRED,
    }
    secure = all(criteria.values())
    previous = previous or {}
    previous_status = str(previous.get("status") or "not_started")
    previous_calls = {str(value) for value in previous.get("evidence_call_ids") or []}
    latest = window[-1] if window else {}
    later_correct_probe = bool(
        previous_status in {"secure", "retained"}
        and latest.get("academic_correctness") == CORRECT
        and str(latest.get("call_id") or "") not in previous_calls
    )
    if secure and later_correct_probe:
        status = "retained"
    elif secure:
        status = "secure"
    elif not window:
        status = "not_started"
    elif len(window) < MASTERY_WINDOW or len(calls) < MASTERY_CALLS_REQUIRED:
        status = "emerging"
    else:
        status = "developing"
    return {
        "skill": skill,
        "status": status,
        "independent_window_size": len(window),
        "independent_correct": int(correct),
        "independent_accuracy": round(correct / len(window), 3) if window else None,
        "evidence_call_ids": calls,
        "item_forms": forms,
        "item_ids": [str(event.get("item_id")) for event in window],
        "criteria": criteria,
        "rule": "4_of_last_5_independent_across_2_calls_and_2_item_forms",
        "grader_version": GRADER_VERSION,
    }


def update_grading_state(
    learning_state: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    """Append evidence and refresh its skill mastery without losing other state."""
    updated = dict(learning_state or {})
    grading = dict(updated.get("grading_evidence") or {})
    events = [dict(row) for row in grading.get("events") or [] if isinstance(row, dict)]
    events.append(dict(event))
    events = events[-MAX_STORED_EVENTS:]
    skills = dict(grading.get("skills") or {})
    skill = str(event.get("skill") or "numeracy")
    skills[skill] = summarize_mastery(events, skill, previous=skills.get(skill))
    grading.update(
        {
            "version": GRADER_VERSION,
            "events": events,
            "skills": skills,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    updated["grading_evidence"] = grading
    updated["updated_at"] = grading["updated_at"]
    return updated


def session_score(events: list[dict[str, Any]], skill: str) -> dict[str, Any]:
    """Build backend counts that keep independent and supported work separate."""
    scorable = [event for event in events if event.get("audio_scorability") == SCORABLE]
    independent = [event for event in scorable if event.get("independence") == INDEPENDENT]
    supported = [event for event in scorable if event.get("independence") != INDEPENDENT]
    independent_correct = sum(event.get("academic_correctness") == CORRECT for event in independent)
    independent_incorrect = sum(event.get("academic_correctness") == INCORRECT for event in independent)
    supported_correct = sum(event.get("academic_correctness") == CORRECT for event in supported)
    supported_incorrect = sum(event.get("academic_correctness") == INCORRECT for event in supported)
    not_scorable = sum(event.get("audio_scorability") == NOT_SCORABLE for event in events)
    independent_total = independent_correct + independent_incorrect
    return {
        "skill": skill,
        "correct_count": int(independent_correct),
        "wrong_count": int(independent_incorrect),
        "independent_correct": int(independent_correct),
        "independent_incorrect": int(independent_incorrect),
        "supported_correct": int(supported_correct),
        "supported_incorrect": int(supported_incorrect),
        "not_scorable": int(not_scorable),
        "independent_accuracy": (
            round(independent_correct / independent_total, 3) if independent_total else None
        ),
        "grader_version": GRADER_VERSION,
    }
