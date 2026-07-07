"""Publishable-grade pilot research protocol for Sabi.

This module keeps the measurement design close to the call state. From the
first child, Sabi should collect data with J-PAL/UNESCO/TEP-level discipline:
versioned protocol, consent-aware measurement, fixed pre/mid/post probes,
auditable assignment fields, dosage, attrition, and reviewer-ready exports.
Early cohorts can be outward-facing as methods and data-quality evidence while
effect-size claims remain scaled to the sample size and power.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any


PROTOCOL_VERSION = "sabi-tep-tarl-rct-v0.1"
PROTOCOL_ID = "sabi-publishable-evidence-001"

PHILOSOPHY = [
    "TEP/LEARNigeria lens: assessment validity, Nigerian learner fit, and safe claim language.",
    "TaRL lens: assess actual level, teach at that level, remediate prerequisites, and reassess regularly.",
    "J-PAL/RCT lens: preserve protocol, assignment, baseline, midline, endline, dosage, attrition, and analysis fields from day one.",
    "UNESCO/GPF lens: keep reading and mathematics outcomes mappable to minimum proficiency language.",
]

STUDY_STAGES = {
    "ten_child_prepilot": {
        "label": "10-child pre-pilot",
        "design": "Publishable-grade single-arm pre-pilot with locked protocol fields, consent-aware baseline/midline/endline/retention probes, and full audit trail.",
        "target_n": 10,
        "claim_boundary": "Outward-facing as methods, feasibility, data-quality, assessment-validity, and exploratory learning-signal evidence; causal effect claims wait for powered randomization.",
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

PROTOCOL_STATUS_ORDER = [
    "draft",
    "board_locked",
    "ethics_ready",
    "registered",
    "active",
    "analysis_frozen",
    "reported",
]

PRIMARY_OUTCOMES = [
    {
        "key": "numeracy_tarl_level_movement",
        "label": "Numeracy TaRL level movement",
        "construct": "foundational numeracy placement and advancement",
        "analysis": "baseline/current paired level movement; report percent up >=1 level",
    },
    {
        "key": "literacy_oral_readiness_level_movement",
        "label": "Literacy/oral-readiness TaRL level movement",
        "construct": "phonological awareness, oral comprehension, and print-bridge readiness",
        "analysis": "baseline/current paired reading-readiness movement",
    },
    {
        "key": "fixed_probe_gain",
        "label": "Fixed-probe gain",
        "construct": "phase-comparable oral literacy and numeracy mastery",
        "analysis": "pre/post paired gain; effect-size reporting only when powered and pre-specified",
    },
]

SECONDARY_OUTCOMES = [
    "skills_mastered",
    "second_call_return",
    "dosage_minutes",
    "scaffold_depth_and_rejoin_success",
    "retention_followup",
    "cost_per_level_gain",
]

FRAMEWORK_ANCHORS = {
    "jpal": "trial registration, PAP, randomization, balance, attrition, reproducible exports",
    "unesco_uis_gpf": "minimum proficiency language for reading and mathematics",
    "tep_learnigeria": "Nigerian foundational literacy/numeracy assessment validity and actionability",
    "tarl": "placement by actual level, remediation, reassessment, and progress tracking",
    "egra_egma": "oral one-on-one early-grade reading and mathematics item discipline",
}

ASSESSMENT_INSTRUMENTS = {
    "sabi-num-pre-v01": {
        "subject": "numeracy",
        "phase": "pre_baseline",
        "form": "A",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["number_recognition", "quantity", "single_digit_addition"],
        "framework_anchors": ["TaRL numeracy placement", "EGMA-inspired oral numeracy", "UNESCO/GPF mathematics"],
    },
    "sabi-lit-pre-v01": {
        "subject": "literacy",
        "phase": "pre_baseline",
        "form": "A",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["listening_comprehension", "beginning_sounds", "phonological_awareness"],
        "framework_anchors": ["TaRL reading-readiness placement", "EGRA-inspired oral literacy", "TEP/LEARNigeria FLN"],
    },
    "sabi-num-mid-v01": {
        "subject": "numeracy",
        "phase": "midline",
        "form": "B",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["number_operations", "word_problem_listening", "place_value_readiness"],
        "framework_anchors": ["TaRL progress check", "EGMA-inspired oral numeracy"],
    },
    "sabi-lit-mid-v01": {
        "subject": "literacy",
        "phase": "midline",
        "form": "B",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["sound_discrimination", "oral_vocabulary", "story_recall"],
        "framework_anchors": ["TaRL progress check", "EGRA-inspired oral literacy"],
    },
    "sabi-num-post-v01": {
        "subject": "numeracy",
        "phase": "post_endline",
        "form": "C",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["number_operations", "word_problem_listening", "mastery_transfer"],
        "framework_anchors": ["TaRL reassessment", "UNESCO/GPF mathematics"],
    },
    "sabi-lit-post-v01": {
        "subject": "literacy",
        "phase": "post_endline",
        "form": "C",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["phonological_awareness", "oral_comprehension", "print_bridge_readiness"],
        "framework_anchors": ["TaRL reassessment", "EGRA-inspired oral literacy"],
    },
    "sabi-num-ret-v01": {
        "subject": "numeracy",
        "phase": "retention_followup",
        "form": "R",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["delayed_recall", "maintenance"],
        "framework_anchors": ["retention check", "TaRL progress tracking"],
    },
    "sabi-lit-ret-v01": {
        "subject": "literacy",
        "phase": "retention_followup",
        "form": "R",
        "mode": "voice_fixed_oral",
        "review_status": "internal_draft",
        "constructs": ["delayed_recall", "oral_story_memory"],
        "framework_anchors": ["retention check", "EGRA-inspired oral literacy"],
    },
}

ASSESSMENT_ITEMS = [
    {
        "item_id": "num-pre-001",
        "instrument_id": "sabi-num-pre-v01",
        "subject": "numeracy",
        "phase": "pre_baseline",
        "construct": "number_recognition",
        "subskill": "recognize spoken numbers 1-20",
        "tarl_level": 0,
        "gpf_descriptor": "counts and identifies small whole numbers",
        "prompt": "I will say a number. Say the number after me: seven.",
        "acceptable_answers": ["7", "seven"],
        "scoring_rule": "1 if child repeats or identifies seven without hint; 0 otherwise.",
        "voice_only_claim_boundary": "oral number recognition only; not written numeral reading.",
        "expected_stt_risks": ["accent variation", "background noise", "short utterance"],
    },
    {
        "item_id": "num-pre-002",
        "instrument_id": "sabi-num-pre-v01",
        "subject": "numeracy",
        "phase": "pre_baseline",
        "construct": "single_digit_addition",
        "subskill": "add within ten",
        "tarl_level": 1,
        "gpf_descriptor": "solves simple addition with small whole numbers",
        "prompt": "No hints for this one: what is two plus three?",
        "acceptable_answers": ["5", "five"],
        "scoring_rule": "1 if five is given before any teaching; 0 otherwise.",
        "voice_only_claim_boundary": "mental/oral addition; not written computation.",
        "expected_stt_risks": ["five/fine confusion", "self-correction"],
    },
    {
        "item_id": "lit-pre-001",
        "instrument_id": "sabi-lit-pre-v01",
        "subject": "literacy",
        "phase": "pre_baseline",
        "construct": "beginning_sounds",
        "subskill": "identify initial sound",
        "tarl_level": 0,
        "gpf_descriptor": "recognizes sounds in spoken words",
        "prompt": "What sound do you hear at the beginning of mama?",
        "acceptable_answers": ["m", "mmm", "mu", "em"],
        "scoring_rule": "1 if /m/ sound is identified; 0 otherwise.",
        "voice_only_claim_boundary": "phonological awareness; not print decoding.",
        "expected_stt_risks": ["single-sound transcription", "Pidgin/English code switch"],
    },
    {
        "item_id": "lit-pre-002",
        "instrument_id": "sabi-lit-pre-v01",
        "subject": "literacy",
        "phase": "pre_baseline",
        "construct": "listening_comprehension",
        "subskill": "recall one story fact",
        "tarl_level": 1,
        "gpf_descriptor": "understands simple oral sentences",
        "prompt": "Listen: Ada has one red bag. What colour is Ada's bag?",
        "acceptable_answers": ["red"],
        "scoring_rule": "1 if red is answered without hint; 0 otherwise.",
        "voice_only_claim_boundary": "oral comprehension; not reading comprehension.",
        "expected_stt_risks": ["low-volume answer", "colour word accent"],
    },
    {
        "item_id": "num-mid-001",
        "instrument_id": "sabi-num-mid-v01",
        "subject": "numeracy",
        "phase": "midline",
        "construct": "word_problem_listening",
        "subskill": "addition story problem",
        "tarl_level": 1,
        "gpf_descriptor": "uses addition to solve a simple contextual problem",
        "prompt": "No help yet: you have four mangoes and get two more. How many mangoes now?",
        "acceptable_answers": ["6", "six"],
        "scoring_rule": "1 if six is answered before teaching; 0 otherwise.",
        "voice_only_claim_boundary": "oral word-problem reasoning.",
        "expected_stt_risks": ["six/sick confusion", "long pause"],
    },
    {
        "item_id": "lit-mid-001",
        "instrument_id": "sabi-lit-mid-v01",
        "subject": "literacy",
        "phase": "midline",
        "construct": "story_recall",
        "subskill": "recall key event",
        "tarl_level": 1,
        "gpf_descriptor": "recalls information from a short oral text",
        "prompt": "Listen: Tunde fed the goat before school. Who did Tunde feed?",
        "acceptable_answers": ["goat", "the goat"],
        "scoring_rule": "1 if goat is answered without hint; 0 otherwise.",
        "voice_only_claim_boundary": "oral recall; not written reading.",
        "expected_stt_risks": ["goat/got confusion", "background speech"],
    },
    {
        "item_id": "num-post-001",
        "instrument_id": "sabi-num-post-v01",
        "subject": "numeracy",
        "phase": "post_endline",
        "construct": "mastery_transfer",
        "subskill": "subtraction story problem",
        "tarl_level": 2,
        "gpf_descriptor": "solves simple subtraction in context",
        "prompt": "No help yet: you had nine sweets and gave away three. How many are left?",
        "acceptable_answers": ["6", "six"],
        "scoring_rule": "1 if six is answered before any scaffold; 0 otherwise.",
        "voice_only_claim_boundary": "oral subtraction and transfer.",
        "expected_stt_risks": ["six/sick confusion", "child repeats whole story"],
    },
    {
        "item_id": "lit-post-001",
        "instrument_id": "sabi-lit-post-v01",
        "subject": "literacy",
        "phase": "post_endline",
        "construct": "oral_comprehension",
        "subskill": "infer simple action",
        "tarl_level": 2,
        "gpf_descriptor": "understands a short oral text and answers a direct question",
        "prompt": "Listen: Amina was thirsty, so she picked up a cup. What does Amina want to do?",
        "acceptable_answers": ["drink", "drink water", "water"],
        "scoring_rule": "1 if drinking/water is answered without hint; 0 otherwise.",
        "voice_only_claim_boundary": "oral comprehension and inference.",
        "expected_stt_risks": ["multiword answer variation", "quiet child"],
    },
]

PUBLICATION_PACK_ITEMS = [
    "locked_protocol",
    "consent_codebook",
    "assessment_item_bank",
    "deidentified_child_csv",
    "item_response_csv",
    "assessment_event_csv",
    "randomization_assignment_csv",
    "dosage_adherence_csv",
    "attrition_safety_fidelity_csv",
    "analysis_snapshot_json",
    "reproducibility_readme",
]

MEASUREMENT_QUALITY_BENCHMARKS = [
    {
        "source": "J-PAL / AEA",
        "standard": "Protocol registration, pre-analysis plan, randomization metadata, balance/attrition tracking, reproducible exports.",
        "sabi_requirement": "Every cohort record carries protocol, outcomes, assignment basis, phase coverage, and export mode.",
        "status": "implemented_spine",
    },
    {
        "source": "UNESCO UIS / GPF",
        "standard": "Learning outcomes map to minimum proficiency in reading and mathematics with clear reporting language.",
        "sabi_requirement": "Each item has subject, construct, TaRL level, GPF descriptor, and voice-only claim boundary.",
        "status": "implemented_seed_mapping",
    },
    {
        "source": "TEP / LEARNigeria",
        "standard": "Nigerian foundational literacy/numeracy assessment is child-level, empirical, locally valid, and action-oriented.",
        "sabi_requirement": "Board sees what each weakness changes in the child's path and whether consent/assent is complete.",
        "status": "implemented_board_visibility",
    },
    {
        "source": "TaRL",
        "standard": "Assess actual level, teach at that level, remediate prerequisites, and reassess progress.",
        "sabi_requirement": "Baseline placement, support/rejoin paths, mid/post probes, and level movement remain visible together.",
        "status": "implemented_core_loop",
    },
    {
        "source": "EGRA / EGMA",
        "standard": "Oral one-on-one items have constructs, administration rules, scoring rules, adaptation notes, and rater review.",
        "sabi_requirement": "Fixed voice probes create assessment events and item-response rows with scorer/adjudication fields for unscored responses.",
        "status": "implemented_scaffold",
    },
]

BOARD_TRAINING_MODULES = [
    {
        "module": "1",
        "title": "Protect Consent First",
        "board_takeaway": "A child is never just a data point. Confirm caregiver consent and child assent before any measured probe.",
        "delivery_rule": "Say warmly: 'We will play a few learning questions first. It is okay to say you do not know.'",
        "do": "Record consent/assent status and pause if the child sounds unwilling or unsafe.",
        "dont": "Do not continue a measured assessment after withdrawal, distress, or missing consent.",
    },
    {
        "module": "2",
        "title": "Separate Measuring From Teaching",
        "board_takeaway": "The evidence is only credible if Sabi does not teach inside the measured item.",
        "delivery_rule": "Ask the fixed question once in neutral language, capture the response, then freeze that response.",
        "do": "After the answer is frozen, teach kindly and repair the skill.",
        "dont": "Do not hint, rephrase toward the answer, count on fingers for the child, or reward until the measured answer is captured.",
    },
    {
        "module": "3",
        "title": "Teach At The Right Level",
        "board_takeaway": "The path should morph around the child's actual level, not their age, grade, or hope.",
        "delivery_rule": "If a child misses a prerequisite, move down to the support ladder and rejoin only after success.",
        "do": "Use TaRL language: place, remediate, reassess, advance.",
        "dont": "Do not push ahead because the curriculum schedule says so.",
    },
    {
        "module": "4",
        "title": "Keep The Audit Trail Clean",
        "board_takeaway": "A funder or evaluator should be able to reconstruct what happened without trusting anyone's memory.",
        "delivery_rule": "Every call should preserve phase, item, score status, dosage, safety/fidelity flags, and next due probe.",
        "do": "Review first calls within 24 hours and mark missingness or attrition honestly.",
        "dont": "Do not delete awkward evidence or hide call drops; missing data is part of the study.",
    },
    {
        "module": "5",
        "title": "Explain The Claim Tier",
        "board_takeaway": "We can be outward-facing immediately, but we must name the evidence tier precisely.",
        "delivery_rule": "Say: 'This is publishable-grade pre-pilot evidence: methods, feasibility, data quality, and learning signal. Causal impact comes after powered randomization.'",
        "do": "Use stronger claims only when the protocol, sample size, and randomization support them.",
        "dont": "Do not call a 10-child pre-pilot a completed RCT.",
    },
]

PARTNER_IMPLEMENTATION_KIT = {
    "product_name": "Sabi Evidence Protocol Kit",
    "audience": "NGOs, school operators, research partners, funders, and field teams running Sabi with children.",
    "promise": (
        "A partner can run Sabi's publishable-grade pre-pilot protocol from day one "
        "and receive comparable protocol, consent, assessment, dosage, learning-outcome, "
        "data-quality, and export outputs."
    ),
    "api_surfaces": [
        {
            "path": "/admin/evidence-protocol-kit",
            "mode": "json",
            "purpose": "Read the current protocol, instruments, item bank, benchmark ladder, training modules, export modes, and implementation checklist.",
        },
        {
            "path": "/admin/pilot-evidence?fmt=csv&mode=board",
            "mode": "csv",
            "purpose": "Board/team export with pseudonymous operational detail for internal review.",
        },
        {
            "path": "/admin/pilot-evidence?fmt=csv&mode=evaluator",
            "mode": "csv",
            "purpose": "Evaluator export with stable child codes and research fields, without direct names.",
        },
        {
            "path": "/admin/pilot-evidence?fmt=csv&mode=public",
            "mode": "csv",
            "purpose": "Public-safe export with de-identified child codes and no raw audio or direct identifiers.",
        },
    ],
    "implementation_checklist": [
        "Run consent/assent onboarding before measured probes.",
        "Use the fixed probe plan when next_assessment_due is pre_baseline, midline, post_endline, or retention_followup.",
        "Do not coach, hint, rephrase toward the answer, or praise correctness inside a measured item.",
        "Freeze measured responses before teaching or remediation starts.",
        "Record call dosage, assessment phase, item-response review status, attrition/missingness, and safety/fidelity review.",
        "Use TaRL placement/remediation/reassessment to decide path changes.",
        "Use board/evaluator/public export modes according to audience and consent.",
        "Do not make causal impact claims until the powered randomization stage is locked and analyzed.",
    ],
    "claim_ladder": [
        {
            "stage": "10-child pre-pilot",
            "allowed_claim": "Publishable-grade methods, feasibility, data quality, assessment validity, and exploratory learning signal.",
            "not_allowed": "Definitive causal impact or RCT effect claim.",
        },
        {
            "stage": "30-child micro-randomization",
            "allowed_claim": "Feasibility of assignment, variance estimates, adherence, contamination checks, and preliminary arm comparability.",
            "not_allowed": "Final treatment effect.",
        },
        {
            "stage": "300-child controlled pilot",
            "allowed_claim": "Pre-specified treatment-control estimates with confidence intervals if protocol, power, attrition, and analysis criteria hold.",
            "not_allowed": "Claims outside registered outcomes or unreported sensitivity assumptions.",
        },
    ],
}


def configured_stage() -> str:
    stage = str(os.getenv("SABI_PILOT_RESEARCH_STAGE") or "ten_child_prepilot").strip().lower()
    return stage if stage in STUDY_STAGES else "ten_child_prepilot"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on", "consented", "recorded", "signed", "approved"}


def protocol_record(stage: str | None = None) -> dict[str, Any]:
    stage = stage or configured_stage()
    if stage not in STUDY_STAGES:
        stage = configured_stage()
    stage_spec = STUDY_STAGES[stage]
    status = str(os.getenv("SABI_PROTOCOL_STATUS") or "draft").strip().lower()
    if status not in PROTOCOL_STATUS_ORDER:
        status = "draft"
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "public_title": "Sabi phone-based foundational literacy and numeracy pilot evidence protocol",
        "study_stage": stage,
        "stage_label": stage_spec["label"],
        "status": status,
        "status_order": PROTOCOL_STATUS_ORDER,
        "registry_type": os.getenv("SABI_PROTOCOL_REGISTRY_TYPE") or "internal_pre_registration",
        "registry_url": os.getenv("SABI_PROTOCOL_REGISTRY_URL") or None,
        "pap_url": os.getenv("SABI_PROTOCOL_PAP_URL") or None,
        "irb_or_ethics_status": os.getenv("SABI_ETHICS_STATUS") or "not_submitted",
        "external_evaluator": os.getenv("SABI_EXTERNAL_EVALUATOR") or None,
        "primary_outcomes": PRIMARY_OUTCOMES,
        "secondary_outcomes": SECONDARY_OUTCOMES,
        "framework_anchors": FRAMEWORK_ANCHORS,
        "sample_plan": {
            "target_n": stage_spec["target_n"],
            "current_stage": stage_spec["label"],
            "next_stage": _next_stage_after(stage),
        },
        "power_assumption": (
            "Effect-size claims remain descriptive until the controlled pilot is powered; "
            "planning target is d>=0.30 with attrition sensitivity."
        ),
        "randomization_unit": "learner_household",
        "clustering_unit": "phone_household",
        "strata": ["baseline_numeracy_level", "baseline_literacy_level", "phone_household", "network"],
        "analysis_freeze_at": None,
    }


def evidence_protocol_kit(stage: str | None = None) -> dict[str, Any]:
    stage = stage or configured_stage()
    protocol = protocol_record(stage)
    return {
        "status": "ok",
        "kit": PARTNER_IMPLEMENTATION_KIT,
        "protocol": protocol,
        "study_stages": STUDY_STAGES,
        "assessment_phases": ASSESSMENT_PHASES,
        "study_arms": STUDY_ARMS,
        "assessment_instruments": [
            {"instrument_id": instrument_id, **instrument}
            for instrument_id, instrument in sorted(ASSESSMENT_INSTRUMENTS.items())
        ],
        "assessment_items": ASSESSMENT_ITEMS,
        "measurement_quality_benchmarks": MEASUREMENT_QUALITY_BENCHMARKS,
        "board_training": {
            "title": "Sabi Evidence Delivery Training",
            "purpose": "Teach board members and partner field teams how to protect children, protect the evidence, and explain the claim tier.",
            "modules": BOARD_TRAINING_MODULES,
            "facilitator_script": (
                "Sabi's standard is publishable-grade measurement from the first child: consent first, "
                "neutral fixed probes, no coaching inside measured items, TaRL remediation after the answer is frozen, "
                "and honest claim tiers."
            ),
        },
        "export_modes": {
            "board": "Pseudonymous operational detail for internal/board review.",
            "evaluator": "Stable child codes and research fields without direct child names.",
            "public": "De-identified public-safe export without raw audio, direct identifiers, or unnecessary operational detail.",
        },
    }


def consent_state_for(student: dict[str, Any] | None) -> dict[str, Any]:
    student = student or {}
    status = str(student.get("consent_status") or "").strip().lower()
    withdrawn = status in {"withdrawn", "revoked"} or _truthy(student.get("withdrawal_recorded"))
    caregiver = (
        status in {"consented", "signed", "approved"}
        or _truthy(student.get("consent_recorded"))
        or _truthy(student.get("caregiver_consent_recorded"))
        or bool(student.get("caregiver_phone"))
    ) and not withdrawn
    assent = _truthy(student.get("assent_recorded")) or _truthy(student.get("child_assent_recorded"))
    training_audio = (
        _truthy(student.get("audio_training_consent"))
        or _truthy(student.get("training_consent"))
        or _truthy(student.get("consent_b_recorded"))
    ) and not withdrawn

    blockers: list[str] = []
    if withdrawn:
        blockers.append("consent withdrawn")
    if not caregiver:
        blockers.append("caregiver consent missing")
    if not assent:
        blockers.append("child assent missing")

    return {
        "caregiver_consent_recorded": caregiver,
        "child_assent_recorded": assent,
        "training_audio_consent_recorded": training_audio,
        "withdrawn": withdrawn,
        "consent_mode": student.get("consent_mode") or "unknown",
        "language": student.get("consent_language") or "unknown",
        "collector": student.get("consent_collector") or None,
        "raw_audio_export_allowed": caregiver and training_audio and not withdrawn,
        "public_export_allowed": caregiver and not withdrawn,
        "child_pilot_ready": caregiver and assent and not withdrawn,
        "blockers": blockers,
        "export_rule": (
            "Public exports exclude names, phone numbers, raw child audio, and direct identifiers. "
            "Raw audio is internal-review only unless separate training/audio consent is recorded."
        ),
    }


def assessment_instruments_for_phase(phase: str | None) -> list[dict[str, Any]]:
    if not phase or phase == "monitoring":
        return []
    records = []
    for instrument_id, instrument in ASSESSMENT_INSTRUMENTS.items():
        if instrument.get("phase") == phase:
            records.append({"instrument_id": instrument_id, **instrument})
    return sorted(records, key=lambda item: (str(item.get("subject")), str(item.get("instrument_id"))))


def assessment_items_for_phase(phase: str | None) -> list[dict[str, Any]]:
    if not phase or phase == "monitoring":
        return []
    return [dict(item) for item in ASSESSMENT_ITEMS if item.get("phase") == phase]


def fixed_probe_plan_for(
    student: dict[str, Any] | None,
    *,
    assessment_status: dict[str, Any] | None = None,
    consent_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    student = student or {}
    assessment_status = assessment_status or assessment_status_for(student)
    consent_state = consent_state or consent_state_for(student)
    due = str(assessment_status.get("next_due_phase") or "monitoring")
    instruments = assessment_instruments_for_phase(due)
    items = assessment_items_for_phase(due)

    if due == "monitoring":
        mode = "adaptive_teaching"
        blocker = None
    elif not consent_state.get("caregiver_consent_recorded"):
        mode = "consent_hold"
        blocker = "Do not administer research probe until caregiver consent is recorded."
    elif not consent_state.get("child_assent_recorded"):
        mode = "assent_check"
        blocker = "Ask child assent/willingness before any fixed probe."
    else:
        mode = "fixed_probe"
        blocker = None

    return {
        "mode": mode,
        "due_phase": due,
        "due_label": ASSESSMENT_PHASES.get(due, {}).get("label", "Monitor"),
        "instrument_ids": [item["instrument_id"] for item in instruments],
        "instruments": instruments,
        "item_count": len(items),
        "items_preview": [
            {
                "item_id": item.get("item_id"),
                "subject": item.get("subject"),
                "construct": item.get("construct"),
                "tarl_level": item.get("tarl_level"),
                "prompt": item.get("prompt"),
                "scoring_rule": item.get("scoring_rule"),
            }
            for item in items[:6]
        ],
        "no_coaching_rule": due != "monitoring",
        "response_freeze_rule": due != "monitoring",
        "blocker": blocker,
    }


def normalize_measurements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict) and item.get("phase")]


def normalize_assessment_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict) and item.get("event_id")]


def normalize_item_responses(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict) and item.get("item_id")]


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
    consent = consent_state_for(student)
    probe_plan = fixed_probe_plan_for(student, assessment_status=status, consent_state=consent)
    protocol = protocol_record(stage)
    return {
        "protocol_id": protocol["protocol_id"],
        "protocol_version": PROTOCOL_VERSION,
        "protocol": protocol,
        "study_stage": stage,
        "stage_label": STUDY_STAGES[stage]["label"],
        "design": STUDY_STAGES[stage]["design"],
        "claim_boundary": STUDY_STAGES[stage]["claim_boundary"],
        "philosophy": PHILOSOPHY,
        "consent": consent,
        "assignment": assignment,
        "assessment_status": status,
        "fixed_probe_plan": probe_plan,
        "assessment_instruments": probe_plan["instruments"],
        "measurements": measurements[-12:],
        "assessment_events": normalize_assessment_events(student.get("assessment_events"))[-24:],
        "item_responses": normalize_item_responses(student.get("item_responses"))[-48:],
        "schedule": ASSESSMENT_PHASES,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def initial_research_payload(student: dict[str, Any] | None = None) -> dict[str, Any]:
    state = build_research_state(student or {})
    return {
        "study_stage": state["study_stage"],
        "study_arm": state["assignment"]["arm"],
        "research_measurements": state["measurements"],
        "assessment_events": state["assessment_events"],
        "item_responses": state["item_responses"],
        "consent_state": state["consent"],
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
    events = normalize_assessment_events(student.get("assessment_events"))
    responses = normalize_item_responses(student.get("item_responses"))
    consent = consent_state_for(student)

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
        event_id = _assessment_event_id(student, due, call_count_after)
        instruments = assessment_instruments_for_phase(due)
        items = assessment_items_for_phase(due)
        events.append({
            "event_id": event_id,
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "phase": due,
            "instrument_ids": [item["instrument_id"] for item in instruments],
            "assessment_mode": "voice_fixed_oral",
            "administration_rule": "neutral_no_coaching_until_measured_response_is_frozen",
            "started_at": now,
            "completed_at": now,
            "call_count_after": int(call_count_after),
            "duration_seconds": int(duration_seconds or 0),
            "aggregate_probe_score": round(float(probe_score), 3) if probe_score is not None else None,
            "scoring_status": "aggregate_scored_item_level_ready_for_adjudication",
            "consent_snapshot": consent,
            "interruption_flag": False,
            "blinded_flag": False,
        })
        for item in items:
            responses.append({
                "response_id": f"{event_id}:{item['item_id']}",
                "event_id": event_id,
                "item_id": item["item_id"],
                "instrument_id": item["instrument_id"],
                "phase": due,
                "subject": item["subject"],
                "construct": item["construct"],
                "subskill": item["subskill"],
                "tarl_level": item["tarl_level"],
                "score": None,
                "aggregate_event_score": round(float(probe_score), 3) if probe_score is not None else None,
                "review_status": "ready_for_item_level_scoring",
                "scoring_rule": item["scoring_rule"],
                "voice_only_claim_boundary": item["voice_only_claim_boundary"],
                "captured_at": now,
            })
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
        "assessment_events": events,
        "item_responses": responses,
    }
    research_state = build_research_state(base_for_state, calls_completed=call_count_after)
    return {
        "study_stage": research_state["study_stage"],
        "study_arm": research_state["assignment"]["arm"],
        "research_measurements": measurements[-24:],
        "assessment_events": events[-48:],
        "item_responses": responses[-96:],
        "consent_state": consent,
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
    consent = research_state.get("consent") if isinstance(research_state.get("consent"), dict) else {}
    probe_plan = research_state.get("fixed_probe_plan") if isinstance(research_state.get("fixed_probe_plan"), dict) else {}
    instrument_ids = probe_plan.get("instrument_ids") if isinstance(probe_plan.get("instrument_ids"), list) else []
    item_count = int(probe_plan.get("item_count") or 0)
    mode = str(probe_plan.get("mode") or "adaptive_teaching")
    blocker = probe_plan.get("blocker")
    consent_line = (
        f"caregiver={bool(consent.get('caregiver_consent_recorded'))}; "
        f"child_assent={bool(consent.get('child_assent_recorded'))}; "
        f"raw_audio_export={bool(consent.get('raw_audio_export_allowed'))}"
    )
    mode_line = (
        f"Measurement mode: {mode}. Instruments due: {', '.join(instrument_ids) if instrument_ids else 'none'}. "
        f"Fixed items available: {item_count}."
    )
    if blocker:
        mode_line = f"{mode_line} Blocker: {blocker}"
    return f"""

