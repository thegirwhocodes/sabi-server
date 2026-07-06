"""Pilot-proof cohort evidence for Sabi (Layer C).

Aggregates the per-child learning evidence (Layers A and B) into the cohort
learning-gains report an NGO needs before paying for delivery. Reports in the
units the sector trusts: TaRL level movement (primary), percentage of the cohort
moving up at least one level, per-skill mastery counts, dosage as calls x minutes
x hours, and a pre/post effect size when a monthly probe is present.

Pure functions only: no I/O, no network, no Supabase. `memory.get_pilot_evidence`
feeds it the learner review records; this module does the math.
"""

from __future__ import annotations

import statistics
from typing import Any

from launch_gates import _is_child_profile
from pilot_research_design import build_research_state, cohort_research_rollup

# Comparator benchmarks (from the project's Evidence research) so a funder can
# place Sabi's numbers in context. Static reference values, not Sabi's results.
BENCHMARKS = {
    "connected": {"effect_sd": 0.33, "cost_per_child_usd": 12, "lays_per_100": 3.4, "dosage_hours": 3},
    "rori": {"effect_sd": 0.36, "cost_per_child_usd": 5, "dosage_hours": 32},
    "tarl_camps": {"readers_before": 0.19, "readers_after": 0.79},
}


def _median(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 2)


