#!/usr/bin/env python3
"""Audit and safely clean Sabi learner identity rows in Supabase.

This intentionally does not invent child names. `name` remains the actual child
name captured by Sabi. Blank, zero-evidence test rows can be removed after a
JSON backup. Named no-phone demo rows with zero sessions can also be removed:
they are browser/demo clutter, not phone pilot learners. Active phone learners
are preserved and shown through derived admin display names.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from memory import StudentMemory, _is_zero_evidence_unlinked_demo, _student_display_identity


BASE_STUDENT_COLUMNS = [
    "id",
    "name",
    "phone_number",
    "browser_id",
    "total_sessions",
    "total_correct",
    "total_wrong",
    "last_session_summary",
    "created_at",
    "updated_at",
]

OPTIONAL_IDENTITY_COLUMNS = [
    "phone_number_normalized",
    "phone_household_key",
    "child_name_normalized",
    "learner_key",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="delete safe zero-evidence placeholder rows")
    parser.add_argument("--backup-dir", default="/tmp", help="directory for cleanup JSON backups")
    args = parser.parse_args()

    memory = StudentMemory()
    if not memory.client:
        print(json.dumps({"status": "unavailable", "reason": "supabase_not_configured"}))
        return 2

    available_optional = _available_optional_columns(memory)
    rows = _load_students(memory, available_optional)
    safe_delete = [row for row in rows if _is_safe_delete(row, memory)]
    blank_name = [row for row in rows if _blank_name(row)]
    phone_pending = [
        row for row in blank_name
        if row not in safe_delete and (_student_display_identity(row)["identity_status"] == "phone_pending_name")
    ]

    report = {
        "status": "ok",
        "mode": "apply" if args.apply else "dry_run",
        "total_students": len(rows),
        "blank_name_rows": len(blank_name),
        "safe_zero_evidence_rows": len(safe_delete),
        "active_phone_learners_pending_name": len(phone_pending),
        "optional_identity_columns_present": available_optional,
        "missing_identity_columns": [
            column for column in OPTIONAL_IDENTITY_COLUMNS if column not in available_optional
        ],
        "sample_safe_delete": [_preview_row(row) for row in safe_delete[:30]],
        "sample_phone_pending": [_preview_row(row) for row in phone_pending[:20]],
    }

    backup_path = None
    if safe_delete:
        backup_path = _write_backup(args.backup_dir, safe_delete)
        report["backup_path"] = str(backup_path)

    deleted = 0
    skipped_delete: list[dict] = []
    if args.apply and safe_delete:
        for row in safe_delete:
            try:
                memory.client.table("sabi_students").delete().eq("id", row["id"]).execute()
                deleted += 1
            except Exception as exc:
                if _is_foreign_key_delete_error(exc):
                    skipped_delete.append({
                        **_preview_row(row),
                        "reason": _error_text(exc)[:240],
                    })
                    continue
                raise
    report["deleted_rows"] = deleted
    report["skipped_referenced_rows"] = skipped_delete

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _available_optional_columns(memory: StudentMemory) -> list[str]:
    available: list[str] = []
    for column in OPTIONAL_IDENTITY_COLUMNS:
        try:
            memory.client.table("sabi_students").select(column).limit(1).execute()
            available.append(column)
        except Exception:
            continue
    return available


def _load_students(memory: StudentMemory, optional_columns: list[str]) -> list[dict]:
    columns = ",".join(BASE_STUDENT_COLUMNS + optional_columns)
    result = memory.client.table("sabi_students").select(columns).limit(5000).execute()
    return result.data or []


def _is_safe_delete(row: dict, memory: StudentMemory) -> bool:
    if not _blank_name(row) and not _is_zero_evidence_unlinked_demo(row):
        return False
    if int(row.get("total_sessions") or 0) != 0:
        return False
    if int(row.get("total_correct") or 0) != 0 or int(row.get("total_wrong") or 0) != 0:
        return False
    if str(row.get("last_session_summary") or "").strip():
        return False
    if _has_student_reference(memory, "sabi_sessions", row.get("id")):
        return False
    if _has_student_reference(memory, "sabi_active_calls", row.get("id")):
        return False
    if _has_student_reference(memory, "sabi_call_feedback", row.get("id")):
        return False
    return True


def _has_student_reference(memory: StudentMemory, table_name: str, student_id: str | None) -> bool:
    if not student_id:
        return True
    try:
        result = memory.client.table(table_name).select("student_id").eq(
            "student_id",
            student_id,
        ).limit(1).execute()
        return bool(result.data)
    except Exception:
        return table_name == "sabi_sessions"


def _error_text(error: Exception) -> str:
    return " ".join(
        str(getattr(error, attr, "") or "")
        for attr in ("message", "details", "hint", "code")
    ) or str(error)


def _is_foreign_key_delete_error(error: Exception) -> bool:
    text = _error_text(error).lower()
    return "23503" in text or "foreign key constraint" in text or "still referenced" in text


def _blank_name(row: dict) -> bool:
    name = str(row.get("name") or "").strip().lower()
    return not name or name in {"unnamed learner", "unknown", "none", "null"}


def _write_backup(backup_dir: str, rows: list[dict]) -> Path:
    path = Path(backup_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path / f"sabi_student_cleanup_backup_{stamp}.json"
    backup_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return backup_path


def _preview_row(row: dict) -> dict:
    identity = _student_display_identity(row)
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "display_name": identity["display_name"],
        "phone_number": row.get("phone_number"),
        "browser_id": row.get("browser_id"),
        "total_sessions": row.get("total_sessions") or 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
