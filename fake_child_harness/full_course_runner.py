from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any, Iterable

from curriculum_mastery import build_call_scorecard
from curriculum_path import (
    advance_learning_state_after_mastery,
    resolve_literacy_lesson,
    resolve_numeracy_lesson,
)
from diagnostic_flow import LITERACY_DIAGNOSTIC_ITEMS, LiteracyDiagnosticItem
from learning_state import analyze_session, default_learning_state, route_next_course_after_session
from teacher_notes import heuristic_teacher_note

from .child_simulator import SimulatedTurn, corrupt_transcript, simulate_diagnostic_call
from .cohort import FakeChildProfile, cohort_to_jsonable, generate_cohort
from .cost_model import FakePilotCostAssumptions, estimate_fake_pilot_cost
from .evaluator import TurnEvaluation, evaluate_turn, summarize_evaluations
from .progression_runner import (
    LESSON_BANK,
    LessonQuestion,
    _lesson_answer_for_child,
    _number_to_text,
    _state_slice,
)


JSONL_OUTPUTS = (
    "full_course_calls.jsonl",
    "full_course_transcripts.jsonl",
    "full_course_turns.jsonl",
    "evaluations.jsonl",
    "failures.jsonl",
    "child_progression.jsonl",
)

FULL_CALL_SECONDS = {
    "greeting_recall": 45,
    "teach": 90,
    "guided_practice": 95,
    "independent_check": 100,
    "wrap": 40,
}

LITERACY_CORRECT_ANSWERS: dict[str, tuple[str, ...]] = {
    "lit_beginning_sound_ball": ("b", "buh"),
    "lit_rhyme_cat_hat": ("bat", "mat", "sat"),
    "lit_blend_cat": ("cat", "kat"),
    "lit_blend_ship": ("ship",),
    "lit_letter_sound_s": ("s", "sss"),
    "lit_spell_sat": ("sat",),
    "lit_story_dog_gate": ("the dog barked", "barked", "ran to the gate"),
}

LITERACY_WRONG_ANSWERS = ("I don't know", "yes", "mango", "goat", "a", "cat")


@dataclass(frozen=True)
class LiteracyQuestion:
    item_id: str
    skill: str
    prompt: str
    expected_answers: tuple[str, ...]
    difficulty: int


LITERACY_LESSON_BANK: dict[str, tuple[LiteracyQuestion, ...]] = {
    "phonemic_awareness": (
        LiteracyQuestion("lit_beginning_mango", "phonemic_awareness", "What sound starts mango? Mmmango.", ("m", "mmm"), 1),
        LiteracyQuestion("lit_ending_bus", "phonemic_awareness", "What sound do you hear at the end of bus?", ("s", "sss"), 1),
        LiteracyQuestion("lit_rhyme_can", "phonemic_awareness", "Which word rhymes with can: man or cup?", ("man",), 1),
        LiteracyQuestion("lit_syllables_market", "phonemic_awareness", "Clap market with me. How many parts do you hear?", ("two", "2"), 2),
    ),
    "oral_vocabulary": (
        LiteracyQuestion("lit_vocab_clinic", "oral_vocabulary", "A clinic is a place people go when they are sick. Say one reason someone goes to a clinic.", ("sick", "medicine", "doctor"), 2),
        LiteracyQuestion("lit_vocab_transport", "oral_vocabulary", "Which one is transport: a bus or a spoon?", ("bus",), 1),
        LiteracyQuestion("lit_vocab_opposite_hot", "oral_vocabulary", "What is the opposite of hot?", ("cold",), 1),
    ),
    "listening_comprehension": (
        LiteracyQuestion("lit_story_umbrella", "listening_comprehension", "Listen: Amina carried an umbrella because the sky was dark. What did Amina carry?", ("umbrella",), 2),
        LiteracyQuestion("lit_story_goat", "listening_comprehension", "Listen: The goat ran into the market and knocked over a basket. What animal ran?", ("goat",), 2),
        LiteracyQuestion("lit_story_why_rain", "listening_comprehension", "Kemi wore slippers because rain made the road wet. Why did she wear slippers?", ("rain", "wet"), 3),
    ),
    "oral_grammar": (
        LiteracyQuestion("lit_sentence_market", "oral_grammar", "Repeat and change one word: I am going to school. Now say it with market.", ("I am going to market", "going to market"), 2),
        LiteracyQuestion("lit_past_buy", "oral_grammar", "Say this in yesterday words: I buy rice.", ("I bought rice", "bought rice"), 3),
        LiteracyQuestion("lit_question_where", "oral_grammar", "Ask a question with where about the book.", ("where is the book", "where book"), 3),
    ),
    "advanced_phonemic_awareness": (
        LiteracyQuestion("lit_segment_cat", "advanced_phonemic_awareness", "Break cat into sounds.", ("c a t", "k a t", "c, a, t"), 3),
        LiteracyQuestion("lit_delete_smile", "advanced_phonemic_awareness", "Say smile without the s sound.", ("mile",), 4),
        LiteracyQuestion("lit_sub_mat_sat", "advanced_phonemic_awareness", "Change the m in mat to s. What word?", ("sat",), 4),
    ),
    "print_bridge": (
        LiteracyQuestion("lit_print_sat", "print_bridge", "I will say letter sounds: s, a, t. What word do they make?", ("sat",), 3),
        LiteracyQuestion("lit_print_mop", "print_bridge", "Blend these sounds: m, o, p.", ("mop",), 3),
    ),
}


