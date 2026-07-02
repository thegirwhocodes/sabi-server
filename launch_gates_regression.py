#!/usr/bin/env python3
"""Regression checks for Sabi launch-gate evidence reporting."""

from __future__ import annotations

import sys

from launch_gates import build_launch_gate_report


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    calls = [
        {
            "call_uuid": f"call-{index}",
            "duration_seconds": 360 if index == 0 else 220,
            "turn_count": 5,
            "user_turns": 5,
            "assistant_turns": 5,
            "quality_flags": [],
        }
        for index in range(5)
    ]
    learners = [
        {
            "id": "child-1",
            "display_name": "Aisha",
            "participant_type": "child",
            "consent_status": "signed",
            "calling": {"recent_call_count": 1},
        },
        {
            "id": "adult-1",
            "display_name": "Naomi",
            "participant_type": "adult_tester",
            "calling": {"recent_call_count": 5},
        },
    ]
    report = build_launch_gate_report(
        calls=calls,
        learners=learners,
        intron_api_key_present=False,
    )
    gates = {gate["key"]: gate for gate in report["gates"]}
    ok = True
    ok &= check("overall_blocks_missing_intron_key", report["overall_status"] == "blocked", report["overall_status"])
    ok &= check("baseline_can_pass_with_call_evidence", gates["baseline_capture"]["status"] == "pass", gates["baseline_capture"])
    ok &= check("adult_canary_can_pass", gates["adult_canary"]["status"] == "pass", gates["adult_canary"])
    ok &= check("isolated_route_blocks_without_key", gates["isolated_route"]["status"] == "blocked", gates["isolated_route"])
    ok &= check("child_canary_not_ready_with_one_child", gates["child_canary"]["status"] == "watch", gates["child_canary"])
    ok &= check("adult_tester_excluded_from_child_count", report["metrics"]["child_profiles"] == 1, report["metrics"])

    unlocked = build_launch_gate_report(
        calls=calls,
        learners=learners + [
            {
                "id": "child-2",
                "display_name": "Tunde",
                "participant_type": "child",
                "consent_status": "signed",
                "calling": {"recent_call_count": 1},
            }
        ],
        intron_api_key_present=True,
    )
    unlocked_gates = {gate["key"]: gate for gate in unlocked["gates"]}
    ok &= check("isolated_route_watch_with_key", unlocked_gates["isolated_route"]["status"] == "watch")
    ok &= check("child_canary_passes_two_consented_called_children", unlocked_gates["child_canary"]["status"] == "pass")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

