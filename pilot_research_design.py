"""TEP/TaRL-informed pilot research protocol for Sabi.

This module keeps the measurement design close to the call state. The 10-child
pre-pilot is evidence-grade and RCT-ready, but it should not be described as a
publishable RCT by itself. The same state shape can scale into the 30-child
micro-randomization and the 300-child controlled pilot.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any


PROTOCOL_VERSION = "sabi-tep-tarl-rct-v0.1"

PHILOSOPHY = [
    "TEP/LEARNigeria lens: assessment validity, Nigerian learner fit, and safe claim language.",
    "TaRL lens: assess actual level, teach at that level, remediate prerequisites, and reassess regularly.",
    "RCT lens: preserve assignment, baseline, midline, endline, dosage, attrition, and analysis fields from day one.",
]

STUDY_STAGES = {
    "ten_child_prepilot": {
        "label": "10-child pre-pilot",
        "design": "Within-child pre/mid/post evidence run; RCT-ready but not powered as an RCT.",
        "target_n": 10,
        "claim_boundary": "Use for product safety, feasibility, placement validity, and learning-signal readiness only.",
    },
    "thirty_child_micro_rct": {
        "label": "30-child micro-randomization",
        "design": "Blocked encouragement or waitlist randomization after baseline; checks feasibility of random assignment.",
        "target_n": 30,
        "claim_boundary": "Use for feasibility and variance estimates, not definitive effect claims.",
    },
    "three_hundred_child_rct": {
        "label": "300-child controlled pilot",
        "design": "Blocked learner/household randomization with baseline, midline, endline, and independent assessor review.",
        "target_n": 300,
        "claim_boundary": "Powered for d >= 0.30 if implementation and attrition targets hold.",
    },
}

ASSESSMENT_PHASES = {
    "pre_baseline": {
        "label": "Pre baseline",
        "call_window": "before or during first diagnostic call",
        "trigger": "diagnostic placement or fixed oral baseline probe",
        "purpose": "Freeze TaRL starting level before Sabi can teach the child.",
    },
    "midline": {
        "label": "Midline",
        "call_window": "around call 3-5 or day 7",
        "trigger": "fixed oral mastery probe before adaptive teaching",
        "purpose": "Catch early learning signal, confusion, attrition risk, and STT/assessment drift.",
    },
    "post_endline": {
        "label": "Post endline",
        "call_window": "around call 8+ or day 14 in the pre-pilot",
        "trigger": "fixed oral endline probe with the same construct map as baseline",
        "purpose": "Measure short-run TaRL movement and mastery-probe gain.",
    },
    "retention_followup": {
        "label": "Retention follow-up",
        "call_window": "around day 30 when feasible",
        "trigger": "short delayed-recall probe",
        "purpose": "Check whether the child keeps the skill after spacing.",
    },
}

STUDY_ARMS = {
    "measured_sabi_pre_pilot": {
        "label": "Measured Sabi pre-pilot",
        "description": "Everyone receives Sabi; the experiment value is clean pre/mid/post measurement and review.",
    },
    "daily_sabi": {
        "label": "Daily Sabi",
        "description": "High-dosage intervention arm for micro/full RCT stages.",
    },
    "light_touch_sabi": {
        "label": "Light-touch Sabi",
        "description": "Lower-dosage comparison or encouragement arm when a micro-randomization is approved.",
    },
    "waitlist_then_sabi": {
        "label": "Waitlist then Sabi",
        "description": "Ethical delayed-start control after baseline, used only with explicit consent and review.",
    },
}


def configured_stage() -> str:
    stage = str(os.getenv("SABI_PILOT_RESEARCH_STAGE") or "ten_child_prepilot").strip().lower()
    return stage if stage in STUDY_STAGES else "ten_child_prepilot"


def normalize_measurements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict) and item.get("phase")]


def stable_subject_key(student: dict[str, Any] | None) -> str:
    student = student or {}
    for key in ("learner_key", "phone_household_key", "phone_number_normalized", "phone_number", "id", "name"):
        value = str(student.get(key) or "").strip()
        if value:
            return value
    return "unknown-subject"


def _bucket(subject_key: str, modulo: int) -> int:
    digest = hashlib.sha256(subject_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(1, modulo)


def assignment_for_student(student: dict[str, Any] | None, *, stage: str | None = None) -> dict[str, Any]:
    student = student or {}
    stage = stage or configured_stage()
    existing_state = student.get("research_state") if isinstance(student.get("research_state"), dict) else {}
    existing_assignment = existing_state.get("assignment") if isinstance(existing_state.get("assignment"), dict) else {}
    explicit_arm = (
        student.get("study_arm")
        or existing_assignment.get("arm")
        or existing_state.get("study_arm")
    )
    if explicit_arm:
        arm = str(explicit_arm)
        return {
            "unit": "learner_household",
            "arm": arm,
            "label": STUDY_ARMS.get(arm, {}).get("label", arm.replace("_", " ")),
            "basis": "stored",
            "stratum": _stratum_for(student),
        }

    key = stable_subject_key(student)
    if stage == "thirty_child_micro_rct":
        arm = "daily_sabi" if _bucket(key, 2) == 0 else "waitlist_then_sabi"
        basis = "deterministic_blocked_hash_ready_for_review"
    elif stage == "three_hundred_child_rct":
        arms = ("daily_sabi", "light_touch_sabi", "waitlist_then_sabi")
        arm = arms[_bucket(key, len(arms))]
        basis = "deterministic_blocked_hash_ready_for_independent_randomization"
    else:
        arm = "measured_sabi_pre_pilot"
        basis = "single_arm_prepilot"

    return {
        "unit": "learner_household",
        "arm": arm,
        "label": STUDY_ARMS[arm]["label"],
        "basis": basis,
        "stratum": _stratum_for(student),
    }


def assessment_status_for(
    student: dict[str, Any] | None,
    *,
    calls_completed: int | None = None,
) -> dict[str, Any]:
    student = student or {}
    measurements = normalize_measurements(student.get("research_measurements"))
    if not measurements:
        existing_state = student.get("research_state") if isinstance(student.get("research_state"), dict) else {}
        measurements = normalize_measurements(existing_state.get("measurements"))

    completed = {str(item.get("phase")) for item in measurements}
    calls = int(calls_completed if calls_completed is not None else student.get("total_sessions") or 0)
    baseline_done = (
        "pre_baseline" in completed
        or student.get("baseline_probe_score") is not None
        or student.get("baseline_tarl_level") is not None
        or str(student.get("baseline_status") or "") == "done"
    )
    midline_done = "midline" in completed
    endline_done = "post_endline" in completed
    retention_done = "retention_followup" in completed

    if not baseline_done:
        due = "pre_baseline"
    elif calls >= 3 and not midline_done:
        due = "midline"
    elif calls >= 8 and not endline_done:
        due = "post_endline"
    elif calls >= 12 and not retention_done:
        due = "retention_followup"
    else:
        due = "monitoring"

    return {
        "calls_completed": calls,
        "completed_phases": sorted(completed),
        "baseline_done": baseline_done,
        "midline_done": midline_done,
        "endline_done": endline_done,
        "retention_done": retention_done,
        "next_due_phase": due,
        "next_due_label": ASSESSMENT_PHASES.get(due, {}).get("label", "Monitor"),
        "next_due_trigger": ASSESSMENT_PHASES.get(due, {}).get("trigger", "continue normal call monitoring"),
    }


def build_research_state(
    student: dict[str, Any] | None = None,
    *,
    calls_completed: int | None = None,
) -> dict[str, Any]:
    student = student or {}
    stage = str(student.get("study_stage") or configured_stage())
    if stage not in STUDY_STAGES:
        stage = configured_stage()
    measurements = normalize_measurements(student.get("research_measurements"))
    if not measurements:
        existing = student.get("research_state") if isinstance(student.get("research_state"), dict) else {}
        measurements = normalize_measurements(existing.get("measurements"))
    status = assessment_status_for({**student, "research_measurements": measurements}, calls_completed=calls_completed)
    assignment = assignment_for_student(student, stage=stage)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "study_stage": stage,
        "stage_label": STUDY_STAGES[stage]["label"],
        "design": STUDY_STAGES[stage]["design"],
        "claim_boundary": STUDY_STAGES[stage]["claim_boundary"],
        "philosophy": PHILOSOPHY,
        "assignment": assignment,
        "assessment_status": status,
        "measurements": measurements[-12:],
        "schedule": ASSESSMENT_PHASES,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def initial_research_payload(student: dict[str, Any] | None = None) -> dict[str, Any]:
    state = build_research_state(student or {})
    return {
        "study_stage": state["study_stage"],
        "study_arm": state["assignment"]["arm"],
        "research_measurements": state["measurements"],
        "research_state": state,
        "latest_assessment_phase": state["assessment_status"]["next_due_phase"],
        "next_assessment_due": state["assessment_status"]["next_due_phase"],
    }


def research_capture_payload(
    student: dict[str, Any] | None,
    *,
    learning_state: dict[str, Any] | None,
    call_count_after: int,
    probe_score: float | None,
    source: str | None,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Return DB fields to update after a completed call."""
    student = student or {}
    learning_state = learning_state or {}
    existing = normalize_measurements(student.get("research_measurements"))
    if not existing:
        previous_state = student.get("research_state") if isinstance(student.get("research_state"), dict) else {}
        existing = normalize_measurements(previous_state.get("measurements"))

    stage = str(student.get("study_stage") or configured_stage())
    status = assessment_status_for({**student, "research_measurements": existing}, calls_completed=call_count_after)
    due = status["next_due_phase"]
    ready = _phase_ready_to_capture(due, learning_state, probe_score)
    measurements = list(existing)
    timestamp_updates: dict[str, Any] = {}

    if ready and due != "monitoring" and due not in {m.get("phase") for m in measurements}:
        now = datetime.now(timezone.utc).isoformat()
        literacy = learning_state.get("literacy") if isinstance(learning_state.get("literacy"), dict) else {}
        entry = {
            "phase": due,
            "label": ASSESSMENT_PHASES[due]["label"],
            "recorded_at": now,
            "source": source or "call_state",
            "probe_score": round(float(probe_score), 3) if probe_score is not None else None,
            "numeracy_tarl_level": learning_state.get("tarl_level"),
            "literacy_tarl_level": literacy.get("tarl_reading_level"),
            "course": learning_state.get("course"),
            "calls_completed": int(call_count_after),
            "duration_seconds": int(duration_seconds or 0),
        }
        measurements.append(entry)
        if due == "pre_baseline":
            timestamp_updates["baseline_assessment_at"] = now
        elif due == "midline":
            timestamp_updates["midline_assessment_at"] = now
        elif due == "post_endline":
            timestamp_updates["endline_assessment_at"] = now
        elif due == "retention_followup":
            timestamp_updates["retention_assessment_at"] = now

    base_for_state = {
        **student,
        "study_stage": stage,
        "research_measurements": measurements,
    }
    research_state = build_research_state(base_for_state, calls_completed=call_count_after)
    return {
        "study_stage": research_state["study_stage"],
        "study_arm": research_state["assignment"]["arm"],
        "research_measurements": measurements[-24:],
        "research_state": research_state,
        "latest_assessment_phase": (measurements[-1]["phase"] if measurements else None),
        "next_assessment_due": research_state["assessment_status"]["next_due_phase"],
        **timestamp_updates,
    }


