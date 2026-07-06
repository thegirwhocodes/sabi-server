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

import csv
import hashlib
import io
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
        "mastery_map": mastery,
        "teacher_note": note.get("narrative") if isinstance(note, dict) else None,
    }


def _child_code(child: dict, index: int = 0) -> str:
    child_key = str(child.get("id") or child.get("name") or index or "child")
    return "sabi-child-" + hashlib.sha256(child_key.encode("utf-8")).hexdigest()[:10]


def _phase_set(child: dict) -> set[str]:
    research = child.get("research") if isinstance(child.get("research"), dict) else {}
    return {
        str(item.get("phase"))
        for item in (research.get("measurements") or [])
        if isinstance(item, dict) and item.get("phase")
    }


def _next_due(child: dict) -> str:
    research = child.get("research") if isinstance(child.get("research"), dict) else {}
    status = research.get("assessment_status") if isinstance(research.get("assessment_status"), dict) else {}
    return str(status.get("next_due_phase") or "monitoring")


def _evidence_child(child: dict, index: int, *, value: str, detail: str, status: str | None = None) -> dict[str, Any]:
    dose = child.get("dosage") or {}
    totals = child.get("totals") or {}
    return {
        "child_code": _child_code(child, index),
        "name": child.get("name"),
        "value": value,
        "detail": detail,
        "status": status or "recorded",
        "calls": dose.get("calls") or 0,
        "hours": dose.get("hours") or 0,
        "next_probe": _next_due(child),
        "practice": f"{totals.get('correct', 0)} correct / {totals.get('wrong', 0)} needs help",
    }


def _indicator_status(*, progress: float | None, evidence_count: int, has_support: bool = False) -> str:
    if has_support:
        return "needs_support"
    if progress is not None and progress >= 0.8:
        return "strong"
    if progress is not None and progress >= 0.4:
        return "emerging"
    if evidence_count:
        return "collecting"
    return "not_started"


def _indicator_record(
    *,
    key: str,
    label: str,
    subject: str,
    construct: str,
    indicator_type: str,
    metric: str,
    detail: str,
    progress: float | None,
    evidence: list[dict[str, Any]],
    status: str | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "subject": subject,
        "construct": construct,
        "type": indicator_type,
        "phase": phase,
        "status": status or _indicator_status(progress=progress, evidence_count=len(evidence)),
        "metric": metric,
        "detail": detail,
        "progress": progress,
        "evidence_count": len(evidence),
        "evidence": evidence[:8],
    }


