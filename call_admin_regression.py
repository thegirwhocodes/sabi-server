#!/usr/bin/env python3
"""Regression checks for Sabi call-quality sidecars."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from call_admin import (
    call_sidecar_path,
    list_call_records,
    load_call_record,
    merge_call_hangup_event,
    quality_flags,
    write_call_review_record,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail else ""))
    return condition


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        call_uuid = "call-qa-001"

        ok &= check(
            "safe_call_path_accepts_uuid",
            call_sidecar_path(call_uuid, root) == root / "call_call-qa-001.json",
            call_sidecar_path(call_uuid, root),
        )
        ok &= check(
            "safe_call_path_rejects_traversal",
            call_sidecar_path("../secret", root) is None,
            call_sidecar_path("../secret", root),
        )

        flags = quality_flags(
            end_reason="channel_closed_waiting_for_speech",
            duration_seconds=42,
            user_turns=0,
            assistant_turns=1,
            hangup_event={"hangup_cause": "16", "dialstatus": "ANSWER"},
        )
        ok &= check(
            "flags_short_no_speech_channel_closed",
            {"very_short_call", "no_child_turns", "no_usable_speech", "channel_closed"}.issubset(flags),
            flags,
        )

        record = write_call_review_record(
            call_uuid=call_uuid,
            call_id="call-abc",
            phone_number="+2348033374126",
            mode="inbound",
            attempt="1",
            student_id="student-1",
            end_reason="sabi_wrap_up",
            duration_seconds=361,
            user_turns=12,
            assistant_turns=13,
            directory=root,
        )
        ok &= check(
            "record_written_without_flags_for_good_call",
            record is not None and record["quality_flags"] == [],
            record,
        )

        merged = merge_call_hangup_event(
            call_uuid,
            {
                "hangup_cause": "16",
                "dialstatus": "ANSWER",
                "duration": "365",
                "billsec": "360",
            },
            root,
        )
        ok &= check(
            "hangup_event_merges_after_record",
            merged is not None
            and merged["hangup_event"]["billsec"] == "360"
            and merged["quality_flags"] == [],
            merged,
        )

        loaded = load_call_record(root / "call_call-qa-001.json")
        ok &= check(
            "load_call_record_adds_sidecar_metadata",
            loaded is not None
            and loaded["call_uuid"] == call_uuid
            and loaded["sidecar_path"].endswith("call_call-qa-001.json"),
            loaded,
        )

        write_call_review_record(
            call_uuid="call-qa-002",
            call_id="call-def",
            phone_number="+18604367048",
            mode="callback",
            attempt="2",
            end_reason="carrier_or_voicemail_audio",
            duration_seconds=8,
            user_turns=0,
            assistant_turns=1,
            directory=root,
        )
        index = list_call_records(root, limit=10)
        ok &= check(
            "index_lists_call_records",
            index["total"] == 2 and len(index["items"]) == 2,
            index,
        )
        phone_filtered = list_call_records(root, phone="08033374126")
        ok &= check(
            "index_filters_by_local_phone",
            phone_filtered["total"] == 1
            and phone_filtered["items"][0]["call_uuid"] == call_uuid,
            phone_filtered,
        )
        flagged = list_call_records(root, flag="carrier_or_voicemail_audio")
        ok &= check(
            "index_filters_by_quality_flag",
            flagged["total"] == 1
            and flagged["items"][0]["call_uuid"] == "call-qa-002",
            flagged,
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
