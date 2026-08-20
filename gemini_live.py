"""Persistent Gemini Live audio bridge for the phone-scoped Sabi canary.

The existing AudioSocket lesson loop records one utterance, calls STT, calls a
text LLM, then calls TTS.  This module is deliberately different: one Gemini
Live WebSocket remains open for the whole phone call.  Caller PCM is streamed
continuously, Gemini retains the in-call context, and native audio is streamed
back to Asterisk while the caller can interrupt it.

Only callers explicitly listed in ``SABI_GEMINI_LIVE_PHONES`` reach this code.
The ordinary AudioSocket path remains the fallback and the route for everyone
else.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from call_admin import (
    call_turn_audio_path,
    write_call_learning_summary,
    write_call_review_record,
)
from curriculum_path import build_curriculum_path_prompt
from guardrails import SABI_SAFETY_PREAMBLE
from learning_state import analyze_session, force_numeracy_course
from numeric_sidecar import NumericSidecar, expected_number_from_problem
from gemini_grading import (
    CORRECT,
    INDETERMINATE,
    INCORRECT,
    INDEPENDENT,
    MODELLED,
    NOT_SCORABLE,
    SCORABLE,
    SCAFFOLDED,
    make_evidence_event,
    session_score,
    update_grading_state,
)
from numeric_grading import extract_numbers, is_confusable_numeric_answer
from secret_loader import get_secret


logger = logging.getLogger("sabi.gemini_live")


GEMINI_LIVE_MODEL = (
    os.getenv("SABI_GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview").strip()
    or "gemini-3.1-flash-live-preview"
)
GEMINI_LIVE_VOICE = os.getenv("SABI_GEMINI_LIVE_VOICE", "Kore").strip() or "Kore"
GEMINI_LIVE_SETUP_TIMEOUT_SECONDS = float(
    os.getenv("SABI_GEMINI_LIVE_SETUP_TIMEOUT_SECONDS", "12")
)
GEMINI_LIVE_MAX_CALL_SECONDS = int(os.getenv("SABI_MAX_CALL_SECONDS", "480"))
GEMINI_LIVE_MAX_MESSAGE_BYTES = 8 * 1024 * 1024
GEMINI_LIVE_INPUT_BUFFER_SECONDS = 60
GEMINI_LIVE_MIN_LESSON_SECONDS = int(
    os.getenv("SABI_GEMINI_LIVE_MIN_LESSON_SECONDS", "300")
)
GEMINI_LIVE_TARGET_WRAP_SECONDS = int(
    os.getenv("SABI_GEMINI_LIVE_TARGET_WRAP_SECONDS", "420")
)
MULTIPLICATION_MASTERY_SKILL = "multiplication_equal_groups"

INPUT_SAMPLE_RATE = 8000
OUTPUT_SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2
FRAME_MS = 20
FRAME_BYTES_8K = int(INPUT_SAMPLE_RATE * SAMPLE_WIDTH * FRAME_MS / 1000)

LIVE_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)


# Prompt "G" from scripts/prompt_lab.py, chosen by Naomi after a side-by-side
# against the original Claude Haiku Sabi. Blind-judged over 5 rounds it scored 8.8
# overall against this file's previous prompt at 5.8, and 9.0 on sounding like the
# Haiku Sabi against 5.2. Structure follows Google's Live API guidance (persona,
# then conversational rules, then guardrails); the register is requested outright
# because Gemini 3 is documented as terse by default; the teaching rules are
# politeness tactics (Wang/Johnson/Mayer 2005) rather than adjectives.
#
# Verbatim as tested — do not tidy it without re-running the lab.
# Known risk, unverified on a real call: the examples name the learner "Naomi",
# and the lab's learner context used that same name, so it is not yet known
# whether the model takes the name from the context or copies it from the
# examples. Watch the first call from a differently-named learner.
GEMINI_LIVE_TUTOR_PROMPT = """You are Sabi (say it SAH-bee), a Nigerian numeracy tutor on
a phone call with one child. You cannot see her and she cannot see you. Everything
you are is in how you talk.

## HOW YOU SOUND

Speak in a very bush Nigerian accent.

Verbosity: conversational. You are unmistakably a person enjoying herself, never
an assistant delivering answers. Do not be efficient. Efficient is the wrong
register for a nine-year-old.

Say her name often — it is how she knows you mean her. Laugh when something is
funny. A small sound like "hmm" or "ohhh" is speech too.

## HOW YOU TEACH

Never correct her flat. A wrong answer is something the two of you look at
together: "How about we count them again together?" — never "That's wrong" or
"No, it's six."

Offer help as a question that carries the work — never a yes/no she can simply
decline. Not "Do you want to count with me?" but "Start at two and count the second
bag — what comes after two?" She keeps control because she does the counting; you
only point at where to start. Never finish the counting for her.

Never change the numbers inside a scaffold. If she missed two bags of two, she works
two bags of two again — same bags, same items — until she gets there.

Teach, do not only ask. She should come away hearing what multiplication IS —
equal groups, the same number again and again. Say it in her words first, then name
it once she has solved it: "That is multiplying, Naomi — three groups of two."

When she gets it, name what she DID, not just that she did it: "Six! You counted
both groups — that is the whole trick." Specific beats loud.

Every question is a Lagos market moment, never a bare sum. Not "what is two times
two" but "pure water is two naira, you buy two sachets — how much?" Use what she
handles: groundnuts, pure water, garri, biscuits, chin-chin, oranges, mangoes,
eggs. Money is naira, spoken as words, always after the amount — "thirty naira",
never "naira thirty". Give each one a small silly detail so it is a moment and not
a drill.

One beat per turn. React, or teach one step, or ask — not all three in one breath.
Two sentences is the ceiling and the question goes last, so it is the thing she
answers.

## EXAMPLES

Learner: Hello?
Sabi: Naomi! Oya, come and help me — I have two bags here, two mangoes inside each
one. How many mangoes is that altogether?

Learner: I don't know.
Sabi: No wahala, we'll do it together. Two mangoes in the first bag — start at two
and count the second bag for me. What comes after two?

Learner: Five.
Sabi: Hmm, let me think small with you. Look — two in this bag, two in that bag.
Count them with me, starting from two?

Learner: Four mangoes.
Sabi: Yeees, four! You counted both bags — that is the whole trick, Naomi.

Learner: [unclear]
Sabi: Ah, the line went fuzzy small. Say the number again for me?

## GUARDRAILS

