"""Launch-gate evidence report for Sabi pre-pilot changes."""

from __future__ import annotations

import os
import time
from typing import Any


def build_launch_gate_report(
    *,
    calls: list[dict[str, Any]],
    learners: list[dict[str, Any]],
    intron_api_key_present: bool = False,
    pilot_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a conservative launch-readiness report from existing evidence."""
    call_count = len(calls)
    calls_with_turns = [call for call in calls if int(call.get("turn_count") or 0) > 0]
    long_calls = [call for call in calls if int(call.get("duration_seconds") or 0) >= 300]
    adult_canary_calls = [
        call
        for call in calls
        if int(call.get("duration_seconds") or 0) >= 180
        and int(call.get("user_turns") or 0) >= 3
        and int(call.get("assistant_turns") or 0) >= 3
    ]
    flagged_calls = [call for call in calls if call.get("quality_flags")]
    no_child_turn_calls = [call for call in calls if int(call.get("user_turns") or 0) <= 0]
    child_profiles = [learner for learner in learners if _is_child_profile(learner)]
    consented_children = [
        learner
        for learner in child_profiles
        if learner.get("consent_status")
        or learner.get("consent_recorded")
        or learner.get("caregiver_phone")
    ]
    children_with_calls = [
        learner
        for learner in child_profiles
        if int((learner.get("calling") or {}).get("recent_call_count") or 0) > 0
    ]
    total_user_turns = sum(int(call.get("user_turns") or 0) for call in calls)
    total_assistant_turns = sum(int(call.get("assistant_turns") or 0) for call in calls)
    max_duration = max([int(call.get("duration_seconds") or 0) for call in calls] or [0])

    # Learning-movement evidence for the 10-child pre-pilot gate (Layer C).
    movement_evidence: list[str] = []
    learning_movement_ok = True
    if pilot_evidence is not None:
        cohort = pilot_evidence.get("cohort") or {}
        tarl = cohort.get("tarl_movement") or {}
        num_move = tarl.get("numeracy") or {}
        lit_move = tarl.get("literacy") or {}
        moved_up = int(num_move.get("children_up_one_plus_level") or 0) + int(lit_move.get("children_up_one_plus_level") or 0)
        learning_movement_ok = moved_up >= 1
        research = cohort.get("research") or {}
        readiness = research.get("rct_readiness") or {}
        measurement_counts = research.get("measurement_counts") or {}
        consent_counts = research.get("consent_counts") or {}
        data_quality = research.get("data_quality") or {}
        publication_pack = research.get("publication_pack") or {}
        movement_evidence = [
            f"{num_move.get('children_up_one_plus_level') or 0} children up 1+ numeracy level (pct {num_move.get('pct_up_one_plus_level')})",
            f"{lit_move.get('children_up_one_plus_level') or 0} children up 1+ literacy level (pct {lit_move.get('pct_up_one_plus_level')})",
            f"{(cohort.get('mastery') or {}).get('skills_mastered_total', 0)} skill-modules mastered across cohort",
            f"probe effect size d={ (cohort.get('probe') or {}).get('effect_size_d') }",
            f"Publishable-grade protocol: {research.get('stage_label', '10-child pre-pilot')}",
            (
                "pre/mid/post records: "
                f"{measurement_counts.get('pre_baseline', readiness.get('baseline_records', 0))}/"
                f"{measurement_counts.get('midline', readiness.get('midline_records', 0))}/"
                f"{measurement_counts.get('post_endline', readiness.get('endline_records', 0))}"
            ),
            f"study arms recorded: {readiness.get('assignment_recorded', 0)}",
            (
                "consent/assent: "
                f"{consent_counts.get('caregiver_consent', 0)} caregiver / "
                f"{consent_counts.get('child_assent', 0)} child assent"
            ),
            (
                "data quality: "
                f"{data_quality.get('fixed_probe_events', 0)} fixed-probe events / "
                f"{data_quality.get('item_response_records', 0)} item responses / "
                f"{data_quality.get('pending_item_scores', 0)} pending item scores"
            ),
            (
                "publication pack: "
                f"{publication_pack.get('ready_count', 0)}/{publication_pack.get('total_count', 0)} artifacts ready"
            ),
        ]

    gates = [
        _gate(
            key="baseline_capture",
            name="Baseline capture",
            status="pass" if call_count >= 5 and calls_with_turns and long_calls else "watch",
            summary="Current working route has enough recent evidence to compare future changes."
            if call_count >= 5 and calls_with_turns and long_calls
            else "Keep collecting baseline calls before switching providers or prompts.",
            evidence=[
                f"{call_count} recent call records",
                f"{len(calls_with_turns)} calls with per-turn evidence",
                f"{len(long_calls)} calls at or above 5 minutes",
                f"longest call {max_duration}s",
            ],
            next_action="Place or review at least 5 adult baseline calls, including one full 5-7 minute lesson.",
        ),
        _gate(
            key="offline_replay",
            name="Offline replay",
            status="watch" if calls_with_turns else "not_started",
            summary="Saved per-turn clips exist for provider bake-offs."
            if calls_with_turns
            else "No per-turn clips are available in the current filtered set.",
            evidence=[
                f"{len(calls_with_turns)} calls have child/Sabi turn clips",
                "Use /admin/stt/intron-test for clip replay",
            ],
            next_action="Build the gold clip set for Naira answers, names, and literacy words, then store old-vs-new STT verdicts.",
        ),
        _gate(
            key="isolated_route",
            name="Isolated route",
            status="watch" if intron_api_key_present else "blocked",
            summary="Intron test route can be exercised."
            if intron_api_key_present
            else "Intron route exists, but the server has no INTRON_API_KEY, so it will fall back.",
            evidence=[
                "Production AudioSocket remains 9019",
                "Intron test AudioSocket is 9020",
                "Asterisk context: sabi-callback-intron",
                f"INTRON_API_KEY present: {bool(intron_api_key_present)}",
            ],
            next_action="Add INTRON_API_KEY before treating the Intron canary as a real provider test.",
        ),
        _gate(
            key="adult_canary",
            name="Adult canary",
            status="pass"
            if len(adult_canary_calls) >= 5 and total_user_turns >= 20 and total_assistant_turns >= 20
            else "watch",
            summary="Adult calls have enough turn evidence for a first canary read."
            if len(adult_canary_calls) >= 5 and total_user_turns >= 20 and total_assistant_turns >= 20
            else "Adult canary evidence is still thin.",
            evidence=[
                f"{len(adult_canary_calls)} adult-like calls at or above 3 minutes with both sides speaking",
                f"{total_user_turns} child/user turns",
                f"{total_assistant_turns} Sabi turns",
                f"{len(flagged_calls)} calls currently flagged",
                f"{len(no_child_turn_calls)} calls with no child/user turns",
            ],
            next_action="Run 5 adult canary calls and review false-wrong, latency, and 'I can't hear you' loops before children.",
        ),
        _gate(
            key="child_canary",
            name="Child canary",
            status="pass"
            if len(consented_children) >= 2 and len(children_with_calls) >= 2
            else ("watch" if child_profiles else "not_started"),
            summary="Small child canary has consent and first-call evidence."
            if len(consented_children) >= 2 and len(children_with_calls) >= 2
            else "Do not expose children until consented child profiles and first-call review are visible.",
            evidence=[
                f"{len(child_profiles)} child/pre-pilot profiles",
                f"{len(consented_children)} child profiles with consent/caregiver evidence",
                f"{len(children_with_calls)} child profiles with at least one call",
            ],
            next_action="Start with 2 consented children, review both first calls within 24 hours, then decide whether to continue.",
        ),
        _gate(
            key="ten_child_prepilot",
            name="10-child pre-pilot",
            status="pass"
            if len(consented_children) >= 10 and len(children_with_calls) >= 8 and learning_movement_ok
            else ("watch" if len(consented_children) >= 2 else "not_started"),
            summary="10-child pre-pilot has enough enrolled, active children and measured learning movement."
            if len(consented_children) >= 10 and len(children_with_calls) >= 8 and learning_movement_ok
            else "The full pre-pilot is not ready yet.",
            evidence=[
                f"{len(consented_children)} consented/caregiver-linked children",
                f"{len(children_with_calls)} children with calls",
                "Target: 10 consented children, 80% first-call completion, 50% second-call return",
                *movement_evidence,
            ],
            next_action="Finish consent, child profile linkage, first-call reviews, second-call return, pre/mid/post probe capture, and measurable TaRL level movement (see /admin/pilot-evidence).",
        ),
    ]

    overall = _overall_status(gates)
    return {
        "status": "ok",
        "generated_at": int(time.time()),
        "overall_status": overall,
        "summary": _overall_summary(overall),
        "metrics": {
            "recent_calls": call_count,
            "calls_with_turn_evidence": len(calls_with_turns),
            "long_calls_5m_plus": len(long_calls),
            "adult_canary_calls": len(adult_canary_calls),
            "flagged_calls": len(flagged_calls),
            "total_user_turns": total_user_turns,
            "total_sabi_turns": total_assistant_turns,
            "child_profiles": len(child_profiles),
            "consented_children": len(consented_children),
            "children_with_calls": len(children_with_calls),
        },
        "config": {
            "production_audiosocket_port": 9019,
            "intron_audiosocket_port": int(os.getenv("SABI_INTRON_AUDIOSOCKET_PORT", "9020")),
            "intron_api_key_present": bool(intron_api_key_present),
            "stt_provider": os.getenv("SABI_STT_PROVIDER", "default/env"),
            "literacy_stt_provider": os.getenv("SABI_LITERACY_STT_PROVIDER", "default/env"),
            "test_stt_provider": os.getenv("SABI_STT_TEST_PROVIDER", "intron_first"),
        },
        "gates": gates,
    }


def _gate(
    *,
    key: str,
    name: str,
    status: str,
    summary: str,
    evidence: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "next_action": next_action,
    }


def _overall_status(gates: list[dict[str, Any]]) -> str:
    if any(gate.get("status") == "blocked" for gate in gates):
        return "blocked"
    if any(gate.get("status") in {"watch", "not_started"} for gate in gates):
        return "watch"
    return "pass"


def _overall_summary(status: str) -> str:
    if status == "pass":
        return "All current launch gates are green for the selected evidence window."
    if status == "blocked":
        return "At least one launch gate is blocked; do not expose the risky path to children."
    return "Some evidence exists, but Sabi is still in controlled testing mode."


def _is_child_profile(record: dict[str, Any]) -> bool:
    type_value = str(
        record.get("participant_type")
        or record.get("profile_type")
        or record.get("learner_type")
        or record.get("kind")
        or ""
    ).lower()
    school = str(
        record.get("school_status")
        or record.get("enrollment_status")
        or record.get("child_status")
        or ""
    ).lower()
    has_pilot_fields = bool(
        record.get("consent_status")
        or record.get("assent_status")
        or record.get("caregiver_phone")
        or record.get("network")
        or record.get("prepilot_status")
        or record.get("is_child")
    )
    if any(word in type_value for word in ("adult", "tester", "staff")):
        return False
    return (
        "child" in type_value
        or "student" in type_value
        or "school" in school
        or has_pilot_fields
    )
