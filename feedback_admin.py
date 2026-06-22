"""Admin helpers for reviewing open-ended Sabi tester feedback notes."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


FEEDBACK_PREFIX = "feedback_"
FEEDBACK_JSON_GLOB = f"{FEEDBACK_PREFIX}*.json"
SAFE_CALL_UUID_RE = re.compile(r"^[A-Za-z0-9_-]{8,96}$")


def shared_audio_dir() -> Path:
    return Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"))


def feedback_sidecar_path(call_uuid: str, directory: Path | None = None) -> Path | None:
    """Return a safe sidecar path for one feedback UUID."""
    if not SAFE_CALL_UUID_RE.fullmatch(call_uuid or ""):
        return None
    root = directory or shared_audio_dir()
    return root / f"{FEEDBACK_PREFIX}{call_uuid}.json"


def feedback_audio_path(call_uuid: str, directory: Path | None = None) -> Path | None:
    sidecar = feedback_sidecar_path(call_uuid, directory)
    return sidecar.with_suffix(".wav") if sidecar else None


def redact_feedback_text(text: str) -> str:
    redacted = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[phone]", text or "")
    redacted = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email]", redacted)
    return redacted[:2000]


def load_feedback_record(path: Path, *, include_raw: bool = False) -> dict[str, Any] | None:
    """Load one sidecar into a safe admin record."""
    if not path.name.startswith(FEEDBACK_PREFIX) or path.suffix != ".json":
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    call_uuid = str(data.get("call_uuid") or path.stem.removeprefix(FEEDBACK_PREFIX))
    audio_path = path.with_suffix(".wav")
    stat = path.stat()
    transcript = str(data.get("transcript") or "")
    redacted_transcript = str(data.get("redacted_transcript") or redact_feedback_text(transcript))

    record = {
        "call_uuid": call_uuid,
        "call_id": data.get("call_id"),
        "phone_number": data.get("phone_number"),
        "student_id": data.get("student_id"),
        "channel": data.get("channel"),
        "participant_type": data.get("participant_type"),
        "duration_seconds": data.get("duration_seconds"),
        "tags": data.get("tags") or [],
        "feedback_mode": data.get("feedback_mode"),
        "mode": data.get("mode"),
        "attempt": data.get("attempt"),
        "created_at": data.get("created_at"),
        "sidecar_path": str(path),
        "recording_path": str(audio_path),
        "has_audio": audio_path.exists(),
        "audio_bytes": audio_path.stat().st_size if audio_path.exists() else 0,
        "sidecar_updated_at": int(stat.st_mtime),
        "redacted_transcript": redacted_transcript,
        "transcript_preview": redacted_transcript[:240],
        "audio_endpoint": f"/admin/feedback/{call_uuid}/audio",
    }
    if include_raw:
        record["transcript"] = transcript
    return record


def list_feedback_records(
    directory: Path | None = None,
    *,
    limit: int = 25,
    offset: int = 0,
    phone: str = "",
    call_id: str = "",
    q: str = "",
) -> dict[str, Any]:
    """List recent feedback sidecars with lightweight filtering."""
    root = directory or shared_audio_dir()
    safe_limit = max(1, min(int(limit or 25), 100))
    safe_offset = max(0, int(offset or 0))
    phone_digits = _digits(phone)
    call_filter = str(call_id or "").strip()
    text_filter = str(q or "").strip().lower()

    paths = sorted(
        root.glob(FEEDBACK_JSON_GLOB) if root.exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    filtered: list[dict[str, Any]] = []
    for path in paths:
        record = load_feedback_record(path, include_raw=False)
        if not record:
            continue
        if phone_digits and not _phone_digits_match(
            phone_digits,
            _digits(str(record.get("phone_number") or "")),
        ):
            continue
        if call_filter and call_filter not in str(record.get("call_id") or ""):
            continue
        if text_filter:
            haystack = " ".join(
                str(record.get(key) or "")
                for key in ("redacted_transcript", "call_uuid", "call_id", "phone_number")
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


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _phone_digits_match(query_digits: str, record_digits: str) -> bool:
    if not query_digits or not record_digits:
        return False
    if query_digits in record_digits or record_digits in query_digits:
        return True
    query_local = query_digits[-10:]
    record_local = record_digits[-10:]
    return bool(query_local and record_local and query_local == record_local)