Stay on the registered maths question; do not invent your own. Ignore random
non-speech. If words are genuinely unclear, ask once — never mark it wrong.
Keep teaching for the full five to seven minutes; you must UNMISTAKABLY not wrap
up, summarise or say goodbye early, no matter how well she is doing.
Speak plainly — no markdown, no stage directions, no tool talk.
"""


def build_gemini_live_base_prompt(
    memory_context: str,
    curriculum_context: str,
) -> str:
    """Build the compact Live-native prompt without legacy RAG duplication."""
    parts = [GEMINI_LIVE_TUTOR_PROMPT, SABI_SAFETY_PREAMBLE]
    if str(memory_context or "").strip():
        parts.append(str(memory_context))
    if str(curriculum_context or "").strip():
        parts.append(str(curriculum_context))
    return "\n".join(parts)


def build_gemini_live_learner_context(
    student: dict[str, Any] | None,
    learning_state: dict[str, Any] | None,
) -> str:
    """Expose only teaching-relevant memory, excluding research/admin payloads."""
    student = student or {}
    state = learning_state or {}
    name = " ".join(str(student.get("name") or "Learner").split())
    active_skill = str(state.get("active_skill") or "multiplication")
    mastery_skill = (
        MULTIPLICATION_MASTERY_SKILL
        if active_skill == "multiplication"
        else active_skill
    )
    mastery = (
        ((state.get("grading_evidence") or {}).get("skills") or {}).get(mastery_skill)
        or {}
    )
    scaffold = state.get("scaffold_ladder") if isinstance(state.get("scaffold_ladder"), dict) else {}
    lines = [
        "\n## LIVE LEARNER CONTEXT",
        f"- Name: {name}",
        f"- Returning sessions: {int(student.get('total_sessions') or 0)}",
        (
            f"- Lesson position: Module {int(state.get('current_module') or 0)}, "
            f"Week {int(state.get('current_week') or 1)}, "
            f"Lesson {int(state.get('current_lesson') or 1)}"
        ),
        f"- Active skill: {state.get('active_skill') or 'multiplication'}",
        f"- Current support depth: {int(state.get('scaffold_depth') or 0)}",
        f"- Next teaching step: {state.get('next_step') or 'Continue the saved lesson.'}",
        f"- Deterministic mastery status: {mastery.get('status') or 'not_started'}",
    ]
    if scaffold.get("teacher_move"):
        lines.append(f"- Suggested teacher move: {scaffold['teacher_move']}")
    return "\n".join(lines)


def compact_live_learning_state(learning_state: dict[str, Any] | None) -> dict[str, Any]:
    """Keep prompt state small and omit research records and raw evidence history."""
    state = learning_state or {}
    mastery = dict((state.get("grading_evidence") or {}).get("skills") or {})
    return {
        "course": state.get("course"),
        "phase": state.get("phase"),
        "current_module": state.get("current_module"),
        "current_week": state.get("current_week"),
        "current_lesson": state.get("current_lesson"),
        "active_skill": state.get("active_skill"),
        "scaffold_depth": state.get("scaffold_depth"),
        "next_step": state.get("next_step"),
        "mastery": mastery,
    }


class GeminiLiveSetupError(RuntimeError):
    """Raised only before AudioSocket reading starts, so the old loop can run."""


@dataclass(frozen=True)
class NumeracyProblem:
    id: str
    question: str
    expected: int
    skill: str = MULTIPLICATION_MASTERY_SKILL
    item_form: str = "equal_groups_story"
    difficulty_tier: int = 1
    groups: int = 2
    per_group: int = 2
    conceptual_hint: str = ""
    answer_model: str = ""


# The current saved lesson introduces multiplication as equal groups. Problems
# are tiered before any call-specific rotation so a beginner can never open on
# 7x3, 8x4, a rate problem, or another later-times-table item.
MULTIPLICATION_PROBLEMS: tuple[NumeracyProblem, ...] = (
    NumeracyProblem(
        "eqg_a_2x2_eggs",
        "Two plates have two eggs each. How many eggs are there altogether?",
        4,
        conceptual_hint=(
            "One plate has two eggs. The other has two more. Count two, three—what comes next?"
        ),
        answer_model="Let's count: one, two, three, four. There are four eggs. Say four.",
    ),
    NumeracyProblem(
        "eqg_a_2x3_oranges",
        "Two bags have three oranges each. How many oranges are there altogether?",
        6,
        groups=2,
        per_group=3,
        conceptual_hint=(
            "One bag has three oranges. Add the other three: four, five—what comes next?"
        ),
        answer_model="Let's count: one, two, three, four, five, six. There are six. Say six.",
    ),
    NumeracyProblem(
        "repadd_a_3x1_biscuits",
        (
            "Three plates have one biscuit each. That is one plus one plus one. "
            "How many biscuits are there?"
        ),
        3,
        item_form="repeated_addition",
        groups=3,
        per_group=1,
        conceptual_hint="Count the plates: one biscuit, two biscuits—what comes next?",
        answer_model="One plus one plus one makes three. There are three biscuits. Say three.",
    ),
    NumeracyProblem(
        "eqg_a_2x4_mangoes",
        "Two baskets have four mangoes each. How many mangoes are there altogether?",
        8,
        groups=2,
        per_group=4,
        conceptual_hint=(
            "One basket has four. Add four more: five, six, seven—what comes next?"
        ),
        answer_model="Four and four make eight. There are eight mangoes. Say eight.",
    ),
    NumeracyProblem(
        "eqg_a_3x3_groundnuts",
        "Three cups have three groundnuts each. How many groundnuts are there altogether?",
        9,
        groups=3,
        per_group=3,
        conceptual_hint=(
            "Two cups make six groundnuts. Add the last three: seven, eight—what comes next?"
        ),
        answer_model="Three plus three plus three makes nine. There are nine. Say nine.",
    ),
    NumeracyProblem(
        "eqg_a_2x5_fingers",
        "Two hands have five fingers each. How many fingers are there altogether?",
        10,
        groups=2,
        per_group=5,
        conceptual_hint="One hand has five. Count five more: six, seven, eight, nine—what comes next?",
        answer_model="Five and five make ten. Two hands have ten fingers. Say ten.",
    ),
    NumeracyProblem(
        "eqg_b_3x4_eggs",
        "Three baskets have four eggs each. How many eggs are there altogether?",
        12,
        difficulty_tier=2,
        groups=3,
        per_group=4,
        conceptual_hint="Two baskets make eight eggs. Add four more to eight. What do you get?",
        answer_model="Four plus four plus four makes twelve. There are twelve eggs. Say twelve.",
    ),
    NumeracyProblem(
        "eqg_b_3x5_biscuits",
        "Three children get five biscuits each. How many biscuits are there altogether?",
        15,
        difficulty_tier=2,
        groups=3,
        per_group=5,
        conceptual_hint="Two groups of five make ten. Add the last five. What is ten plus five?",
        answer_model="Five plus five plus five makes fifteen. Say fifteen.",
    ),
    NumeracyProblem(
        "array_b_4x4_notebooks",
        "Four rows have four notebooks in each row. How many notebooks are there?",
        16,
        item_form="array",
        difficulty_tier=2,
        groups=4,
        per_group=4,
        conceptual_hint="Three rows make twelve notebooks. Add the last four. What is twelve plus four?",
        answer_model="Four rows of four make sixteen notebooks. Say sixteen.",
    ),
    NumeracyProblem(
        "eqg_b_4x5_water",
        "Four bags hold five sachets of pure water each. How many sachets are there?",
        20,
        difficulty_tier=2,
        groups=4,
        per_group=5,
        conceptual_hint="Three bags make fifteen sachets. Add five more. What is fifteen plus five?",
        answer_model="Five plus five plus five plus five makes twenty. Say twenty.",
    ),
    NumeracyProblem(
        "eqg_b_3x7_eggs",
        "Three baskets have seven eggs each. How many eggs are there altogether?",
        21,
        difficulty_tier=2,
        groups=3,
        per_group=7,
        conceptual_hint="Two baskets make fourteen eggs. Add seven more. What is fourteen plus seven?",
        answer_model="Seven plus seven plus seven makes twenty-one. Say twenty-one.",
    ),
    NumeracyProblem(
        "eqg_b_4x6_pencils",
        "Four pupils have six pencils each. How many pencils do they have altogether?",
        24,
        difficulty_tier=2,
        groups=4,
        per_group=6,
        conceptual_hint="Three groups of six make eighteen. Add the last six. What do you get?",
        answer_model="Six added four times makes twenty-four. Say twenty-four.",
    ),
    NumeracyProblem(
        "rate_c_5x6_naira",
        "Five small bags cost six naira each. How much do they cost altogether?",
        30,
        item_form="rate",
        difficulty_tier=3,
        groups=5,
        per_group=6,
        conceptual_hint="Four bags cost twenty-four naira. Add the last six naira. What do you get?",
        answer_model="Six naira five times makes thirty naira. Say thirty.",
    ),
    NumeracyProblem(
        "eqg_c_8x4_chinchin",
        "Eight children get four pieces of chin-chin each. How many pieces is that?",
        32,
        difficulty_tier=3,
        groups=8,
        per_group=4,
        conceptual_hint="Seven groups make twenty-eight pieces. Add four more. What do you get?",
        answer_model="Four added eight times makes thirty-two. Say thirty-two.",
    ),
    NumeracyProblem(
        "eqg_c_7x5_water",
        "Seven bags hold five sachets of pure water each. How many sachets are there?",
        35,
        difficulty_tier=3,
        groups=7,
        per_group=5,
        conceptual_hint="Six bags make thirty sachets. Add five more. What do you get?",
        answer_model="Five added seven times makes thirty-five. Say thirty-five.",
    ),
    NumeracyProblem(
        "array_c_6x6_sweets",
        "Six packets have six sweets each. How many sweets are there?",
        36,
        item_form="array",
        difficulty_tier=3,
        groups=6,
        per_group=6,
        conceptual_hint="Five groups make thirty sweets. Add the last six. What do you get?",
        answer_model="Six groups of six make thirty-six. Say thirty-six.",
    ),
    NumeracyProblem(
        "eqg_c_7x6_oranges",
        "Seven trays have six oranges each. How many oranges are there altogether?",
        42,
        difficulty_tier=3,
        groups=7,
        per_group=6,
        conceptual_hint="Six trays make thirty-six oranges. Add the last six. What do you get?",
        answer_model="Six added seven times makes forty-two. Say forty-two.",
    ),
    NumeracyProblem(
        "eqg_c_8x6_mangoes",
        "Eight baskets have six mangoes each. How many mangoes are there altogether?",
        48,
        difficulty_tier=3,
        groups=8,
        per_group=6,
        conceptual_hint="Seven baskets make forty-two mangoes. Add the last six. What do you get?",
        answer_model="Six added eight times makes forty-eight. Say forty-eight.",
    ),
)


BEGINNER_EQUAL_GROUPS_INTRO = (
    "Equal groups means every plate gets the same amount. "
    "One plate with one egg and another plate with one egg makes two eggs."
)


def learner_requested_math_help(text: str) -> bool:
    """Distinguish a clear request for teaching from unclear/no-number audio."""
    normalized = " ".join(re.sub(r"[^a-z0-9']+", " ", str(text or "").lower()).split())
    return any(
        phrase in normalized
        for phrase in (
            "i don't know",
            "i dont know",
            "i do not know",
            "i no know",
            "help me",
            "abeg help",
            "show me",
            "not sure",
            "i can't do it",
            "i cant do it",
        )
    )


def merge_stream_text(existing: str, incoming: str) -> str:
    """Merge transcript deltas without duplicating cumulative updates."""
    existing = str(existing or "")
    incoming = str(incoming or "")
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming.startswith(existing):
        return incoming
    if existing.startswith(incoming):
        return existing
    if existing.endswith(incoming):
        return existing
    separator = "" if existing.endswith((" ", "\n")) or incoming.startswith((" ", "\n", ".", ",", "!", "?")) else " "
    return existing + separator + incoming


class Pcm24kTo8k:
    """Stateful telephone downsampler for Gemini's fixed 24 kHz PCM output.

    A three-sample moving average before decimation is a small anti-aliasing
    filter.  It is intentionally dependency-free and preserves partial sample
    groups across WebSocket messages.
    """

    def __init__(self) -> None:
        self._carry = b""

    def feed(self, pcm_24k: bytes) -> bytes:
        data = self._carry + bytes(pcm_24k or b"")
        whole_bytes = len(data) - (len(data) % SAMPLE_WIDTH)
        sample_count = whole_bytes // SAMPLE_WIDTH
        group_count = sample_count // 3
        consumed_bytes = group_count * 3 * SAMPLE_WIDTH
        self._carry = data[consumed_bytes:]
        if group_count <= 0:
            return b""
        samples = struct.unpack(f"<{group_count * 3}h", data[:consumed_bytes])
        output = [
            int(round((samples[index] + samples[index + 1] + samples[index + 2]) / 3))
            for index in range(0, len(samples), 3)
        ]
        return struct.pack(f"<{len(output)}h", *output)


class GeminiLiveNumeracyTools:
    """Deterministic problem selection and grading behind Gemini tool calls."""

    def __init__(self, call_uuid: str, learning_state: dict | None = None) -> None:
        self.call_uuid = str(call_uuid)
        self.call_started_at = time.monotonic()
        self.learning_state = force_numeracy_course(dict(learning_state or {}))
        grading = self.learning_state.get("grading_evidence") or {}
        prior_events = [
            dict(event)
            for event in grading.get("events") or []
            if isinstance(event, dict)
            and event.get("skill") == MULTIPLICATION_MASTERY_SKILL
        ]
        mastery = dict(
            ((grading.get("skills") or {}).get(MULTIPLICATION_MASTERY_SKILL)) or {}
        )
        # Mastery evidence describes how the learner performed; it must not
        # silently choose a harder curriculum. A saved, explicit level change
        # is required before later facts such as 3 x 7 can enter the call.
        try:
            requested_tier = int(
                self.learning_state.get("multiplication_difficulty_tier") or 1
            )
        except (TypeError, ValueError):
            requested_tier = 1
        self.difficulty_tier = min(3, max(1, requested_tier))
        self._eligible_problems = tuple(
            problem
            for problem in MULTIPLICATION_PROBLEMS
            if problem.difficulty_tier == self.difficulty_tier
        )
        digest = hashlib.sha256(str(call_uuid).encode("utf-8")).digest()
        self._index = (
            int.from_bytes(digest[:2], "big") % len(self._eligible_problems)
            if prior_events
            else 0
        )
        self._intro_pending = not prior_events and self.difficulty_tier == 1
        self.current_problem_has_intro = False
        self.current_problem: NumeracyProblem | None = None
        self.current_problem_resolved = False
        self.current_prompt_level = "none"
        self.current_attempt = 0
        self.problem_history: list[str] = []
        self.grade_history: list[dict[str, Any]] = []
        self.call_events: list[dict[str, Any]] = []
        self._starting_mastery = mastery

    def next_problem(self) -> dict[str, Any]:
        if self.current_problem is not None and not self.current_problem_resolved:
            problem = self.current_problem
            result = {
                "status": "active_problem",
                "problem_id": problem.id,
                "skill": problem.skill,
                "item_form": problem.item_form,
                "difficulty_tier": problem.difficulty_tier,
                "factors": [problem.groups, problem.per_group],
                "question": problem.question,
                "instruction": (
                    "Do not ask a different maths question. Continue or repeat this exact problem."
                ),
            }
            if self.current_problem_has_intro:
                result["teaching_intro"] = BEGINNER_EQUAL_GROUPS_INTRO
            return result

        prior_events = list(
            ((self.learning_state.get("grading_evidence") or {}).get("events") or [])
        )
        recent_ids = {
            str(event.get("item_id"))
            for event in prior_events[-5:]
            if isinstance(event, dict) and event.get("item_id")
        }
        problem = self._eligible_problems[self._index % len(self._eligible_problems)]
        for _ in range(len(self._eligible_problems)):
            candidate = self._eligible_problems[self._index % len(self._eligible_problems)]
            self._index += 1
            if candidate.id not in recent_ids and candidate.id not in self.problem_history[-5:]:
                problem = candidate
                break
        self.current_problem = problem
        self.current_problem_resolved = False
        self.current_prompt_level = "none"
        self.current_attempt = 0
        self.problem_history.append(problem.id)
        self.current_problem_has_intro = self._intro_pending
        self._intro_pending = False
        result = {
            "status": "ready",
            "problem_id": problem.id,
            "skill": problem.skill,
            "item_form": problem.item_form,
            "difficulty_tier": problem.difficulty_tier,
            "factors": [problem.groups, problem.per_group],
            "question": problem.question,
            "instruction": (
                "If teaching_intro is present, explain that idea first in your natural voice. "
                "Then ask the exact question once and wait."
            ),
        }
        if self.current_problem_has_intro:
            result["teaching_intro"] = BEGINNER_EQUAL_GROUPS_INTRO
        return result

    def grade_answer(self, learner_answer: str) -> dict[str, Any]:
        answer = " ".join(str(learner_answer or "").split())
        problem = self.current_problem
        if problem is None:
            result = {
                "status": "no_active_problem",
                "is_correct": None,
                "learner_answer": answer,
                "instruction": "Call get_next_numeracy_problem before asking or grading maths.",
            }
            self.grade_history.append(result)
            return result
        if self.current_problem_resolved:
            result = {
                "status": "problem_already_resolved",
                "is_correct": None,
                "problem_id": problem.id,
                "learner_answer": answer,
                "audio_scorability": NOT_SCORABLE,
                "academic_correctness": INDETERMINATE,
                "instruction": (
                    "Do not judge this answer against the old item. Call "
                    "get_next_numeracy_problem, ask that registered question, and wait."
                ),
            }
            self.grade_history.append(result)
            return result

        numbers = extract_numbers(answer)
        unique_numbers = list(dict.fromkeys(numbers))
        self.current_attempt += 1
        prompt_level = self.current_prompt_level
        independence = (
            MODELLED
            if prompt_level == "answer_model"
            else SCAFFOLDED
            if prompt_level == "conceptual"
            else INDEPENDENT
        )
        if problem.expected in unique_numbers and len(unique_numbers) == 1:
            status = "correct"
            is_correct: bool | None = True
            audio_scorability = SCORABLE
            academic_correctness = CORRECT
            instruction = (
                "Explicitly say the numeric answer is correct, regardless of any object noun. "
                "The next problem is already registered in next_problem. If continuing, ask "
                "that exact question and never invent or substitute a different one."
            )
            self.current_problem_resolved = True
        elif not unique_numbers and learner_requested_math_help(answer):
            status = "help_requested"
            is_correct = None
            audio_scorability = SCORABLE
            academic_correctness = INDETERMINATE
            instruction = (
                "The learner clearly asked for help. Reassure them and teach one small step "
                f"for the SAME problem using this idea: {problem.conceptual_hint} "
                "Phrase it naturally, then wait for their answer."
            )
            self.current_prompt_level = "conceptual"
        elif not unique_numbers:
            status = "not_scorable"
            is_correct = None
            audio_scorability = NOT_SCORABLE
            academic_correctness = INDETERMINATE
            instruction = "Do not mark this wrong. Ask the learner to repeat just the number."
            self.current_prompt_level = "technical_repeat"
        elif len(unique_numbers) > 1 or is_confusable_numeric_answer(
            (problem.expected,), unique_numbers
        ):
            status = "not_scorable"
            is_correct = None
            audio_scorability = NOT_SCORABLE
            academic_correctness = INDETERMINATE
            instruction = (
                "Do not mark this right or wrong. Ask the learner to repeat or confirm the number once."
            )
            self.current_prompt_level = "neutral_confirmation"
        else:
            status = "incorrect"
            is_correct = False
            audio_scorability = SCORABLE
            academic_correctness = INCORRECT
            instruction = (
                "Do not say 'wrong'. Acknowledge the effort and teach this one small step for "
                f"the SAME problem: {problem.conceptual_hint} Then wait for another try."
            )
            self.current_prompt_level = "conceptual"

        event = make_evidence_event(
            call_id=self.call_uuid,
            item_id=problem.id,
            item_form=problem.item_form,
            skill=problem.skill,
            expected_answer=problem.expected,
            learner_answer=answer,
            heard_numbers=numbers,
            audio_scorability=audio_scorability,
            academic_correctness=academic_correctness,
            independence=independence,
            prompt_level=prompt_level,
            attempt_index=self.current_attempt,
        )
        self.call_events.append(event)
        self.learning_state = update_grading_state(self.learning_state, event)
        mastery = (
            ((self.learning_state.get("grading_evidence") or {}).get("skills") or {}).get(
                problem.skill
            )
            or {}
        )

        result = {
            "status": status,
            "is_correct": is_correct,
            "problem_id": problem.id,
            "question": problem.question,
            "expected_answer": problem.expected,
            "difficulty_tier": problem.difficulty_tier,
            "learner_answer": answer,
            "heard_numbers": numbers,
            "object_nouns_ignored": True,
            "audio_scorability": audio_scorability,
            "academic_correctness": academic_correctness,
            "independence": independence,
            "prompt_level": prompt_level,
            "mastery": mastery,
            "grader_version": event["grader_version"],
            "instruction": instruction,
        }
        if status == "correct":
            # Reserve the next answer key atomically with the successful grade.
            # This removes the gap in which the model could improvise a spoken
            # question while the backend was still holding the solved item.
            result["next_problem"] = self.next_problem()
        self.grade_history.append(result)
        return result

    def execute(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        if name == "get_next_numeracy_problem":
            return self.next_problem()
        if name == "grade_numeric_answer":
            return self.grade_answer(str(args.get("learner_answer") or ""))
        if name == "get_lesson_progress":
            return self.lesson_progress()
        return {"status": "unknown_tool", "tool": str(name or "")}

    def lesson_progress(self, elapsed_seconds: int | None = None) -> dict[str, Any]:
        elapsed = int(
            max(0, elapsed_seconds)
            if elapsed_seconds is not None
            else max(0.0, time.monotonic() - self.call_started_at)
        )
        if elapsed < 30:
            phase = "greeting_and_recall"
        elif elapsed < 120:
            phase = "today_lesson"
        elif elapsed < 210:
            phase = "guided_practice"
        elif elapsed < GEMINI_LIVE_MIN_LESSON_SECONDS:
            phase = "independent_practice"
        elif elapsed < GEMINI_LIVE_TARGET_WRAP_SECONDS:
            phase = "wrap_window"
        else:
            phase = "wrap_now"
        score = session_score(self.call_events, MULTIPLICATION_MASTERY_SKILL)
        enough_evidence = (
            score.get("independent_correct", 0) + score.get("independent_incorrect", 0) >= 3
        )
        may_wrap = elapsed >= GEMINI_LIVE_MIN_LESSON_SECONDS and enough_evidence
        must_wrap = elapsed >= GEMINI_LIVE_TARGET_WRAP_SECONDS
        return {
            "status": "continue" if not may_wrap and not must_wrap else "wrap",
            "elapsed_seconds": elapsed,
            "phase": phase,
            "minimum_lesson_seconds": GEMINI_LIVE_MIN_LESSON_SECONDS,
            "target_wrap_seconds": GEMINI_LIVE_TARGET_WRAP_SECONDS,
            "may_wrap": bool(may_wrap or must_wrap),
            "must_wrap": bool(must_wrap),
            "instruction": (
                "Briefly summarize and close the lesson now."
                if must_wrap
                else "You may wrap after completing the current problem."
                if may_wrap
                else (
                    f"Do not summarize, say next time, or close. Continue the {phase} phase "
                    "with the active problem or call get_next_numeracy_problem."
                )
            ),
        }

    def authoritative_session_score(self) -> dict[str, Any]:
        score = session_score(self.call_events, MULTIPLICATION_MASTERY_SKILL)
        mastery = (
            ((self.learning_state.get("grading_evidence") or {}).get("skills") or {}).get(
                MULTIPLICATION_MASTERY_SKILL
            )
            or {}
        )
        score["mastery"] = mastery
        score["should_advance"] = (
            self._starting_mastery.get("status") not in {"secure", "retained"}
            and mastery.get("status") == "secure"
        )
        return score


def build_live_setup(system_prompt: str) -> dict[str, Any]:
    """Return the raw BidiGenerateContent setup payload.

    ``responseModalities`` must be nested in ``generationConfig`` on the raw
    WebSocket protocol.  This shape is verified against the production Google
    endpoint; putting it directly under ``setup`` produces protocol error 1007.
    """
    return {
        "setup": {
            "model": f"models/{GEMINI_LIVE_MODEL}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": GEMINI_LIVE_VOICE}
                    }
                },
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "disabled": False,
                    # Low sensitivity means fewer false speech starts from
                    # breaths, clicks, and ordinary room sounds on PSTN audio.
                    "startOfSpeechSensitivity": "START_SENSITIVITY_LOW",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                    "prefixPaddingMs": 160,
                    "silenceDurationMs": 650,
                },
                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
                "turnCoverage": "TURN_INCLUDES_ONLY_ACTIVITY",
            },
            "contextWindowCompression": {
                "triggerTokens": 12000,
                "slidingWindow": {"targetTokens": 8000},
            },
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "get_next_numeracy_problem",
                            "description": (
                                "Get Sabi's next deterministic, non-repeating numeracy problem. "
                                "Use this at lesson opening or when no active problem exists. If "
                                "a problem is already active, it returns that exact same problem."
                            ),
                            "parameters": {"type": "OBJECT", "properties": {}},
                        },
                        {
                            "name": "grade_numeric_answer",
                            "description": (
                                "Handle the learner's reply to the active maths problem. Call this "
                                "for a spoken numeric answer OR a clear request such as 'I don't "
                                "know' or 'help me'. It grades numbers deterministically and returns "
                                "a small teaching cue for help. Object nouns never affect correctness."
                            ),
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "learner_answer": {
                                        "type": "STRING",
                                        "description": (
                                            "The learner's complete reply, including any request for help."
                                        ),
                                    }
                                },
                                "required": ["learner_answer"],
                            },
                        },
                        {
                            "name": "get_lesson_progress",
                            "description": (
                                "Read Sabi's authoritative lesson clock and phase. You MUST call "
                                "this before summarizing, saying next time, saying goodbye, or "
                                "otherwise ending the lesson."
                            ),
                            "parameters": {"type": "OBJECT", "properties": {}},
                        },
                    ]
                }
            ],
        }
    }


def build_live_call_constraints(opening_turn: str, learning_state: dict | None) -> str:
    state_json = json.dumps(
        compact_live_learning_state(learning_state),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return f"""