def _level_distribution(levels: list[int | None]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for level in levels:
        if level is None:
            continue
        key = str(int(level))
        dist[key] = dist.get(key, 0) + 1
    return dist


def _is_consented(learner: dict) -> bool:
    return bool(
        learner.get("consent_status")
        or learner.get("consent_recorded")
        or learner.get("caregiver_phone")
    )


def child_evidence(learner: dict) -> dict[str, Any]:
    """Build one child's evidence record from a learner review record."""
    state = learner.get("effective_state") or {}
    literacy_state = state.get("literacy") or {}
    mastery = learner.get("mastery_map") or {}
    numeracy_map = mastery.get("numeracy") or {}
    literacy_map = mastery.get("literacy") or {}
    calling = learner.get("calling") or {}
    note = learner.get("last_teacher_note") or {}
    research_state = learner.get("research_state") if isinstance(learner.get("research_state"), dict) else None

    num_base = learner.get("baseline_tarl_level")
    num_now = state.get("tarl_level")
    lit_base = learner.get("baseline_reading_level")
    lit_now = literacy_state.get("tarl_reading_level")

    def _gain(base: Any, now: Any) -> int | None:
        if base is None or now is None:
            return None
        return int(now) - int(base)

    calls = int(calling.get("recent_call_count") or 0)
    seconds = int(calling.get("recent_call_seconds") or 0)
    total_sessions = int(learner.get("total_sessions") or calls or 0)
    if research_state is None:
        research_state = build_research_state(learner, calls_completed=total_sessions)

    probe = None
    base_probe = learner.get("baseline_probe_score")
    latest_probe = learner.get("latest_probe_score")
    if base_probe is not None and latest_probe is not None:
        probe = {
            "baseline": float(base_probe),
            "latest": float(latest_probe),
            "gain": round(float(latest_probe) - float(base_probe), 3),
        }

    return {
        "id": learner.get("id"),
        "name": learner.get("display_name") or learner.get("name"),
        "consented": _is_consented(learner),
        "numeracy": {
            "baseline_level": num_base,
            "current_level": num_now,
            "levels_gained": _gain(num_base, num_now),
            "current_module": state.get("current_module"),
            "mastered_modules": int(numeracy_map.get("mastered_modules") or 0),
        },
        "literacy": {
            "baseline_level": lit_base,
            "current_level": lit_now,
            "levels_gained": _gain(lit_base, lit_now),
            "current_module": literacy_state.get("current_module"),
            "mastered_modules": int(literacy_map.get("mastered_modules") or 0),
        },
        "dosage": {
            "calls": calls,
            "total_sessions": total_sessions,
            "minutes": round(seconds / 60, 1),
            "hours": round(seconds / 3600, 2),
            "second_call_returned": calls >= 2,
        },
        "totals": {
            "correct": int(learner.get("total_correct") or 0),
            "wrong": int(learner.get("total_wrong") or 0),
            "sessions": int(learner.get("total_sessions") or 0),
        },
        "probe": probe,
        "research": research_state,
        "teacher_note": note.get("narrative") if isinstance(note, dict) else None,
    }


def _course_movement(children: list[dict], course: str) -> dict[str, Any]:
    baseline_levels = [c[course]["baseline_level"] for c in children]
    current_levels = [c[course]["current_level"] for c in children]
    paired = [c for c in children if c[course]["levels_gained"] is not None]
    moved_up = [c for c in paired if c[course]["levels_gained"] >= 1]
    return {
        "baseline_distribution": _level_distribution(baseline_levels),
        "current_distribution": _level_distribution(current_levels),
        "children_with_baseline_and_current": len(paired),
        "children_up_one_plus_level": len(moved_up),
        "pct_up_one_plus_level": round(len(moved_up) / len(paired), 3) if paired else None,
        "median_levels_gained": _median([c[course]["levels_gained"] for c in paired]),
    }


def _probe_stats(children: list[dict]) -> dict[str, Any]:
    gains = [c["probe"]["gain"] for c in children if c.get("probe")]
    if not gains:
        return {"n_paired": 0, "mean_gain": None, "sd": None, "effect_size_d": None}
    mean_gain = round(statistics.mean(gains), 3)
    sd = round(statistics.stdev(gains), 3) if len(gains) >= 2 else None
    effect = round(mean_gain / sd, 3) if sd else None
    return {"n_paired": len(gains), "mean_gain": mean_gain, "sd": sd, "effect_size_d": effect}


def cohort_rollup(children: list[dict], *, cost_per_child: float | None = None) -> dict[str, Any]:
    n = len(children)
    with_calls = [c for c in children if c["dosage"]["calls"] > 0]
    returned = [c for c in with_calls if c["dosage"]["second_call_returned"]]
    probe = _probe_stats(children)

    cost_block: dict[str, Any] = {"cost_per_child_usd": cost_per_child}
    if cost_per_child and probe.get("effect_size_d"):
        cost_block["sd_per_dollar"] = round(probe["effect_size_d"] / float(cost_per_child), 5)
    else:
        cost_block["sd_per_dollar"] = None
    cost_block["lays_note"] = (
        "LAYS conversion requires an external test-to-LAYS mapping; report SD and "
        "cost, and compare against ConnectEd (3.4 LAYS per $100) and Rori ($5/child)."
    )

    return {
        "children": n,
        "consented": sum(1 for c in children if c["consented"]),
        "with_calls": len(with_calls),
        "tarl_movement": {
            "numeracy": _course_movement(children, "numeracy"),
            "literacy": _course_movement(children, "literacy"),
        },
        "mastery": {
            "skills_mastered_total": sum(
                c["numeracy"]["mastered_modules"] + c["literacy"]["mastered_modules"] for c in children
            ),
        },
        "dosage": {
            "median_calls": _median([c["dosage"]["calls"] for c in with_calls]),
            "median_minutes": _median([c["dosage"]["minutes"] for c in with_calls]),
            "median_hours": _median([c["dosage"]["hours"] for c in with_calls]),
            "second_call_return_rate": round(len(returned) / len(with_calls), 3) if with_calls else None,
        },
        "research": cohort_research_rollup(children),
        "probe": probe,
        "cost": cost_block,
    }


def build_pilot_evidence_report(learners: list[dict], *, cost_per_child: float | None = None) -> dict[str, Any]:
    """Full cohort pilot-proof report. Children only; adult testers excluded."""
    child_learners = [learner for learner in (learners or []) if _is_child_profile(learner)]
    children = [child_evidence(learner) for learner in child_learners]
    rollup = cohort_rollup(children, cost_per_child=cost_per_child)
    return {
        "status": "ok",
        "cohort": rollup,
        "children": children,
        "benchmarks": BENCHMARKS,
        "notes": {
            "primary_outcome": "TaRL level movement (baseline placement -> current); % of cohort up >=1 level.",
            "probe": "Effect size populates once a monthly baseline/endline probe is captured per child.",
            "child_only": "Adult testers are excluded from all cohort figures.",
            "research_design": "Pre-pilot evidence is TEP/LEARNigeria assessment-validity plus TaRL placement/remediation/reassessment, with RCT-ready assignment and pre/mid/post fields.",
        },
    }
