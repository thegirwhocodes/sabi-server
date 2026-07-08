from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any

from curriculum_path import advance_learning_state_after_mastery
from learning_state import analyze_session, default_learning_state

from .child_simulator import NUMBER_WORDS, SimulatedTurn, corrupt_transcript, simulate_diagnostic_call
from .cohort import FakeChildProfile, cohort_to_jsonable, generate_cohort
from .evaluator import TurnEvaluation, evaluate_turn, summarize_evaluations
from .report import write_regression_case_suggestions


STT_GROQ_USD_PER_HOUR = 0.04
AFRICAS_TALKING_NGN_PER_MINUTE = 3.0
NGN_PER_USD_ASSUMPTION = 1400.0
LEAN_LLM_TTS_USD_PER_CALL = 0.03
PRODUCTION_LLM_TTS_USD_PER_CALL = 0.18


@dataclass(frozen=True)
class LessonQuestion:
    item_id: str
    module: int
    prompt: str
    expected: int


LESSON_BANK: dict[int, tuple[LessonQuestion, ...]] = {
    1: (
        LessonQuestion("count_after_8", 1, "What number comes after eight?", 9),
        LessonQuestion("count_before_12", 1, "What number comes before twelve?", 11),
        LessonQuestion("count_objects_6", 1, "Count six mangoes with me. How many mangoes?", 6),
    ),
    2: (
        LessonQuestion("addition_2_plus_3", 2, "You have two mangoes and buy three more. How many mangoes altogether?", 5),
        LessonQuestion("addition_4_plus_5", 2, "Four biscuits plus five biscuits is how many biscuits?", 9),
        LessonQuestion("addition_total_spend_15_30", 2, "Groundnuts cost fifteen naira and pure water costs thirty naira. How much do you spend?", 45),
    ),
    3: (
        LessonQuestion("subtraction_7_minus_2", 3, "You have seven biscuits and eat two. How many are left?", 5),
        LessonQuestion("subtraction_change_100_40", 3, "You have one hundred naira and spend forty naira. How much is left?", 60),
        LessonQuestion("subtraction_12_minus_5", 3, "Twelve oranges minus five oranges leaves how many oranges?", 7),
    ),
    4: (
        LessonQuestion("multiplication_3_groups_4", 4, "Three bags have four oranges each. How many oranges altogether?", 12),
        LessonQuestion("multiplication_5_times_2", 4, "Five children each get two pencils. How many pencils?", 10),
        LessonQuestion("multiplication_4_times_5", 4, "Four trays have five eggs each. How many eggs?", 20),
    ),
    5: (
        LessonQuestion("division_6_shared_2", 5, "Share six oranges equally between two children. How many oranges does each child get?", 3),
        LessonQuestion("division_10_shared_5", 5, "Share ten sweets equally among five children. How many sweets each?", 2),
        LessonQuestion("division_20_by_4", 5, "Twenty naira shared equally by four children is how many naira each?", 5),
    ),
    6: (
        LessonQuestion("word_problem_total_50_30", 6, "You buy bread for fifty naira and water for thirty naira. How much do you spend?", 80),
        LessonQuestion("word_problem_change_200_120", 6, "You have two hundred naira and spend one hundred and twenty. How much is left?", 80),
        LessonQuestion("word_problem_groups_3_10", 6, "Three children each pay ten naira for bus fare. How much do they pay altogether?", 30),
    ),
    7: (
        LessonQuestion("grade_bridge_total_120_85", 7, "A notebook is one hundred and twenty naira and a pencil is eighty five naira. What is the total?", 205),
        LessonQuestion("grade_bridge_change_500_275", 7, "You have five hundred naira and spend two hundred and seventy five. How much is left?", 225),
    ),
}


