#!/usr/bin/env python3
"""Offline regression checks for the OneDrive call-audio organizer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


SCRIPT = Path(__file__).parent / "scripts" / "sync_sabi_call_audio_to_onedrive.py"
spec = importlib.util.spec_from_file_location("sabi_onedrive_sync", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def check(name: str, condition: bool, detail: object = "") -> bool:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="sabi-onedrive-regression-") as temp:
        destination = Path(temp)
        metadata = destination / ".metadata"
        calls = destination / "Calls" / "call-123"
        caller_full = destination / "Caller-only full calls"
        metadata.mkdir()
        calls.mkdir(parents=True)
        caller_full.mkdir()
        (calls / "user_turn_03.wav").write_bytes(b"RIFF-test")
        original_name = "20260805-175641_test_123_rx-network.wav"
        (caller_full / original_name).write_bytes(b"RIFF-full")
        record = {
            "call_uuid": "call-123",
            "created_at": 1785952613,
            "duration_seconds": 417,
            "end_reason": "caller_hangup",
            "stt_providers_used": ["gemini"],
            "hangup_event": {"recording": f"/shared/audio/calls/{original_name[:-15]}.wav"},
            "turns": [
                {
                    "turn_index": 3,
                    "user": {"stt_transcript": "d", "stt_provider": "gemini"},
                    "assistant": {"text": "Yes, the first sound is d."},
                    "timings": {"stt_seconds": 1.75},
                    "flags": ["literacy_stt"],
                }
            ],
        }
        (metadata / "call_call-123.json").write_text(json.dumps(record), encoding="utf-8")
        organized, attached = module._organize(destination)
        transcript = (calls / "what-sabi-heard.txt").read_text(encoding="utf-8")
        ok &= check("organizes_sidecar_by_call_uuid", organized == 1 and (calls / "call.json").exists())
        ok &= check("keeps_numbered_user_clip", (calls / "user_turn_03.wav").exists())
        ok &= check("writes_model_output_warning", "not ground truth" in transcript.lower())
        ok &= check("writes_turn_transcript", "Sabi heard: d" in transcript and "Turn 3" in transcript)
        ok &= check(
            "attaches_caller_only_recording",
            attached == 1 and (calls / "full-caller-only.wav").read_bytes() == b"RIFF-full",
            {"attached": attached},
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
