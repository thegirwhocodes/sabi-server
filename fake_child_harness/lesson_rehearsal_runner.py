from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any

from curriculum_mastery import build_call_scorecard
from curriculum_path import advance_learning_state_after_mastery, resolve_numeracy_lesson
from learning_state import analyze_session
from teacher_notes import heuristic_teacher_note

from .child_simulator import SimulatedTurn, simulate_diagnostic_call
from .cohort import FakeChildProfile, cohort_to_jsonable, generate_cohort
from .evaluator import evaluate_turn, summarize_evaluations
from .progression_runner import (
    LESSON_BANK,
    _initial_student,
    _lesson_answer_for_child,
    _state_slice,
)
from .report import write_regression_case_suggestions


PHASE_SECONDS = {
    "greeting_recall": 45,
    "teach": 90,
    "guided_practice": 95,
    "independent_check": 100,
    "wrap": 40,
}


def run_lesson_rehearsal(
    *,
    children: int,
    calls_per_child: int,
    seed: int,
    output_root: Path,
) -> dict[str, Any]:
    run_id = f"lessonfake-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    cohort = generate_cohort(children, seed=seed)
    call_rows: list[dict[str, Any]] = []
    transcript_rows: list[dict[str, Any]] = []
    teacher_note_rows: list[dict[str, Any]] = []
    scorecard_rows: list[dict[str, Any]] = []
    all_turns: list[SimulatedTurn] = []
    evaluations = []

    for child in cohort:
        student, state = _initial_student(child)
        state = _place_child_with_diagnostic(child, student, seed)
        student["current_module"] = int(state.get("current_module") or 1)
        student["learning_state"] = state

        for call_index in range(1, calls_per_child + 1):
            before = dict(state)
            lesson = resolve_numeracy_lesson(state) or {}
            rng = random.Random(f"{seed}:{child.child_id}:lesson:{call_index}")
            rehearsal = _build_lesson_call(
                child=child,
                child_id=child.child_id,
                child_name=child.display_name,
                call_index=call_index,
                state=state,
                lesson=lesson,
                rng=rng,
            )
            stats = analyze_session(student, rehearsal["messages"])
            after = dict(stats.learning_state or {})
            advanced = False
            if stats.should_advance:
                after = advance_learning_state_after_mastery(after)
                advanced = True
            after["course"] = "numeracy"
            state = after
            student["current_module"] = int(state.get("current_module") or 0)
            student["learning_state"] = state

            scorecard = build_call_scorecard(
                course="numeracy",
                lesson=lesson,
                correct_count=stats.correct_count,
                wrong_count=stats.wrong_count,
                skills=stats.skills,
                learning_state_before=before,
                learning_state_after=after,
                should_advance=stats.should_advance,
            )
            teacher_note = heuristic_teacher_note(
                correct_count=stats.correct_count,
                wrong_count=stats.wrong_count,
                skills=stats.skills,
                summary=stats.summary,
                current_level=stats.current_level,
                lesson=lesson,
                learning_state=after,
                user_turns=sum(1 for message in rehearsal["messages"] if message.get("role") == "user"),
            )
            turn_evaluations = [evaluate_turn(turn) for turn in rehearsal["turns"]]
            all_turns.extend(rehearsal["turns"])
            evaluations.extend(turn_evaluations)

            call_id = f"{child.child_id}-call-{call_index:02d}"
            call_rows.append(
                {
                    "call_id": call_id,
                    "child_id": child.child_id,
                    "call_index": call_index,
                    "lesson": lesson,
                    "before": _state_slice(before),
                    "after": _state_slice(after),
                    "duration_seconds": rehearsal["duration_seconds"],
                    "completed_5_7_minute_window": 300 <= rehearsal["duration_seconds"] <= 420,
                    "early_hangup": rehearsal["early_hangup"],
                    "phases_completed": rehearsal["phases_completed"],
                    "correct_count": stats.correct_count,
                    "wrong_count": stats.wrong_count,
                    "should_advance": stats.should_advance,
                    "advanced": advanced,
                    "teacher_note": teacher_note,
                    "scorecard": scorecard,
                    "release_blocking_failures": sum(1 for item in turn_evaluations if item.severity == "release_blocking"),
                }
            )
            transcript_rows.extend(
                {
                    "call_id": call_id,
                    "child_id": child.child_id,
                    "call_index": call_index,
                    "turn_index": index,
                    "role": message.get("role"),
                    "content": message.get("content"),
                }
                for index, message in enumerate(rehearsal["messages"], start=1)
            )
            teacher_note_rows.append(_teacher_note_audit_row(call_id, child.child_id, teacher_note, rehearsal, stats))
            scorecard_rows.append(_scorecard_row(call_id, child.child_id, scorecard))

    evaluation_summary = summarize_evaluations(evaluations)
    summary = {
        **evaluation_summary,
        **_summarize_calls(call_rows),
    }
    metadata = {
        "run_id": run_id,
        "mode": "lesson_rehearsal",
        "children": children,
        "calls_per_child": calls_per_child,
        "seed": seed,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Deterministic 5-7 minute lesson-shape rehearsal using curriculum path, learning-state analysis, scorecards, and heuristic teacher notes; not yet real LLM/TTS/AudioSocket.",
    }

    _write_json(run_dir / "run_summary.json", {"metadata": metadata, "summary": summary})
    _write_json(run_dir / "cohort.json", cohort_to_jsonable(cohort))
    _write_jsonl(run_dir / "lesson_calls.jsonl", call_rows)
    _write_jsonl(run_dir / "lesson_transcripts.jsonl", transcript_rows)
    _write_jsonl(run_dir / "turns.jsonl", [turn.to_dict() for turn in all_turns])
    _write_jsonl(run_dir / "evaluations.jsonl", [item.to_dict() for item in evaluations])
    _write_jsonl(run_dir / "failures.jsonl", [item.to_dict() for item in evaluations if item.failure_type])
    _write_csv(run_dir / "teacher_notes_audit.csv", teacher_note_rows)
    _write_csv(run_dir / "scorecards.csv", scorecard_rows)
    write_lesson_report(run_dir / "lesson_rehearsal_report.md", run_id=run_id, metadata=metadata, summary=summary, call_rows=call_rows)
    write_regression_case_suggestions(run_dir / "regression_cases_to_add.md", evaluations)
    return {"run_dir": str(run_dir), "metadata": metadata, "summary": summary}