def run_progression_harness(
    *,
    children: int,
    calls_per_child: int,
    seed: int,
    output_root: Path,
    turns_per_lesson_call: int,
    diagnostic_turns: int,
) -> dict[str, Any]:
    run_id = f"progressionfake-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    cohort = generate_cohort(children, seed=seed)
    calls: list[dict[str, Any]] = []
    child_rows: list[dict[str, Any]] = []
    turns: list[SimulatedTurn] = []
    evaluations: list[TurnEvaluation] = []

    for child in cohort:
        student, state = _initial_student(child)
        first_placed_position: tuple[int, int, int] | None = None
        lesson_advances = 0
        child_correct = 0
        child_wrong = 0

        for call_index in range(1, calls_per_child + 1):
            before = dict(state)
            call_turns = _simulate_progression_call(
                child,
                state=state,
                call_index=call_index,
                seed=seed,
                max_diagnostic_turns=diagnostic_turns,
                turns_per_lesson_call=turns_per_lesson_call,
            )
            messages = _messages_from_turns(call_turns)
            stats = analyze_session(student, messages)
            after = dict(stats.learning_state or {})
            advanced = False
            if stats.should_advance:
                after = advance_learning_state_after_mastery(after)
                advanced = True
                lesson_advances += 1
            # This runner is a numeracy TaRL backend probe. Keep course rotation out
            # of the measurement until the literacy progression runner exists.
            after["course"] = "numeracy"

            child_correct += int(stats.correct_count or 0)
            child_wrong += int(stats.wrong_count or 0)
            state = after
            student = {
                "id": child.child_id,
                "name": child.display_name,
                "current_module": int(state.get("current_module") or 0),
                "learning_state": state,
            }
            if first_placed_position is None and int(state.get("current_module") or 0) > 0:
                first_placed_position = _position_tuple(state)

            turn_evaluations = [evaluate_turn(turn) for turn in call_turns]
            turns.extend(call_turns)
            evaluations.extend(turn_evaluations)
            calls.append(
                {
                    "child_id": child.child_id,
                    "call_index": call_index,
                    "before": _state_slice(before),
                    "after": _state_slice(after),
                    "correct_count": stats.correct_count,
                    "wrong_count": stats.wrong_count,
                    "should_advance": stats.should_advance,
                    "advanced": advanced,
                    "summary": stats.summary,
                    "topics_covered": stats.topics_covered,
                    "release_blocking_failures": sum(1 for item in turn_evaluations if item.severity == "release_blocking"),
                }
            )

        final_position = _position_tuple(state)
        placed_position = first_placed_position or final_position
        child_rows.append(
            {
                "child_id": child.child_id,
                "display_name": child.display_name,
                "hidden_numeracy_level": child.numeracy_level,
                "noise_level": child.noise_level,
                "temperament": child.temperament,
                "call_behavior": child.call_behavior,
                "placed_position": _position_dict(placed_position),
                "final_position": _position_dict(final_position),
                "lesson_advances": lesson_advances,
                "correct_count": child_correct,
                "wrong_count": child_wrong,
                "accuracy": _accuracy(child_correct, child_wrong),
                "possible_over_advance": _possible_over_advance(child, final_position, child_correct, child_wrong),
                "possible_under_advance": _possible_under_advance(child, placed_position, final_position, lesson_advances),
            }
        )

    evaluation_summary = summarize_evaluations(evaluations)
    progression_summary = _summarize_progression(child_rows, evaluations)
    learning_gain_rows = _learning_gain_rows(child_rows)
    stt_confusion_rows = _stt_confusion_rows(turns)
    cost_report = _cost_report(
        children=children,
        calls_per_child=calls_per_child,
        observed_calls=len(calls),
        target_call_seconds=360,
    )
    summary = {**evaluation_summary, **progression_summary}
    metadata = {
        "run_id": run_id,
        "mode": "progression",
        "children": children,
        "calls_per_child": calls_per_child,
        "seed": seed,
        "turns_per_lesson_call": turns_per_lesson_call,
        "diagnostic_turns": diagnostic_turns,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Numeracy-only TaRL backend progression probe; does not yet run full LLM/TTS phone lessons.",
    }

    _write_json(run_dir / "run_summary.json", {"metadata": metadata, "summary": summary})
    _write_json(run_dir / "cost_report.json", cost_report)
    _write_json(run_dir / "cohort.json", cohort_to_jsonable(cohort))
    _write_jsonl(run_dir / "child_progression.jsonl", child_rows)
    _write_csv(run_dir / "learning_gain.csv", learning_gain_rows)
    _write_csv(run_dir / "stt_confusion_matrix.csv", stt_confusion_rows)
    _write_jsonl(run_dir / "calls.jsonl", calls)
    _write_jsonl(run_dir / "turns.jsonl", [turn.to_dict() for turn in turns])
    _write_jsonl(run_dir / "evaluations.jsonl", [item.to_dict() for item in evaluations])
    _write_jsonl(run_dir / "failures.jsonl", [item.to_dict() for item in evaluations if item.failure_type])
    write_progression_report(run_dir / "progression_report.md", run_id=run_id, metadata=metadata, summary=summary, child_rows=child_rows)
    write_regression_case_suggestions(run_dir / "regression_cases_to_add.md", evaluations)
    return {"run_dir": str(run_dir), "metadata": metadata, "summary": summary}


