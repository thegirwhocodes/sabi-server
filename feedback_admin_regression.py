#!/usr/bin/env python3
"""Regression checks for protected feedback-note review helpers."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from feedback_admin import (
    feedback_audio_path,
    feedback_sidecar_path,
    list_feedback_records,
    load_feedback_record,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail else ""))
    return condition


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        first_uuid = "fb-note-001"
        second_uuid = "fb-note-002"

        first_sidecar = root / f"feedback_{first_uuid}.json"
        first_audio = root / f"feedback_{first_uuid}.wav"
        first_audio.write_bytes(b"RIFFfake")
        first_sidecar.write_text(
            json.dumps(
                {
                    "call_uuid": first_uuid,
                    "call_id": "call-abc",
                    "phone_number": "+2348033374126",
                    "student_id": "student-1",
                    "channel": "asterisk_audiosocket",
                    "participant_type": "tester",
                    "duration_seconds": 12,
                    "tags": ["open_voice_note"],
                    "feedback_mode": "testers",
                    "created_at": "2026-06-22T23:00:00Z",
                    "transcript": "Sabi marked me wrong. Call me on +2348033374126 or me@example.com.",
                }
            )
        )

        second_sidecar = root / f"feedback_{second_uuid}.json"
        second_sidecar.write_text(
            json.dumps(
                {
                    "call_uuid": second_uuid,
                    "call_id": "call-def",
                    "phone_number": "+18604367048",
                    "transcript": "The audio was clear.",
                }
            )
        )

        ok &= check(
            "safe_sidecar_path_accepts_uuid",
            feedback_sidecar_path(first_uuid, root) == first_sidecar,
            feedback_sidecar_path(first_uuid, root),
        )
        ok &= check(
            "safe_sidecar_path_rejects_traversal",
            feedback_sidecar_path("../secret", root) is None,
            feedback_sidecar_path("../secret", root),
        )
        ok &= check(
            "audio_path_matches_sidecar",
            feedback_audio_path(first_uuid, root) == first_audio,
            feedback_audio_path(first_uuid, root),
        )

        loaded = load_feedback_record(first_sidecar)
        ok &= check(
            "record_redacts_preview",
            loaded is not None
            and "[phone]" in loaded["redacted_transcript"]
            and "[email]" in loaded["redacted_transcript"]
            and "me@example.com" not in loaded["transcript_preview"],
            loaded,
        )
        ok &= check(
            "record_marks_audio_available",
            loaded is not None and loaded["has_audio"] and loaded["audio_bytes"] > 0,
            loaded,
        )

        raw_loaded = load_feedback_record(first_sidecar, include_raw=True)
        ok &= check(
            "raw_transcript_is_opt_in",
            raw_loaded is not None
            and raw_loaded.get("transcript", "").startswith("Sabi marked")
            and "transcript" not in loaded,
            raw_loaded,
        )

        index = list_feedback_records(root, limit=10)
        ok &= check(
            "index_lists_sidecars",
            index["total"] == 2 and len(index["items"]) == 2,
            index,
        )
        phone_filtered = list_feedback_records(root, phone="08033374126")
        ok &= check(
            "index_filters_by_phone",
            phone_filtered["total"] == 1
            and phone_filtered["items"][0]["call_uuid"] == first_uuid,
            phone_filtered,
        )
        text_filtered = list_feedback_records(root, q="clear")
        ok &= check(
            "index_filters_by_text",
            text_filtered["total"] == 1
            and text_filtered["items"][0]["call_uuid"] == second_uuid,
            text_filtered,
        )
        limited = list_feedback_records(root, limit=1)
        ok &= check(
            "index_applies_limit",
            limited["count"] == 1 and limited["total"] == 2,
            limited,
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
