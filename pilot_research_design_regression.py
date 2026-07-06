#!/usr/bin/env python3
"""Regression checks for Sabi's publishable-grade pilot protocol."""

from __future__ import annotations

import sys

from pilot_research_design import (
    ASSESSMENT_PHASES,
    ASSESSMENT_ITEMS,
    PROTOCOL_VERSION,
    assignment_for_student,
    assessment_items_for_phase,
    build_research_state,
    cohort_research_rollup,
    consent_state_for,
    fixed_probe_plan_for,
    evidence_protocol_kit,
    protocol_record,
    research_capture_payload,
    research_prompt_block,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return bool(condition)


def main() -> int:
    ok = True
    student = {
        "id": "kid-1",
        "phone_number_normalized": "+2348000000001",
        "participant_type": "child",
        "consent_status": "consented",
        "assent_recorded": True,
        "learning_state": {"tarl_level": 1, "literacy": {"tarl_reading_level": 0}},
    }
    placed_student = {**student, "baseline_tarl_level": 0}

    state = build_research_state(student, calls_completed=0)
    ok &= check("uses_protocol_version", state["protocol_version"] == PROTOCOL_VERSION, state)
    ok &= check("default_stage_is_prepilot", state["study_stage"] == "ten_child_prepilot", state)
    ok &= check("prep_pilot_single_arm", state["assignment"]["arm"] == "measured_sabi_pre_pilot", state["assignment"])
    ok &= check("baseline_due_first", state["assessment_status"]["next_due_phase"] == "pre_baseline", state["assessment_status"])
    ok &= check("protocol_record_attached", state["protocol"]["protocol_id"] == "sabi-publishable-evidence-001", state["protocol"])
    ok &= check("consent_state_attached", state["consent"]["child_pilot_ready"] is True, state["consent"])
    ok &= check("fixed_probe_plan_has_items", state["fixed_probe_plan"]["item_count"] >= 2, state["fixed_probe_plan"])
    prompt = research_prompt_block(state)
    ok &= check("prompt_mentions_publishable_grade", "publishable-grade methods from call one" in prompt, prompt)
    ok &= check("prompt_mentions_no_coaching", "do not hint" in prompt.lower(), prompt)

    blocked_consent = consent_state_for({"consent_status": None})
    blocked_plan = fixed_probe_plan_for({"consent_status": None}, assessment_status={"next_due_phase": "pre_baseline"}, consent_state=blocked_consent)
    ok &= check("probe_blocks_without_consent", blocked_plan["mode"] == "consent_hold", blocked_plan)
    ok &= check("item_bank_seeded", len(assessment_items_for_phase("pre_baseline")) >= 4 and len(ASSESSMENT_ITEMS) >= 8)
    ok &= check("protocol_has_primary_outcomes", len(protocol_record()["primary_outcomes"]) >= 3)

    capture = research_capture_payload(
        student,
        learning_state={"diagnostic_status": "done", "tarl_level": 1, "course": "numeracy", "literacy": {"tarl_reading_level": 0}},
        call_count_after=1,
        probe_score=0.4,
        source="diagnostic_baseline",
        duration_seconds=360,
    )
    ok &= check("captures_pre_baseline_measurement", capture["research_measurements"][0]["phase"] == "pre_baseline", capture)
    ok &= check("captures_assessment_event", capture["assessment_events"][0]["phase"] == "pre_baseline", capture["assessment_events"])
    ok &= check("creates_pending_item_responses", len(capture["item_responses"]) >= 4 and capture["item_responses"][0]["review_status"] == "pending_item_level_scoring", capture["item_responses"])
    ok &= check("next_due_midline_after_baseline", capture["next_assessment_due"] == "midline" or capture["next_assessment_due"] == "monitoring", capture)

    micro = assignment_for_student(placed_student, stage="thirty_child_micro_rct")
    ok &= check("micro_rct_assigns_comparison_arm", micro["arm"] in {"daily_sabi", "waitlist_then_sabi"}, micro)
    full = assignment_for_student(placed_student, stage="three_hundred_child_rct")
    ok &= check("full_rct_assigns_three_arm_design", full["arm"] in {"daily_sabi", "light_touch_sabi", "waitlist_then_sabi"}, full)

    rollup = cohort_research_rollup([
        {"research": capture["research_state"]},
        {"research": build_research_state({"id": "kid-2"}, calls_completed=0)},
    ])
    ok &= check("rollup_counts_baseline", rollup["measurement_counts"]["pre_baseline"] == 1, rollup)
    ok &= check("rollup_includes_all_phases", all(phase in rollup["measurement_counts"] for phase in ASSESSMENT_PHASES), rollup)
    ok &= check("rollup_has_data_quality", rollup["data_quality"]["item_response_records"] >= 4, rollup["data_quality"])
    ok &= check("rollup_has_publication_pack", rollup["publication_pack"]["total_count"] >= 10, rollup["publication_pack"])
    ok &= check("rollup_has_measurement_benchmarks", len(rollup["measurement_quality_benchmarks"]) >= 5, rollup["measurement_quality_benchmarks"])
    ok &= check("rollup_has_board_training", len(rollup["board_training"]["modules"]) >= 5, rollup["board_training"])
    kit = evidence_protocol_kit()
    ok &= check("kit_has_partner_api_surfaces", len(kit["kit"]["api_surfaces"]) >= 4, kit["kit"])
    ok &= check("kit_has_claim_ladder", len(kit["kit"]["claim_ladder"]) == 3, kit["kit"]["claim_ladder"])
    ok &= check("kit_exposes_item_bank", len(kit["assessment_items"]) >= 8, kit)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