def write_lesson_report(
    path: Path,
    *,
    run_id: str,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    call_rows: list[dict[str, Any]],
) -> None:
    short_calls = [row for row in call_rows if not row["completed_5_7_minute_window"]]
    release_blockers = [row for row in call_rows if row["release_blocking_failures"]]
    lines = [
        f"# Sabi 5-7 minute lesson rehearsal report: {run_id}",
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
    if release_blockers:
        for row in release_blockers[:25]:
            lines.append(f"- {row['call_id']}: {row['release_blocking_failures']} release-blocking turn failures")
    else:
        lines.append("- none")

    lines.extend(["", "## Calls Outside 5-7 Minute Window", ""])
    if short_calls:
        for row in short_calls[:25]:
            reason = "early_hangup" if row["early_hangup"] else "duration_model"
            lines.append(f"- {row['call_id']}: {row['duration_seconds']}s ({reason}), phases={row['phases_completed']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Sample Teacher Notes", ""])
    for row in call_rows[:10]:
        note = row.get("teacher_note") or {}
        lines.append(f"- {row['call_id']}: {note.get('narrative', 'no note')}")

    path.write_text("\n".join(lines) + "\n")


def _place_child_with_diagnostic(child, student: dict[str, Any], seed: int) -> dict[str, Any]:
    diagnostic_turns = simulate_diagnostic_call(child, call_index=0, seed=seed, max_turns=18)
    messages: list[dict[str, str]] = []
    for turn in diagnostic_turns:
        messages.append({"role": "assistant", "content": turn.prompt})
        messages.append({"role": "user", "content": turn.stt_text})
    stats = analyze_session(student, messages)
    state = dict(stats.learning_state or student["learning_state"])
    if int(state.get("current_module") or 0) <= 0:
        state["current_module"] = 1
        state["current_week"] = 1
        state["current_lesson"] = 1
        state["diagnostic_status"] = "done"
        state["phase"] = "first_mini_lesson"
    state["course"] = "numeracy"
    return state


