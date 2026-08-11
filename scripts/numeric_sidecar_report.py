#!/usr/bin/env python3
"""Summarise the Gemini Live numeric-sidecar shadow records.

Answers the Phase 1 question from the research plan: on real Nigerian phone
turns, would Groq + local Whisper agreement have graded the number correctly,
and would it have arrived inside the live deadline?

    python3 scripts/numeric_sidecar_report.py                 # every call
    python3 scripts/numeric_sidecar_report.py --call <uuid>   # one call
    python3 scripts/numeric_sidecar_report.py --turns         # per-turn rows

Nothing here changes production; it only reads the JSONL the sidecar wrote.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Run from anywhere: the number parser lives beside the server modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _numbers(text: str) -> list[int]:
    try:
        from numeric_grading import extract_numbers

        return [int(value) for value in extract_numbers(text or "")]
    except Exception:
        return []


def load_records(directory: Path, call_uuid: str = "") -> list[dict]:
    pattern = f"{call_uuid}.jsonl" if call_uuid else "*.jsonl"
    rows: list[dict] = []
    for path in sorted(directory.glob(pattern)):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default=os.getenv("SABI_NUMERIC_SIDECAR_DIR", "")
        or str(Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio")) / "numeric_sidecar"),
    )
    parser.add_argument("--call", default="", help="single call UUID")
    parser.add_argument("--turns", action="store_true", help="print every measured turn")
    args = parser.parse_args()

    directory = Path(args.dir)
    if not directory.exists():
        print(f"No sidecar records at {directory}")
        return 0
    rows = load_records(directory, args.call)
    if not rows:
        print(f"No sidecar records in {directory}")
        return 0

    calls = sorted({row.get("call_uuid", "") for row in rows})
    agreed = [row for row in rows if row.get("numeric_agreement")]
    eligible = [row for row in rows if row.get("decision_eligible")]
    correct_agreements = [row for row in agreed if row.get("agreement_matches_expected")]
    wrong_agreements = [row for row in agreed if not row.get("agreement_matches_expected")]

    gemini_right = [
        row for row in rows if row.get("expected_answer") in _numbers(row.get("gemini_text", ""))
    ]
    rescued = [
        row
        for row in correct_agreements
        if row.get("expected_answer") not in _numbers(row.get("gemini_text", ""))
    ]
    latencies = [
        float(row["decision_latency_seconds"])
        for row in rows
        if row.get("decision_latency_seconds") is not None
    ]

    if args.turns:
        print(f"{'turn':>5}  {'expected':>8}  {'gemini':<24} {'groq':<20} {'local':<20} status")
        for row in rows:
            print(
                f"{row.get('turn_index', -1):>5}  {row.get('expected_answer'):>8}  "
                f"{(row.get('gemini_text') or '')[:23]:<24} "
                f"{(row.get('groq_text') or '')[:19]:<20} "
                f"{(row.get('local_whisper_text') or '')[:19]:<20} "
                f"{row.get('status', '')}"
                + ("  [stale]" if row.get("stale") else "")
            )
        print()

    total = len(rows)
    print(f"Sidecar records : {total} numeric turns across {len(calls)} call(s)")
    print(f"Mode            : {rows[-1].get('mode', 'shadow')} (never applied to grading)")
    print(
        f"Agreement       : {len(agreed)}/{total} "
        f"({len(agreed) / total:.0%}), within deadline {len(eligible)}/{total}"
    )
    print(
        f"  correct       : {len(correct_agreements)}  "
        f"(precision if graded {len(correct_agreements) / len(agreed):.0%})"
        if agreed
        else "  correct       : 0"
    )
    print(f"  WRONG         : {len(wrong_agreements)}  <- these would have mis-graded")
    print(f"Gemini heard it : {len(gemini_right)}/{total} ({len(gemini_right) / total:.0%})")
    print(f"Sidecar rescues : {len(rescued)}  (Gemini's text missed the number, sidecar agreed on it)")
    print(
        "Decision latency: "
        f"p50 {percentile(latencies, 0.5)}s  p95 {percentile(latencies, 0.95)}s  "
        f"max {max(latencies) if latencies else None}s"
    )
    print(f"Stale results   : {sum(1 for row in rows if row.get('stale'))}")
    if wrong_agreements:
        print("\nWrong agreements (inspect before any Phase 3 rollout):")
        for row in wrong_agreements:
            print(
                f"  call={row.get('call_uuid')} turn={row.get('turn_index')} "
                f"expected={row.get('expected_answer')} consensus={row.get('consensus_numeric_value')} "
                f"groq={row.get('groq_text')!r} local={row.get('local_whisper_text')!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