def write_progression_report(
    path: Path,
    *,
    run_id: str,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    child_rows: list[dict[str, Any]],
) -> None:
    over = [row for row in child_rows if row["possible_over_advance"]]
    under = [row for row in child_rows if row["possible_under_advance"]]
    top_advancers = sorted(child_rows, key=lambda row: row["lesson_advances"], reverse=True)[:10]

    lines = [
        f"# Sabi fake-child TaRL progression report: {run_id}",
        "",
        "## Run",
        "",
        f"- Children: {metadata['children']}",
        f"- Calls per child: {metadata['calls_per_child']}",
        f"- Lesson turns per call: {metadata['turns_per_lesson_call']}",
        f"- Diagnostic turns: {metadata['diagnostic_turns']}",
        f"- Scope: {metadata['note']}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Possible Over-Advancement", ""])
    if over:
        for row in over[:25]:
            lines.append(
                f"- {row['child_id']} hidden_level={row['hidden_numeracy_level']} "
                f"final_module={row['final_position']['module']} accuracy={row['accuracy']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Possible Under-Advancement", ""])
    if under:
        for row in under[:25]:
            lines.append(
                f"- {row['child_id']} hidden_level={row['hidden_numeracy_level']} "
                f"placed_module={row['placed_position']['module']} final_module={row['final_position']['module']} "
                f"lesson_advances={row['lesson_advances']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Top Advancers", ""])
    for row in top_advancers:
        lines.append(
            f"- {row['child_id']}: {row['lesson_advances']} lesson advances, "
            f"final M{row['final_position']['module']} W{row['final_position']['week']} L{row['final_position']['lesson']}, "
            f"accuracy={row['accuracy']}"
        )
    path.write_text("\n".join(lines) + "\n")


def _initial_student(child: FakeChildProfile) -> tuple[dict[str, Any], dict[str, Any]]:
    state = default_learning_state()
    state["onboarding_status"] = "complete"
    state["phase"] = "diagnostic"
    state["course"] = "numeracy"
    student = {
        "id": child.child_id,
        "name": child.display_name,
        "current_module": 0,
        "learning_state": state,
    }
    return student, state


def _simulate_progression_call(
    child: FakeChildProfile,
    *,
    state: dict[str, Any],
    call_index: int,
    seed: int,
    max_diagnostic_turns: int,
    turns_per_lesson_call: int,
) -> list[SimulatedTurn]:
    module = int(state.get("current_module") or 0)
    diagnostic_status = str(state.get("diagnostic_status") or "not_started")
    if module == 0 or diagnostic_status != "done":
        return simulate_diagnostic_call(
            child,
            call_index=call_index,
            seed=seed,
            max_turns=max_diagnostic_turns,
        )

    rng = random.Random(f"{seed}:{child.child_id}:{call_index}:progression")
    bank = LESSON_BANK.get(module) or LESSON_BANK[6]
    turns: list[SimulatedTurn] = []
    for turn_index in range(1, turns_per_lesson_call + 1):
        question = bank[(call_index + turn_index - 2) % len(bank)]
        answer_text, correct, notes = _lesson_answer_for_child(child, question, rng)
        stt_text, stt_notes = corrupt_transcript(answer_text, child, rng)
        turns.append(
            SimulatedTurn(
                child_id=child.child_id,
                call_index=call_index,
                turn_index=turn_index,
                prompt=question.prompt,
                item_id=question.item_id,
                expected_answers=_expected_answers(question.expected),
                ground_truth_correct=correct,
                child_answer_text=answer_text,
                stt_text=stt_text,
                noise_level=child.noise_level,
                notes=tuple([*notes, *stt_notes]),
            )
        )
    return turns


def _lesson_answer_for_child(
    child: FakeChildProfile,
    question: LessonQuestion,
    rng: random.Random,
) -> tuple[str, bool, list[str]]:
    module = max(1, int(question.module))
    if child.numeracy_level >= module:
        correct_prob = 0.86
    elif child.numeracy_level + 1 == module:
        correct_prob = 0.52
    else:
        correct_prob = 0.18

    if child.temperament == "guesses":
        correct_prob -= 0.12
    if child.temperament == "eager":
        correct_prob += 0.04
    if child.noise_level in {"lagos_market", "brutal_market"}:
        correct_prob -= 0.04
    correct_prob = max(0.02, min(0.96, correct_prob))

    if rng.random() < correct_prob:
        return _number_to_text(question.expected, rng), True, []
    wrong = _nearby_wrong_number(question.expected, rng)
    return _number_to_text(wrong, rng), False, [f"lesson_ability_miss:module_{module}"]