def learning_indicator_evidence(children: list[dict]) -> list[dict[str, Any]]:
    """Aggregate child records into board-facing learning indicators.

    The UI should read as "what learning signals are moving?" rather than
    "which children are in a table?", while still preserving the evidence under
    each signal for audit and board review.
    """
    n = len(children)
    indicators: list[dict[str, Any]] = []

    for subject, block_key, label in (
        ("numeracy", "numeracy", "Numeracy TaRL movement"),
        ("literacy", "literacy", "Literacy readiness movement"),
    ):
        paired = [child for child in children if (child.get(block_key) or {}).get("levels_gained") is not None]
        moved = [child for child in paired if int((child.get(block_key) or {}).get("levels_gained") or 0) >= 1]
        evidence = [
            _evidence_child(
                child,
                index,
                value=(
                    f"L{(child.get(block_key) or {}).get('baseline_level')} -> "
                    f"L{(child.get(block_key) or {}).get('current_level')}"
                ),
                detail=f"{(child.get(block_key) or {}).get('levels_gained'):+} level movement",
                status="moved_up" if child in moved else "steady",
            )
            for index, child in enumerate(paired, start=1)
        ]
        progress = (len(moved) / len(paired)) if paired else None
        indicators.append(_indicator_record(
            key=f"{subject}_tarl_level_movement",
            label=label,
            subject=subject,
            construct="TaRL placement movement",
            indicator_type="primary_outcome",
            metric=f"{len(moved)}/{len(paired)} up one or more levels",
            detail="Baseline-to-current movement from actual placed level, not age or grade.",
            progress=round(progress, 3) if progress is not None else None,
            evidence=evidence,
            status="signal_visible" if moved else _indicator_status(progress=progress, evidence_count=len(evidence)),
            phase="baseline_to_current",
        ))

    probe_children = [child for child in children if child.get("probe")]
    probe_gainers = [child for child in probe_children if float((child.get("probe") or {}).get("gain") or 0) > 0]
    probe_progress = (len(probe_gainers) / len(probe_children)) if probe_children else None
    indicators.append(_indicator_record(
        key="fixed_probe_gain",
        label="Fixed oral probe gain",
        subject="cross_subject",
        construct="pre/post fixed-probe mastery",
        indicator_type="primary_outcome",
        metric=f"{len(probe_gainers)}/{len(probe_children)} positive gains",
        detail="Same-construct probes before instruction, midstream, and after the cycle.",
        progress=round(probe_progress, 3) if probe_progress is not None else None,
        evidence=[
            _evidence_child(
                child,
                index,
                value=f"{(child.get('probe') or {}).get('baseline')} -> {(child.get('probe') or {}).get('latest')}",
                detail=f"gain {(child.get('probe') or {}).get('gain')}",
                status="gain" if child in probe_gainers else "flat",
            )
            for index, child in enumerate(probe_children, start=1)
        ],
        status="signal_visible" if probe_gainers else None,
        phase="pre_mid_post",
    ))

    returned = [child for child in children if (child.get("dosage") or {}).get("second_call_returned")]
    return_progress = (len(returned) / n) if n else None
    indicators.append(_indicator_record(
        key="second_call_return",
        label="Second-call return",
        subject="engagement",
        construct="dosage and persistence",
        indicator_type="implementation_signal",
        metric=f"{len(returned)}/{n} returned",
        detail="A child coming back is an early signal that the learning path is usable at home.",
        progress=round(return_progress, 3) if return_progress is not None else None,
        evidence=[
            _evidence_child(
                child,
                index,
                value=f"{(child.get('dosage') or {}).get('calls', 0)} calls",
                detail=f"{(child.get('dosage') or {}).get('hours', 0)} learning hours",
                status="returned" if child in returned else "first_call_only",
            )
            for index, child in enumerate(children, start=1)
            if (child.get("dosage") or {}).get("calls")
        ],
        phase="dosage",
    ))

    phase_order = [
        ("pre_baseline", "Baseline probe", "Freeze starting level before Sabi teaches."),
        ("midline", "Midline probe", "Check early signal before changing instruction or scaling."),
        ("post_endline", "Endline probe", "Compare learning signal against the same construct map."),
        ("retention_followup", "Retention probe", "Check whether the child keeps the skill after spacing."),
    ]
    for phase, label, detail in phase_order:
        covered = [child for child in children if phase in _phase_set(child)]
        progress = (len(covered) / n) if n else None
        indicators.append(_indicator_record(
            key=f"{phase}_coverage",
            label=label,
            subject="measurement",
            construct="pre/mid/post RCT readiness",
            indicator_type="measurement_fidelity",
            metric=f"{len(covered)}/{n} recorded",
            detail=detail,
            progress=round(progress, 3) if progress is not None else None,
            evidence=[
                _evidence_child(
                    child,
                    index,
                    value="recorded" if child in covered else "due",
                    detail=f"next due: {_next_due(child).replace('_', ' ')}",
                    status="recorded" if child in covered else "due",
                )
                for index, child in enumerate(children, start=1)
                if child in covered or _next_due(child) == phase
            ],
            phase=phase,
        ))

    module_groups: dict[str, dict[str, Any]] = {}
    for index, child in enumerate(children, start=1):
        mastery = child.get("mastery_map") if isinstance(child.get("mastery_map"), dict) else {}
        for subject in ("numeracy", "literacy"):
            modules = ((mastery.get(subject) or {}).get("modules") or []) if isinstance(mastery.get(subject), dict) else []
            for row in modules:
                if not isinstance(row, dict):
                    continue
                key = f"{subject}_{row.get('skill') or row.get('module')}"
                group = module_groups.setdefault(key, {
                    "key": key,
                    "label": row.get("module_name") or str(row.get("skill") or "Skill").replace("_", " ").title(),
                    "subject": subject,
                    "construct": str(row.get("skill") or "curriculum_skill").replace("_", " "),
                    "rows": [],
                })
                group["rows"].append((child, index, row))

    for group in module_groups.values():
        rows = group["rows"]
        active_rows = [row for row in rows if (row[2].get("position") != "not_started" or row[2].get("score") is not None)]
        mastered = [row for row in active_rows if row[2].get("mastery") == "mastered"]
        support = [
            row for row in active_rows
            if row[2].get("mastery") in {"insufficient", "emerging"}
            or (row[2].get("score") is not None and float(row[2].get("score") or 0) < 0.5)
        ]
        denom = len(active_rows) or len(rows)
        progress = (len(mastered) / denom) if denom else None
        evidence = [
            _evidence_child(
                child,
                index,
                value=str(row.get("mastery_label") or row.get("mastery") or row.get("position") or "not started"),
                detail=(
                    f"{str(row.get('position') or 'not started').replace('_', ' ')}"
                    + (f" · score {row.get('score')}" if row.get("score") is not None else "")
                ),
                status=str(row.get("mastery") or row.get("position") or "not_started"),
            )
            for child, index, row in active_rows[:8]
        ]
        indicators.append(_indicator_record(
            key=group["key"],
            label=group["label"],
            subject=group["subject"],
            construct=group["construct"],
            indicator_type="curriculum_skill",
            metric=f"{len(mastered)}/{denom} mastered",
            detail="Rolling lesson evidence from Sabi's adaptive TaRL path.",
            progress=round(progress, 3) if progress is not None else None,
            evidence=evidence,
            status=_indicator_status(
                progress=progress,
                evidence_count=len(evidence),
                has_support=bool(support) and not mastered,
            ),
            phase="adaptive_learning",
        ))

    construct_groups: dict[str, dict[str, Any]] = {}
    for index, child in enumerate(children, start=1):
        research = child.get("research") if isinstance(child.get("research"), dict) else {}
        for response in research.get("item_responses") or []:
            if not isinstance(response, dict) or not response.get("item_id"):
                continue
            subject = str(response.get("subject") or "assessment")
            construct = str(response.get("construct") or "fixed_probe")
            key = f"probe_{subject}_{construct}"
            group = construct_groups.setdefault(key, {
                "key": key,
                "label": construct.replace("_", " ").title(),
                "subject": subject,
                "construct": construct.replace("_", " "),
                "rows": [],
            })
            group["rows"].append((child, index, response))

    for group in construct_groups.values():
        rows = group["rows"]
        scored = [row for row in rows if row[2].get("score") is not None]
        correct = [row for row in scored if float(row[2].get("score") or 0) > 0]
        pending = len(rows) - len(scored)
        progress = (len(correct) / len(scored)) if scored else None
        indicators.append(_indicator_record(
            key=group["key"],
            label=group["label"],
            subject=group["subject"],
            construct=group["construct"],
            indicator_type="fixed_probe_construct",
            metric=f"{len(correct)}/{len(scored)} scored correct; {pending} pending",
            detail="Item-level fixed-probe evidence with scorer/adjudication fields preserved.",
            progress=round(progress, 3) if progress is not None else None,
            evidence=[
                _evidence_child(
                    child,
                    index,
                    value=f"{response.get('phase') or 'probe'} · {response.get('item_id')}",
                    detail=(
                        "pending score" if response.get("score") is None
                        else f"score {response.get('score')}"
                    ),
                    status="pending_score" if response.get("score") is None else "scored",
                )
                for child, index, response in rows[:8]
            ],
            status="needs_scoring" if pending else None,
            phase="fixed_probe_item",
        ))

    order = {
        "primary_outcome": 0,
        "curriculum_skill": 1,
        "fixed_probe_construct": 2,
        "measurement_fidelity": 3,
        "implementation_signal": 4,
    }
    return sorted(
        indicators,
        key=lambda item: (
            order.get(str(item.get("type")), 9),
            str(item.get("subject")),
            str(item.get("label")),
        ),
    )


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
    research = cohort_research_rollup(children)

    cost_block: dict[str, Any] = {"cost_per_child_usd": cost_per_child}
    if cost_per_child and probe.get("effect_size_d"):
        cost_block["sd_per_dollar"] = round(probe["effect_size_d"] / float(cost_per_child), 5)
    else:
        cost_block["sd_per_dollar"] = None
    cost_block["lays_note"] = (
        "LAYS conversion requires an external test-to-LAYS mapping; report SD and "
        "cost, and compare against ConnectEd (3.4 LAYS per $100) and Rori ($5/child)."
    )

    tarl_movement = {
        "numeracy": _course_movement(children, "numeracy"),
        "literacy": _course_movement(children, "literacy"),
    }
    mastery = {
        "skills_mastered_total": sum(
            c["numeracy"]["mastered_modules"] + c["literacy"]["mastered_modules"] for c in children
        ),
    }
    dosage = {
        "median_calls": _median([c["dosage"]["calls"] for c in with_calls]),
        "median_minutes": _median([c["dosage"]["minutes"] for c in with_calls]),
        "median_hours": _median([c["dosage"]["hours"] for c in with_calls]),
        "second_call_return_rate": round(len(returned) / len(with_calls), 3) if with_calls else None,
    }

    return {
        "children": n,
        "consented": sum(1 for c in children if c["consented"]),
        "with_calls": len(with_calls),
        "tarl_movement": tarl_movement,
        "mastery": mastery,
        "dosage": dosage,
        "research": research,
        "probe": probe,
        "cost": cost_block,
        "rct_advancement": _rct_advancement(
            cohort_n=n,
            consented=sum(1 for c in children if c["consented"]),
            with_calls=len(with_calls),
            tarl_movement=tarl_movement,
            mastery=mastery,
            dosage=dosage,
            probe=probe,
            research=research,
        ),
    }


