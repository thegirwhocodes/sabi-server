#!/usr/bin/env python3
"""Mirror Sabi caller audio into a OneDrive folder arranged for STT testing.

The server remains the source of raw evidence. This creates an incremental,
human-friendly OneDrive library containing:

* every caller-only full-call recording (`*_rx-network.wav`);
* every saved per-turn caller clip, grouped into dated learner folders;
* the call sidecar and a plain-text "what Sabi heard" transcript.

No credentials are stored: rsync and the protected learner-roster lookup use
the Mac's existing SSH key. Learner names come only from stored profiles, never
from a speech-to-text transcript.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


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


def _received_datetime(record: dict) -> datetime | None:
    try:
        stamp = float(record.get("created_at") or 0)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc)


def _safe_path_component(value: object, fallback: str) -> str:
    text = " ".join(str(value or "").strip().split())
    text = re.sub(r"[^\w .'-]+", "-", text, flags=re.UNICODE).strip(" .-_")
    return text[:48] or fallback


def _fetch_learner_names(server: str) -> dict[str, str]:
    """Read authoritative stored names through Sabi's protected local API.

    The API key is read *inside* the running server container and never crosses
    the SSH command line. The response is consumed in memory and is not cached.
    """
    remote_script = """\
import urllib.request
key = open('/run/secrets/SABI_API_KEY', encoding='utf-8').read().strip()
request = urllib.request.Request(
    'http://127.0.0.1:8000/admin/learners?limit=100',
    headers={'X-API-Key': key},
)
with urllib.request.urlopen(request, timeout=20) as response:
    print(response.read().decode('utf-8'))