def _messages_from_turns(turns: list[SimulatedTurn]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "assistant", "content": turn.prompt})
        messages.append({"role": "user", "content": turn.stt_text})
    return messages


def _expected_answers(value: int) -> tuple[str, ...]:
    values = [str(value), NUMBER_WORDS.get(value, str(value))]
    return tuple(dict.fromkeys(values))


def _number_to_text(value: int, rng: random.Random) -> str:
    if value in NUMBER_WORDS and rng.random() < 0.82:
        return NUMBER_WORDS[value]
    return str(value)


def _nearby_wrong_number(expected: int, rng: random.Random) -> int:
    if expected <= 10:
        options = [n for n in (expected - 2, expected - 1, expected + 1, expected + 2) if n >= 0]
    else:
        options = [max(0, expected - 10), max(0, expected - 1), expected + 1, expected + 10]
    return rng.choice(options)


def _state_slice(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "course": state.get("course"),
        "phase": state.get("phase"),
        "diagnostic_status": state.get("diagnostic_status"),
        "module": int(state.get("current_module") or 0),
        "week": int(state.get("current_week") or 1),
        "lesson": int(state.get("current_lesson") or 1),
        "active_skill": state.get("active_skill"),
        "correct_streak": int(state.get("correct_streak") or 0),
        "wrong_streak": int(state.get("wrong_streak") or 0),
        "scaffold_depth": int(state.get("scaffold_depth") or 0),
    }


def _position_tuple(state: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(state.get("current_module") or 0),
        int(state.get("current_week") or 1),
        int(state.get("current_lesson") or 1),
    )


def _position_dict(position: tuple[int, int, int]) -> dict[str, int]:
    return {"module": position[0], "week": position[1], "lesson": position[2]}


def _accuracy(correct: int, wrong: int) -> float | None:
    total = int(correct or 0) + int(wrong or 0)
    if total <= 0:
        return None
    return round(correct / total, 3)


def _possible_over_advance(
    child: FakeChildProfile,
    final_position: tuple[int, int, int],
    correct: int,
    wrong: int,
) -> bool:
    final_module = final_position[0]
    accuracy = _accuracy(correct, wrong)
    return final_module > max(1, child.numeracy_level + 1) and (accuracy is None or accuracy < 0.70)


def _possible_under_advance(
    child: FakeChildProfile,
    placed_position: tuple[int, int, int],
    final_position: tuple[int, int, int],
    lesson_advances: int,
) -> bool:
    placed_module = placed_position[0]
    final_module = final_position[0]
    return child.numeracy_level >= max(1, placed_module + 2) and final_module <= placed_module and lesson_advances == 0


def _summarize_progression(child_rows: list[dict[str, Any]], evaluations: list[TurnEvaluation]) -> dict[str, Any]:
    moved = [row for row in child_rows if row["lesson_advances"] > 0]
    over = [row for row in child_rows if row["possible_over_advance"]]
    under = [row for row in child_rows if row["possible_under_advance"]]
    final_modules = [row["final_position"]["module"] for row in child_rows]
    release_blockers = [item for item in evaluations if item.severity == "release_blocking"]
    return {
        "children": len(child_rows),
        "children_with_lesson_advances": len(moved),
        "mean_lesson_advances": round(sum(row["lesson_advances"] for row in child_rows) / max(1, len(child_rows)), 3),
        "possible_over_advance_children": len(over),
        "possible_under_advance_children": len(under),
        "final_module_min": min(final_modules) if final_modules else 0,
        "final_module_max": max(final_modules) if final_modules else 0,
        "release_blocking_children": len({item.child_id for item in release_blockers}),
    }