def research_prompt_block(research_state: dict[str, Any] | None) -> str:
    if not isinstance(research_state, dict):
        return ""
    status = research_state.get("assessment_status") if isinstance(research_state.get("assessment_status"), dict) else {}
    due = status.get("next_due_phase")
    if not due or due == "monitoring":
        due_line = "No fixed pre/mid/post probe is due this call; keep normal lesson evidence clean."
    else:
        phase = ASSESSMENT_PHASES.get(str(due), {})
        due_line = (
            f"Next fixed assessment due: {phase.get('label', due)}. "
            f"Trigger: {phase.get('trigger', 'fixed oral probe')}."
        )
    assignment = research_state.get("assignment") if isinstance(research_state.get("assignment"), dict) else {}
    return f"""

## PILOT EVIDENCE PROTOCOL
- Protocol: {research_state.get('protocol_version', PROTOCOL_VERSION)}
- Stage: {research_state.get('stage_label', '10-child pre-pilot')}
- Design: {research_state.get('design', STUDY_STAGES['ten_child_prepilot']['design'])}
- Study arm: {assignment.get('label', assignment.get('arm', 'measured pre-pilot'))}
- Assessment rule: {due_line}
- During a fixed probe, ask neutrally, do not coach inside the measured item, then resume warm TaRL teaching.
- Claim boundary: {research_state.get('claim_boundary', STUDY_STAGES['ten_child_prepilot']['claim_boundary'])}"""