def _build_lesson_call(
    *,
    child: FakeChildProfile,
    child_id: str,
    child_name: str,
    call_index: int,
    state: dict[str, Any],
    lesson: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    module = int((lesson or {}).get("module") or state.get("current_module") or 1)
    bank = LESSON_BANK.get(module) or LESSON_BANK[1]
    early_hangup = rng.random() < 0.06
    turns: list[SimulatedTurn] = []
    messages: list[dict[str, str]] = []
    phases_completed: list[str] = []

    recall = bank[(call_index - 1) % len(bank)]
    messages.append(
        {
            "role": "assistant",
            "content": (
                f"Welcome back, {child_name}. Before today's lesson, let's warm up: "
                f"{recall.prompt}"
            ),
        }
    )
    turns.append(_answer_turn(child, child_id, call_index, 1, recall, rng))
    messages.append({"role": "user", "content": turns[-1].stt_text})
    phases_completed.append("greeting_recall")

    messages.append(
        {
            "role": "assistant",
            "content": (
                f"Good trying. Today is {lesson.get('title', 'our number lesson')}. "
                f"We will use a market story first, then name the maths."
            ),
        }
    )
    phases_completed.append("teach")

    guided = bank[call_index % len(bank)]
    messages.append(
        {
            "role": "assistant",
            "content": f"Let's do one together. {guided.prompt}",
        }
    )
    turns.append(_answer_turn(child, child_id, call_index, 2, guided, rng))
    messages.append({"role": "user", "content": turns[-1].stt_text})
    phases_completed.append("guided_practice")

    if not early_hangup:
        independent = bank[(call_index + 1) % len(bank)]
        messages.append(
            {
                "role": "assistant",
                "content": f"Now you try this one on your own. {independent.prompt}",
            }
        )
        turns.append(_answer_turn(child, child_id, call_index, 3, independent, rng))
        messages.append({"role": "user", "content": turns[-1].stt_text})
        phases_completed.append("independent_check")

        check = bank[(call_index + 2) % len(bank)]
        messages.append(
            {
                "role": "assistant",
                "content": f"Sharp. Last check before we close: {check.prompt}",
            }
        )
        turns.append(_answer_turn(child, child_id, call_index, 4, check, rng))
        messages.append({"role": "user", "content": turns[-1].stt_text})

        messages.append(
            {
                "role": "assistant",
                "content": (
                    f"Well done today. You practiced {lesson.get('title', 'this skill')}. "
                    f"Next time we will continue with {lesson.get('next_title', 'the next lesson')}."
                ),
            }
        )
        phases_completed.append("wrap")

    duration = _estimated_duration_seconds(phases_completed, rng, early_hangup)
    return {
        "messages": messages,
        "turns": turns,
        "duration_seconds": duration,
        "early_hangup": early_hangup,
        "phases_completed": phases_completed,
    }


def _answer_turn(
    child: FakeChildProfile,
    child_id: str,
    call_index: int,
    turn_index: int,
    question,
    rng: random.Random,
) -> SimulatedTurn:
    answer_text, correct, notes = _lesson_answer_for_child(child, question, rng)
    from .child_simulator import corrupt_transcript

    stt_text, stt_notes = corrupt_transcript(answer_text, child, rng)
    expected = [str(question.expected)]
    from .child_simulator import NUMBER_WORDS

    expected.append(NUMBER_WORDS.get(question.expected, str(question.expected)))
    return SimulatedTurn(
        child_id=child_id,
        call_index=call_index,
        turn_index=turn_index,
        prompt=question.prompt,
        item_id=question.item_id,
        expected_answers=tuple(dict.fromkeys(expected)),
        ground_truth_correct=correct,
        child_answer_text=answer_text,
        stt_text=stt_text,
        noise_level=child.noise_level,
        notes=tuple([*notes, *stt_notes, "lesson_rehearsal"]),
    )


def _estimated_duration_seconds(phases_completed: list[str], rng: random.Random, early_hangup: bool) -> int:
    if early_hangup:
        return int(sum(PHASE_SECONDS[phase] for phase in phases_completed) + rng.randint(-10, 20))
    return int(sum(PHASE_SECONDS.values()) + rng.randint(-20, 30))


def _teacher_note_audit_row(call_id: str, child_id: str, note: dict[str, Any], rehearsal: dict[str, Any], stats) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "child_id": child_id,
        "note_generated": bool(note),
        "source": note.get("source") if note else None,
        "engagement": note.get("engagement") if note else None,
        "strengths_count": len(note.get("strengths") or []) if note else 0,
        "struggles_count": len(note.get("struggles") or []) if note else 0,
        "has_recommended_focus": bool(note.get("recommended_focus")) if note else False,
        "has_narrative": bool(note.get("narrative")) if note else False,
        "duration_seconds": rehearsal["duration_seconds"],
        "user_turns": sum(1 for message in rehearsal["messages"] if message.get("role") == "user"),
        "correct_count": stats.correct_count,
        "wrong_count": stats.wrong_count,
    }


def _scorecard_row(call_id: str, child_id: str, scorecard: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "child_id": child_id,
        "course": scorecard.get("course"),
        "module": scorecard.get("module"),
        "lesson_global": scorecard.get("lesson_global"),
        "questions_correct": scorecard.get("questions_correct"),
        "questions_total": scorecard.get("questions_total"),
        "accuracy": scorecard.get("accuracy"),
        "mastery_signal": scorecard.get("mastery_signal"),
        "mastery_label": scorecard.get("mastery_label"),
        "lesson_passed": scorecard.get("lesson_passed"),
        "should_advance": scorecard.get("should_advance"),
    }


def _summarize_calls(call_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(call_rows)
    completed = [row for row in call_rows if row["completed_5_7_minute_window"]]
    early = [row for row in call_rows if row["early_hangup"]]
    notes = [row for row in call_rows if row.get("teacher_note")]
    scorecards = [row for row in call_rows if row.get("scorecard")]
    release_blockers = [row for row in call_rows if row["release_blocking_failures"]]
    return {
        "lesson_rehearsal_calls": total,
        "completed_5_7_minute_calls": len(completed),
        "completed_5_7_minute_rate": round(len(completed) / total, 4) if total else 0.0,
        "early_hangups": len(early),
        "teacher_notes_generated": len(notes),
        "scorecards_generated": len(scorecards),
        "calls_with_release_blockers": len(release_blockers),
    }


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic 5-7 minute Sabi lesson rehearsal calls.")
    parser.add_argument("--children", type=int, default=100)
    parser.add_argument("--calls-per-child", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--output-root", type=Path, default=Path("../outputs/fake-child-harness/lesson-runs"))
    args = parser.parse_args()

    # Attach fake-child profile to transient learning-state dicts inside the run.
    result = run_lesson_rehearsal(
        children=args.children,
        calls_per_child=args.calls_per_child,
        seed=args.seed,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