"""
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            server,
            "docker exec -i sabi-server python -",
        ],
        input=remote_script,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    if payload.get("status") != "ok":
        raise RuntimeError("Sabi learner roster was unavailable")
    total = int(payload.get("total") or 0)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if total > len(items):
        raise RuntimeError(
            f"Sabi learner roster was truncated ({len(items)} of {total}); refusing an unsafe rename"
        )
    names: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        student_id = str(item.get("id") or "").strip()
        # Use the raw stored name. `display_name` may be a phone-based admin
        # fallback and must not be promoted to a learner identity.
        learner_name = _safe_path_component(item.get("name"), "")
        if learner_name.lower() in {"unnamed learner", "unknown", "none", "null"}:
            learner_name = ""
        if student_id and learner_name:
            names[student_id] = learner_name
    return names


def _learner_name(record: dict, learner_names: dict[str, str]) -> str:
    """Resolve by stable student_id only, keeping shared-phone learners apart."""
    student_id = str(record.get("student_id") or "").strip()
    return learner_names.get(student_id, "") or "Unknown Learner"


def _call_subject(record: dict) -> str:
    """Derive a broad subject from structured call evidence, never STT text."""
    explicit_subjects: set[str] = set()
    summary = record.get("learning_summary")
    if isinstance(summary, dict) and summary.get("course") in {"literacy", "numeracy"}:
        explicit_subjects.add(str(summary["course"]))

    turns = record.get("turns") if isinstance(record.get("turns"), list) else []
    has_literacy_stt = False
    has_numeric_stt = False
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        for state_key in ("learning_state_before", "learning_state_after"):
            state = turn.get(state_key)
            if isinstance(state, dict) and state.get("course") in {"literacy", "numeracy"}:
                explicit_subjects.add(str(state["course"]))
        flags = set(turn.get("flags") or [])
        if "literacy_stt" in flags:
            has_literacy_stt = True
        if "numeric_stt" in flags or "dtmf_input" in flags:
            has_numeric_stt = True

    subjects = set(explicit_subjects)
    # Numeric input is strong evidence that a numeracy segment occurred. By
    # contrast, `literacy_stt` historically also marked ordinary free-form
    # speech during numeracy calls, so use it only when no course was saved.
    if has_numeric_stt:
        subjects.add("numeracy")
    if has_literacy_stt and not explicit_subjects:
        subjects.add("literacy")

    if subjects == {"literacy", "numeracy"}:
        return "literacy-numeracy"
    if subjects:
        return next(iter(subjects))
    return "lesson" if turns else "unknown"


def _date_directory(destination: Path, record: dict) -> Path:
    received = _received_datetime(record)
    if received:
        month = received.strftime("%Y-%m %B")
        day = received.strftime("%Y-%m-%d")
    else:
        month = "Unknown month"
        day = "Unknown date"
    return destination / "Calls" / month / day


def _call_folder_base(record: dict, learner_names: dict[str, str]) -> str:
    return f"{_learner_name(record, learner_names)}_{_call_subject(record)}"


def _read_call_uuid(call_dir: Path) -> str:
    try:
        payload = json.loads((call_dir / "call.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("call_uuid") or "").strip()


def _existing_call_dirs(destination: Path) -> dict[str, Path]:
    """Index both normal folders and interrupted-migration staging folders."""
    found: dict[str, Path] = {}
    roots = [destination / "Calls", destination / ".organization-staging"]
    for root in roots:
        if not root.exists():
            continue
        for sidecar in root.rglob("call.json"):
            call_dir = sidecar.parent
            call_uuid = _read_call_uuid(call_dir)
            if call_uuid and call_uuid not in found:
                found[call_uuid] = call_dir
    return found


def _planned_call_dirs(
    destination: Path,
    records: list[dict],
    learner_names: dict[str, str],
) -> dict[str, Path]:
    """Assign stable human-friendly suffixes without exposing identifiers."""
    existing = _existing_call_dirs(destination)
    plans: dict[str, Path] = {}
    occupied: set[Path] = set()

    # Preserve a previously assigned human folder when its date/name/subject
    # still match. Preserve only a contiguous base, _2, _3 sequence: if calls
    # change subject/name and leave a lone _3 behind, compact that harmless gap.
    grouped_existing: dict[tuple[Path, str], dict[int, tuple[str, Path]]] = {}
    for record in records:
        call_uuid = str(record.get("call_uuid") or "").strip()
        current = existing.get(call_uuid)
        day_dir = _date_directory(destination, record)
        base = _call_folder_base(record, learner_names)
        if not current or current.parent != day_dir:
            continue
        if current.name == base:
            slot = 1
        else:
            match = re.fullmatch(re.escape(base) + r"_([2-9]|[1-9]\d+)", current.name)
            if not match:
                continue
            slot = int(match.group(1))
        grouped_existing.setdefault((day_dir, base), {})[slot] = (call_uuid, current)

    for slots in grouped_existing.values():
        slot = 1
        while slot in slots:
            call_uuid, current = slots[slot]
            plans[call_uuid] = current
            occupied.add(current)
            slot += 1

    ordered = sorted(
        records,
        key=lambda item: (
            float(item.get("created_at") or 0),
            str(item.get("call_uuid") or ""),
        ),
    )
    record_ids = {str(item.get("call_uuid") or "").strip() for item in records}
    for record in ordered:
        call_uuid = str(record.get("call_uuid") or "").strip()
        if not call_uuid or call_uuid in plans:
            continue
        day_dir = _date_directory(destination, record)
        base = _call_folder_base(record, learner_names)
        suffix = 1
        candidate = day_dir / base
        while candidate in occupied or (
            candidate.exists()
            and _read_call_uuid(candidate) not in {call_uuid, *record_ids}
        ):
            suffix += 1
            candidate = day_dir / f"{base}_{suffix}"
        plans[call_uuid] = candidate
        occupied.add(candidate)
    return plans


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


def _organize(
    destination: Path,
    turns_dir: Path | None = None,
    caller_full_dir: Path | None = None,
    learner_names: dict[str, str] | None = None,
) -> tuple[int, int]:
    metadata_dir = destination / ".metadata"
    turns_dir = turns_dir or destination / ".turns"
    caller_full_dir = caller_full_dir or destination / "Caller-only full calls"
    learner_names = learner_names or {}
    organized = 0
    caller_full_attached = 0

    records: list[tuple[Path, dict]] = []
    for sidecar in sorted(metadata_dir.glob("call_*.json")):
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        call_uuid = str(record.get("call_uuid") or "").strip()
        if not call_uuid:
            continue
        records.append((sidecar, record))

    record_values = [record for _, record in records]
    plans = _planned_call_dirs(destination, record_values, learner_names)
    existing = _existing_call_dirs(destination)
    staging_root = destination / ".organization-staging"

    # Two-phase moves prevent one rename from overwriting another. If a run is
    # interrupted, the next run indexes and recovers these staged folders.
    for _, record in records:
        call_uuid = str(record.get("call_uuid") or "").strip()
        current = existing.get(call_uuid)
        desired = plans[call_uuid]
        if not current or current == desired or current.parent == staging_root:
            continue
        staging_root.mkdir(parents=True, exist_ok=True)
        staged = staging_root / _safe_path_component(call_uuid, "call")
        if staged.exists() and _read_call_uuid(staged) != call_uuid:
            raise RuntimeError(f"Organization staging conflict for call {call_uuid}")
        if not staged.exists():
            shutil.move(str(current), str(staged))
        existing[call_uuid] = staged

    for sidecar, record in records:
        call_uuid = str(record.get("call_uuid") or "").strip()
        call_dir = plans[call_uuid]
        current = existing.get(call_uuid)
        call_dir.parent.mkdir(parents=True, exist_ok=True)
        if current and current != call_dir:
            if call_dir.exists() and _read_call_uuid(call_dir) not in {"", call_uuid}:
                raise RuntimeError(f"Refusing to merge different calls into {call_dir}")
            if call_dir.exists():
                shutil.copytree(current, call_dir, dirs_exist_ok=True)
                shutil.rmtree(current)
            else:
                shutil.move(str(current), str(call_dir))
        else:
            call_dir.mkdir(parents=True, exist_ok=True)

        staged_turns = turns_dir / call_uuid
        if staged_turns.is_dir():
            for clip in staged_turns.glob("user_turn_*.wav"):
                shutil.copy2(clip, call_dir / clip.name)
        shutil.copy2(sidecar, call_dir / "call.json")
        (call_dir / "what-sabi-heard.txt").write_text(_transcript_text(record), encoding="utf-8")

        recording_name = _caller_recording_name(record)
        caller_source = caller_full_dir / recording_name if recording_name else None
        if caller_source and caller_source.exists():
            shutil.copy2(caller_source, call_dir / "full-caller-only.wav")
            caller_full_attached += 1
        organized += 1

    if staging_root.is_dir() and not any(staging_root.iterdir()):
        staging_root.rmdir()

    return organized, caller_full_attached


def sync(server: str, remote_root: str, destination: Path) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    metadata_dir = destination / ".metadata"

    _rsync_filtered(
        f"{server}:{remote_root}/",
        metadata_dir,
        includes=["call_*.json"],
    )
    learner_names = _fetch_learner_names(server)

    (destination / "README.txt").write_text(
        "SABI CALL AUDIO LIBRARY\n"
        "=======================\n\n"
        "Calls/<YYYY-MM Month>/<YYYY-MM-DD>/<Learner Name_subject>/ contains "
        "numbered child-only turn clips, the full caller-only recording when available, "
        "call.json, and what-sabi-heard.txt.\n\n"
        "Names come only from Sabi's stored learner profiles. Calls without a stored name use "
        "Unknown Learner; names are never guessed from speech-to-text output. A stable student "
        "profile ID links calls to the right child even when two learners share one phone.\n\n"
        "The subject label is literacy, numeracy, literacy-numeracy, lesson, or unknown, based "
        "on structured call evidence. Repeated same-name calls use _2, _3, and so on. All other "
        "metadata remains inside call.json instead of the folder name.\n\n"
        "Important: what-sabi-heard.txt is the model output, not a ground-truth transcript.\n"
        "These files may contain children's voices and personal information. Keep the folder private.\n",
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(prefix="sabi-call-turns-") as staging:
        staging_dir = Path(staging)
        turns_dir = staging_dir / "turns"
        caller_full_dir = staging_dir / "full"
        _rsync_filtered(
            f"{server}:{remote_root}/call_turns/",
            turns_dir,
            includes=["*/", "user_turn_*.wav"],
        )
        _rsync_filtered(
            f"{server}:{remote_root}/calls/",
            caller_full_dir,
            includes=["*_rx-network.wav"],
        )
        result = _organize(
            destination,
            turns_dir=turns_dir,
            caller_full_dir=caller_full_dir,
            learner_names=learner_names,
        )

    # Versions before the dated organizer stored a duplicate hidden turn
    # cache inside OneDrive. Remove it only after the fresh server sync and
    # organization both succeed; the raw server audio remains authoritative.
    legacy_turn_cache = destination / ".turns"
    if legacy_turn_cache.is_dir():
        shutil.rmtree(legacy_turn_cache)
    legacy_full_cache = destination / "Caller-only full calls"
    if legacy_full_cache.is_dir():
        shutil.rmtree(legacy_full_cache)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    try:
        calls, full_calls = sync(args.server, args.remote_root.rstrip("/"), args.destination)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Sabi audio sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"Sabi audio sync complete: {calls} call folders; {full_calls} linked caller-only recordings")
    print(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
