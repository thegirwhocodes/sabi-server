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
        legacy_calls = destination / "Calls" / "call-123"
        staged_turns = destination / ".turns" / "call-123"
        caller_full = destination / "Caller-only full calls"
        metadata.mkdir()
        legacy_calls.mkdir(parents=True)
        staged_turns.mkdir(parents=True)
        caller_full.mkdir()
        (legacy_calls / "legacy-note.txt").write_text("migrate me", encoding="utf-8")
        (staged_turns / "user_turn_03.wav").write_bytes(b"RIFF-test")
        original_name = "20260805-175641_test_123_rx-network.wav"
        (caller_full / original_name).write_bytes(b"RIFF-full")
        record = {
            "call_uuid": "call-123",
            "created_at": 1785952613,
            "student_id": "06fbefe3-d924-4dd9-a5fc-a76b192f6fa6",
            "phone_number": "+17542993781",
            "duration_seconds": 417,
            "end_reason": "caller_hangup",
            "stt_providers_used": ["gemini"],
            "learning_summary": {"course": "numeracy"},
            "hangup_event": {"recording": f"/shared/audio/calls/{original_name[:-15]}.wav"},
            "turns": [
                {
                    "turn_index": 3,
                    "user": {"stt_transcript": "d", "stt_provider": "gemini"},
                    "assistant": {"text": "Yes, the first sound is d."},
                    "timings": {"stt_seconds": 1.75},
                    "flags": ["numeric_stt"],
                }
            ],
        }
        (metadata / "call_call-123.json").write_text(json.dumps(record), encoding="utf-8")
        (legacy_calls / "call.json").write_text(json.dumps(record), encoding="utf-8")
        learner_names = {record["student_id"]: "Oluremi"}
        organized, attached = module._organize(
            destination,
            turns_dir=staged_turns.parent,
            learner_names=learner_names,
        )
        calls = destination / "Calls" / "2026-08 August" / "2026-08-05" / "Oluremi_numeracy"
        transcript = (calls / "what-sabi-heard.txt").read_text(encoding="utf-8")
        ok &= check("organizes_sidecar_by_call_uuid", organized == 1 and (calls / "call.json").exists())
        ok &= check("keeps_numbered_user_clip", (calls / "user_turn_03.wav").exists())
        ok &= check(
            "nests_call_under_month_and_day",
            calls.parent.name == "2026-08-05" and calls.parent.parent.name == "2026-08 August",
            calls,
        )
        ok &= check(
            "folder_name_contains_only_stored_name_and_subject",
            calls.name == "Oluremi_numeracy"
            and "3781" not in calls.name
            and "call-123" not in calls.name
            and "17-56" not in calls.name,
            calls.name,
        )
        ok &= check(
            "migrates_old_flat_call_folder",
            not legacy_calls.exists() and (calls / "legacy-note.txt").read_text(encoding="utf-8") == "migrate me",
        )
        ok &= check("writes_model_output_warning", "not ground truth" in transcript.lower())
        ok &= check("writes_turn_transcript", "Sabi heard: d" in transcript and "Turn 3" in transcript)
        ok &= check(
            "attaches_caller_only_recording",
            attached == 1 and (calls / "full-caller-only.wav").read_bytes() == b"RIFF-full",
            {"attached": attached},
        )
        second_learner = dict(
            record,
            call_uuid="call-456",
            student_id="different-student",
            phone_number="+17542993781",
        )
        ok &= check(
            "two_learners_on_one_phone_get_different_folders",
            module._call_folder_base(record, learner_names) == "Oluremi_numeracy"
            and module._call_folder_base(
                second_learner,
                {**learner_names, "different-student": "Amara"},
            )
            == "Amara_numeracy",
        )
        replay = dict(record, call_uuid="call-123-lwreplay", created_at=1785952614)
        (metadata / "call_call-123-lwreplay.json").write_text(json.dumps(replay), encoding="utf-8")
        module._organize(destination, turns_dir=staged_turns.parent, learner_names=learner_names)
        replay_dir = calls.parent / "Oluremi_numeracy_2"
        ok &= check(
            "same_name_subject_date_uses_human_suffix_without_merging",
            replay_dir.is_dir()
            and module._read_call_uuid(calls) == "call-123"
            and module._read_call_uuid(replay_dir) == "call-123-lwreplay",
        )

        # A later run must preserve suffix assignments instead of reshuffling
        # them, even when another call is added.
        third = dict(record, call_uuid="call-789", created_at=1785952612)
        (metadata / "call_call-789.json").write_text(json.dumps(third), encoding="utf-8")
        module._organize(destination, turns_dir=staged_turns.parent, learner_names=learner_names)
        ok &= check(
            "suffixes_remain_stable_when_older_call_arrives_later",
            module._read_call_uuid(calls) == "call-123"
            and module._read_call_uuid(replay_dir) == "call-123-lwreplay"
            and module._read_call_uuid(calls.parent / "Oluremi_numeracy_3") == "call-789",
        )

        # If the first two calls later move to another subject, do not leave a
        # lone human-facing `_3` behind for the remaining call.
        third_changed = dict(
            third,
            learning_summary={"course": "literacy"},
            turns=[{"turn_index": 0, "flags": ["literacy_stt"]}],
        )
        (metadata / "call_call-789.json").write_text(json.dumps(third_changed), encoding="utf-8")
        record_changed = dict(record, learning_summary={"course": "literacy"})
        (metadata / "call_call-123.json").write_text(json.dumps(record_changed), encoding="utf-8")
        module._organize(destination, turns_dir=staged_turns.parent, learner_names=learner_names)
        ok &= check(
            "compacts_suffix_gap_after_subject_change",
            module._read_call_uuid(calls) == "call-123-lwreplay"
            and module._read_call_uuid(calls.parent / "Oluremi_literacy") == "call-789"
            and module._read_call_uuid(calls.parent / "Oluremi_literacy-numeracy") == "call-123",
        )

        unknown = dict(
            record,
            call_uuid="call-unknown",
            created_at=1786039013,
            student_id="missing-profile",
            learner_name="An STT Guess",
            learning_summary={},
            turns=[],
        )
        (metadata / "call_call-unknown.json").write_text(json.dumps(unknown), encoding="utf-8")
        module._organize(destination, turns_dir=staged_turns.parent, learner_names=learner_names)
        unknown_dir = destination / "Calls" / "2026-08 August" / "2026-08-06" / "Unknown Learner_unknown"
        ok &= check(
            "unknown_name_is_exact_and_never_inferred_from_sidecar_or_stt",
            unknown_dir.is_dir() and "An STT Guess" not in str(unknown_dir),
        )

        mixed = dict(
            record,
            call_uuid="call-mixed",
            created_at=1786039014,
            learning_summary={"course": "literacy"},
            turns=[
                {"turn_index": 0, "flags": ["literacy_stt"]},
                {"turn_index": 1, "flags": ["numeric_stt"]},
            ],
        )
        ok &= check(
            "mixed_lesson_gets_combined_subject",
            module._call_subject(mixed) == "literacy-numeracy",
            module._call_subject(mixed),
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