def cohort_research_rollup(children: list[dict[str, Any]]) -> dict[str, Any]:
    arm_counts: dict[str, int] = {}
    phase_counts = {phase: 0 for phase in ASSESSMENT_PHASES}
    due_counts: dict[str, int] = {}
    for child in children:
        research = child.get("research") if isinstance(child.get("research"), dict) else {}
        assignment = research.get("assignment") if isinstance(research.get("assignment"), dict) else {}
        arm = str(assignment.get("arm") or "unknown")
        arm_counts[arm] = arm_counts.get(arm, 0) + 1
        status = research.get("assessment_status") if isinstance(research.get("assessment_status"), dict) else {}
        due = str(status.get("next_due_phase") or "unknown")
        due_counts[due] = due_counts.get(due, 0) + 1
        phases = {str(item.get("phase")) for item in normalize_measurements(research.get("measurements"))}
        for phase in phase_counts:
            if phase in phases:
                phase_counts[phase] += 1
    stage = configured_stage()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "stage": stage,
        "stage_label": STUDY_STAGES[stage]["label"],
        "design": STUDY_STAGES[stage]["design"],
        "philosophy": PHILOSOPHY,
        "arm_distribution": arm_counts,
        "measurement_counts": phase_counts,
        "next_due_counts": due_counts,
        "rct_readiness": {
            "assignment_recorded": sum(arm_counts.values()),
            "baseline_records": phase_counts["pre_baseline"],
            "midline_records": phase_counts["midline"],
            "endline_records": phase_counts["post_endline"],
            "retention_records": phase_counts["retention_followup"],
        },
        "claim_boundary": STUDY_STAGES[stage]["claim_boundary"],
        "next_design_step": (
            "For the 10-child pre-pilot, complete pre/mid/post probes and review every first call. "
            "For the 30-child micro-pilot, switch SABI_PILOT_RESEARCH_STAGE to thirty_child_micro_rct "
            "only after consent scripts and independent review are ready."
        ),
    }


def _phase_ready_to_capture(due: str, learning_state: dict[str, Any], probe_score: float | None) -> bool:
    if due == "monitoring":
        return False
    if probe_score is not None:
        return True
    if due == "pre_baseline":
        return str(learning_state.get("diagnostic_status") or "") == "done"
    return False


def _stratum_for(student: dict[str, Any]) -> dict[str, Any]:
    state = student.get("effective_state") if isinstance(student.get("effective_state"), dict) else {}
    if not state:
        state = student.get("learning_state") if isinstance(student.get("learning_state"), dict) else {}
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    return {
        "baseline_numeracy_level": student.get("baseline_tarl_level"),
        "baseline_literacy_level": student.get("baseline_reading_level"),
        "current_numeracy_level": state.get("tarl_level") or student.get("tarl_level"),
        "current_literacy_level": literacy.get("tarl_reading_level"),
        "network": student.get("network"),
    }
