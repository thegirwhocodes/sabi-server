#!/usr/bin/env python3
"""Offline regression checks for the local recent-call dashboard."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile


SCRIPT = Path(__file__).parent / "scripts" / "sync_sabi_recent_calls.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("sabi_recent_call_sync", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def check(name: str, condition: bool, detail: object = "") -> bool:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="sabi-recent-dashboard-") as temp:
        destination = Path(temp)
        metadata = destination / ".metadata"
        call_dir = destination / "Calls" / "2026-08 August" / "2026-08-06" / "Naomi_numeracy"
        metadata.mkdir()
        call_dir.mkdir(parents=True)
        record = {
            "call_uuid": "recent-call-123",
            "created_at": 1786039014,
            "duration_seconds": 216.4,
            "end_reason": "caller_hangup",
            "turns": [
                {
                    "turn_index": 3,
                    "user": {"stt_transcript": "forty", "stt_provider": "gemini"},
                    "assistant": {"text": "Yes, forty naira."},
                    "timings": {"stt_seconds": 3.21},
                    "flags": ["numeric_stt"],
                }
            ],
        }
        (metadata / "call_recent-call-123.json").write_text(json.dumps(record), encoding="utf-8")
        (call_dir / "call.json").write_text(json.dumps(record), encoding="utf-8")
        (call_dir / "user_turn_03.wav").write_bytes(b"RIFF-turn")
        (call_dir / "full-caller-only.wav").write_bytes(b"RIFF-full")
        (call_dir / "what-sabi-heard.txt").write_text("Sabi heard: forty", encoding="utf-8")

        visible, total = module._write_dashboard(destination, 20)
        html = (destination / "index.html").read_text(encoding="utf-8")
        readme = (destination / "README.txt").read_text(encoding="utf-8")
        ok &= check("counts_recent_calls", visible == 1 and total == 1, (visible, total))
        ok &= check("renders_inline_audio", html.count("<audio controls") == 2)
        ok &= check("renders_actual_stt_and_reply", "forty" in html and "Yes, forty naira." in html)
        ok &= check("labels_model_output_not_ground_truth", "not ground truth" in html.lower())
        ok &= check("browser_audio_uses_relative_paths", "file://" not in html and "user_turn_03.wav" in html)
        ok &= check("creates_latest_call_shortcut", (destination / "Latest Call").resolve() == call_dir.resolve())
        ok &= check("documents_no_onedrive_sync", "does not sync to OneDrive" in readme)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
