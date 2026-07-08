from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .child_simulator import simulate_diagnostic_call
from .cohort import cohort_to_jsonable, generate_cohort
from .evaluator import evaluate_turn, summarize_evaluations
from .report import write_markdown_report, write_regression_case_suggestions


def run_text_harness(
    *,
    children: int,
    calls_per_child: int,
    seed: int,
    output_root: Path,
    max_turns: int,
) -> dict[str, Any]:
    run_id = f"fakepilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    cohort = generate_cohort(children, seed=seed)
    turns = []
    evaluations = []

    for child in cohort:
        for call_index in range(1, calls_per_child + 1):
            for turn in simulate_diagnostic_call(child, call_index=call_index, seed=seed, max_turns=max_turns):
                turns.append(turn)
                evaluations.append(evaluate_turn(turn))

    summary = summarize_evaluations(evaluations)
    metadata = {
        "run_id": run_id,
        "mode": "text",
        "children": children,
        "calls_per_child": calls_per_child,
        "seed": seed,
        "max_turns": max_turns,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _write_json(run_dir / "run_summary.json", {"metadata": metadata, "summary": summary})
    _write_json(run_dir / "cohort.json", cohort_to_jsonable(cohort))
    _write_jsonl(run_dir / "turns.jsonl", [turn.to_dict() for turn in turns])
    _write_jsonl(run_dir / "evaluations.jsonl", [item.to_dict() for item in evaluations])
    _write_jsonl(
        run_dir / "failures.jsonl",
        [item.to_dict() for item in evaluations if item.failure_type],
    )
    write_markdown_report(
        run_dir / "cohort_report.md",
        run_id=run_id,
        cohort=cohort,
        summary=summary,
        evaluations=evaluations,
    )
    write_regression_case_suggestions(run_dir / "regression_cases_to_add.md", evaluations)
    return {"run_dir": str(run_dir), "metadata": metadata, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Sabi fake-child harness.")
    parser.add_argument("--children", type=int, default=100)
    parser.add_argument("--calls-per-child", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--max-turns", type=int, default=7)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("../outputs/fake-child-harness/runs"),
    )
    args = parser.parse_args()

    result = run_text_harness(
        children=args.children,
        calls_per_child=args.calls_per_child,
        seed=args.seed,
        output_root=args.output_root,
        max_turns=args.max_turns,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


if __name__ == "__main__":
    main()
