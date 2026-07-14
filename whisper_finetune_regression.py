#!/usr/bin/env python3
"""Regression checks for Sabi's full mixed-data/telephony STT pipeline."""

from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "whisper-finetune"))

from audio_augmentation import g711_roundtrip, missing_noise_categories
from prepare_external_manifests import common_voice_rows, sabi_corrected_rows
from training_data import load_external_manifest, mix_training_rows, validate_source_mix, write_jsonl


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def _wav(path: Path, seconds: float = 0.4, rate: int = 8000) -> None:
    samples = (np.sin(np.arange(int(rate * seconds)) * 2 * np.pi * 440 / rate) * 10000).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())


def main() -> int:
    ok = True
    tone = np.linspace(-0.95, 0.95, 8000, dtype=np.float32)
    alaw = g711_roundtrip(tone, "alaw")
    ulaw = g711_roundtrip(tone, "ulaw")
    ok &= check(
        "g711_pcma_and_pcmu_are_real_lossy_roundtrips",
        alaw.shape == tone.shape
        and ulaw.shape == tone.shape
        and not np.array_equal(alaw, tone)
        and not np.array_equal(alaw, ulaw)
        and np.max(np.abs(alaw)) <= 1.0,
    )
    ok &= check(
        "all_six_real_noise_categories_required",
        missing_noise_categories({"market": ["x"]})
        == ["generator", "chatter", "television", "baby", "connection"],
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        clip = root / "clip.wav"
        _wav(clip)

        manifest = root / "sabi.jsonl"
        write_jsonl(
            manifest,
            [{
                "id": "call-a-turn-00",
                "audio_path": str(clip),
                "transcript": "thirty",
                "split": "train",
                "source": "sabi_corrected",
                "license": "SABI-PRIVATE-CONSENTED",
                "consent_for_model_training": True,
                "review_status": "approved",
            }],
        )
        rows = load_external_manifest(manifest, expected_source="sabi_corrected")
        ok &= check("consented_corrected_call_loads", len(rows) == 1, rows)
        excluded = load_external_manifest(
            manifest,
            expected_source="sabi_corrected",
            gold_ids={f"audio:{clip.resolve()}"},
        )
        ok &= check("held_out_audio_path_never_enters_training", excluded == [], excluded)

        unsafe = root / "unsafe.jsonl"
        payload = json.loads(manifest.read_text().strip())
        payload["consent_for_model_training"] = False
        write_jsonl(unsafe, [payload])
        try:
            load_external_manifest(unsafe, expected_source="sabi_corrected")
            rejected = False
        except ValueError:
            rejected = True
        ok &= check("ordinary_recording_consent_is_not_training_consent", rejected)

        cv = root / "cv"
        _wav(cv / "clips" / "ng.wav")
        _wav(cv / "clips" / "uk.wav")
        (cv / "validated.tsv").write_text(
            "client_id\tpath\tsentence\taccents\tlocale\n"
            "ng-speaker\tng.wav\tMy name is Ada\tNigerian English\ten\n"
            "uk-speaker\tuk.wav\tMy name is Sam\tEngland English\ten\n"
        )
        cv_rows = common_voice_rows(cv)
        ok &= check(
            "official_common_voice_export_filters_nigerian_accent",
            len(cv_rows) == 1 and cv_rows[0]["license"] == "CC0-1.0",
            cv_rows,
        )

        sidecar_root = root / "shared"
        sabi_audio = sidecar_root / "call_turns" / "call-safe-01" / "user_turn_00.wav"
        _wav(sabi_audio)
        gold = root / "gold.json"
        gold.write_text(json.dumps([{"id": "private", "audio_path": str(sabi_audio), "truth": "thirty"}]))
        (sidecar_root / "call_call-safe-01.json").write_text(json.dumps({
            "call_uuid": "call-safe-01",
            "turns": [{
                "turn_index": 0,
                "user": {
                    "audio_path": str(sabi_audio),
                    "audio_seconds": 0.4,
                    "stt_correction": {
                        "transcript": "thirty",
                        "review_status": "approved",
                        "reviewed_by": "Naomi",
                        "consent_for_model_training": True,
                    },
                },
            }],
        }))
        ok &= check(
            "sabi_exporter_excludes_private_gold_clip",
            sabi_corrected_rows(sidecar_root, gold) == [],
        )

    afri = [
        {"id": f"a{i}", "audio": f"a{i}.wav", "transcript": "hello", "source": "afrispeech_ng", "license": "CC-BY-NC-SA-4.0"}
        for i in range(100)
    ]
    external = {
        "nigerian_common_voice": [
            {"id": f"c{i}", "audio": f"c{i}.wav", "source": "nigerian_common_voice", "license": "CC0-1.0"}
            for i in range(100)
        ],
        "sabi_corrected": [
            {"id": f"s{i}", "audio": f"s{i}.wav", "source": "sabi_corrected", "license": "SABI-PRIVATE-CONSENTED", "is_short_response": True}
            for i in range(100)
        ],
        "general_english_retention": [
            {"id": f"r{i}", "audio": f"r{i}.wav", "source": "general_english_retention", "license": "CC-BY-4.0"}
            for i in range(100)
        ],
    }
    mixed = mix_training_rows(afri, external)
    retention_share = sum(row["source"] == "general_english_retention" for row in mixed) / len(mixed)
    ok &= check("general_english_retention_is_10_to_20_percent", 0.10 <= retention_share <= 0.20, retention_share)
    try:
        validate_source_mix(mixed, allow_noncommercial=False)
        blocked = False
    except RuntimeError:
        blocked = True
    ok &= check("afrispeech_noncommercial_model_cannot_auto_export", blocked)

    print("PASS all Whisper fine-tuning regressions" if ok else "FAIL Whisper fine-tuning regressions")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
