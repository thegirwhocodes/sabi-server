#!/usr/bin/env python3
"""Regression checks that the STT provider used for each turn is recorded.

This is the data plumbing behind the admin Calls view: every turn sidecar
carries `user.stt_provider` and every call rollup carries `stt_providers_used`
so the board console can show which STT engine handled each transcript and
filter by provider.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(tempfile.mkdtemp(prefix="sabi-stt-provider-"))
os.environ["SABI_SHARED_AUDIO_DIR"] = str(ROOT)

import call_admin  # noqa: E402
import stt as stt_mod  # noqa: E402


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    # 1. STT module: every provider path must label its returned dict.
    #    Read the source — exercising live transcription requires a model on disk
    #    and a real audio file. The source-level check catches silent drops
    #    of the provider field that would break the admin view.
    source = Path(stt_mod.__file__).read_text()
    ok &= check("stt_groq_sets_provider", '"provider": "groq"' in source, "missing in _transcribe_groq")
    ok &= check("stt_local_sets_provider", '"provider": "local_whisper"' in source, "missing in _transcribe_local")
    ok &= check("stt_intron_sets_provider", '"provider": "intron"' in source, "missing in _transcribe_intron")

    # 2. append_call_turn_review writes stt_provider into the per-turn payload.
    call_uuid = "stt-provider-regression-001"
    call_admin.append_call_turn_review(
        call_uuid=call_uuid,
        turn_index=1,
        user_audio_path="",
        user_audio_seconds=1.2,
        stt_transcript="ten naira",
        stt_confidence=0.91,
        normalized_transcript="ten naira",
        learning_state_before={"current_module": 2},
        learning_state_after={"current_module": 2},
        assistant_text="Correct!",
        assistant_tts_text="Correct!",
        assistant_audio_path="",
        assistant_audio_seconds=0.4,
        timings={"stt_seconds": 0.24, "llm_seconds": 1.1, "tts_seconds": 0.38},
        flags=[],
        directory=ROOT,
        stt_provider="gemini",
        stt_prompt="A Nigerian child is walking through a numeracy lesson in naira. Reply with their response",
        stt_prompt_mode="curriculum",
        stt_prompt_label="naira",
        stt_details={
            "consensus": True,
            "consensus_numeric_value": 10,
            "ensemble_results": {
                "groq": {"text": "ten naira"},
                "local_whisper": {"text": "ten naira"},
            },
        },
    )
    sidecar = ROOT / f"call_{call_uuid}.json"
    data = json.loads(sidecar.read_text())
    turn = data["turns"][0]
    ok &= check(
        "turn_sidecar_has_stt_provider",
        turn.get("user", {}).get("stt_provider") == "gemini",
        turn.get("user", {}),
    )
    ok &= check(
        "turn_sidecar_has_exact_gemini_prompt",
        turn.get("user", {}).get("stt_prompt")
        == "A Nigerian child is walking through a numeracy lesson in naira. Reply with their response"
        and turn.get("user", {}).get("stt_prompt_mode") == "curriculum"
        and turn.get("user", {}).get("stt_prompt_label") == "naira",
        turn.get("user", {}),
    )
    ok &= check(
        "turn_sidecar_has_parallel_stt_evidence",
        turn.get("user", {}).get("stt_details", {}).get("consensus_numeric_value") == 10
        and turn.get("user", {}).get("stt_details", {}).get("ensemble_results", {}).get("groq", {}).get("text") == "ten naira",
        turn.get("user", {}),
    )
    ok &= check(
        "call_rollup_lists_stt_providers_used",
        data.get("stt_providers_used") == ["gemini"],
        data.get("stt_providers_used"),
    )

    # 3. A second turn from a different provider — rollup should aggregate both.
    call_admin.append_call_turn_review(
        call_uuid=call_uuid,
        turn_index=2,
        user_audio_path="",
        user_audio_seconds=0.9,
        stt_transcript="cat",
        stt_confidence=0.78,
        normalized_transcript="cat",
        learning_state_before={"current_module": 2},
        learning_state_after={"current_module": 2},
        assistant_text="Yes!",
        assistant_tts_text="Yes!",
        assistant_audio_path="",
        assistant_audio_seconds=0.3,
        timings={"stt_seconds": 0.42},
        flags=[],
        directory=ROOT,
        stt_provider="intron",
    )
    data = json.loads(sidecar.read_text())
    ok &= check(
        "call_rollup_aggregates_multiple_providers",
        data.get("stt_providers_used") == ["gemini", "intron"],
        data.get("stt_providers_used"),
    )

    # 4. Backwards compat: a turn with no stt_provider passed still works,
    #    and a turn that fell back to local Whisper is recorded as such.
    call_admin.append_call_turn_review(
        call_uuid=call_uuid,
        turn_index=3,
        user_audio_path="",
        user_audio_seconds=1.0,
        stt_transcript="thirty naira",
        stt_confidence=0.55,
        normalized_transcript="thirty naira",
        learning_state_before={"current_module": 2},
        learning_state_after={"current_module": 2},
        assistant_text="Right.",
        assistant_tts_text="Right.",
        assistant_audio_path="",
        assistant_audio_seconds=0.3,
        directory=ROOT,
        stt_provider="local_whisper",
    )
    call_admin.append_call_turn_review(
        call_uuid=call_uuid,
        turn_index=4,
        user_audio_path="",
        user_audio_seconds=1.0,
        stt_transcript="four",
        stt_confidence=0.6,
        normalized_transcript="four",
        learning_state_before={"current_module": 2},
        learning_state_after={"current_module": 2},
        assistant_text="OK.",
        assistant_tts_text="OK.",
        assistant_audio_path="",
        assistant_audio_seconds=0.3,
        directory=ROOT,
        # no stt_provider arg — old callers must keep working
    )
    data = json.loads(sidecar.read_text())
    ok &= check(
        "call_rollup_includes_local_whisper_fallback",
        "local_whisper" in (data.get("stt_providers_used") or []),
        data.get("stt_providers_used"),
    )
    ok &= check(
        "missing_stt_provider_stored_as_empty_string",
        data["turns"][3]["user"].get("stt_provider") == "",
        data["turns"][3]["user"],
    )

    # 5. list_call_records surfaces stt_providers_used to the admin index.
    listing = call_admin.list_call_records(directory=ROOT)
    item = listing["items"][0] if listing["items"] else {}
    ok &= check(
        "admin_calls_index_exposes_stt_providers_used",
        sorted(item.get("stt_providers_used") or []) == ["gemini", "intron", "local_whisper"],
        item.get("stt_providers_used"),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
