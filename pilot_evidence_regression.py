#!/usr/bin/env python3
"""Regression checks for Sabi pilot-proof cohort evidence (Layer C)."""

from __future__ import annotations

import sys

from launch_gates import build_launch_gate_report
from pilot_evidence import build_pilot_evidence_report, child_evidence, pilot_evidence_csv


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return bool(condition)


def _child(cid, base_num, cur_num, calls, seconds, *, mastered_num=0, probe=None, consent=True):
    row = {
        "id": cid,
        "name": cid,
        "participant_type": "child",
        "consent_status": "consented" if consent else None,
        "assent_recorded": bool(consent),
        "baseline_tarl_level": base_num,
        "baseline_reading_level": 0,
        "effective_state": {"tarl_level": cur_num, "current_module": 2, "literacy": {"tarl_reading_level": 0}},
        "mastery_map": {
            "numeracy": {
                "mastered_modules": mastered_num,
                "modules": [
                    {
                        "module": 1,
                        "module_name": "Counting and number sense",
                        "skill": "counting_number_sense",
                        "score": 0.9 if mastered_num else 0.35,
                        "mastery": "mastered" if mastered_num else "emerging",
                        "mastery_label": "Mastered" if mastered_num else "Still building",
                        "position": "completed" if mastered_num else "in_progress",
                    }
                ],
            },
            "literacy": {
                "mastered_modules": 0,
                "modules": [
                    {
                        "module": 1,
                        "module_name": "Beginning sounds",
                        "skill": "beginning_sounds",
                        "score": 0.4,
                        "mastery": "emerging",
                        "mastery_label": "Still building",
                        "position": "in_progress",
                    }
                ],
            },
        },
        "total_correct": 20,
        "total_wrong": 5,
        "total_sessions": calls,
        "calling": {"recent_call_count": calls, "recent_call_seconds": seconds},
    }
    if probe is not None:
        row["baseline_probe_score"], row["latest_probe_score"] = probe
    return row