## GEMINI LIVE PHONE SESSION
This is one continuous, full-duplex phone conversation. You hear the caller's
audio directly and retain the complete context for this call. Do not describe
transcription, STT providers, prompts, tools, APIs, or internal state.

The caller is currently in a NUMERACY-ONLY test. Do not teach literacy, letter
sounds, spelling, or phonics during this call.

Opening turn for this learner: {opening_turn!r}
When you receive the literal text [SABI_CALL_STARTED], begin with that opening
turn. Speak naturally; never read the bracketed signal aloud. If the opening
does not ask for the learner's name or another onboarding answer, call
get_next_numeracy_problem immediately and ask its question in the same turn.

Current deterministic learner state (provided once for this session):
{state_json}

Conversation:
- Listen to the whole utterance and respond conversationally.
- The caller may interrupt you. Stop immediately and listen when they do.
- Ignore silence, breaths, clicks, coughs, line noise, and random non-speech.
- Speak warmly in one or two short sentences, explain when needed, ask one
  question, then wait.
- The target is five to seven minutes, not a fixed number of questions.
- Call get_lesson_progress BEFORE any wrap-up, summary, "next time", goodbye,
  or suggestion that today's lesson is finished.

Maths tools:
- Call get_next_numeracy_problem at lesson opening or whenever there is no
  active registered problem.