def run_full_course_harness(
    *,
    children: int,
    calls_per_child: int,
    seed: int,
    output_root: Path,
    resume_run_dir: Path | None = None,
) -> dict[str, Any]:
    if resume_run_dir:
        run_dir = resume_run_dir
        metadata = _read_json(run_dir / "run_metadata.json")
        cohort = _load_cohort(run_dir / "cohort.json")
        run_id = str(metadata["run_id"])
        children = int(metadata["children"])
        calls_per_child = int(metadata["calls_per_child"])
        seed = int(metadata["seed"])
    else:
        run_id = f"fullcoursefake-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        metadata = {
            "run_id": run_id,
            "mode": "full_course_phone_harness",
            "children": children,
            "calls_per_child": calls_per_child,
            "seed": seed,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "Deterministic phone-call-shaped full-course rehearsal over fake children. "
                "Runs local curriculum/assessment/teacher-note logic only; does not write live Supabase "
                "and does not spend STT/TTS/LLM/telephony money."
            ),
            "limitations": [
                "Not a real AudioSocket call yet.",
                "Not real LLM reasoning yet; assistant turns are deterministic curriculum fixtures.",
                "Literacy lesson scoring is simulated because backend literacy lesson analysis currently checks completion shape, not answer correctness.",
            ],
        }
        cohort = generate_cohort(children, seed=seed)
        _write_json(run_dir / "run_metadata.json", metadata)
        _write_json(run_dir / "cohort.json", cohort_to_jsonable(cohort))
        for name in JSONL_OUTPUTS:
            (run_dir / name).write_text("")

    completed_child_ids = _completed_child_ids(run_dir / "child_progression.jsonl")
    for child_index, child in enumerate(cohort, start=1):
        if child.child_id in completed_child_ids:
            continue
        child_result = _run_child_full_course(
            child=child,
            child_index=child_index,
            calls_per_child=calls_per_child,
            seed=seed,
        )
        _append_jsonl(run_dir / "full_course_calls.jsonl", child_result["calls"])
        _append_jsonl(run_dir / "full_course_transcripts.jsonl", child_result["transcripts"])
        _append_jsonl(run_dir / "full_course_turns.jsonl", child_result["turns"])
        _append_jsonl(run_dir / "evaluations.jsonl", child_result["evaluations"])
        _append_jsonl(run_dir / "failures.jsonl", [row for row in child_result["evaluations"] if row.get("failure_type")])
        _append_jsonl(run_dir / "child_progression.jsonl", [child_result["child_progression"]])
        _write_json(
            run_dir / "checkpoint.json",
            {
                "run_id": run_id,
                "last_completed_child_id": child.child_id,
                "last_completed_child_index": child_index,
                "completed_children": len(_completed_child_ids(run_dir / "child_progression.jsonl")),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return _finalize_full_course_run(run_dir, metadata=metadata, cohort=cohort)


def _run_child_full_course(
    *,
    child: FakeChildProfile,
    child_index: int,
    calls_per_child: int,
    seed: int,
) -> dict[str, Any]:
    state = default_learning_state()
    state.update(
        {
            "course": "numeracy",
            "phase": "diagnostic",
            "onboarding_status": "complete",
            "diagnostic_status": "not_started",
        }
    )
    student = {
        "id": child.child_id,
        "name": child.display_name,
        "current_module": 0,
        "learning_state": state,
    }

    calls: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []
    turns_out: list[dict[str, Any]] = []
    evaluations_out: list[dict[str, Any]] = []
    first_numeracy_position: tuple[int, int, int] | None = None
    first_literacy_position: tuple[int, int, int, int] | None = None
    numeracy_advances = 0
    literacy_advances = 0
    numeracy_correct = 0
    numeracy_wrong = 0
    literacy_correct = 0
    literacy_wrong = 0

    for call_index in range(1, calls_per_child + 1):
        before = dict(state)
        student["current_module"] = int(before.get("current_module") or 0)
        student["learning_state"] = before
        course = str(before.get("course") or "numeracy")
        call_id = f"{child.child_id}-full-{call_index:03d}"
        rng = random.Random(f"{seed}:{child.child_id}:full:{call_index}")

        if course == "literacy":
            literacy = dict(before.get("literacy") or {})
            if literacy.get("diagnostic_status") != "done":
                call_type = "literacy_diagnostic"
                lesson = resolve_literacy_lesson(before)
                rehearsal = _build_literacy_diagnostic_call(child=child, call_index=call_index, seed=seed)
            else:
                call_type = "literacy_lesson"
                lesson = resolve_literacy_lesson(before)
                rehearsal = _build_literacy_lesson_call(
                    child=child,
                    call_index=call_index,
                    lesson=lesson or {},
                    rng=rng,
                )
        else:
            if int(before.get("current_module") or 0) <= 0 or before.get("diagnostic_status") != "done":
                call_type = "numeracy_diagnostic"
                lesson = resolve_numeracy_lesson(before)
                rehearsal = _build_numeracy_diagnostic_call(child=child, call_index=call_index, seed=seed)
            else:
                call_type = "numeracy_lesson"
                lesson = resolve_numeracy_lesson(before)
                rehearsal = _build_numeracy_lesson_call(
                    child=child,
                    call_index=call_index,
                    lesson=lesson or {},
                    rng=rng,
                )

        stats = analyze_session(student, rehearsal["messages"])
        analyzed_after = dict(stats.learning_state or before)
        advanced = False
        if stats.should_advance:
            advanced = True
            analyzed_after = advance_learning_state_after_mastery(analyzed_after)
            if course == "literacy":
                literacy_advances += 1
            else:
                numeracy_advances += 1

        user_turns = sum(1 for message in rehearsal["messages"] if message.get("role") == "user")
        after = route_next_course_after_session(
            analyzed_after,
            user_turns=user_turns,
            has_learning_evidence=bool(user_turns and rehearsal["turns"]),
        )

        if first_numeracy_position is None and int(after.get("current_module") or 0) > 0 and after.get("diagnostic_status") == "done":
            first_numeracy_position = _numeracy_position(after)
        literacy_after = after.get("literacy") if isinstance(after.get("literacy"), dict) else {}
        if first_literacy_position is None and literacy_after.get("diagnostic_status") == "done":
            first_literacy_position = _literacy_position(after)

        simulated_correct = sum(1 for turn in rehearsal["turns"] if turn.ground_truth_correct)
        simulated_wrong = sum(1 for turn in rehearsal["turns"] if not turn.ground_truth_correct)
        score_correct = stats.correct_count if call_type.startswith("numeracy") else simulated_correct
        score_wrong = stats.wrong_count if call_type.startswith("numeracy") else simulated_wrong
        if call_type.startswith("numeracy"):
            numeracy_correct += int(score_correct or 0)
            numeracy_wrong += int(score_wrong or 0)
        else:
            literacy_correct += int(score_correct or 0)
            literacy_wrong += int(score_wrong or 0)

        scorecard = build_call_scorecard(
            course=course,
            lesson=lesson,
            correct_count=score_correct,
            wrong_count=score_wrong,
            skills=stats.skills,
            learning_state_before=before,
            learning_state_after=after,
            should_advance=stats.should_advance,
        )
        teacher_note = heuristic_teacher_note(
            correct_count=score_correct,
            wrong_count=score_wrong,
            skills=stats.skills,
            summary=stats.summary,
            current_level=stats.current_level,
            lesson=lesson,
            learning_state=after,
            user_turns=user_turns,
        )

        turn_evaluations = [evaluate_turn(turn) for turn in rehearsal["turns"]]
        evaluations_out.extend(
            {
                **evaluation.to_dict(),
                "call_id": call_id,
                "course": course,
                "call_type": call_type,
            }
            for evaluation in turn_evaluations
        )
        turns_out.extend(
            {
                **turn.to_dict(),
                "call_id": call_id,
                "course": course,
                "call_type": call_type,
            }
            for turn in rehearsal["turns"]
        )
        transcripts.extend(
            {
                "call_id": call_id,
                "child_id": child.child_id,
                "call_index": call_index,
                "course": course,
                "call_type": call_type,
                "turn_index": index,
                "role": message.get("role"),
                "content": message.get("content"),
            }
            for index, message in enumerate(rehearsal["messages"], start=1)
        )
        release_blockers = sum(1 for item in turn_evaluations if item.severity == "release_blocking")
        calls.append(
            {
                "call_id": call_id,
                "child_id": child.child_id,
                "child_index": child_index,
                "call_index": call_index,
                "course": course,
                "call_type": call_type,
                "lesson": lesson or {},
                "before": _state_summary(before),
                "after": _state_summary(after),
                "duration_seconds": rehearsal["duration_seconds"],
                "completed_5_7_minute_window": 300 <= rehearsal["duration_seconds"] <= 420,
                "early_hangup": rehearsal["early_hangup"],
                "phases_completed": rehearsal["phases_completed"],
                "user_turns": user_turns,
                "analyzer_correct_count": stats.correct_count,
                "analyzer_wrong_count": stats.wrong_count,
                "score_correct_count": score_correct,
                "score_wrong_count": score_wrong,
                "simulated_correct_count": simulated_correct,
                "simulated_wrong_count": simulated_wrong,
                "should_advance": stats.should_advance,
                "advanced": advanced,
                "teacher_note": teacher_note,
                "scorecard": scorecard,
                "release_blocking_failures": release_blockers,
                "summary": stats.summary,
                "topics_covered": stats.topics_covered,
            }
        )
        state = after

    final_numeracy_position = _numeracy_position(state)
    final_literacy_position = _literacy_position(state)
    child_progression = {
        "child_id": child.child_id,
        "display_name": child.display_name,
        "age": child.age,
        "gender": child.gender,
        "language_profile": child.language_profile,
        "school_status": child.school_status,
        "hidden_numeracy_level": child.numeracy_level,
        "hidden_literacy_level": child.literacy_level,
        "noise_level": child.noise_level,
        "environment": child.environment,
        "temperament": child.temperament,
        "call_behavior": child.call_behavior,
        "calls_completed": calls_per_child,
        "first_numeracy_position": _numeracy_position_dict(first_numeracy_position),
        "final_numeracy_position": _numeracy_position_dict(final_numeracy_position),
        "first_literacy_position": _literacy_position_dict(first_literacy_position),
        "final_literacy_position": _literacy_position_dict(final_literacy_position),
        "numeracy_lesson_advances": numeracy_advances,
        "literacy_lesson_advances": literacy_advances,
        "numeracy_correct_count": numeracy_correct,
        "numeracy_wrong_count": numeracy_wrong,
        "literacy_correct_count": literacy_correct,
        "literacy_wrong_count": literacy_wrong,
        "numeracy_accuracy": _accuracy(numeracy_correct, numeracy_wrong),
        "literacy_accuracy": _accuracy(literacy_correct, literacy_wrong),
        "numeracy_lesson_gain_from_placement": _numeracy_gain(first_numeracy_position, final_numeracy_position),
        "literacy_lesson_gain_from_placement": _literacy_gain(first_literacy_position, final_literacy_position),
        "possible_numeracy_over_advance": _possible_numeracy_over_advance(child, final_numeracy_position, numeracy_correct, numeracy_wrong),
        "possible_numeracy_under_advance": _possible_numeracy_under_advance(child, first_numeracy_position, final_numeracy_position, numeracy_advances),
        "possible_literacy_under_advance": _possible_literacy_under_advance(child, first_literacy_position, final_literacy_position, literacy_advances),
        "final_state": _state_summary(state),
    }
    return {
        "calls": calls,
        "transcripts": transcripts,
        "turns": turns_out,
        "evaluations": evaluations_out,
        "child_progression": child_progression,
    }


def _build_numeracy_diagnostic_call(
    *,
    child: FakeChildProfile,
    call_index: int,
    seed: int,
) -> dict[str, Any]:
    turns = simulate_diagnostic_call(child, call_index=call_index, seed=seed, max_turns=18)
    messages = _messages_from_turns(turns)
    return {
        "messages": messages,
        "turns": turns,
        "duration_seconds": _estimated_duration_seconds(["greeting_recall", "teach", "guided_practice", "independent_check", "wrap"], random.Random(f"{seed}:{child.child_id}:numdiag:{call_index}"), False),
        "early_hangup": False,
        "phases_completed": ["greeting_recall", "teach", "guided_practice", "independent_check", "wrap"],
    }


def _build_numeracy_lesson_call(
    *,
    child: FakeChildProfile,
    call_index: int,
    lesson: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    module = int((lesson or {}).get("module") or 1)
    bank = LESSON_BANK.get(module) or LESSON_BANK[6]
    early_hangup = child.call_behavior == "hangs_up_early" and rng.random() < 0.22
    turns: list[SimulatedTurn] = []
    messages: list[dict[str, str]] = []
    phases_completed: list[str] = []

    recall = bank[(call_index - 1) % len(bank)]
    messages.append({"role": "assistant", "content": f"Welcome back. Warm-up: {recall.prompt}"})
    turns.append(_numeracy_answer_turn(child, call_index, 1, recall, rng))
    messages.append({"role": "user", "content": turns[-1].stt_text})
    phases_completed.append("greeting_recall")

    messages.append({"role": "assistant", "content": f"Today is {lesson.get('title', 'our number lesson')}. We will use a Nigerian market example and solve it slowly."})
    phases_completed.append("teach")

    guided = bank[call_index % len(bank)]
    messages.append({"role": "assistant", "content": f"Let's do one together. {guided.prompt}"})
    turns.append(_numeracy_answer_turn(child, call_index, 2, guided, rng))
    messages.append({"role": "user", "content": turns[-1].stt_text})
    phases_completed.append("guided_practice")

    if not early_hangup:
        independent = bank[(call_index + 1) % len(bank)]
        messages.append({"role": "assistant", "content": f"Now you try this one. {independent.prompt}"})
        turns.append(_numeracy_answer_turn(child, call_index, 3, independent, rng))
        messages.append({"role": "user", "content": turns[-1].stt_text})
        phases_completed.append("independent_check")

        check = bank[(call_index + 2) % len(bank)]
        messages.append({"role": "assistant", "content": f"Last check before we close: {check.prompt}"})
        turns.append(_numeracy_answer_turn(child, call_index, 4, check, rng))
        messages.append({"role": "user", "content": turns[-1].stt_text})
        messages.append({"role": "assistant", "content": f"Well done today. Today you learned {lesson.get('title', 'this skill')}. Next time we will continue with {lesson.get('next_title', 'the next lesson')}."})
        phases_completed.append("wrap")

    return {
        "messages": messages,
        "turns": turns,
        "duration_seconds": _estimated_duration_seconds(phases_completed, rng, early_hangup),
        "early_hangup": early_hangup,
        "phases_completed": phases_completed,
    }


def _build_literacy_diagnostic_call(
    *,
    child: FakeChildProfile,
    call_index: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(f"{seed}:{child.child_id}:litdiag:{call_index}")
    turns: list[SimulatedTurn] = []
    for turn_index, item in enumerate(LITERACY_DIAGNOSTIC_ITEMS, start=1):
        if child.call_behavior == "hangs_up_early" and turn_index > 3 and rng.random() < 0.45:
            break
        answer_text, correct, notes = _literacy_answer_for_diagnostic_item(child, item, rng)
        stt_text, stt_notes = corrupt_transcript(answer_text, child, rng)
        turns.append(
            SimulatedTurn(
                child_id=child.child_id,
                call_index=call_index,
                turn_index=turn_index,
                prompt=item.prompt,
                item_id=item.id,
                expected_answers=LITERACY_CORRECT_ANSWERS.get(item.id, (answer_text,)),
                ground_truth_correct=correct,
                child_answer_text=answer_text,
                stt_text=stt_text,
                noise_level=child.noise_level,
                notes=tuple([*notes, *stt_notes, "literacy_diagnostic"]),
            )
        )
    messages = _messages_from_turns(turns)
    return {
        "messages": messages,
        "turns": turns,
        "duration_seconds": _estimated_duration_seconds(["greeting_recall", "teach", "guided_practice", "independent_check", "wrap"], rng, False),
        "early_hangup": False,
        "phases_completed": ["greeting_recall", "teach", "guided_practice", "independent_check", "wrap"],
    }


def _build_literacy_lesson_call(
    *,
    child: FakeChildProfile,
    call_index: int,
    lesson: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    skill = _literacy_skill_for_lesson(lesson)
    bank = LITERACY_LESSON_BANK.get(skill) or LITERACY_LESSON_BANK["phonemic_awareness"]
    early_hangup = child.call_behavior == "hangs_up_early" and rng.random() < 0.22
    turns: list[SimulatedTurn] = []
    messages: list[dict[str, str]] = []
    phases_completed: list[str] = []

    recall = bank[(call_index - 1) % len(bank)]
    messages.append({"role": "assistant", "content": f"Welcome back. Sound warm-up: {recall.prompt}"})
    turns.append(_literacy_answer_turn(child, call_index, 1, recall, rng))
    messages.append({"role": "user", "content": turns[-1].stt_text})
    phases_completed.append("greeting_recall")

    messages.append({"role": "assistant", "content": f"Today is {lesson.get('title', 'our literacy lesson')}. Listen first, then you will try one."})
    phases_completed.append("teach")

    guided = bank[call_index % len(bank)]
    messages.append({"role": "assistant", "content": f"Let's do one together. {guided.prompt}"})
    turns.append(_literacy_answer_turn(child, call_index, 2, guided, rng))
    messages.append({"role": "user", "content": turns[-1].stt_text})
    phases_completed.append("guided_practice")

    if not early_hangup:
        independent = bank[(call_index + 1) % len(bank)]
        messages.append({"role": "assistant", "content": f"Now you try. {independent.prompt}"})
        turns.append(_literacy_answer_turn(child, call_index, 3, independent, rng))
        messages.append({"role": "user", "content": turns[-1].stt_text})
        phases_completed.append("independent_check")
        messages.append({"role": "assistant", "content": f"Well done today. Today you learned {lesson.get('title', 'this skill')}. Next time we will continue with {lesson.get('next_title', 'the next literacy lesson')}."})
        phases_completed.append("wrap")

    return {
        "messages": messages,
        "turns": turns,
        "duration_seconds": _estimated_duration_seconds(phases_completed, rng, early_hangup),
        "early_hangup": early_hangup,
        "phases_completed": phases_completed,
    }


def _numeracy_answer_turn(
    child: FakeChildProfile,
    call_index: int,
    turn_index: int,
    question: LessonQuestion,
    rng: random.Random,
) -> SimulatedTurn:
    answer_text, correct, notes = _lesson_answer_for_child(child, question, rng)
    stt_text, stt_notes = corrupt_transcript(answer_text, child, rng)
    expected = [str(question.expected), _number_to_text(question.expected, rng)]
    return SimulatedTurn(
        child_id=child.child_id,
        call_index=call_index,
        turn_index=turn_index,
        prompt=question.prompt,
        item_id=question.item_id,
        expected_answers=tuple(dict.fromkeys(expected)),
        ground_truth_correct=correct,
        child_answer_text=answer_text,
        stt_text=stt_text,
        noise_level=child.noise_level,
        notes=tuple([*notes, *stt_notes, "full_course_numeracy"]),
    )


def _literacy_answer_turn(
    child: FakeChildProfile,
    call_index: int,
    turn_index: int,
    question: LiteracyQuestion,
    rng: random.Random,
) -> SimulatedTurn:
    answer_text, correct, notes = _literacy_answer_for_lesson_question(child, question, rng)
    stt_text, stt_notes = corrupt_transcript(answer_text, child, rng)
    return SimulatedTurn(
        child_id=child.child_id,
        call_index=call_index,
        turn_index=turn_index,
        prompt=question.prompt,
        item_id=question.item_id,
        expected_answers=question.expected_answers,
        ground_truth_correct=correct,
        child_answer_text=answer_text,
        stt_text=stt_text,
        noise_level=child.noise_level,
        notes=tuple([*notes, *stt_notes, "full_course_literacy"]),
    )


def _literacy_answer_for_diagnostic_item(
    child: FakeChildProfile,
    item: LiteracyDiagnosticItem,
    rng: random.Random,
) -> tuple[str, bool, list[str]]:
    difficulty = int(item.fail_tarl_level or 0) + 1
    return _literacy_answer_by_ability(
        child=child,
        expected=LITERACY_CORRECT_ANSWERS.get(item.id, ("yes",)),
        difficulty=difficulty,
        rng=rng,
        miss_note=f"literacy_ability_miss:{item.domain}",
    )


def _literacy_answer_for_lesson_question(
    child: FakeChildProfile,
    question: LiteracyQuestion,
    rng: random.Random,
) -> tuple[str, bool, list[str]]:
    return _literacy_answer_by_ability(
        child=child,
        expected=question.expected_answers,
        difficulty=question.difficulty,
        rng=rng,
        miss_note=f"literacy_lesson_miss:{question.skill}",
    )


def _literacy_answer_by_ability(
    *,
    child: FakeChildProfile,
    expected: tuple[str, ...],
    difficulty: int,
    rng: random.Random,
    miss_note: str,
) -> tuple[str, bool, list[str]]:
    if child.literacy_level >= difficulty:
        correct_prob = 0.84
    elif child.literacy_level + 1 == difficulty:
        correct_prob = 0.48
    else:
        correct_prob = 0.16
    if child.temperament == "guesses":
        correct_prob -= 0.10
    if child.temperament == "eager":
        correct_prob += 0.04
    if child.noise_level in {"lagos_market", "brutal_market"}:
        correct_prob -= 0.04
    correct_prob = max(0.02, min(0.95, correct_prob))
    if rng.random() < correct_prob:
        return rng.choice(expected), True, []
    expected_normalized = {_normalize_answer(answer) for answer in expected}
    wrong_pool = [
        answer
        for answer in LITERACY_WRONG_ANSWERS
        if _normalize_answer(answer) not in expected_normalized
    ] or ["I don't know"]
    return rng.choice(wrong_pool), False, [miss_note]


def _messages_from_turns(turns: Iterable[SimulatedTurn]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "assistant", "content": turn.prompt})
        messages.append({"role": "user", "content": turn.stt_text})
    return messages


def _normalize_answer(text: str) -> str:
    return " ".join(str(text or "").lower().replace(",", " ").split())


def _estimated_duration_seconds(phases_completed: list[str], rng: random.Random, early_hangup: bool) -> int:
    if early_hangup:
        return int(sum(FULL_CALL_SECONDS[phase] for phase in phases_completed) + rng.randint(-10, 20))
    return int(sum(FULL_CALL_SECONDS.values()) + rng.randint(-20, 30))


def _literacy_skill_for_lesson(lesson: dict[str, Any]) -> str:
    module = int((lesson or {}).get("module") or 1)
    return {
        1: "phonemic_awareness",
        2: "oral_vocabulary",
        3: "listening_comprehension",
        4: "oral_grammar",
        5: "advanced_phonemic_awareness",
        6: "print_bridge",
    }.get(module, "phonemic_awareness")


def _finalize_full_course_run(run_dir: Path, *, metadata: dict[str, Any], cohort: list[FakeChildProfile]) -> dict[str, Any]:
    calls = _read_jsonl(run_dir / "full_course_calls.jsonl")
    evaluations = _read_jsonl(run_dir / "evaluations.jsonl")
    child_rows = _read_jsonl(run_dir / "child_progression.jsonl")
    summary = _summarize_full_course(calls, evaluations, child_rows, cohort)
    run_summary = {"metadata": metadata, "summary": summary}
    _write_json(run_dir / "run_summary.json", run_summary)
    _write_json(
        run_dir / "cost_report.json",
        estimate_fake_pilot_cost(
            FakePilotCostAssumptions(
                children=int(metadata["children"]),
                calls_per_child=int(metadata["calls_per_child"]),
            )
        ),
    )
    _write_csv(run_dir / "learning_gain.csv", _learning_gain_rows(child_rows))
    _write_csv(run_dir / "teacher_notes_audit.csv", _teacher_note_rows(calls))
    _write_csv(run_dir / "scorecards.csv", _scorecard_rows(calls))
    _write_csv(run_dir / "course_coverage.csv", _course_coverage_rows(calls))
    _write_regression_suggestions_from_dicts(run_dir / "regression_cases_to_add.md", evaluations)
    _write_full_course_report(
        run_dir / "full_course_report.md",
        run_id=str(metadata["run_id"]),
        metadata=metadata,
        summary=summary,
        calls=calls,
        child_rows=child_rows,
    )
    return {"run_dir": str(run_dir), "metadata": metadata, "summary": summary}


def _summarize_full_course(
    calls: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    child_rows: list[dict[str, Any]],
    cohort: list[FakeChildProfile],
) -> dict[str, Any]:
    eval_objects = [_evaluation_from_dict(row) for row in evaluations]
    evaluation_summary = summarize_evaluations(eval_objects)
    total_calls = len(calls)
    complete_window = [row for row in calls if row.get("completed_5_7_minute_window")]
    early_hangups = [row for row in calls if row.get("early_hangup")]
    release_blocking_calls = [row for row in calls if int(row.get("release_blocking_failures") or 0) > 0]
    course_counts = Counter(str(row.get("course") or "unknown") for row in calls)
    call_type_counts = Counter(str(row.get("call_type") or "unknown") for row in calls)
    notes = [row for row in calls if row.get("teacher_note")]
    scorecards = [row for row in calls if row.get("scorecard")]
    numeracy_gains = [int(row.get("numeracy_lesson_gain_from_placement") or 0) for row in child_rows]
    literacy_gains = [int(row.get("literacy_lesson_gain_from_placement") or 0) for row in child_rows]
    return {
        **evaluation_summary,
        "children": len(cohort),
        "completed_children": len(child_rows),
        "full_course_calls": total_calls,
        "completed_5_7_minute_calls": len(complete_window),
        "completed_5_7_minute_rate": _rate(len(complete_window), total_calls),
        "early_hangups": len(early_hangups),
        "calls_with_release_blockers": len(release_blocking_calls),
        "teacher_notes_generated": len(notes),
        "teacher_note_rate": _rate(len(notes), total_calls),
        "scorecards_generated": len(scorecards),
        "scorecard_rate": _rate(len(scorecards), total_calls),
        "course_counts": dict(sorted(course_counts.items())),
        "call_type_counts": dict(sorted(call_type_counts.items())),
        "mean_numeracy_lesson_gain": round(sum(numeracy_gains) / max(1, len(numeracy_gains)), 3),
        "mean_literacy_lesson_gain": round(sum(literacy_gains) / max(1, len(literacy_gains)), 3),
        "children_with_numeracy_gain": sum(1 for gain in numeracy_gains if gain > 0),
        "children_with_literacy_gain": sum(1 for gain in literacy_gains if gain > 0),
        "possible_numeracy_over_advance_children": sum(1 for row in child_rows if row.get("possible_numeracy_over_advance")),
        "possible_numeracy_under_advance_children": sum(1 for row in child_rows if row.get("possible_numeracy_under_advance")),
        "possible_literacy_under_advance_children": sum(1 for row in child_rows if row.get("possible_literacy_under_advance")),
    }


def _evaluation_from_dict(row: dict[str, Any]) -> TurnEvaluation:
    data = dict(row)
    data["expected_answers"] = tuple(data.get("expected_answers") or ())
    data["notes"] = tuple(data.get("notes") or ())
    for extra in ("call_id", "course", "call_type"):
        data.pop(extra, None)
    return TurnEvaluation(**data)


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    return {
        "course": state.get("course"),
        "phase": state.get("phase"),
        "numeracy": _state_slice(state),
        "literacy": {
            "phase": literacy.get("phase"),
            "diagnostic_status": literacy.get("diagnostic_status"),
            "module": int(literacy.get("current_module") or 1),
            "week": int(literacy.get("current_week") or 1),
            "lesson": int(literacy.get("current_lesson") or 1),
            "tarl_reading_level": int(literacy.get("tarl_reading_level") or 0),
            "active_skill": literacy.get("active_skill"),
        },
    }


def _numeracy_position(state: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(state.get("current_module") or 0),
        int(state.get("current_week") or 1),
        int(state.get("current_lesson") or 1),
    )


def _literacy_position(state: dict[str, Any]) -> tuple[int, int, int, int]:
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    return (
        int(literacy.get("current_phase") or 1),
        int(literacy.get("current_module") or 1),
        int(literacy.get("current_week") or 1),
        int(literacy.get("current_lesson") or 1),
    )


def _numeracy_position_dict(position: tuple[int, int, int] | None) -> dict[str, int] | None:
    if position is None:
        return None
    return {"module": position[0], "week": position[1], "lesson": position[2]}


def _literacy_position_dict(position: tuple[int, int, int, int] | None) -> dict[str, int] | None:
    if position is None:
        return None
    return {"phase": position[0], "module": position[1], "week": position[2], "lesson": position[3]}


def _numeracy_gain(start: tuple[int, int, int] | None, final: tuple[int, int, int]) -> int:
    if start is None:
        return 0
    return max(0, _numeracy_ordinal(final) - _numeracy_ordinal(start))


def _literacy_gain(start: tuple[int, int, int, int] | None, final: tuple[int, int, int, int]) -> int:
    if start is None:
        return 0
    return max(0, _literacy_ordinal(final) - _literacy_ordinal(start))


def _numeracy_ordinal(position: tuple[int, int, int]) -> int:
    return int(position[0]) * 1000 + int(position[1]) * 10 + int(position[2])


def _literacy_ordinal(position: tuple[int, int, int, int]) -> int:
    return int(position[0]) * 10000 + int(position[1]) * 1000 + int(position[2]) * 10 + int(position[3])


def _accuracy(correct: int, wrong: int) -> float | None:
    total = int(correct or 0) + int(wrong or 0)
    if total <= 0:
        return None
    return round(int(correct or 0) / total, 3)


def _possible_numeracy_over_advance(child: FakeChildProfile, final: tuple[int, int, int], correct: int, wrong: int) -> bool:
    accuracy = _accuracy(correct, wrong)
    return final[0] > max(1, child.numeracy_level + 1) and (accuracy is None or accuracy < 0.70)


def _possible_numeracy_under_advance(
    child: FakeChildProfile,
    start: tuple[int, int, int] | None,
    final: tuple[int, int, int],
    advances: int,
) -> bool:
    if start is None:
        return True
    return child.numeracy_level >= max(1, start[0] + 2) and final[0] <= start[0] and advances == 0


def _possible_literacy_under_advance(
    child: FakeChildProfile,
    start: tuple[int, int, int, int] | None,
    final: tuple[int, int, int, int],
    advances: int,
) -> bool:
    if start is None:
        return True
    return child.literacy_level >= max(1, start[1] + 1) and final[1] <= start[1] and advances == 0


def _learning_gain_rows(child_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in child_rows:
        numeracy_start = row.get("first_numeracy_position") or {}
        numeracy_final = row.get("final_numeracy_position") or {}
        literacy_start = row.get("first_literacy_position") or {}
        literacy_final = row.get("final_literacy_position") or {}
        rows.append(
            {
                "child_id": row.get("child_id"),
                "hidden_numeracy_level": row.get("hidden_numeracy_level"),
                "hidden_literacy_level": row.get("hidden_literacy_level"),
                "noise_level": row.get("noise_level"),
                "temperament": row.get("temperament"),
                "call_behavior": row.get("call_behavior"),
                "numeracy_start_module": numeracy_start.get("module"),
                "numeracy_final_module": numeracy_final.get("module"),
                "numeracy_lesson_advances": row.get("numeracy_lesson_advances"),
                "numeracy_lesson_gain_from_placement": row.get("numeracy_lesson_gain_from_placement"),
                "numeracy_accuracy": row.get("numeracy_accuracy"),
                "literacy_start_module": literacy_start.get("module"),
                "literacy_final_module": literacy_final.get("module"),
                "literacy_lesson_advances": row.get("literacy_lesson_advances"),
                "literacy_lesson_gain_from_placement": row.get("literacy_lesson_gain_from_placement"),
                "literacy_accuracy": row.get("literacy_accuracy"),
                "possible_numeracy_over_advance": row.get("possible_numeracy_over_advance"),
                "possible_numeracy_under_advance": row.get("possible_numeracy_under_advance"),
                "possible_literacy_under_advance": row.get("possible_literacy_under_advance"),
            }
        )
    return rows


def _teacher_note_rows(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in calls:
        note = call.get("teacher_note") or {}
        rows.append(
            {
                "call_id": call.get("call_id"),
                "child_id": call.get("child_id"),
                "course": call.get("course"),
                "call_type": call.get("call_type"),
                "note_generated": bool(note),
                "source": note.get("source"),
                "engagement": note.get("engagement"),
                "strengths_count": len(note.get("strengths") or []),
                "struggles_count": len(note.get("struggles") or []),
                "has_recommended_focus": bool(note.get("recommended_focus")),
                "has_narrative": bool(note.get("narrative")),
                "duration_seconds": call.get("duration_seconds"),
                "user_turns": call.get("user_turns"),
            }
        )
    return rows


def _scorecard_rows(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in calls:
        scorecard = call.get("scorecard") or {}
        rows.append(
            {
                "call_id": call.get("call_id"),
                "child_id": call.get("child_id"),
                "course": scorecard.get("course"),
                "call_type": call.get("call_type"),
                "module": scorecard.get("module"),
                "lesson_global": scorecard.get("lesson_global"),
                "questions_correct": scorecard.get("questions_correct"),
                "questions_total": scorecard.get("questions_total"),
                "accuracy": scorecard.get("accuracy"),
                "mastery_signal": scorecard.get("mastery_signal"),
                "lesson_passed": scorecard.get("lesson_passed"),
                "should_advance": scorecard.get("should_advance"),
            }
        )
    return rows


def _course_coverage_rows(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    call_counts: Counter[tuple[Any, ...]] = Counter()
    titles: dict[tuple[Any, ...], str] = {}
    for call in calls:
        lesson = call.get("lesson") or {}
        key = (
            call.get("course"),
            lesson.get("module"),
            lesson.get("week"),
            lesson.get("lesson"),
            lesson.get("global_lesson") or lesson.get("script_lesson"),
        )
        call_counts[key] += 1
        counts[key].add(str(call.get("child_id")))
        titles[key] = str(lesson.get("title") or "")
    rows: list[dict[str, Any]] = []
    for key, count in sorted(call_counts.items(), key=lambda item: tuple(str(part) for part in item[0])):
        rows.append(
            {
                "course": key[0],
                "module": key[1],
                "week": key[2],
                "lesson": key[3],
                "global_or_script_lesson": key[4],
                "title": titles.get(key, ""),
                "calls": count,
                "children": len(counts[key]),
            }
        )
    return rows


def _write_full_course_report(
    path: Path,
    *,
    run_id: str,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    calls: list[dict[str, Any]],
    child_rows: list[dict[str, Any]],
) -> None:
    release_calls = [row for row in calls if int(row.get("release_blocking_failures") or 0) > 0]
    outside_window = [row for row in calls if not row.get("completed_5_7_minute_window")]
    over = [row for row in child_rows if row.get("possible_numeracy_over_advance")]
    under_num = [row for row in child_rows if row.get("possible_numeracy_under_advance")]
    under_lit = [row for row in child_rows if row.get("possible_literacy_under_advance")]
    lines = [
        f"# Sabi full-course fake-child pilot report: {run_id}",
        "",
        "## Run",
        "",
        f"- Children: {metadata['children']}",
        f"- Calls per child: {metadata['calls_per_child']}",
        f"- Scope: {metadata['note']}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Release Blockers", ""])
    if release_calls:
        for row in release_calls[:25]:
            lines.append(f"- {row['call_id']}: {row['release_blocking_failures']} release-blocking turn failures")
    else:
        lines.append("- none")

    lines.extend(["", "## Calls Outside 5-7 Minute Window", ""])
    if outside_window:
        for row in outside_window[:25]:
            reason = "early_hangup" if row.get("early_hangup") else "duration_model"
            lines.append(f"- {row['call_id']}: {row['duration_seconds']}s ({reason})")
    else:
        lines.append("- none")

    lines.extend(["", "## Advancement Risks", ""])
    if not (over or under_num or under_lit):
        lines.append("- none flagged by the deterministic harness")
    for row in over[:15]:
        lines.append(f"- numeracy over-advance risk {row['child_id']}: hidden={row['hidden_numeracy_level']} final={row['final_numeracy_position']}")
    for row in under_num[:15]:
        lines.append(f"- numeracy under-advance risk {row['child_id']}: hidden={row['hidden_numeracy_level']} final={row['final_numeracy_position']}")
    for row in under_lit[:15]:
        lines.append(f"- literacy under-advance risk {row['child_id']}: hidden={row['hidden_literacy_level']} final={row['final_literacy_position']}")

    lines.extend(
        [
            "",
            "## Limitations To Close Next",
            "",
            "- Replay the same cohort through real AudioSocket media, STT, and TTS.",
            "- Replace deterministic assistant fixtures with the live LLM prompt while preserving curriculum path constraints.",
            "- Strengthen literacy backend scoring so lesson advancement depends on answer evidence, not only call shape.",
        ]
    )
    if int(metadata.get("children") or 0) < 100 or int(metadata.get("calls_per_child") or 0) < 240:
        lines.append("- Run the full 100 x 240 call configuration after the next smoke passes.")
    else:
        lines.append("- Re-run this full configuration after AudioSocket, live LLM, or literacy-scoring changes.")
    path.write_text("\n".join(lines) + "\n")


def _write_regression_suggestions_from_dicts(path: Path, evaluations: list[dict[str, Any]]) -> None:
    failures = [row for row in evaluations if row.get("failure_type")]
    lines = [
        "# Regression Cases To Add",
        "",
        "Generated from the full-course fake-child harness. Release-blocking rows should become code regressions before the fix is considered done.",
        "",
    ]
    if not failures:
        lines.append("No failures in this run.")
        path.write_text("\n".join(lines) + "\n")
        return
    for row in failures:
        lines.extend(
            [
                f"## {row.get('child_id')} call {row.get('call_index')} turn {row.get('turn_index')}: {row.get('failure_type')}",
                "",
                f"- Severity: {row.get('severity')}",
                f"- Course/type: {row.get('course')} / {row.get('call_type')}",
                f"- Item: {row.get('item_id')}",
                f"- Prompt: {row.get('assistant_prompt')}",
                f"- Expected answers: {', '.join(row.get('expected_answers') or [])}",
                f"- Child intended answer: `{row.get('child_answer_text')}`",
                f"- STT transcript: `{row.get('stt_text')}`",
                f"- Noise: {row.get('noise_level')}",
                f"- Notes: {', '.join(row.get('notes') or []) if row.get('notes') else 'none'}",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n")


def _completed_child_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(row.get("child_id")) for row in _read_jsonl(path) if row.get("child_id")}


def _load_cohort(path: Path) -> list[FakeChildProfile]:
    rows = _read_json(path)
    return [FakeChildProfile(**{**row, "stt_risks": tuple(row.get("stt_risks") or ())}) for row in rows]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _rate(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(count / denominator, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full-course fake-child Sabi phone-call harness.")
    parser.add_argument("--children", type=int, default=100)
    parser.add_argument("--calls-per-child", type=int, default=240)
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--output-root", type=Path, default=Path("../outputs/fake-child-harness/full-course-runs"))
    parser.add_argument("--resume-run-dir", type=Path, default=None)
    args = parser.parse_args()

    result = run_full_course_harness(
        children=args.children,
        calls_per_child=args.calls_per_child,
        seed=args.seed,
        output_root=args.output_root,
        resume_run_dir=args.resume_run_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
