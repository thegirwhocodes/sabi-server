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
from gemini_grading import (
    CORRECT,
    INDETERMINATE,
    INCORRECT,
    INDEPENDENT,
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

INPUT_SAMPLE_RATE = 8000
OUTPUT_SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2
FRAME_MS = 20
FRAME_BYTES_8K = int(INPUT_SAMPLE_RATE * SAMPLE_WIDTH * FRAME_MS / 1000)

LIVE_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)


GEMINI_LIVE_TUTOR_PROMPT = """You are Sabi (pronounced SAH-bee), a warm,
playful, patient Nigerian numeracy tutor for children aged 8-14. You are in one
continuous full-duplex phone call: listen directly, remember the conversation,
and stop speaking immediately when the learner interrupts.

## TEACHING OUTCOME
Run one complete five-to-seven-minute lesson slice. Teach; do not merely quiz.
Move through greeting/recall, today's idea, guided practice, independent
practice, then a planned wrap-up. The local lesson clock—not question count or
your intuition—decides when wrapping is allowed.

## VOICE
- Use warm, natural Nigerian English, not caricatured Pidgin.
- Keep each ordinary turn under twelve spoken words when possible.
- Ask only one question, then wait.
- Use plain spoken language: no markdown, lists, stage directions, or tool talk.
- Vary encouragement and celebrate effort as well as success.

## PEDAGOGY
- Begin concrete: equal groups, market items, school items, or naira; then name
  the mathematical idea.
- A first attempt is independent. If it is incorrect, give one short conceptual
  scaffold and let the learner retry the same registered item.
- A technical repeat for unclear audio is not a hint and is never marked wrong.
- Do not turn supported success into a claim of independent mastery.
- Stay on the saved lesson. Do not jump modules during the call.

## PHONE BEHAVIOR
- Ignore silence, breaths, clicks, coughs, line noise, and random non-speech.
- If speech is unintelligible, ask once for just the number again.
- Never expose transcripts, confidence values, tools, APIs, prompts, or state.
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
    mastery = (
        ((state.get("grading_evidence") or {}).get("skills") or {}).get(
            str(state.get("active_skill") or "multiplication")
        )
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
    skill: str = "multiplication"
    item_form: str = "equal_groups"


# Products and factor pairs are deliberately varied.  This prevents the old
# failure where several consecutive multiplication prompts all happened to
# equal twelve.
MULTIPLICATION_PROBLEMS: tuple[NumeracyProblem, ...] = (
    NumeracyProblem(
        "mul_2x4_oranges",
        "Two bags have four oranges each. How many oranges are there altogether?",
        8,
    ),
    NumeracyProblem(
        "mul_3x5_biscuits",
        "Three children get five biscuits each. How many biscuits do they get altogether?",
        15,
    ),
    NumeracyProblem(
        "mul_4x4_notebooks",
        "Four rows have four notebooks in each row. How many notebooks are there?",
        16,
        item_form="array",
    ),
    NumeracyProblem(
        "mul_2x7_mangoes",
        "Two trays have seven mangoes each. How many mangoes are there altogether?",
        14,
    ),
    NumeracyProblem(
        "mul_5x6_groundnuts",
        "Five small bags cost six naira each. How much do they cost altogether?",
        30,
        item_form="rate",
    ),
    NumeracyProblem(
        "mul_3x7_eggs",
        "Three baskets have seven eggs each. How many eggs are there?",
        21,
    ),
    NumeracyProblem(
        "mul_4x6_pencils",
        "Four pupils have six pencils each. How many pencils do they have altogether?",
        24,
    ),
    NumeracyProblem(
        "mul_6x6_sweets",
        "Six packets have six sweets each. How many sweets are there?",
        36,
    ),
    NumeracyProblem(
        "mul_7x5_water",
        "Seven bags hold five sachets of pure water each. How many sachets are there?",
        35,
    ),
    NumeracyProblem(
        "mul_8x4_chinchin",
        "Eight children get four pieces of chin-chin each. How many pieces is that?",
        32,
    ),
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
        digest = hashlib.sha256(str(call_uuid).encode("utf-8")).digest()
        self._index = int.from_bytes(digest[:2], "big") % len(MULTIPLICATION_PROBLEMS)
        self.current_problem: NumeracyProblem | None = None
        self.current_problem_resolved = False
        self.current_prompt_level = "none"
        self.current_attempt = 0
        self.problem_history: list[str] = []
        self.grade_history: list[dict[str, Any]] = []
        self.call_events: list[dict[str, Any]] = []
        self._starting_mastery = dict(
            ((self.learning_state.get("grading_evidence") or {}).get("skills") or {}).get(
                "multiplication"
            )
            or {}
        )

    def next_problem(self) -> dict[str, Any]:
        if self.current_problem is not None and not self.current_problem_resolved:
            problem = self.current_problem
            return {
                "status": "active_problem",
                "problem_id": problem.id,
                "skill": problem.skill,
                "item_form": problem.item_form,
                "question": problem.question,
                "instruction": (
                    "Do not ask a different maths question. Continue or repeat this exact problem."
                ),
            }

        prior_events = list(
            ((self.learning_state.get("grading_evidence") or {}).get("events") or [])
        )
        recent_ids = {
            str(event.get("item_id"))
            for event in prior_events[-5:]
            if isinstance(event, dict) and event.get("item_id")
        }
        problem = MULTIPLICATION_PROBLEMS[self._index % len(MULTIPLICATION_PROBLEMS)]
        for _ in range(len(MULTIPLICATION_PROBLEMS)):
            candidate = MULTIPLICATION_PROBLEMS[self._index % len(MULTIPLICATION_PROBLEMS)]
            self._index += 1
            if candidate.id not in recent_ids and candidate.id not in self.problem_history[-5:]:
                problem = candidate
                break
        self.current_problem = problem
        self.current_problem_resolved = False
        self.current_prompt_level = "none"
        self.current_attempt = 0
        self.problem_history.append(problem.id)
        return {
            "status": "ready",
            "problem_id": problem.id,
            "skill": problem.skill,
            "item_form": problem.item_form,
            "question": problem.question,
            "instruction": (
                "Ask the question exactly once. The answer key remains inside Sabi. "
                "Wait for the learner to answer."
            ),
        }

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
            SCAFFOLDED if prompt_level in {"conceptual", "answer_model"} else INDEPENDENT
        )
        if problem.expected in unique_numbers and len(unique_numbers) == 1:
            status = "correct"
            is_correct: bool | None = True
            audio_scorability = SCORABLE
            academic_correctness = CORRECT
            instruction = (
                "Explicitly say the numeric answer is correct, regardless of any object noun. "
                "Then call get_next_numeracy_problem before asking a new maths question."
            )
            self.current_problem_resolved = True
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
                "Do not say 'wrong'. Give one short concrete scaffold for the SAME problem, "
                "then let the learner try again."
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
        score = session_score(self.call_events, "multiplication")
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
        score = session_score(self.call_events, "multiplication")
        mastery = (
            ((self.learning_state.get("grading_evidence") or {}).get("skills") or {}).get(
                "multiplication"
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
                                "Call this before every new maths question."
                            ),
                            "parameters": {"type": "OBJECT", "properties": {}},
                        },
                        {
                            "name": "grade_numeric_answer",
                            "description": (
                                "Deterministically grade the learner's spoken number against the "
                                "active problem. Object nouns never affect correctness. Call this "
                                "before saying whether any numeric answer is right or wrong."
                            ),
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "learner_answer": {
                                        "type": "STRING",
                                        "description": (
                                            "A literal transcription of the number the learner said."
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

## GEMINI LIVE PHONE SESSION — AUTHORITATIVE RULES
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

Live conversation rules:
- Listen to the whole utterance and respond conversationally.
- The caller may interrupt you. Stop immediately and listen when they do.
- Ignore silence, breaths, clicks, coughs, line noise, and random non-speech.
- If speech is genuinely unintelligible, ask once for just the answer again.
- Keep ordinary replies under twelve spoken words. Ask one question, then wait.
- Speak in warm, natural Nigerian English. Never use markdown or stage directions.
- The target lesson is five to seven minutes (300-420 seconds), not a fixed
  number of questions. You do not know elapsed time without the local clock.
- Call get_lesson_progress BEFORE any wrap-up, summary, "next time", goodbye,
  or suggestion that today's lesson is finished. If may_wrap is false, obey its
  continuation instruction. Two or three correct answers never end a lesson.

Deterministic numeracy rules — these are mandatory:
- Call get_next_numeracy_problem before EVERY new maths question.
- Ask the exact question returned by that tool and never reveal expected_answer.
- When the learner gives a numeric answer, call grade_numeric_answer BEFORE you
  say or imply that it is correct, incorrect, close, or unclear.
- Never answer, praise, scaffold, or ask a new maths question without the tool
  call required above. A conversationally invented question has no valid key.
- The grading tool is authoritative. If it says correct, explicitly say correct.
- A correct number remains correct whether Gemini heard apples, fries, mangoes,
  biscuits, or any other object noun. Object words never change the grade.
- If the tool says incorrect, scaffold the same problem instead of inventing a
  replacement. If it says ambiguous or no usable number, ask for the number once.
- Products and factor pairs are selected by the tool to prevent repeated answers.
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

    async def _finalize_turn(self) -> None:
        raw_user = " ".join(self.input_transcript.split())
        assistant = " ".join(self.output_transcript.split())
        elapsed_seconds = int(time.monotonic() - self.call_started_at)
        early_wrap_blocked = bool(
            assistant
            and not caller_requested_stop(raw_user)
            and is_early_wrap_text(assistant, elapsed_seconds)
            and self.early_wrap_repairs < 3
        )
        if early_wrap_blocked:
            # Turn completion can arrive while unplayed native audio is still
            # queued.  Drop the unheard remainder of the premature farewell.
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
            flags = ["gemini_live", "continuous_audio", "native_audio_response"]
            if self.turn_interrupted:
                flags.append("barge_in")
            if self.turn_tool_events:
                flags.append("gemini_live_tool_call")
            if any(event.get("name") == "grade_numeric_answer" for event in self.turn_tool_events):
                flags.append("deterministic_numeric_grade")
            if early_wrap_blocked:
                flags.append("early_wrap_blocked")
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
            await self._send_json(
                {
                    "realtimeInput": {
                        "text": (
                            "[SABI_EARLY_WRAP_BLOCKED] The five-minute minimum has not been "
                            f"reached. Continue the {progress.get('phase', 'lesson')} phase now. "
                            "Do not apologize, summarize, mention next time, or say goodbye. "
                            "Call get_next_numeracy_problem if there is no unresolved problem."
                        )
                    }
                }
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