def main() -> int:
    ok = True

    # Adult testers are excluded from cohort figures.
    adult = {"id": "a1", "participant_type": "adult tester", "effective_state": {"tarl_level": 4, "literacy": {}}, "mastery_map": {}, "calling": {}}
    kids = [
        _child("c1", 0, 2, 8, 2880, mastered_num=2, probe=(0.30, 0.60)),   # up 2 levels
        _child("c2", 1, 1, 1, 300, mastered_num=0, probe=(0.40, 0.50)),    # no level movement
        _child("c3", 0, 1, 4, 1200, mastered_num=1, probe=(0.20, 0.55)),   # up 1 level
    ]
    report = build_pilot_evidence_report([*kids, adult], cost_per_child=10.0)
    cohort = report["cohort"]

    ok &= check("excludes_adult_testers", cohort["children"] == 3, cohort["children"])
    num = cohort["tarl_movement"]["numeracy"]
    ok &= check("counts_children_up_one_plus_level", num["children_up_one_plus_level"] == 2, num)
    ok &= check("pct_up_level", num["pct_up_one_plus_level"] == round(2 / 3, 3), num["pct_up_one_plus_level"])
    ok &= check("baseline_distribution", num["baseline_distribution"] == {"0": 2, "1": 1}, num["baseline_distribution"])
    ok &= check("skills_mastered_total", cohort["mastery"]["skills_mastered_total"] == 3, cohort["mastery"])
    ok &= check("second_call_return_rate", cohort["dosage"]["second_call_return_rate"] == round(2 / 3, 3), cohort["dosage"])
    ok &= check("probe_effect_size_present", cohort["probe"]["n_paired"] == 3 and cohort["probe"]["effect_size_d"] is not None, cohort["probe"])
    ok &= check("cost_sd_per_dollar", cohort["cost"]["sd_per_dollar"] is not None, cohort["cost"])
    ok &= check("benchmarks_included", "connected" in report["benchmarks"] and "rori" in report["benchmarks"])
    ok &= check("research_protocol_rollup_present", cohort["research"]["stage"] == "ten_child_prepilot", cohort["research"])
    ok &= check("research_arm_distribution_present", cohort["research"]["arm_distribution"].get("measured_sabi_pre_pilot") == 3, cohort["research"])
    ok &= check("rct_advancement_present", len(cohort["rct_advancement"]["cards"]) >= 10, cohort["rct_advancement"])
    ok &= check("data_quality_present", "baseline_coverage" in cohort["research"]["data_quality"], cohort["research"]["data_quality"])
    ok &= check("publication_pack_present", cohort["research"]["publication_pack"]["total_count"] >= 10, cohort["research"]["publication_pack"])
    ok &= check("measurement_benchmark_ladder_present", len(cohort["research"]["measurement_quality_benchmarks"]) >= 5, cohort["research"])
    ok &= check("board_training_present", "no coaching" in cohort["research"]["board_training"]["facilitator_script"].lower(), cohort["research"]["board_training"])
    ok &= check("partner_implementation_kit_present", len(cohort["research"]["partner_implementation_kit"]["api_surfaces"]) >= 4, cohort["research"]["partner_implementation_kit"])
    ok &= check("research_design_note_present", "research_design" in report["notes"], report["notes"])
    indicators = report["learning_indicators"]
    ok &= check("learning_indicators_present", len(indicators) >= 8, indicators)
    ok &= check(
        "learning_indicators_replace_child_rows_with_signals",
        any(item["key"] == "numeracy_tarl_level_movement" and item["metric"] == "2/3 up one or more levels" for item in indicators)
        and any(item["type"] == "curriculum_skill" for item in indicators)
        and any(item["key"] == "second_call_return" for item in indicators),
        indicators,
    )
    ok &= check(
        "learning_indicator_evidence_carries_child_snippets",
        any(item.get("evidence") and item["evidence"][0].get("child_code", "").startswith("sabi-child-") for item in indicators),
        indicators,
    )

    public_csv = pilot_evidence_csv(report, mode="public")
    ok &= check("public_export_deidentifies_name", "name" not in public_csv.splitlines()[0] and "child_code" in public_csv.splitlines()[0], public_csv.splitlines()[0])
    ok &= check("public_export_strips_raw_audio_permission", "raw_audio_export_allowed" not in public_csv.splitlines()[0], public_csv.splitlines()[0])

    # Child record shape and no-baseline handling.
    rec = child_evidence(_child("cx", None, 3, 5, 1500))
    ok &= check("levels_gained_none_without_baseline", rec["numeracy"]["levels_gained"] is None, rec["numeracy"])
    ok &= check("dosage_hours_computed", rec["dosage"]["hours"] == round(1500 / 3600, 2), rec["dosage"])
    ok &= check("child_research_assignment_present", rec["research"]["assignment"]["arm"] == "measured_sabi_pre_pilot", rec["research"])

    # Empty cohort is safe.
    empty = build_pilot_evidence_report([])
    ok &= check("empty_cohort_safe", empty["cohort"]["children"] == 0 and empty["cohort"]["tarl_movement"]["numeracy"]["pct_up_one_plus_level"] is None)
    ok &= check("empty_cohort_has_preview_mode", empty["preview_mode"] is True and empty["preview_note"], empty)
    ok &= check(
        "empty_cohort_preview_indicators_are_complete",
        len(empty["preview_learning_indicators"]) >= 10
        and empty["preview_cohort"]["children"] == 4
        and any(item["status"] == "signal_visible" for item in empty["preview_learning_indicators"]),
        empty["preview_learning_indicators"],
    )
    empty_cards = {card["key"]: card for card in empty["cohort"]["rct_advancement"]["cards"]}
    ok &= check(
        "empty_cohort_rct_cards_are_ready_not_pending",
        empty_cards["baseline"]["status"] == "ready_to_capture"
        and empty_cards["data_quality"]["status"] == "instrumented"
        and empty_cards["learning_outcomes"]["status"] == "awaiting_live_cohort",
        empty_cards,
    )

    # Gate 6 wiring: movement gates the 10-child pre-pilot pass.
    learners_10 = [
        _child(f"k{i}", 0, (2 if i < 6 else 0), 5, 1500, probe=(0.3, 0.5)) for i in range(10)
    ]
    pilot = build_pilot_evidence_report(learners_10)
    gate_report = build_launch_gate_report(calls=[], learners=learners_10, pilot_evidence=pilot)
    ten_child = next(g for g in gate_report["gates"] if g["key"] == "ten_child_prepilot")
    ok &= check(
        "gate6_evidence_includes_movement",
        any("up 1+ numeracy level" in e for e in ten_child["evidence"]),
        ten_child["evidence"],
    )
    ok &= check(
        "gate6_evidence_includes_protocol_counts",
        any("pre/mid/post records" in e for e in ten_child["evidence"]),
        ten_child["evidence"],
    )
    ok &= check(
        "gate6_evidence_includes_publication_pack",
        any("publication pack" in e for e in ten_child["evidence"]),
        ten_child["evidence"],
    )

    # No movement -> movement flag blocks the pass path (learning_movement_ok False).
    flat = [_child(f"f{i}", 1, 1, 5, 1500) for i in range(10)]
    pilot_flat = build_pilot_evidence_report(flat)
    gate_flat = build_launch_gate_report(calls=[], learners=flat, pilot_evidence=pilot_flat)
    ten_flat = next(g for g in gate_flat["gates"] if g["key"] == "ten_child_prepilot")
    ok &= check("gate6_no_movement_not_pass", ten_flat["status"] != "pass", ten_flat["status"])

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
