#!/usr/bin/env python3
"""Report Gemini Live token usage per call, so the lane's cost is measured.

Reads the call sidecars written by ``write_call_review_record`` and totals the
``usage_metadata`` Google returns on each live session. Prices are NOT baked in
— pass the current per-million rates for the model you are running, because
native-audio input and output are billed at different rates and those rates
change.

    python3 scripts/gemini_live_cost_report.py
    python3 scripts/gemini_live_cost_report.py --in-per-m 3.00 --out-per-m 12.00
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

CHANNEL = "asterisk_audiosocket_gemini_live"


def _iter_records(directory: Path):
    for path in sorted(directory.glob("call_*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("channel") == CHANNEL:
            yield record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default=os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"),
        help="directory holding the call sidecars",
    )
    parser.add_argument("--in-per-m", type=float, default=None,
                        help="input price per 1M tokens")
    parser.add_argument("--out-per-m", type=float, default=None,
                        help="output price per 1M tokens")
    args = parser.parse_args()

    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"No such directory: {directory}")
        return 1

    calls = 0
    missing_usage = 0
    total_seconds = 0
    prompt_tokens = 0
    response_tokens = 0
    grand_total = 0

    rows = []
    for record in _iter_records(directory):
        calls += 1
        seconds = int(record.get("duration_seconds") or 0)
        total_seconds += seconds
        usage = record.get("usage_metadata") or {}
        if not usage:
            missing_usage += 1
            continue
        prompt = int(usage.get("promptTokenCount") or 0)
        response = int(usage.get("responseTokenCount") or 0)
        total = int(usage.get("totalTokenCount") or (prompt + response))
        prompt_tokens += prompt
        response_tokens += response
        grand_total += total
        rows.append((record.get("call_uuid", "")[:8], seconds, prompt, response, total))

    print(f"Gemini Live calls: {calls}   with usage recorded: {calls - missing_usage}")
    if missing_usage:
        print(f"  ({missing_usage} call(s) predate usage capture — they will fill in from now on)")
    print(f"Total call time: {total_seconds / 60:.1f} min")
    print(f"Prompt tokens:   {prompt_tokens:,}")
    print(f"Response tokens: {response_tokens:,}")
    print(f"Total tokens:    {grand_total:,}")
    if total_seconds:
        print(f"Tokens / minute: {grand_total / (total_seconds / 60):,.0f}")

    if args.in_per_m is not None and args.out_per_m is not None:
        cost = (prompt_tokens / 1e6) * args.in_per_m + (response_tokens / 1e6) * args.out_per_m
        print(f"\nEstimated spend: ${cost:,.2f}")
        if total_seconds:
            print(f"Per minute:      ${cost / (total_seconds / 60):,.4f}")
            print(f"Per 7-min lesson: ${cost / (total_seconds / 60) * 7:,.3f}")
    else:
        print("\nPass --in-per-m and --out-per-m for a spend estimate.")

    if rows:
        print("\ncall      secs   prompt  response     total")
        for uuid_short, seconds, prompt, response, total in rows[-15:]:
            print(f"{uuid_short:<8} {seconds:>5} {prompt:>8} {response:>9} {total:>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
