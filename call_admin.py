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
CALL_TURN_DIR = "call_turns"
SAFE_CALL_UUID_RE = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
SAFE_TURN_ROLE_RE = re.compile(r"^(user|assistant)$")
MIN_LESSON_SECONDS = int(os.getenv("SABI_MIN_LESSON_SECONDS", "300"))


def shared_audio_dir() -> Path:
    return Path(os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"))


def call_sidecar_path(call_uuid: str, directory: Path | None = None) -> Path | None:
    if not SAFE_CALL_UUID_RE.fullmatch(call_uuid or ""):
        return None
    root = directory or shared_audio_dir()
    return root / f"{CALL_PREFIX}{call_uuid}.json"


def call_turn_dir(call_uuid: str, directory: Path | None = None) -> Path | None:
    if not SAFE_CALL_UUID_RE.fullmatch(call_uuid or ""):
        return None
    root = directory or shared_audio_dir()
    return root / CALL_TURN_DIR / call_uuid


def call_turn_audio_path(
    call_uuid: str,
    turn_index: int,
    role: str,
    directory: Path | None = None,
) -> Path | None:
    """Return the safe per-turn audio path for a child or Sabi turn."""
    if int(turn_index) < 0 or not SAFE_TURN_ROLE_RE.fullmatch(role or ""):
        return None
    turn_dir = call_turn_dir(call_uuid, directory)
    if not turn_dir:
        return None
    return turn_dir / f"{role}_turn_{int(turn_index):02d}.wav"


def call_recording_path(
    call_uuid: str,
    kind: str = "mixed",
    directory: Path | None = None,
) -> Path | None:
    """Return a safe full-call recording path from the call sidecar.

    kind:
      - mixed: full MixMonitor call audio
      - rx: network/caller side
      - tx: Sabi side
    """
    if kind not in {"mixed", "rx", "tx"}:
        return None
    sidecar = call_sidecar_path(call_uuid, directory)
    if not sidecar:
        return None
    record = load_call_record(sidecar, include_artifacts=False)
    if not record:
        return None
    recording_path = str(
        record.get("recording_path")
        or (record.get("hangup_event") or {}).get("recording")
        or ""
    )
    base = _path_inside_shared_audio(recording_path, directory)
    if not base:
        return None
    if kind == "mixed":
        return base if base.exists() else None
    suffix = "_rx-network.wav" if kind == "rx" else "_tx-sabi.wav"
    candidate = base.with_name(f"{base.stem}{suffix}")
    return candidate if candidate.exists() else None


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


def append_call_turn_review(
    *,
    call_uuid: str,
    turn_index: int,
    user_audio_path: str,
    user_audio_seconds: float,
    stt_transcript: str,
    stt_confidence: float,
    normalized_transcript: str,
    learning_state_before: dict[str, Any] | None,
    learning_state_after: dict[str, Any] | None,
    assistant_text: str,
    assistant_tts_text: str,
    assistant_audio_path: str,
    assistant_audio_seconds: float,
    timings: dict[str, Any] | None = None,
    flags: list[str] | None = None,
    directory: Path | None = None,
) -> dict[str, Any] | None:
    """Attach one complete tutor turn to the call review sidecar."""
    path = call_sidecar_path(call_uuid, directory)
    if not path:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _load_json(path) or {
        "call_uuid": call_uuid,
        "call_id": call_uuid,
        "created_at": int(time.time()),
    }
    turn_record = _turn_review_record(
        call_uuid=call_uuid,
        turn_index=int(turn_index),
        user_audio_path=user_audio_path,
        user_audio_seconds=user_audio_seconds,
        stt_transcript=stt_transcript,
        stt_confidence=stt_confidence,
        normalized_transcript=normalized_transcript,
        learning_state_before=learning_state_before,
        learning_state_after=learning_state_after,
        assistant_text=assistant_text,
        assistant_tts_text=assistant_tts_text,
        assistant_audio_path=assistant_audio_path,
        assistant_audio_seconds=assistant_audio_seconds,
        timings=timings or {},
        flags=flags or [],
    )
    turns = [
        turn
        for turn in record.get("turns", [])
        if int(turn.get("turn_index", -1)) != int(turn_index)
    ]
    turns.append(turn_record)
    record["turns"] = sorted(turns, key=lambda turn: int(turn.get("turn_index", 0)))
    record["turn_count"] = len(record["turns"])
    record["updated_at"] = int(time.time())
    path.write_text(json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True, default=str))
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


