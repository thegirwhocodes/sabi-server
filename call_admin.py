"""Call-quality review helpers for Sabi phone sessions."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


CALL_PREFIX = "call_"
CALL_JSON_GLOB = f"{CALL_PREFIX}*.json"
SAFE_CALL_UUID_RE = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
MIN_LESSON_SECONDS = int(os.getenv("SABI_MIN_LESSON_SECONDS", "300"))


def shared_audio_dir() -> Path:
    return Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"))


def call_sidecar_path(call_uuid: str, directory: Path | None = None) -> Path | None:
    if not SAFE_CALL_UUID_RE.fullmatch(call_uuid or ""):
        return None
    root = directory or shared_audio_dir()
    return root / f"{CALL_PREFIX}{call_uuid}.json"


def write_call_review_record(
    *,
    call_uuid: str,
    call_id: str,
    phone_number: str,
    mode: str,
    attempt: str,
    end_reason: str,
    duration_seconds: int,
    user_turns: int,
    assistant_turns: int,
    student_id: str | None = None,
    channel: str = "asterisk_audiosocket",
    hangup_event: dict[str, Any] | None = None,
    directory: Path | None = None,
) -> dict[str, Any] | None:
    path = call_sidecar_path(call_uuid, directory)
    if not path:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _load_json(path) or {}
    record.update(
        {
            "call_uuid": call_uuid,
            "call_id": call_id,
            "phone_number": phone_number,
            "mode": mode,
            "attempt": str(attempt or ""),
            "student_id": student_id,
            "channel": channel,
            "end_reason": end_reason,
            "duration_seconds": int(duration_seconds or 0),
            "user_turns": int(user_turns or 0),
            "assistant_turns": int(assistant_turns or 0),
            "quality_flags": quality_flags(
                end_reason=end_reason,
                duration_seconds=int(duration_seconds or 0),
                user_turns=int(user_turns or 0),
                assistant_turns=int(assistant_turns or 0),
                hangup_event=hangup_event or record.get("hangup_event") or {},
            ),
            "updated_at": int(time.time()),
        }
    )
    record.setdefault("created_at", int(time.time()))
    if hangup_event:
        record["hangup_event"] = hangup_event
    path.write_text(json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True))
    return record


def merge_call_hangup_event(
    call_uuid: str,
    hangup_event: dict[str, Any],
    directory: Path | None = None,
) -> dict[str, Any] | None:
    path = call_sidecar_path(call_uuid, directory)
    if not path:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _load_json(path) or {
        "call_uuid": call_uuid,
        "created_at": int(time.time()),
    }
    record["hangup_event"] = hangup_event
    record["updated_at"] = int(time.time())
    record["quality_flags"] = quality_flags(
        end_reason=str(record.get("end_reason") or ""),
        duration_seconds=int(record.get("duration_seconds") or 0),
        user_turns=int(record.get("user_turns") or 0),
        assistant_turns=int(record.get("assistant_turns") or 0),
        hangup_event=hangup_event,
    )
    path.write_text(json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True))
    return record


def quality_flags(
    *,
    end_reason: str,
    duration_seconds: int,
    user_turns: int,
    assistant_turns: int,
    hangup_event: dict[str, Any] | None = None,
) -> list[str]:
    flags: list[str] = []
    reason = (end_reason or "").lower()
    hangup_event = hangup_event or {}
    dialstatus = str(hangup_event.get("dialstatus") or "").upper()
    hangup_cause = str(hangup_event.get("hangup_cause") or "")

    if duration_seconds and duration_seconds < 60:
        flags.append("very_short_call")
    elif duration_seconds and duration_seconds < MIN_LESSON_SECONDS:
        flags.append("ended_before_minimum_lesson_window")
    if user_turns <= 0:
        flags.append("no_child_turns")
    if assistant_turns <= 0:
        flags.append("no_sabi_turns")
    if "carrier_or_voicemail" in reason:
        flags.append("carrier_or_voicemail_audio")
    if "no_utterance" in reason or "waiting_for_speech" in reason:
        flags.append("no_usable_speech")
    if "exception:" in reason:
        flags.append("server_exception")
    if "channel_closed" in reason or "hangup" in reason:
        flags.append("channel_closed")
    if dialstatus and dialstatus not in {"ANSWER", "ANSWERED", "NOANSWER"}:
        flags.append(f"dialstatus_{dialstatus.lower()}")
    if hangup_cause and hangup_cause not in {"16", "0", "normal", "NORMAL_CLEARING"}:
        flags.append(f"hangup_cause_{hangup_cause}")
    return sorted(set(flags))


def load_call_record(path: Path) -> dict[str, Any] | None:
    if not path.name.startswith(CALL_PREFIX) or path.suffix != ".json":
        return None
    data = _load_json(path)
    if not isinstance(data, dict):
        return None
    data.setdefault("call_uuid", path.stem.removeprefix(CALL_PREFIX))
    data["sidecar_path"] = str(path)
    data["sidecar_updated_at"] = int(path.stat().st_mtime)
    return data


def list_call_records(
    directory: Path | None = None,
    *,
    limit: int = 25,
    offset: int = 0,
    phone: str = "",
    call_id: str = "",
    flag: str = "",
    q: str = "",
) -> dict[str, Any]:
    root = directory or shared_audio_dir()
    safe_limit = max(1, min(int(limit or 25), 100))
    safe_offset = max(0, int(offset or 0))
    phone_digits = _digits(phone)
    call_filter = str(call_id or "").strip()
    flag_filter = str(flag or "").strip()
    text_filter = str(q or "").strip().lower()

    paths = sorted(
        root.glob(CALL_JSON_GLOB) if root.exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    filtered: list[dict[str, Any]] = []
    for path in paths:
        record = load_call_record(path)
        if not record:
            continue
        if phone_digits and not _phone_digits_match(
            phone_digits,
            _digits(str(record.get("phone_number") or "")),
        ):
            continue
        if call_filter and call_filter not in str(record.get("call_id") or ""):
            continue
        if flag_filter and flag_filter not in set(record.get("quality_flags") or []):
            continue
        if text_filter:
            haystack = " ".join(
                str(record.get(key) or "")
                for key in ("call_uuid", "call_id", "phone_number", "end_reason", "quality_flags")
            ).lower()
            if text_filter not in haystack:
                continue
        filtered.append(record)

    end = safe_offset + safe_limit
    return {
        "status": "ok",
        "count": len(filtered[safe_offset:end]),
        "total": len(filtered),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": filtered[safe_offset:end],
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _phone_digits_match(query_digits: str, record_digits: str) -> bool:
    if not query_digits or not record_digits:
        return False
    if query_digits in record_digits or record_digits in query_digits:
        return True
    return query_digits[-10:] == record_digits[-10:]
