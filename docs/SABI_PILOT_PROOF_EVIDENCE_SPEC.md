# Sabi Pilot-Proof Evidence Spec (Layer C)

Created: 2026-07-04

Purpose: define the cohort-level learning-gains report an NGO needs to see before it will pay Sabi to deliver literacy and numeracy. This is the funder-facing report that sits on top of the per-child evidence built in Layers A (teacher's notes) and B (curriculum-aligned scoreboard + mastery map).

Implementation: `pilot_evidence.py`, `mastery_probe.py`, `GET /admin/pilot-evidence`, Pilot Evidence tab in the board console, Gate 6 wiring in `launch_gates.py`.

## Why this report exists

NGOs and funders do not buy "the demo worked." They buy measured learning gains at a defensible cost per child, reported in the units the sector already trusts. The three programs Sabi is benchmarked against all report the same small set of numbers:

- ConnectEd / J-PAL phone tutoring: 0.33 SD average (0.45 SD Philippines, 0.89 SD Uganda), ~$12/child, 3.4 LAYS per $100 spent, from ~3 hours of tutoring over 8-9 weeks.
- Rori (Rising Academies): 0.36-0.37 SD (~1 extra year of learning), ~$5/child/year, from ~32 hours over 8 months.
- TaRL / Pratham: percentage of children moving up a reading level (19% to 79% readers in learning camps), 0.10-0.71 SD across 6 RCTs.

Sabi's own research plan already targets 300 children over 6 months powered for d >= 0.30, with a 10-child / 7-14 day baseline-to-endline pre-pilot as the first step. This spec turns those targets into a report the backend can generate on demand.

## Primary outcome: TaRL level movement

The headline number, because it is what TaRL/Pratham and structured-pedagogy funders recognize.

- Per child: baseline placement level (from the diagnostic) versus current level, per course.
  - Numeracy TaRL levels (0-4): Beginner, one-digit/number recognition, two-digit, subtraction, word problems / Grade-4 ready. Already tracked as `tarl_level` in `learning_state.py` and surfaced on every call scorecard as `tarl_level_before` / `tarl_level_after`.
  - Literacy levels (0-4): Beginner, letter, word, paragraph, story (`tarl_reading_level`).
- Per cohort: percentage of children who moved up at least one level (the "19% to 79%" framing), and the level distribution at baseline versus now.

## Secondary outcomes

1. Pre/post effect size (SD) on a monthly mastery probe.
   - A short, fixed, comparable set of oral items given at baseline and re-given monthly (distinct from the adaptive lesson, so scores are comparable over time).
   - Report mean gain and standard deviation; target d >= 0.30 (the repo's 300-child / 6-month power plan; n approx 175 per arm at alpha 0.05, power 0.80 for a controlled study).
2. Per-skill mastery counts.
   - Count of children at "mastered / near / needs practice" per module/skill, aggregated from the Layer B mastery map (`build_learner_mastery_map` + `curriculum_mastery.classify_mastery`).
   - "Skills mastered per child per month" as a velocity metric.
3. Lesson progression.
   - Lessons completed and lessons passed (against the `curriculum_mastery.lesson_passed` line, including the numeracy Lesson 20 70% gate and module-assessment n-of-m rules) per child and per cohort.

## Dosage (tie effort to outcome)

Report per child and cohort-average:

- Calls placed / answered / completed.
- Minutes and hours of actual lesson time (from call `duration_seconds`).
- Calls per week and week-over-week retention (already partially in the `_calling_summary` helper and `launch_gates.py` second-call-return metric).

Anchor dosage against comparators so a funder can judge intensity: ConnectEd produced 0.33 SD from ~3 hours; Rori 0.36 SD from ~32 hours. Sabi's 2-calls-a-day design delivers far more minutes per child, so the report should show gain-per-hour, not just total gain.

## Cost framing

- Cost per child (delivery cost from the cost model; see `5. Cost & Feasibility/`).
- SD per dollar and LAYS (learning-adjusted years of schooling) so the number sits directly beside ConnectEd ($12/child, 3.4 LAYS per $100) and Rori ($5/child). Nigeria's system-level anchor: ~5 LAYS out of 10.2 expected years; best programs globally add ~3 LAYS per $100/child.

## Per-child evidence record (data model)

One record per child, assembled from data that now exists after Layers A and B:

```
child_evidence = {
  "learner_id", "display_name", "phone_household_key", "network",
  "consent_status", "is_child",                       # from Kids/consent layer
  "course_records": {
    "numeracy": {
      "baseline": { "tarl_level", "placed_at", "diagnostic_results" },
      "current":  { "tarl_level", "current_module", "current_lesson" },
      "levels_gained",                                 # current - baseline
      "mastery_map",                                   # build_learner_mastery_map()
      "skills_mastered_count",
      "lessons_completed", "lessons_passed"
    },
    "literacy": { ... same shape ... }
  },
  "probe": { "baseline_score", "latest_score", "gain", "history": [...] },
  "dosage": { "calls_completed", "total_minutes", "calls_per_week", "second_call_returned" },
  "latest_teacher_note",                               # Layer A
  "first_call_reviewed", "safety_incidents"
}
```

Sources already in place:
- `tarl_level` / levels, mastery: `learning_state.py`, `curriculum_mastery.py`, `memory.build_learner_mastery_map`.
- Per-call scorecard + teacher note: call sidecars via `call_admin.write_call_learning_summary`, and Supabase session rows / `last_teacher_note`.
- Dosage and consent: `memory._calling_summary`, Kids/pre-pilot profiles, `launch_gates.py`.
- New for Layer C: the monthly probe (baseline/endline) capture and storage — the one genuinely new data collection this report requires.

## Cohort rollup + endpoint sketch

New read-only endpoint: `GET /admin/pilot-evidence`.

Query params: `cohort` (or date range), `course`, `min_calls`. Child-only (reuse the child-profile detection in `launch_gates.py` / `admin_review.py`; never mix adult testers into cohort gains).

Response shape:

```
{
  "cohort": { "children": N, "consented": N, "with_calls": N, "window": {from, to} },
  "tarl_movement": {
    "numeracy": { "baseline_distribution": {0:.., 1:.., ...},
                  "current_distribution": {...},
                  "pct_up_one_plus_level": 0.0 },
    "literacy":  { ... }
  },
  "probe": { "n_paired", "mean_gain", "sd", "effect_size_d" },
  "mastery": { "skills_mastered_total", "per_module": {...} },
  "dosage": { "median_calls", "median_minutes", "median_hours", "second_call_return_rate" },
  "cost": { "cost_per_child", "sd_per_dollar", "lays_per_100" },
  "children": [ child_evidence, ... ],       # for CSV export / audit
  "generated_at"
}
```

- CSV export (per-child rows) for funder due diligence and RCT analysis, matching the existing CSV export pattern in `admin_review.py`.
- Render a "Pilot Evidence" tab in the board console beside Launch Gates.

## Tie into the launch gates

`launch_gates.py` Gate 6 (10-child pre-pilot) already lists "learning movement measured by baseline/endline or mastery probes" as a requirement but computes nothing for it. When Layer C ships:

- Feed `pct_up_one_plus_level`, `probe.effect_size_d`, and `skills_mastered_total` into Gate 6 so the gate turns green on evidence, not just on call counts.
- Add a promotion rule: do not quote an NGO a delivery contract until the pre-pilot cohort shows measurable, reviewed learning movement.

## Build order (when Layer C is greenlit)

1. Monthly probe: fixed oral item bank + baseline/endline capture and storage (the only new data collection).
2. `pilot_evidence.py`: assemble per-child records from existing sources + probe; compute cohort rollup, effect size, and cost framing.
3. `GET /admin/pilot-evidence` endpoint + Pilot Evidence tab + CSV export.
4. Wire outputs into `launch_gates.py` Gate 6.
5. Regression: `pilot_evidence_regression.py` (level-movement math, effect size, child-only filtering, CSV shape).

## Dependencies / non-goals

- Depends on Layers A and B running in production long enough to accumulate baseline and endline data across a real cohort.
- Not a substitute for an independent RCT; it is the operational evidence system that makes an RCT (and NGO contracts) possible and credible.
- Keep it read-only and child-safe: no raw child audio in exports, consented children only, adult testers excluded from all cohort gains.