- Ask the exact question returned by that tool and never reveal expected_answer.
- For a numeric answer or a clear "I don't know/help me", call
  grade_numeric_answer before judging or teaching. Follow its result naturally.
- If it returns next_problem, use that exact registered question. Do not invent
  or replace maths questions. The number determines correctness; object words do not.
"""


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(INPUT_SAMPLE_RATE)
        wav.writeframes(pcm)


def _drain_queue(queue: asyncio.Queue) -> int:
    drained = 0
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        else:
            drained += 1
            try:
                queue.task_done()
            except ValueError:
                pass
    return drained


EARLY_WRAP_PHRASES = (
    "today we learned",
    "today, we learned",
    "next time",
    "that's all for today",
    "that is all for today",
    "go and enjoy your day",
    "talk to you next time",
    "see you next time",
    "take care oh",
)


def is_early_wrap_text(text: str, elapsed_seconds: int) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return int(elapsed_seconds) < GEMINI_LIVE_MIN_LESSON_SECONDS and any(
        phrase in normalized for phrase in EARLY_WRAP_PHRASES
    )


def caller_requested_stop(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return any(
        phrase in normalized
        for phrase in ("stop", "goodbye", "bye", "end the call", "i am done", "i'm done")
    )


def _normalize_question_text(text: str) -> str:
    """Normalize punctuation/casing while preserving the question's words."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())


