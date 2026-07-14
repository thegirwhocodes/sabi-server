#!/usr/bin/env python3
"""Regression checks for Sabi call-quality sidecars."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from call_admin import (
    append_call_turn_review,
    call_recording_path,
    call_sidecar_path,
    call_turn_audio_path,
    list_call_records,
    load_call_record,
    merge_call_hangup_event,
    quality_flags,
    set_call_review_status,
    set_call_turn_stt_correction,
    write_call_learning_summary,
    write_call_review_record,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
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
                "recording": str(root / "calls" / "call-qa-001.wav"),
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

        calls_dir = root / "calls"
        calls_dir.mkdir()
        for name in ["call-qa-001.wav", "call-qa-001_rx-network.wav", "call-qa-001_tx-sabi.wav"]:
            (calls_dir / name).write_bytes(b"RIFFtest")

        user_audio = call_turn_audio_path(call_uuid, 0, "user", root)
        assistant_audio = call_turn_audio_path(call_uuid, 0, "assistant", root)
        user_audio.parent.mkdir(parents=True, exist_ok=True)
        user_audio.write_bytes(b"RIFFuser")
        assistant_audio.write_bytes(b"RIFFassistant")
        append_call_turn_review(
            call_uuid=call_uuid,
            turn_index=0,
            user_audio_path=str(user_audio),
            user_audio_seconds=1.2,
            stt_transcript="fifteen naira",
            stt_confidence=0.91,
            normalized_transcript="15 naira",
            learning_state_before={
                "course": "numeracy",
                "current_module": 4,
                "current_week": 14,
                "current_lesson": 2,
                "tarl_level": 4,
                "active_skill": "multiplication",
                "wrong_streak": 1,
                "scaffold_depth": 0,
            },
            learning_state_after={
                "course": "numeracy",
                "current_module": 4,
                "current_week": 14,
                "current_lesson": 2,
                "tarl_level": 4,
                "active_skill": "multiplication",
                "repair_skill": "multiplication",
                "wrong_streak": 2,
                "scaffold_depth": 1,
                "scaffold_ladder": {
                    "level": 1,
                    "skill": "multiplication",
                    "teacher_move": "Translate multiplication back to equal groups.",
                    "example_prompt": "Two bags have three oranges each.",
                },
            },
            assistant_text="Good try. Let's use groups.",
            assistant_tts_text="Good try. Let's use groups.",
            assistant_audio_path=str(assistant_audio),
            assistant_audio_seconds=2.4,
            timings={"stt_seconds": 0.2, "llm_seconds": 0.5, "tts_seconds": 0.4},
            flags=["transcript_normalized"],
            directory=root,
        )

        loaded = load_call_record(root / "call_call-qa-001.json")
        ok &= check(
            "load_call_record_adds_sidecar_metadata",
            loaded is not None
            and loaded["call_uuid"] == call_uuid
            and loaded["sidecar_path"].endswith("call_call-qa-001.json"),
            loaded,
        )
        ok &= check(
            "call_record_exposes_full_and_split_recordings",
            loaded["recordings"]["mixed"]["exists"] is True
            and loaded["recordings"]["rx_network"]["exists"] is True
            and loaded["recordings"]["tx_sabi"]["exists"] is True
            and call_recording_path(call_uuid, "rx", root).name.endswith("_rx-network.wav"),
            loaded.get("recordings"),
        )
        turn = loaded["turns"][0] if loaded.get("turns") else {}
        ok &= check(
            "turn_review_links_audio_transcript_and_bump_down",
            turn.get("user", {}).get("has_audio") is True
            and turn.get("assistant", {}).get("has_audio") is True
            and turn.get("user", {}).get("stt_transcript") == "fifteen naira"
            and turn.get("user", {}).get("normalized_transcript") == "15 naira"
            and turn.get("bump_down", {}).get("detected") is True
            and loaded.get("learning_progression", {}).get("bump_down_turns") == [0],
            turn,
        )
        corrected = set_call_turn_stt_correction(
            call_uuid,
            0,
            "fifteen naira",
            reviewer="Naomi",
            consent_for_model_training=False,
            directory=root,
        )
        correction = ((corrected or {}).get("turns") or [{}])[0].get("user", {}).get("stt_correction", {})
        ok &= check(
            "stt_correction_keeps_training_consent_separate",
            correction.get("transcript") == "fifteen naira"
            and correction.get("review_status") == "approved"
            and correction.get("reviewed_by") == "Naomi"
            and correction.get("consent_for_model_training") is False,
            correction,
        )
        ok &= check(
            "stt_correction_requires_reviewer",
            set_call_turn_stt_correction(
                call_uuid,
                0,
                "fifteen",
                reviewer="",
                consent_for_model_training=True,
                directory=root,
            ) is None,
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

        ok &= check(
            "load_call_record_defaults_review_status_unreviewed",
            load_call_record(root / "call_call-qa-001.json").get("review_status") == "unreviewed",
        )
        reviewed = set_call_review_status(call_uuid, "reviewed", reviewer="Naomi", directory=root)
        ok &= check(
            "set_review_status_marks_reviewed_with_timestamp",
            reviewed is not None
            and reviewed["review_status"] == "reviewed"
            and reviewed.get("reviewed_at")
            and reviewed.get("reviewed_by") == "Naomi",
            reviewed,
        )
        ok &= check(
            "set_review_status_rejects_invalid",
            set_call_review_status(call_uuid, "nonsense", directory=root) is None,
        )
        ok &= check(
            "index_filters_by_review_status",
            list_call_records(root, review_status="reviewed")["total"] == 1
            and list_call_records(root, review_status="unreviewed")["total"] == 1,
        )
        cleared = set_call_review_status(call_uuid, "unreviewed", directory=root)
        ok &= check(
            "set_review_status_unreviewed_clears_timestamp",
            cleared is not None and cleared["review_status"] == "unreviewed" and cleared.get("reviewed_at") is None,
            cleared,
        )

        ok &= check(
            "load_call_record_defaults_learning_summary_and_note_none",
            load_call_record(root / "call_call-qa-001.json").get("learning_summary") is None
            and load_call_record(root / "call_call-qa-001.json").get("teacher_note") is None,
        )
        scorecard = {
            "course": "numeracy",
            "module": 4,
            "lesson_title": "The 6 times table",
            "lesson_global": 51,
            "questions_correct": 4,
            "questions_total": 6,
            "accuracy": 0.667,
            "per_skill": {"multiplication": {"accuracy": 0.67, "mastery": "near"}},
            "mastery_signal": "near",
            "should_advance": False,
        }
        teacher_note = {
            "strengths": ["Understood equal groups"],
            "struggles": ["Slower on 6 times table"],
            "engagement": "focused",
            "misconceptions": [],
            "recommended_focus": "Practice sixes with market trays.",
            "narrative": "Chidi is getting multiplication as groups; the sixes still need repetition.",
            "source": "heuristic",
        }
        summarized = write_call_learning_summary(call_uuid, scorecard, teacher_note, directory=root)
        ok &= check(
            "write_call_learning_summary_persists_scorecard_and_note",
            summarized is not None
            and summarized.get("learning_summary", {}).get("mastery_signal") == "near"
            and summarized.get("teacher_note", {}).get("engagement") == "focused",
            summarized,
        )
        reloaded = load_call_record(root / "call_call-qa-001.json")
        ok &= check(
            "load_call_record_surfaces_scorecard_and_note",
            reloaded.get("learning_summary", {}).get("questions_correct") == 4
            and reloaded.get("teacher_note", {}).get("recommended_focus", "").startswith("Practice sixes"),
            reloaded.get("learning_summary"),
        )
        ok &= check(
            "write_call_learning_summary_preserves_existing_turns",
            len(reloaded.get("turns") or []) == 1,
            reloaded.get("turn_count"),
        )
        ok &= check(
            "write_call_learning_summary_noop_when_both_none",
            write_call_learning_summary("call-missing", None, None, directory=root) is None,
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