## PILOT EVIDENCE PROTOCOL
- Protocol: {research_state.get('protocol_id', PROTOCOL_ID)} / {research_state.get('protocol_version', PROTOCOL_VERSION)}
- Stage: {research_state.get('stage_label', '10-child pre-pilot')}
- Design: {research_state.get('design', STUDY_STAGES['ten_child_prepilot']['design'])}
- Study arm: {assignment.get('label', assignment.get('arm', 'measured pre-pilot'))}
- Consent/assent: {consent_line}
- {mode_line}
- Assessment rule: {due_line}
- Evidence standard: publishable-grade methods from call one; preserve clean item-level evidence and never coach inside measured items.
- During a fixed probe, ask neutrally, capture the answer, do not hint/rephrase toward the answer, then resume warm TaRL teaching only after the measured response is frozen.
- Claim boundary: {research_state.get('claim_boundary', STUDY_STAGES['ten_child_prepilot']['claim_boundary'])}"""


def cohort_research_rollup(children: list[dict[str, Any]]) -> dict[str, Any]:
    arm_counts: dict[str, int] = {}
    phase_counts = {phase: 0 for phase in ASSESSMENT_PHASES}
    due_counts: dict[str, int] = {}
    consent_counts = {
        "caregiver_consent": 0,
        "child_assent": 0,
        "training_audio": 0,
        "withdrawn": 0,
        "public_export_allowed": 0,
    }
    fixed_probe_events = 0
    item_response_count = 0
    pending_item_scores = 0
    for child in children:
        research = child.get("research") if isinstance(child.get("research"), dict) else {}
        assignment = research.get("assignment") if isinstance(research.get("assignment"), dict) else {}
        arm = str(assignment.get("arm") or "unknown")
        arm_counts[arm] = arm_counts.get(arm, 0) + 1
        consent = research.get("consent") if isinstance(research.get("consent"), dict) else {}
        if consent.get("caregiver_consent_recorded"):
            consent_counts["caregiver_consent"] += 1
        if consent.get("child_assent_recorded"):
            consent_counts["child_assent"] += 1
        if consent.get("training_audio_consent_recorded"):
            consent_counts["training_audio"] += 1
        if consent.get("withdrawn"):
            consent_counts["withdrawn"] += 1
        if consent.get("public_export_allowed"):
            consent_counts["public_export_allowed"] += 1
        status = research.get("assessment_status") if isinstance(research.get("assessment_status"), dict) else {}
        due = str(status.get("next_due_phase") or "unknown")
        due_counts[due] = due_counts.get(due, 0) + 1
        phases = {str(item.get("phase")) for item in normalize_measurements(research.get("measurements"))}
        for phase in phase_counts:
            if phase in phases:
                phase_counts[phase] += 1
        events = normalize_assessment_events(research.get("assessment_events"))
        responses = normalize_item_responses(research.get("item_responses"))
        fixed_probe_events += sum(1 for event in events if event.get("assessment_mode") == "voice_fixed_oral")
        item_response_count += len(responses)
        pending_item_scores += sum(1 for response in responses if response.get("score") is None)
    stage = configured_stage()
    n = len(children)
    protocol = protocol_record(stage)
    partner_kit = evidence_protocol_kit(stage)["kit"]
    protocol_ready = _protocol_ready(protocol)
    instrument_ready = instrument_readiness_summary()
    data_quality = _cohort_data_quality(
        n=n,
        phase_counts=phase_counts,
        fixed_probe_events=fixed_probe_events,
        item_response_count=item_response_count,
        pending_item_scores=pending_item_scores,
    )
    publication_pack = publication_pack_status(
        protocol_ready=protocol_ready,
        instrument_ready=instrument_ready,
        data_quality=data_quality,
        phase_counts=phase_counts,
    )
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "protocol": protocol,
        "stage": stage,
        "stage_label": STUDY_STAGES[stage]["label"],
        "design": STUDY_STAGES[stage]["design"],
        "philosophy": PHILOSOPHY,
        "arm_distribution": arm_counts,
        "measurement_counts": phase_counts,
        "consent_counts": consent_counts,
        "next_due_counts": due_counts,
        "instrument_readiness": instrument_ready,
        "data_quality": data_quality,
        "publication_pack": publication_pack,
        "measurement_quality_benchmarks": MEASUREMENT_QUALITY_BENCHMARKS,
        "board_training": {
            "title": "Sabi Evidence Delivery Training",
            "purpose": "Teach board members and pilot operators how to protect children, protect the evidence, and explain the claim tier.",
            "modules": BOARD_TRAINING_MODULES,
            "facilitator_script": (
                "Sabi's standard is publishable-grade measurement from the first child: consent first, "
                "neutral fixed probes, no coaching inside measured items, TaRL remediation after the answer is frozen, "
                "and honest claim tiers."
            ),
        },
        "partner_implementation_kit": partner_kit,
        "rct_readiness": {
            "assignment_recorded": sum(arm_counts.values()),
            "baseline_records": phase_counts["pre_baseline"],
            "midline_records": phase_counts["midline"],
            "endline_records": phase_counts["post_endline"],
            "retention_records": phase_counts["retention_followup"],
            "fixed_probe_events": fixed_probe_events,
            "item_response_records": item_response_count,
            "pending_item_scores": pending_item_scores,
            "protocol_board_locked": protocol.get("status") in {"board_locked", "ethics_ready", "registered", "active", "analysis_frozen", "reported"},
            "ethics_ready": protocol.get("status") in {"ethics_ready", "registered", "active", "analysis_frozen", "reported"},
        },
        "claim_boundary": STUDY_STAGES[stage]["claim_boundary"],
        "next_design_step": (
            "For the 10-child pre-pilot, complete publishable-grade pre/mid/post probes, consent audit, item-level scoring, and first-call review. "
            "For the 30-child micro-pilot, switch SABI_PILOT_RESEARCH_STAGE to thirty_child_micro_rct "
            "only after consent scripts and independent review are ready."
        ),
    }


def instrument_readiness_summary() -> dict[str, Any]:
    by_phase: dict[str, dict[str, Any]] = {}
    for phase in ASSESSMENT_PHASES:
        instruments = assessment_instruments_for_phase(phase)
        items = assessment_items_for_phase(phase)
        reviewed = [item for item in instruments if item.get("review_status") in {"tep_reviewed", "external_reviewed", "approved"}]
        by_phase[phase] = {
            "instrument_count": len(instruments),
            "item_count": len(items),
            "reviewed_count": len(reviewed),
            "subjects": sorted({str(item.get("subject")) for item in instruments}),
            "status": "ready_for_internal_prepilot" if instruments and items else "missing",
        }
    total_instruments = len(ASSESSMENT_INSTRUMENTS)
    total_items = len(ASSESSMENT_ITEMS)
    return {
        "status": "ready_for_internal_prepilot" if total_instruments >= 4 and total_items >= 4 else "missing_items",
        "total_instruments": total_instruments,
        "total_items": total_items,
        "review_status": "needs_TEP_LEARNigeria_or_external_assessment_review",
        "frameworks": list(FRAMEWORK_ANCHORS),
        "by_phase": by_phase,
    }


def publication_pack_status(
    *,
    protocol_ready: dict[str, Any],
    instrument_ready: dict[str, Any],
    data_quality: dict[str, Any],
    phase_counts: dict[str, int],
) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    items["locked_protocol"] = {
        "ready": protocol_ready["status"] != "draft",
        "note": "Protocol should be board-locked before the first external-facing child evidence report.",
    }
    items["consent_codebook"] = {"ready": False, "note": "Consent records table and withdrawal workflow must be populated."}
    items["assessment_item_bank"] = {
        "ready": instrument_ready["total_items"] > 0,
        "note": f"{instrument_ready['total_items']} seeded items; external review still needed.",
    }
    items["deidentified_child_csv"] = {"ready": True, "note": "Available through board/evaluator/public export modes."}
    items["item_response_csv"] = {
        "ready": data_quality["item_response_records"] > 0,
        "note": "Ready after fixed probes create item-response rows; unscored responses are flagged.",
    }
    items["assessment_event_csv"] = {
        "ready": data_quality["fixed_probe_events"] > 0,
        "note": "Ready after baseline/mid/post events are captured.",
    }
    items["randomization_assignment_csv"] = {"ready": False, "note": "Needed for 30-child and 300-child stages."}
    items["dosage_adherence_csv"] = {"ready": True, "note": "Calls/minutes are already included in evidence export."}
    items["attrition_safety_fidelity_csv"] = {"ready": False, "note": "Attrition reasons and safety/fidelity review fields need live rows."}
    items["analysis_snapshot_json"] = {
        "ready": phase_counts.get("pre_baseline", 0) > 0,
        "note": "Current JSON report is snapshot-ready once baseline evidence exists.",
    }
    items["reproducibility_readme"] = {"ready": False, "note": "Add after export schema stabilizes."}
    ready_count = sum(1 for item in items.values() if item["ready"])
    return {
        "ready_count": ready_count,
        "total_count": len(items),
        "status": "partial" if ready_count else "not_started",
        "items": items,
    }


def _protocol_ready(protocol: dict[str, Any]) -> dict[str, Any]:
    status = str(protocol.get("status") or "draft")
    index = PROTOCOL_STATUS_ORDER.index(status) if status in PROTOCOL_STATUS_ORDER else 0
    checklist = {
        "protocol_versioned": bool(protocol.get("protocol_version")),
        "outcomes_named": bool(protocol.get("primary_outcomes")),
        "sample_plan_named": bool(protocol.get("sample_plan")),
        "registry_or_internal_prereg_named": bool(protocol.get("registry_type")),
        "ethics_status_named": bool(protocol.get("irb_or_ethics_status")),
        "board_locked": index >= PROTOCOL_STATUS_ORDER.index("board_locked"),
        "ethics_ready": index >= PROTOCOL_STATUS_ORDER.index("ethics_ready"),
    }
    return {
        "status": status,
        "step_index": index,
        "step_total": len(PROTOCOL_STATUS_ORDER) - 1,
        "checklist": checklist,
        "missing": [key for key, value in checklist.items() if not value],
    }


def _cohort_data_quality(
    *,
    n: int,
    phase_counts: dict[str, int],
    fixed_probe_events: int,
    item_response_count: int,
    pending_item_scores: int,
) -> dict[str, Any]:
    def coverage(phase: str) -> float | None:
        if not n:
            return None
        return round(float(phase_counts.get(phase, 0)) / n, 3)

    return {
        "cohort_n": n,
        "baseline_coverage": coverage("pre_baseline"),
        "midline_coverage": coverage("midline"),
        "endline_coverage": coverage("post_endline"),
        "retention_coverage": coverage("retention_followup"),
        "fixed_probe_events": fixed_probe_events,
        "item_response_records": item_response_count,
        "pending_item_scores": pending_item_scores,
        "item_scoring_complete_rate": (
            round((item_response_count - pending_item_scores) / item_response_count, 3)
            if item_response_count else None
        ),
        "status": (
            "baseline_started"
            if phase_counts.get("pre_baseline", 0) > 0
            else "awaiting_child_baselines"
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


def _next_stage_after(stage: str) -> str | None:
    order = ["ten_child_prepilot", "thirty_child_micro_rct", "three_hundred_child_rct"]
    try:
        index = order.index(stage)
    except ValueError:
        return order[0]
    if index + 1 >= len(order):
        return None
    return order[index + 1]


def _assessment_event_id(student: dict[str, Any], phase: str, call_count_after: int) -> str:
    subject = stable_subject_key(student)
    digest = hashlib.sha256(f"{PROTOCOL_ID}:{subject}:{phase}:{call_count_after}".encode("utf-8")).hexdigest()[:12]
    return f"{PROTOCOL_ID}:{phase}:{digest}"
