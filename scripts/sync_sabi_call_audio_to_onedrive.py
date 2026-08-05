#!/usr/bin/env python3
"""Mirror Sabi caller audio into a OneDrive folder arranged for STT testing.

The server remains the source of raw evidence. This creates an incremental,
human-friendly OneDrive library containing:

* every caller-only full-call recording (`*_rx-network.wav`);
* every saved per-turn caller clip, grouped by call UUID;
* the call sidecar and a plain-text "what Sabi heard" transcript.

No credentials are stored: rsync uses the Mac's existing SSH key.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys


DEFAULT_SERVER = "root@136.243.8.51"
DEFAULT_REMOTE_ROOT = "/var/lib/docker/volumes/sabi-server_shared_audio/_data"
DEFAULT_DESTINATION = Path(
    "/Users/naomiivie/Library/CloudStorage/OneDrive-wesleyan.edu/Sabi Call Audio Library"
)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _rsync_filtered(
    source: str,
    destination: Path,
    *,
    includes: list[str],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    command = ["rsync", "-az", "--prune-empty-dirs"]
    for pattern in includes:
        command.extend(["--include", pattern])
    command.extend(["--exclude", "*", source, f"{destination}/"])
    _run(command)


def _safe_timestamp(value: object) -> str:
    try:
        stamp = float(value or 0)
    except (TypeError, ValueError):
        stamp = 0
    if stamp <= 0:
        return "unknown-date"
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")


def _transcript_text(record: dict) -> str:
    lines = [
        f"Call: {record.get('call_uuid') or 'unknown'}",
        f"Date: {_safe_timestamp(record.get('created_at'))}",
        f"Duration: {record.get('duration_seconds') or 0} seconds",
        f"End reason: {record.get('end_reason') or 'unknown'}",
        f"STT providers: {', '.join(record.get('stt_providers_used') or []) or 'unknown'}",
        "",
        "WHAT SABI HEARD (not ground truth)",
        "==================================",
    ]
    for turn in record.get("turns") or []:
        index = turn.get("turn_index")
        user = turn.get("user") if isinstance(turn.get("user"), dict) else {}
        assistant = turn.get("assistant") if isinstance(turn.get("assistant"), dict) else {}
        timings = turn.get("timings") if isinstance(turn.get("timings"), dict) else {}
        flags = turn.get("flags") if isinstance(turn.get("flags"), list) else []
        lines.extend(
            [
                "",
                f"Turn {index}",
                f"Clip: user_turn_{int(index):02d}.wav" if isinstance(index, int) else "Clip: unknown",
                f"Sabi heard: {user.get('stt_transcript') or '[empty]'}",
                f"STT provider: {user.get('stt_provider') or 'unknown'}",
                f"STT time: {timings.get('stt_seconds') or 0} seconds",
                f"Sabi replied: {assistant.get('text') or '[no saved reply]'}",
                f"Flags: {', '.join(str(flag) for flag in flags) or 'none'}",
            ]
        )
    lines.extend(
        [
            "",
            "Privacy: these recordings may contain children's voices and personal information.",
            "Keep this OneDrive folder private and use it only for authorized Sabi testing.",
            "",
        ]
    )
    return "\n".join(lines)


def _caller_recording_name(record: dict) -> str | None:
    hangup = record.get("hangup_event") if isinstance(record.get("hangup_event"), dict) else {}
    recording = Path(str(hangup.get("recording") or "")).name
    if not recording:
        return None
    if recording.endswith("_rx-network.wav"):
        return recording
    if recording.endswith(".wav"):
        return f"{recording[:-4]}_rx-network.wav"
    return None


def _organize(destination: Path) -> tuple[int, int]:
    metadata_dir = destination / ".metadata"
    calls_dir = destination / "Calls"
    caller_full_dir = destination / "Caller-only full calls"
    organized = 0
    caller_full_attached = 0

    for sidecar in sorted(metadata_dir.glob("call_*.json")):
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        call_uuid = str(record.get("call_uuid") or "").strip()
        if not call_uuid:
            continue
        call_dir = calls_dir / call_uuid
        call_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sidecar, call_dir / "call.json")
        (call_dir / "what-sabi-heard.txt").write_text(_transcript_text(record), encoding="utf-8")

        recording_name = _caller_recording_name(record)
        caller_source = caller_full_dir / recording_name if recording_name else None
        if caller_source and caller_source.exists():
            shutil.copy2(caller_source, call_dir / "full-caller-only.wav")
            caller_full_attached += 1
        organized += 1

    return organized, caller_full_attached


def sync(server: str, remote_root: str, destination: Path) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    metadata_dir = destination / ".metadata"
    calls_dir = destination / "Calls"
    caller_full_dir = destination / "Caller-only full calls"

    _rsync_filtered(
        f"{server}:{remote_root}/",
        metadata_dir,
        includes=["call_*.json"],
    )
    _rsync_filtered(
        f"{server}:{remote_root}/call_turns/",
        calls_dir,
        includes=["*/", "user_turn_*.wav"],
    )
    _rsync_filtered(
        f"{server}:{remote_root}/calls/",
        caller_full_dir,
        includes=["*_rx-network.wav"],
    )

    (destination / "README.txt").write_text(
        "SABI CALL AUDIO LIBRARY\n"
        "=======================\n\n"
        "Calls/<call UUID>/ contains numbered child-only turn clips, the full caller-only "
        "recording when available, call.json, and what-sabi-heard.txt.\n\n"
        "Caller-only full calls/ also contains the original caller-only recordings for legacy "
        "calls that predate per-turn capture.\n\n"
        "Important: what-sabi-heard.txt is the model output, not a ground-truth transcript.\n"
        "These files may contain children's voices and personal information. Keep the folder private.\n",
        encoding="utf-8",
    )
    return _organize(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    try:
        calls, full_calls = sync(args.server, args.remote_root.rstrip("/"), args.destination)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Sabi audio sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"Sabi audio sync complete: {calls} call folders; {full_calls} linked caller-only recordings")
    print(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