def load_call_record(path: Path, *, include_artifacts: bool = True) -> dict[str, Any] | None:
    if not path.name.startswith(CALL_PREFIX) or path.suffix != ".json":
        return None
    data = _load_json(path)
    if not isinstance(data, dict):
        return None
    data.setdefault("call_uuid", path.stem.removeprefix(CALL_PREFIX))
    data.setdefault("call_id", data["call_uuid"])
    data["sidecar_path"] = str(path)
    data["sidecar_updated_at"] = int(path.stat().st_mtime)
    data.setdefault("turns", [])
    data["turn_count"] = len(data.get("turns") or [])
    data["learning_progression"] = _call_learning_progression(data)
    if include_artifacts:
        data["recordings"] = _recording_review_paths(data, path.parent)
        data["turns"] = [
            _enrich_turn_artifacts(data["call_uuid"], turn, path.parent)
            for turn in data.get("turns") or []
        ]
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
                for key in (
                    "call_uuid",
                    "call_id",
                    "phone_number",
                    "end_reason",
                    "quality_flags",
                    "student_id",
                )
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


def _path_inside_shared_audio(value: str, directory: Path | None = None) -> Path | None:
    if not value:
        return None
    root = (directory or shared_audio_dir()).resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved


def _recording_review_paths(record: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    call_uuid = str(record.get("call_uuid") or "")
    recording_path = str(
        record.get("recording_path")
        or (record.get("hangup_event") or {}).get("recording")
        or ""
    )
    if recording_path and not record.get("recording_path"):
        record["recording_path"] = recording_path
    base = _path_inside_shared_audio(recording_path, directory)
    result = {
        "mixed": _recording_item(call_uuid, "mixed", base),
        "rx_network": None,
        "tx_sabi": None,
    }
    if base:
        result["rx_network"] = _recording_item(
            call_uuid,
            "rx",
            base.with_name(f"{base.stem}_rx-network.wav"),
        )
        result["tx_sabi"] = _recording_item(
            call_uuid,
            "tx",
            base.with_name(f"{base.stem}_tx-sabi.wav"),
        )
    return result


def _recording_item(call_uuid: str, kind: str, path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists else 0,
        "audio_endpoint": f"/admin/calls/{call_uuid}/audio/{kind}",
    }


def _turn_review_record(
    *,
    call_uuid: str,
    turn_index: int,
    user_audio_path: str,
    user_audio_seconds: float,
    stt_transcript: str,
    stt_confidence: float,
    normalized_transcript: str,
    learning_state_before: dict[str, Any] | None,
    learning_state_after: dict[str, Any] | None,
    assistant_text: str,
    assistant_tts_text: str,
    assistant_audio_path: str,
    assistant_audio_seconds: float,
    timings: dict[str, Any],
    flags: list[str],
) -> dict[str, Any]:
    state_before = _learning_state_review(learning_state_before or {})
    state_after = _learning_state_review(learning_state_after or {})
    normalized_changed = (normalized_transcript or "").strip() != (stt_transcript or "").strip()
    return {
        "turn_index": int(turn_index),
        "user": {
            "audio_path": user_audio_path,
            "audio_seconds": round(float(user_audio_seconds or 0), 2),
            "audio_endpoint": f"/admin/calls/{call_uuid}/turns/{turn_index}/audio/user",
            "stt_transcript": stt_transcript,
            "stt_confidence": round(float(stt_confidence or 0), 3),
            "normalized_transcript": normalized_transcript,
            "normalization_changed": normalized_changed,
            "input_audio_note": (
                "This WAV is the exact AudioSocket PCM segment Sabi sent to STT "
                "for this turn, after barge-in/VAD trimming and short pre-roll."
            ),
        },
        "assistant": {
            "text": assistant_text,
            "tts_text": assistant_tts_text,
            "tts_text_changed": (assistant_tts_text or "").strip() != (assistant_text or "").strip(),
            "audio_path": assistant_audio_path,
            "audio_seconds": round(float(assistant_audio_seconds or 0), 2),
            "audio_endpoint": f"/admin/calls/{call_uuid}/turns/{turn_index}/audio/assistant",
        },
        "learning_state_before": state_before,
        "learning_state_after": state_after,
        "bump_down": _bump_down_review(state_before, state_after),
        "timings": timings,
        "flags": sorted(set(flags or [])),
        "created_at": int(time.time()),
    }


def _enrich_turn_artifacts(call_uuid: str, turn: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    turn = dict(turn or {})
    turn_index = int(turn.get("turn_index") or 0)
    for role in ("user", "assistant"):
        payload = dict(turn.get(role) or {})
        path = _path_inside_shared_audio(str(payload.get("audio_path") or ""), directory)
        payload["has_audio"] = bool(path and path.exists())
        payload["audio_bytes"] = path.stat().st_size if path and path.exists() else 0
        payload["audio_endpoint"] = f"/admin/calls/{call_uuid}/turns/{turn_index}/audio/{role}"
        turn[role] = payload
    return turn


def _learning_state_review(state: dict[str, Any]) -> dict[str, Any]:
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    scaffold_ladder = state.get("scaffold_ladder") if isinstance(state.get("scaffold_ladder"), dict) else {}
    return {
        "course": state.get("course"),
        "phase": state.get("phase"),
        "onboarding_status": state.get("onboarding_status"),
        "diagnostic_status": state.get("diagnostic_status"),
        "current_module": state.get("current_module"),
        "current_week": state.get("current_week"),
        "current_lesson": state.get("current_lesson"),
        "tarl_level": state.get("tarl_level"),
        "active_skill": state.get("active_skill"),
        "repair_skill": state.get("repair_skill"),
        "next_step": state.get("next_step"),
        "last_turn_correct": state.get("last_turn_correct"),
        "correct_streak": state.get("correct_streak"),
        "wrong_streak": state.get("wrong_streak"),
        "scaffold_depth": state.get("scaffold_depth"),
        "scaffold_ladder": {
            "level": scaffold_ladder.get("level"),
            "skill": scaffold_ladder.get("skill"),
            "teacher_move": scaffold_ladder.get("teacher_move"),
            "example_prompt": scaffold_ladder.get("example_prompt"),
            "rebuild_move": scaffold_ladder.get("rebuild_move"),
            "avoid": scaffold_ladder.get("avoid"),
        } if scaffold_ladder else None,
        "course_rotation": state.get("course_rotation"),
        "literacy": {
            "phase": literacy.get("phase"),
            "diagnostic_status": literacy.get("diagnostic_status"),
            "current_phase": literacy.get("current_phase"),
            "current_module": literacy.get("current_module"),
            "current_week": literacy.get("current_week"),
            "current_lesson": literacy.get("current_lesson"),
            "tarl_reading_level": literacy.get("tarl_reading_level"),
            "active_skill": literacy.get("active_skill"),
            "next_step": literacy.get("next_step"),
        },
    }


def _bump_down_review(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_scaffold = int(before.get("scaffold_depth") or 0)
    after_scaffold = int(after.get("scaffold_depth") or 0)
    before_module = int(before.get("current_module") or 0)
    after_module = int(after.get("current_module") or 0)
    before_tarl = int(before.get("tarl_level") or 0)
    after_tarl = int(after.get("tarl_level") or 0)
    detected = (
        after_scaffold > before_scaffold
        or after_module < before_module
        or after_tarl < before_tarl
        or bool(after.get("scaffold_ladder"))
    )
    reasons = []
    if after_scaffold > before_scaffold:
        reasons.append("scaffold_depth_increased")
    if after_module < before_module:
        reasons.append("module_lowered")
    if after_tarl < before_tarl:
        reasons.append("tarl_level_lowered")
    if after.get("scaffold_ladder"):
        reasons.append("scaffold_ladder_active")
    return {
        "detected": detected,
        "reasons": reasons,
        "from": {
            "module": before.get("current_module"),
            "skill": before.get("active_skill"),
            "tarl_level": before.get("tarl_level"),
            "scaffold_depth": before.get("scaffold_depth"),
            "wrong_streak": before.get("wrong_streak"),
        },
        "to": {
            "module": after.get("current_module"),
            "skill": after.get("active_skill"),
            "repair_skill": after.get("repair_skill"),
            "tarl_level": after.get("tarl_level"),
            "scaffold_depth": after.get("scaffold_depth"),
            "wrong_streak": after.get("wrong_streak"),
            "teacher_move": (after.get("scaffold_ladder") or {}).get("teacher_move")
            if isinstance(after.get("scaffold_ladder"), dict)
            else None,
        },
    }


def _call_learning_progression(record: dict[str, Any]) -> dict[str, Any]:
    turns = record.get("turns") or []
    if not turns:
        return {
            "has_turn_evidence": False,
            "starting_state": None,
            "ending_state": None,
            "bump_down_turns": [],
        }
    first_state = turns[0].get("learning_state_before")
    last_state = turns[-1].get("learning_state_after")
    return {
        "has_turn_evidence": True,
        "starting_state": first_state,
        "ending_state": last_state,
        "bump_down_turns": [
            turn.get("turn_index")
            for turn in turns
            if (turn.get("bump_down") or {}).get("detected")
        ],
    }
