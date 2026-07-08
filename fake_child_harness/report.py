from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .cohort import FakeChildProfile
from .evaluator import TurnEvaluation


def write_markdown_report(
    path: Path,
    *,
    run_id: str,
    cohort: list[FakeChildProfile],
    summary: dict[str, Any],
    evaluations: list[TurnEvaluation],
) -> None:
    failure_counts = Counter(item.failure_type for item in evaluations if item.failure_type)
    noise_counts = Counter(child.noise_level for child in cohort)
    release_blockers = [item for item in evaluations if item.severity == "release_blocking"]

    lines = [
        f"# Sabi fake-child harness report: {run_id}",
        "",
        "## Cohort",
        "",
        f"- Children: {len(cohort)}",
        f"- Noise levels: {_format_counter(noise_counts)}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Failure Types",
            "",
        ]
    )
    if failure_counts:
        for key, value in sorted(failure_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## First Release Blockers",
            "",
        ]
    )
    for item in release_blockers[:25]:
        lines.append(
            "- "
            f"{item.child_id} call {item.call_index} turn {item.turn_index} "
            f"{item.item_id}: {item.failure_type}; "
            f"child='{item.child_answer_text}' stt='{item.stt_text}'"
        )
    if not release_blockers:
        lines.append("- none")

    path.write_text("\n".join(lines) + "\n")


def write_regression_case_suggestions(path: Path, evaluations: list[TurnEvaluation]) -> None:
    failures = [item for item in evaluations if item.failure_type]
    lines = [
        "# Regression Cases To Add",
        "",
        "Generated from the fake-child harness. Release-blocking rows should become code regressions before the fix is considered done.",
        "",
    ]
    if not failures:
        lines.append("No failures in this run.")
        path.write_text("\n".join(lines) + "\n")
        return

    for item in failures:
        lines.extend(
            [
                f"## {item.child_id} call {item.call_index} turn {item.turn_index}: {item.failure_type}",
                "",
                f"- Severity: {item.severity}",
                f"- Item: {item.item_id}",
                f"- Prompt: {item.assistant_prompt}",
                f"- Expected answers: {', '.join(item.expected_answers)}",
                f"- Child intended answer: `{item.child_answer_text}`",
                f"- STT transcript: `{item.stt_text}`",
                f"- Noise: {item.noise_level}",
                f"- Notes: {', '.join(item.notes) if item.notes else 'none'}",
                "",
            ]
        )

    path.write_text("\n".join(lines) + "\n")


def _format_counter(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))