def _pct(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 3)


def _rct_advancement(
    *,
    cohort_n: int,
    consented: int,
    with_calls: int,
    tarl_movement: dict[str, Any],
    mastery: dict[str, Any],
    dosage: dict[str, Any],
    probe: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    protocol = research.get("protocol") or {}
    measurement_counts = research.get("measurement_counts") or {}
    consent_counts = research.get("consent_counts") or {}
    readiness = research.get("rct_readiness") or {}
    data_quality = research.get("data_quality") or {}
    instruments = research.get("instrument_readiness") or {}
    publication_pack = research.get("publication_pack") or {}
    num = tarl_movement.get("numeracy") or {}
    lit = tarl_movement.get("literacy") or {}

    cards = [
        {
            "key": "protocol",
            "label": "Protocol",
            "status": protocol.get("status") or "draft",
            "metric": protocol.get("stage_label") or research.get("stage_label"),
            "detail": "Versioned protocol, outcomes, sample plan, registry/PAP fields, and ethics state.",
        },
        {
            "key": "instruments",
            "label": "Instruments",
            "status": instruments.get("status") or "missing",
            "metric": f"{instruments.get('total_instruments', 0)} forms / {instruments.get('total_items', 0)} items",
            "detail": instruments.get("review_status") or "TEP/LEARNigeria review pending.",
        },
        {
            "key": "consent",
            "label": "Consent",
            "status": "ready" if cohort_n and consent_counts.get("caregiver_consent", 0) == cohort_n else "partial",
            "metric": f"{consent_counts.get('caregiver_consent', 0)}/{cohort_n} caregiver; {consent_counts.get('child_assent', 0)}/{cohort_n} assent",
            "detail": "Tracks caregiver consent, child assent, withdrawal, and raw-audio export permission.",
        },
        {
            "key": "baseline",
            "label": "Baseline",
            "status": "ready" if cohort_n and measurement_counts.get("pre_baseline", 0) == cohort_n else "in_progress",
            "metric": f"{measurement_counts.get('pre_baseline', 0)}/{cohort_n}",
            "detail": "TaRL placement and fixed baseline probe coverage before adaptive teaching claims.",
        },
        {
            "key": "randomization",
            "label": "Randomization",
            "status": "single_arm" if research.get("stage") == "ten_child_prepilot" else "assignment_ready",
            "metric": f"{readiness.get('assignment_recorded', 0)} assignments",
            "detail": "Single-arm pre-pilot now; sealed randomization batch required before 30-child micro-RCT.",
        },
        {
            "key": "midline",
            "label": "Midline",
            "status": "ready" if cohort_n and measurement_counts.get("midline", 0) == cohort_n else "pending",
            "metric": f"{measurement_counts.get('midline', 0)}/{cohort_n}",
            "detail": "Early fixed-probe signal before changing instruction or scaling.",
        },
        {
            "key": "endline",
            "label": "Endline",
            "status": "ready" if cohort_n and measurement_counts.get("post_endline", 0) == cohort_n else "pending",
            "metric": f"{measurement_counts.get('post_endline', 0)}/{cohort_n}",
            "detail": "Primary endline availability for learning-signal and data-quality report.",
        },
        {
            "key": "data_quality",
            "label": "Data Quality",
            "status": data_quality.get("status") or "awaiting_child_baselines",
            "metric": f"{data_quality.get('item_response_records', 0)} item rows; {data_quality.get('pending_item_scores', 0)} pending scores",
            "detail": "Tracks coverage, fixed-probe events, missingness, and item-scoring completion.",
        },
        {
            "key": "learning_outcomes",
            "label": "Learning Outcomes",
            "status": "signal_visible" if (num.get("children_up_one_plus_level", 0) or lit.get("children_up_one_plus_level", 0)) else "collecting",
            "metric": f"Num +1: {num.get('children_up_one_plus_level', 0)}; Lit +1: {lit.get('children_up_one_plus_level', 0)}; probe d={probe.get('effect_size_d')}",
            "detail": f"{mastery.get('skills_mastered_total', 0)} mastered skill-modules; median calls {dosage.get('median_calls')}.",
        },
        {
            "key": "safety_fidelity",
            "label": "Safety/Fidelity",
            "status": "needs_review_rows",
            "metric": f"{with_calls}/{cohort_n} with calls",
            "detail": "First-call review, no-coaching measurement compliance, and safety incidents must be tracked for publication.",
        },
        {
            "key": "publication_pack",
            "label": "Publication Pack",
            "status": publication_pack.get("status") or "not_started",
            "metric": f"{publication_pack.get('ready_count', 0)}/{publication_pack.get('total_count', 0)} artifacts ready",
            "detail": "Protocol, codebook, de-identified data, item responses, assignment, and reproducibility README.",
        },
    ]
    return {
        "stage": research.get("stage"),
        "stage_label": research.get("stage_label"),
        "claim_tier": research.get("claim_boundary"),
        "cohort_progress": {
            "children": cohort_n,
            "consented_rate": _pct(consented, cohort_n),
            "call_coverage": _pct(with_calls, cohort_n),
            "baseline_coverage": data_quality.get("baseline_coverage"),
            "midline_coverage": data_quality.get("midline_coverage"),
            "endline_coverage": data_quality.get("endline_coverage"),
        },
        "cards": cards,
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
        "learning_indicators": learning_indicator_evidence(children),
        "benchmarks": BENCHMARKS,
        "notes": {
            "primary_outcome": "TaRL level movement (baseline placement -> current); % of cohort up >=1 level.",
            "probe": "Effect size populates once a monthly baseline/endline probe is captured per child.",
            "child_only": "Adult testers are excluded from all cohort figures.",
            "research_design": "Pre-pilot evidence uses publishable-grade methods from call one: TEP/LEARNigeria assessment validity, TaRL placement/remediation/reassessment, UNESCO/GPF outcome language, and J-PAL-style protocol/assignment/pre-mid-post fields.",
        },
    }


def pilot_evidence_csv(report: dict, *, mode: str = "board") -> str:
    """Export child evidence with board/evaluator/public redaction modes."""
    export_mode = str(mode or "board").strip().lower()
    if export_mode not in {"board", "evaluator", "public"}:
        export_mode = "board"
    identity_fields = ["id", "name"] if export_mode == "board" else ["child_code"]
    fields = [
        *identity_fields,
        "export_mode", "consented",
        "caregiver_consent", "child_assent", "training_audio_consent", "raw_audio_export_allowed",
        "protocol_id", "protocol_version", "study_stage", "study_arm", "next_assessment_due",
        "pre_baseline_recorded", "midline_recorded", "post_endline_recorded", "retention_recorded",
        "assessment_event_count", "item_response_count", "pending_item_scores",
        "numeracy_baseline", "numeracy_current", "numeracy_levels_gained", "numeracy_mastered_modules",
        "literacy_baseline", "literacy_current", "literacy_levels_gained", "literacy_mastered_modules",
        "calls", "minutes", "hours", "second_call_returned",
        "correct", "wrong", "sessions", "probe_gain",
    ]
    if export_mode == "public":
        fields = [
            field for field in fields
            if field not in {"training_audio_consent", "raw_audio_export_allowed", "correct", "wrong"}
        ]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(fields)
    for index, child in enumerate(report.get("children") or [], start=1):
        num = child.get("numeracy") or {}
        lit = child.get("literacy") or {}
        dosage = child.get("dosage") or {}
        totals = child.get("totals") or {}
        probe = child.get("probe") or {}
        research = child.get("research") or {}
        consent = research.get("consent") or {}
        assignment = research.get("assignment") or {}
        status = research.get("assessment_status") or {}
        phases = {str(item.get("phase")) for item in (research.get("measurements") or []) if isinstance(item, dict)}
        events = [item for item in (research.get("assessment_events") or []) if isinstance(item, dict)]
        responses = [item for item in (research.get("item_responses") or []) if isinstance(item, dict)]
        child_code = _child_code(child, index)
        row = {
            "id": child.get("id"),
            "name": child.get("name"),
            "child_code": child_code,
            "export_mode": export_mode,
            "consented": child.get("consented"),
            "caregiver_consent": consent.get("caregiver_consent_recorded"),
            "child_assent": consent.get("child_assent_recorded"),
            "training_audio_consent": consent.get("training_audio_consent_recorded"),
            "raw_audio_export_allowed": consent.get("raw_audio_export_allowed"),
            "protocol_id": research.get("protocol_id"),
            "protocol_version": research.get("protocol_version"),
            "study_stage": research.get("study_stage"),
            "study_arm": assignment.get("arm"),
            "next_assessment_due": status.get("next_due_phase"),
            "pre_baseline_recorded": "pre_baseline" in phases,
            "midline_recorded": "midline" in phases,
            "post_endline_recorded": "post_endline" in phases,
            "retention_recorded": "retention_followup" in phases,
            "assessment_event_count": len(events),
            "item_response_count": len(responses),
            "pending_item_scores": sum(1 for response in responses if response.get("score") is None),
            "numeracy_baseline": num.get("baseline_level"),
            "numeracy_current": num.get("current_level"),
            "numeracy_levels_gained": num.get("levels_gained"),
            "numeracy_mastered_modules": num.get("mastered_modules"),
            "literacy_baseline": lit.get("baseline_level"),
            "literacy_current": lit.get("current_level"),
            "literacy_levels_gained": lit.get("levels_gained"),
            "literacy_mastered_modules": lit.get("mastered_modules"),
            "calls": dosage.get("calls"),
            "minutes": dosage.get("minutes"),
            "hours": dosage.get("hours"),
            "second_call_returned": dosage.get("second_call_returned"),
            "correct": totals.get("correct"),
            "wrong": totals.get("wrong"),
            "sessions": totals.get("sessions"),
            "probe_gain": probe.get("gain"),
        }
        writer.writerow([row.get(field) for field in fields])
    return buffer.getvalue()