def _learning_gain_rows(child_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in child_rows:
        placed = row["placed_position"]
        final = row["final_position"]
        baseline_ordinal = _position_ordinal(placed)
        final_ordinal = _position_ordinal(final)
        lesson_gain = max(0, final_ordinal - baseline_ordinal)
        rows.append(
            {
                "child_id": row["child_id"],
                "hidden_numeracy_level": row["hidden_numeracy_level"],
                "noise_level": row["noise_level"],
                "temperament": row["temperament"],
                "call_behavior": row["call_behavior"],
                "placed_module": placed["module"],
                "placed_week": placed["week"],
                "placed_lesson": placed["lesson"],
                "final_module": final["module"],
                "final_week": final["week"],
                "final_lesson": final["lesson"],
                "lesson_advances": row["lesson_advances"],
                "lesson_gain_from_placement": lesson_gain,
                "accuracy": row["accuracy"],
                "correct_count": row["correct_count"],
                "wrong_count": row["wrong_count"],
                "gain_signal": "advanced" if row["lesson_advances"] > 0 else "no_advance",
                "possible_over_advance": row["possible_over_advance"],
                "possible_under_advance": row["possible_under_advance"],
            }
        )
    return rows


def _stt_confusion_rows(turns: list[SimulatedTurn]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str, str, str]] = Counter()
    for turn in turns:
        intended = " ".join(str(turn.child_answer_text or "").lower().split())
        heard = " ".join(str(turn.stt_text or "").lower().split())
        if intended == heard:
            continue
        counts[(intended, heard, turn.noise_level, turn.item_id)] += 1
    rows: list[dict[str, Any]] = []
    for (intended, heard, noise_level, item_id), count in counts.most_common():
        rows.append(
            {
                "intended": intended,
                "stt_text": heard,
                "noise_level": noise_level,
                "item_id": item_id,
                "count": count,
            }
        )
    return rows


def _cost_report(
    *,
    children: int,
    calls_per_child: int,
    observed_calls: int,
    target_call_seconds: int,
) -> dict[str, Any]:
    minutes = observed_calls * target_call_seconds / 60.0
    groq_stt_usd = (minutes / 60.0) * STT_GROQ_USD_PER_HOUR
    sip_ngn = minutes * AFRICAS_TALKING_NGN_PER_MINUTE
    sip_usd = sip_ngn / NGN_PER_USD_ASSUMPTION
    lean_llm_tts_usd = observed_calls * LEAN_LLM_TTS_USD_PER_CALL
    production_llm_tts_usd = observed_calls * PRODUCTION_LLM_TTS_USD_PER_CALL
    return {
        "mode": "synthetic_progression_fixture",
        "children": children,
        "calls_per_child": calls_per_child,
        "observed_calls": observed_calls,
        "target_call_seconds": target_call_seconds,
        "target_call_minutes": round(minutes, 2),
        "marginal_fixture_run_usd": 0.0,
        "estimated_real_stt_usd_groq_whisper": round(groq_stt_usd, 4),
        "estimated_real_sip_ngn_africas_talking": round(sip_ngn, 2),
        "estimated_real_sip_usd_at_1400_ngn_per_usd": round(sip_usd, 4),
        "estimated_lean_llm_tts_usd": round(lean_llm_tts_usd, 2),
        "estimated_production_llm_tts_usd": round(production_llm_tts_usd, 2),
        "estimated_total_lean_usd": round(groq_stt_usd + sip_usd + lean_llm_tts_usd, 2),
        "estimated_total_production_like_usd": round(groq_stt_usd + sip_usd + production_llm_tts_usd, 2),
        "assumptions": {
            "groq_stt_usd_per_hour": STT_GROQ_USD_PER_HOUR,
            "africas_talking_sip_ngn_per_minute": AFRICAS_TALKING_NGN_PER_MINUTE,
            "ngn_per_usd": NGN_PER_USD_ASSUMPTION,
            "lean_llm_tts_usd_per_call": LEAN_LLM_TTS_USD_PER_CALL,
            "production_llm_tts_usd_per_call": PRODUCTION_LLM_TTS_USD_PER_CALL,
            "note": "Fixture mode spent no API/telephony money. This report estimates the same call count if replayed through real STT plus SIP and paid LLM/TTS.",
        },
    }


def _position_ordinal(position: dict[str, int]) -> int:
    return int(position.get("module") or 0) * 1000 + int(position.get("week") or 0) * 10 + int(position.get("lesson") or 0)


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
    parser = argparse.ArgumentParser(description="Run a stateful numeracy progression probe over fake Sabi learners.")
    parser.add_argument("--children", type=int, default=100)
    parser.add_argument("--calls-per-child", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--turns-per-lesson-call", type=int, default=4)
    parser.add_argument("--diagnostic-turns", type=int, default=18)
    parser.add_argument("--output-root", type=Path, default=Path("../outputs/fake-child-harness/progression-runs"))
    args = parser.parse_args()

    result = run_progression_harness(
        children=args.children,
        calls_per_child=args.calls_per_child,
        seed=args.seed,
        output_root=args.output_root,
        turns_per_lesson_call=args.turns_per_lesson_call,
        diagnostic_turns=args.diagnostic_turns,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