def registered_followup_from_tool_events(
    tool_events: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Return the newest problem atomically registered by a correct grade."""
    for event in reversed(tool_events or []):
        if event.get("name") != "grade_numeric_answer":
            continue
        result = event.get("result") or {}
        next_problem = result.get("next_problem") or {}
        if (
            result.get("status") == "correct"
            and next_problem.get("problem_id")
            and next_problem.get("question")
        ):
            return dict(next_problem)
    return None


def assistant_asked_registered_problem(
    assistant_text: str,
    problem: dict[str, Any] | None,
) -> bool:
    """Check whether Gemini actually spoke the registered question."""
    question = _normalize_question_text((problem or {}).get("question") or "")
    assistant = _normalize_question_text(assistant_text)
    return bool(question and question in assistant)


def assistant_asked_math_question(assistant_text: str) -> bool:
    """Detect a spoken maths prompt that may conflict with the answer key."""
    raw = str(assistant_text or "")
    normalized = _normalize_question_text(raw)
    explicit_math_prompt = any(
        phrase in normalized
        for phrase in (
            "how many",
            "how much",
            "what is",
            "what s",
            "tell me the number",
            "what do you get",
            "what does that make",
        )
    )
    math_terms = (" times ", " groups ", " each ", " altogether", " total", " naira")
    terse_math_prompt = "?" in raw and any(term in f" {normalized} " for term in math_terms)
    return explicit_math_prompt or terse_math_prompt


def registered_followup_enforcement(
    tool_events: list[dict[str, Any]] | None,
    assistant_text: str,
    user_text: str,
    elapsed_seconds: int,
) -> dict[str, Any] | None:
    """Build a controller cue when Gemini omits or replaces the reserved item."""
    problem = registered_followup_from_tool_events(tool_events)
    if not problem or caller_requested_stop(user_text):
        return None
    if assistant_asked_registered_problem(assistant_text, problem):
        return None

    asked_other_question = assistant_asked_math_question(assistant_text)
    # Once the minimum lesson time has passed, a praise-only turn may lead into
    # the clock-controlled wrap. A conflicting question is never permitted.
    if int(elapsed_seconds) >= GEMINI_LIVE_MIN_LESSON_SECONDS and not asked_other_question:
        return None

    question = str(problem["question"])
    return {
        "problem_id": str(problem["problem_id"]),
        "question": question,
        "unregistered_question_corrected": asked_other_question,
        "instruction": (
            f'[SABI_ASK_REGISTERED_PROBLEM] Ask exactly: "{question}" '
            "Do not add, paraphrase, or replace the maths question."
        ),
    }


class GeminiLiveCallRunner:
    """Run one AudioSocket call through one persistent Gemini Live session."""

    def __init__(self, call: Any) -> None:
        self.call = call
        self.websocket: Any = None
        self.send_lock = asyncio.Lock()
        self.buffer_lock = asyncio.Lock()
        self.playback_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.downsampler = Pcm24kTo8k()
        self.output_packet_buffer = bytearray()
        self.input_pcm = bytearray()
        self.played_pcm = bytearray()
        self.input_transcript = ""
        self.output_transcript = ""
        self.messages: list[dict[str, str]] = []
        self.turn_index = 0
        self.turn_interrupted = False
        self.turn_tool_events: list[dict[str, Any]] = []
        self.early_wrap_repairs = 0
        self.usage_metadata: dict[str, Any] = {}
        self.student: dict[str, Any] | None = None
        self.student_id: str | None = None
        self.effective_state: dict[str, Any] = {}
        self.starting_learning_state: dict[str, Any] = {}
        self.module = 0
        self.tools: GeminiLiveNumeracyTools | None = None
        self.call_started_at = time.monotonic()
        self.turn_started_at = self.call_started_at
        # Shadow only: Groq + local Whisper listen to the same finished turn so
        # we can measure Gemini's number hearing without touching the call.
        self.sidecar = NumericSidecar(
            self.call.call_uuid,
            getattr(self.call, "stt", None),
            audio_dir=os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"),
        )

    async def _prepare_prompt(self) -> str:
        self.student = await self.call.memory.find_or_create_student(self.call.phone)
        self.student_id = self.student["id"]
        state = await self.call.memory.get_effective_learning_state(self.student)
        self.effective_state = force_numeracy_course(state)
        self.starting_learning_state = dict(self.effective_state)
        self.module = int(
            self.effective_state.get("current_module")
            or self.student.get("current_module")
            or 0
        )
        self.tools = GeminiLiveNumeracyTools(self.call.call_uuid, self.effective_state)

        # Gemini Live gets a compact native prompt.  The legacy text pipeline's
        # full RAG prompt duplicated the curriculum block and included turn-
        # based instructions that conflict with a continuous session.
        memory_context = build_gemini_live_learner_context(
            self.student,
            self.effective_state,
        )
        curriculum_context = build_curriculum_path_prompt(
            self.effective_state,
            self.module,
            "numeracy",
        )
        base_prompt = build_gemini_live_base_prompt(
            memory_context or "",
            curriculum_context or "",
        )
        from diagnostic_flow import build_opening_turn

        opening_turn = build_opening_turn(self.student, self.effective_state)
        # Returning learners normally receive a hard-coded warm-up from
        # ``build_opening_turn``.  In the Live canary every maths question must
        # come from the deterministic deck so it has an authoritative answer
        # and cannot cluster around twelve.
        if self.module > 0 and not self.student.get("needs_identity_confirmation"):
            learner_name = " ".join(str(self.student.get("name") or "").split())
            skill = str(self.effective_state.get("active_skill") or "numbers").replace("_", " ")
            if learner_name:
                opening_turn = f"Welcome back, {learner_name}! Let's continue with {skill}."
            else:
                opening_turn = f"Welcome back! Let's continue with {skill}."
        return base_prompt + build_live_call_constraints(opening_turn, self.effective_state)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        async with self.send_lock:
            await self.websocket.send(json.dumps(payload, ensure_ascii=True, default=str))

    async def _connect(self, system_prompt: str) -> None:
        key = get_secret("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise GeminiLiveSetupError("GEMINI_API_KEY is not configured")
        try:
            import websockets

            self.websocket = await websockets.connect(
                f"{LIVE_ENDPOINT}?key={key}",
                open_timeout=GEMINI_LIVE_SETUP_TIMEOUT_SECONDS,
                close_timeout=3,
                ping_interval=20,
                ping_timeout=20,
                max_size=GEMINI_LIVE_MAX_MESSAGE_BYTES,
            )
            await self._send_json(build_live_setup(system_prompt))
            raw = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=GEMINI_LIVE_SETUP_TIMEOUT_SECONDS,
            )
            response = json.loads(raw)
            if "setupComplete" not in response:
                raise GeminiLiveSetupError(
                    f"Gemini Live setup was not acknowledged (fields={sorted(response)})"
                )
        except GeminiLiveSetupError:
            if self.websocket is not None:
                await self.websocket.close()
            self.websocket = None
            raise
        except Exception as exc:
            if self.websocket is not None:
                try:
                    await self.websocket.close()
                except Exception:
                    pass
            self.websocket = None
            # Avoid embedding the authenticated WebSocket URL in logs.
            raise GeminiLiveSetupError(
                f"Gemini Live connection failed ({type(exc).__name__})"
            ) from None

    async def _audio_sender(self) -> None:
        while not self.call.hungup:
            frame = await self.call.audio_queue.get()
            if frame is None:
                break
            if not frame:
                continue
            async with self.buffer_lock:
                self.input_pcm.extend(frame)
                maximum = INPUT_SAMPLE_RATE * SAMPLE_WIDTH * GEMINI_LIVE_INPUT_BUFFER_SECONDS
                if len(self.input_pcm) > maximum:
                    del self.input_pcm[:-maximum]
            await self._send_json(
                {
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(frame).decode("ascii"),
                            "mimeType": "audio/pcm;rate=8000",
                        }
                    }
                }
            )
        if self.websocket is not None:
            try:
                await self._send_json({"realtimeInput": {"audioStreamEnd": True}})
            except Exception:
                pass

    async def _playback(self) -> None:
        while True:
            frame = await self.playback_queue.get()
            if frame is None:
                self.playback_queue.task_done()
                return
            try:
                if self.call.hungup:
                    return
                started = time.monotonic()
                await self.call.send_pcm_frame(frame)
                async with self.buffer_lock:
                    self.played_pcm.extend(frame)
                elapsed = time.monotonic() - started
                await asyncio.sleep(max(0.0, FRAME_MS / 1000 - elapsed))
            finally:
                self.playback_queue.task_done()

    def _queue_native_audio(self, pcm_24k: bytes) -> None:
        pcm_8k = self.downsampler.feed(pcm_24k)
        if not pcm_8k:
            return
        self.output_packet_buffer.extend(pcm_8k)
        while len(self.output_packet_buffer) >= FRAME_BYTES_8K:
            frame = bytes(self.output_packet_buffer[:FRAME_BYTES_8K])
            del self.output_packet_buffer[:FRAME_BYTES_8K]
            self.playback_queue.put_nowait(frame)

    async def _handle_tool_call(self, tool_call: dict[str, Any]) -> None:
        responses = []
        for function_call in tool_call.get("functionCalls") or []:
            name = str(function_call.get("name") or "")
            args = function_call.get("args") or {}
            try:
                result = (self.tools or GeminiLiveNumeracyTools(self.call.call_uuid)).execute(
                    name, args
                )
                response = {"result": result}
            except Exception as exc:
                result = {"status": "tool_error", "error_type": type(exc).__name__}
                response = {"error": result}
            event = {"name": name, "args": args, "result": result}
            self.turn_tool_events.append(event)
            logger.info(
                "Gemini Live tool uuid=%s name=%s result=%s",
                self.call.call_uuid,
                name,
                result,
            )
            responses.append(
                {
                    "name": name,
                    "id": function_call.get("id"),
                    "response": response,
                }
            )
        if responses:
            await self._send_json({"toolResponse": {"functionResponses": responses}})

    def _graded_item_this_turn(self) -> dict[str, Any]:
        """The item the backend actually graded on this turn, if any."""
        for event in reversed(self.turn_tool_events):
            if event.get("name") != "grade_numeric_answer":
                continue
            result = event.get("result") or {}
            if isinstance(result, dict) and result.get("expected_answer") is not None:
                return result
        return {}

    def _submit_numeric_sidecar(self, user_path: Path | None, raw_user: str) -> bool:
        """Queue the shadow Groq/local comparison for a numeric-answer turn.

        Prefers the item the grader used, because a correct grade immediately
        reserves the *next* problem — comparing against that reserved item
        would score the sidecar against a question the child never heard.
        """
        if not getattr(self, "sidecar", None) or not self.sidecar.enabled:
            return False
        graded = self._graded_item_this_turn()
        if graded:
            expected = expected_number_from_problem(graded)
            problem_id = str(graded.get("problem_id") or "")
            prompt_level = str(graded.get("prompt_level") or "")
        elif self.tools and not self.tools.current_problem_resolved:
            expected = expected_number_from_problem(self.tools.current_problem)
            problem_id = str(getattr(self.tools.current_problem, "id", "") or "")
            prompt_level = str(self.tools.current_prompt_level or "")
        else:
            return False
        try:
            return self.sidecar.submit(
                turn_index=self.turn_index,
                audio_path=user_path,
                gemini_text=raw_user,
                expected_answer=expected,
                problem_id=problem_id,
                attempt=int(getattr(self.tools, "current_attempt", 0) or 0),
                prompt_level=prompt_level,
            )
        except Exception as exc:
            # A measurement path must never be able to break a live lesson.
            logger.warning(
                "Numeric sidecar submit failed uuid=%s turn=%s error=%s",
                self.call.call_uuid,
                self.turn_index,
                type(exc).__name__,
            )
            return False

    async def _finalize_turn(self) -> None:
        raw_user = " ".join(self.input_transcript.split())
        assistant = " ".join(self.output_transcript.split())
        elapsed_seconds = int(time.monotonic() - self.call_started_at)
        followup_enforcement = registered_followup_enforcement(
            self.turn_tool_events,
            assistant,
            raw_user,
            elapsed_seconds,
        )
        early_wrap_blocked = bool(
            assistant
            and not caller_requested_stop(raw_user)
            and is_early_wrap_text(assistant, elapsed_seconds)
            and self.early_wrap_repairs < 3
        )
        if early_wrap_blocked or (
            followup_enforcement
            and followup_enforcement.get("unregistered_question_corrected")
        ):
            # Turn completion can arrive while unplayed native audio is still
            # queued. Drop the unheard remainder of a premature farewell or an
            # invented question whose answer key would not match the backend.
            _drain_queue(self.playback_queue)
            self.output_packet_buffer.clear()
        async with self.buffer_lock:
            user_pcm = bytes(self.input_pcm)
            assistant_pcm = bytes(self.played_pcm)
            self.input_pcm.clear()
            self.played_pcm.clear()

        # The call-start signal produces an assistant-only greeting.  Preserve
        # it in session history but don't create a fake learner turn.
        if assistant and not raw_user:
            self.messages.append({"role": "assistant", "content": assistant})
        elif raw_user:
            state_before = dict(self.effective_state)
            self.messages.append({"role": "user", "content": raw_user})
            if assistant:
                self.messages.append({"role": "assistant", "content": assistant})
            # Gemini's conversational prose is not grading evidence.  Once a
            # local grade tool has run, its versioned state is authoritative.
            if self.tools and self.tools.call_events:
                self.effective_state = force_numeracy_course(self.tools.learning_state)
                self.module = int(self.effective_state.get("current_module") or self.module)
            else:
                try:
                    stats = analyze_session(
                        {
                            **(self.student or {}),
                            "learning_state": self.effective_state,
                            "current_module": self.module,
                        },
                        self.messages,
                    )
                    self.effective_state = force_numeracy_course(stats.learning_state)
                    self.module = int(self.effective_state.get("current_module") or self.module)
                except Exception as exc:
                    logger.warning(
                        "Gemini Live state update failed uuid=%s turn=%s error=%s",
                        self.call.call_uuid,
                        self.turn_index,
                        type(exc).__name__,
                    )

            user_path = call_turn_audio_path(
                self.call.call_uuid,
                self.turn_index,
                "user",
                Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio")),
            )
            if user_path and user_pcm:
                _write_wav(user_path, user_pcm)
            sidecar_submitted = self._submit_numeric_sidecar(user_path, raw_user)
            flags = ["gemini_live", "continuous_audio", "native_audio_response"]
            if sidecar_submitted:
                flags.append("numeric_sidecar_shadow")
            if self.turn_interrupted:
                flags.append("barge_in")
            if self.turn_tool_events:
                flags.append("gemini_live_tool_call")
            if any(event.get("name") == "grade_numeric_answer" for event in self.turn_tool_events):
                flags.append("deterministic_numeric_grade")
            if early_wrap_blocked:
                flags.append("early_wrap_blocked")
            if followup_enforcement:
                flags.append("registered_followup_cued")
                if followup_enforcement.get("unregistered_question_corrected"):
                    flags.append("unregistered_question_corrected")
            self.call.last_tts_provider = "gemini_live_native_audio"
            transcript = {
                "text": raw_user,
                # Gemini Live input transcription has no calibrated confidence.
                "confidence": 0.0,
                "provider": "gemini_live",
                "gemini_model": GEMINI_LIVE_MODEL,
                "audio_seconds": len(user_pcm) / (INPUT_SAMPLE_RATE * SAMPLE_WIDTH),
                "selection_reason": "persistent_native_audio_session",
                "ensemble_results": {"gemini_live_tools": self.turn_tool_events},
            }
            self.call.persist_turn_review(
                turn=self.turn_index,
                user_audio_path=user_path,
                transcript=transcript,
                raw_text=raw_user,
                normalized_text=raw_user,
                learning_state_before=state_before,
                learning_state_after=dict(self.effective_state),
                assistant_text=assistant,
                assistant_pcm=assistant_pcm,
                timings={
                    "turn_total_seconds": round(time.monotonic() - self.turn_started_at, 3),
                    "pipeline": "gemini_live_native_audio",
                },
                flags=flags,
            )
            logger.info(
                "Gemini Live turn uuid=%s turn=%s user=%r assistant=%r interrupted=%s",
                self.call.call_uuid,
                self.turn_index,
                raw_user,
                assistant,
                self.turn_interrupted,
            )
            self.turn_index += 1
            self.sidecar.note_current_turn(self.turn_index)

        self.input_transcript = ""
        self.output_transcript = ""
        self.turn_interrupted = False
        self.turn_tool_events = []
        self.turn_started_at = time.monotonic()
        if early_wrap_blocked and self.websocket is not None and not self.call.hungup:
            self.early_wrap_repairs += 1
            progress = (
                self.tools.lesson_progress(elapsed_seconds) if self.tools else {"phase": "lesson"}
            )
            logger.warning(
                "Gemini Live early wrap blocked uuid=%s elapsed=%ss phase=%s",
                self.call.call_uuid,
                elapsed_seconds,
                progress.get("phase"),
            )
            controller_text = (
                str(followup_enforcement["instruction"])
                if followup_enforcement
                else (
                    "[SABI_EARLY_WRAP_BLOCKED] The five-minute minimum has not been "
                    f"reached. Continue the {progress.get('phase', 'lesson')} phase now. "
                    "Do not apologize, summarize, mention next time, or say goodbye. "
                    "Call get_next_numeracy_problem if there is no unresolved problem."
                )
            )
            await self._send_json(
                {
                    "realtimeInput": {
                        "text": controller_text
                    }
                }
            )
        elif followup_enforcement and self.websocket is not None and not self.call.hungup:
            logger.warning(
                "Gemini Live registered follow-up enforced uuid=%s problem=%s corrected=%s",
                self.call.call_uuid,
                followup_enforcement.get("problem_id"),
                followup_enforcement.get("unregistered_question_corrected"),
            )
            await self._send_json(
                {"realtimeInput": {"text": str(followup_enforcement["instruction"])}}
            )

    async def _receiver(self) -> None:
        async for raw in self.websocket:
            response = json.loads(raw)
            if response.get("usageMetadata"):
                self.usage_metadata = response["usageMetadata"]
            if response.get("goAway"):
                logger.warning(
                    "Gemini Live goAway uuid=%s detail=%s",
                    self.call.call_uuid,
                    response.get("goAway"),
                )
            if response.get("toolCall"):
                await self._handle_tool_call(response["toolCall"])

            server_content = response.get("serverContent") or {}
            if server_content.get("interrupted"):
                drained = _drain_queue(self.playback_queue)
                self.output_packet_buffer.clear()
                self.turn_interrupted = True
                logger.info(
                    "Gemini Live barge-in uuid=%s cleared_frames=%s",
                    self.call.call_uuid,
                    drained,
                )

            input_piece = (server_content.get("inputTranscription") or {}).get("text")
            if input_piece:
                self.input_transcript = merge_stream_text(self.input_transcript, input_piece)
            output_piece = (server_content.get("outputTranscription") or {}).get("text")
            if output_piece:
                self.output_transcript = merge_stream_text(self.output_transcript, output_piece)

            for part in ((server_content.get("modelTurn") or {}).get("parts") or []):
                inline_data = part.get("inlineData") or {}
                encoded = inline_data.get("data")
                if encoded:
                    self._queue_native_audio(base64.b64decode(encoded))

            if server_content.get("turnComplete"):
                await self._finalize_turn()

    async def _finish(self, reader_task: asyncio.Task, playback_task: asyncio.Task) -> None:
        if self.input_transcript or self.output_transcript:
            try:
                await self._finalize_turn()
            except Exception as exc:
                logger.warning(
                    "Could not finalize last Gemini Live turn uuid=%s error=%s",
                    self.call.call_uuid,
                    type(exc).__name__,
                )
        self.call.hungup = True
        reader_task.cancel()
        _drain_queue(self.playback_queue)
        self.playback_queue.put_nowait(None)
        try:
            await asyncio.wait_for(playback_task, timeout=2)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            playback_task.cancel()
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass
        try:
            await self.call.send_hangup()
        except Exception:
            pass
        self.call.writer.close()
        try:
            await self.call.writer.wait_closed()
        except Exception:
            pass

        duration_seconds = int(time.monotonic() - self.call_started_at)
        learning_result = None
        if self.student_id and self.messages:
            learning_result = await self.call.memory.save_phone_session(
                student_id=self.student_id,
                phone_number=self.call.phone,
                call_id=self.call.call_id,
                messages=self.messages,
                duration_seconds=duration_seconds,
                channel="asterisk_audiosocket_gemini_live",
                starting_learning_state=self.starting_learning_state,
                authoritative_learning_state=(
                    self.tools.learning_state if self.tools else self.effective_state
                ),
                authoritative_score=(
                    self.tools.authoritative_session_score() if self.tools else None
                ),
            )
        user_turns = sum(1 for message in self.messages if message.get("role") == "user")
        assistant_turns = sum(1 for message in self.messages if message.get("role") == "assistant")
        from voice_realtime import HANGUP_EVENTS, SHARED_AUDIO_DIR

        write_call_review_record(
            call_uuid=self.call.call_uuid,
            call_id=self.call.call_id,
            phone_number=self.call.phone,
            mode=self.call.mode,
            attempt=str(self.call.attempt),
            student_id=self.student_id,
            channel="asterisk_audiosocket_gemini_live",
            end_reason=self.call.end_reason,
            duration_seconds=duration_seconds,
            user_turns=user_turns,
            assistant_turns=assistant_turns,
            hangup_event=HANGUP_EVENTS.get(self.call.call_uuid),
            directory=SHARED_AUDIO_DIR,
        )
        if learning_result:
            try:
                write_call_learning_summary(
                    self.call.call_uuid,
                    learning_result.get("scorecard"),
                    learning_result.get("teacher_note"),
                    directory=SHARED_AUDIO_DIR,
                )
            except Exception as exc:
                logger.warning(
                    "Gemini Live learning summary failed uuid=%s error=%s",
                    self.call.call_uuid,
                    type(exc).__name__,
                )
        self.call.memory.clear_call(self.call.call_id)
        if self.sidecar.enabled:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    self.sidecar.drain,
                    float(os.getenv("SABI_NUMERIC_SIDECAR_DRAIN_SECONDS", "20")),
                )
                logger.warning("Numeric sidecar summary %s", self.sidecar.summary())
            except Exception as exc:
                logger.warning(
                    "Numeric sidecar summary failed uuid=%s error=%s",
                    self.call.call_uuid,
                    type(exc).__name__,
                )
        logger.warning(
            "Gemini Live call complete uuid=%s phone=%s end_reason=%s duration=%ss "
            "user_turns=%s assistant_turns=%s usage=%s",
            self.call.call_uuid,
            self.call.phone,
            self.call.end_reason,
            duration_seconds,
            user_turns,
            assistant_turns,
            self.usage_metadata,
        )

    async def run(self) -> None:
        """Connect first, then take ownership of the live AudioSocket call."""
        try:
            prompt = await self._prepare_prompt()
            await self._connect(prompt)
        except GeminiLiveSetupError:
            raise
        except Exception as exc:
            raise GeminiLiveSetupError(
                f"Gemini Live prompt preparation failed ({type(exc).__name__})"
            ) from None

        logger.info(
            "Gemini Live call start uuid=%s phone=%s model=%s voice=%s module=%s",
            self.call.call_uuid,
            self.call.phone,
            GEMINI_LIVE_MODEL,
            GEMINI_LIVE_VOICE,
            self.module,
        )
        reader_task = asyncio.create_task(self.call.read_loop())
        playback_task = asyncio.create_task(self._playback())
        sender_task = asyncio.create_task(self._audio_sender())
        receiver_task = asyncio.create_task(self._receiver())
        deadline_task = asyncio.create_task(asyncio.sleep(GEMINI_LIVE_MAX_CALL_SECONDS))

        try:
            await self._send_json({"realtimeInput": {"text": "[SABI_CALL_STARTED]"}})
            done, _pending = await asyncio.wait(
                {sender_task, receiver_task, deadline_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if deadline_task in done:
                self.call.set_end_reason("max_call_seconds")
            elif sender_task in done:
                self.call.set_end_reason("channel_closed")
            elif receiver_task in done:
                error = receiver_task.exception()
                if error:
                    logger.error(
                        "Gemini Live receive loop failed uuid=%s error=%s",
                        self.call.call_uuid,
                        type(error).__name__,
                    )
                    self.call.set_end_reason(
                        f"gemini_live_error:{type(error).__name__}"
                    )
                else:
                    self.call.set_end_reason("gemini_live_closed")
        finally:
            for task in (sender_task, receiver_task, deadline_task):
                if not task.done():
                    task.cancel()
            if self.call.end_reason == "unknown":
                self.call.set_end_reason("gemini_live_session_complete")
            await self._finish(reader_task, playback_task)
