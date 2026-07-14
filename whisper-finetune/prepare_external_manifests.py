#!/usr/bin/env python3
"""Prepare auditable manifests for every non-AfriSpeech Sabi STT source.

This script never downloads or relicenses audio. Point it at an official
Mozilla Common Voice export, an OpenSLR LibriSpeech tree, and/or Sabi's private
call volume. Output manifests retain source/license/consent provenance.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import wave
from pathlib import Path
from typing import Any, Iterable

from training_data import is_short_response, load_records, stable_split, write_jsonl


AUDIO_SUFFIXES = (".wav", ".flac", ".mp3", ".ogg", ".m4a")


def _audio_duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wav:
                return wav.getnframes() / max(1, wav.getframerate())
        except (wave.Error, OSError):
            return 0.0
    return 0.0


def common_voice_rows(root: Path) -> list[dict[str, Any]]:
    """Filter an official English Common Voice export to Nigerian speakers."""
    candidates = [root / "validated.tsv", root / "train.tsv"]
    tsv_path = next((path for path in candidates if path.is_file()), None)
    if not tsv_path:
        raise FileNotFoundError(f"no validated.tsv or train.tsv under {root}")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with tsv_path.open(encoding="utf-8") as handle:
        for record in csv.DictReader(handle, delimiter="\t"):
            accent_evidence = " ".join(
                str(record.get(key) or "")
                for key in ("accent", "accents", "variant", "country", "locale")
            ).lower()
            if not (
                "nigeria" in accent_evidence
                or "nigerian" in accent_evidence
                or "en-ng" in accent_evidence
            ):
                continue
            relative = str(record.get("path") or "").strip()
            transcript = " ".join(str(record.get("sentence") or "").split())
            if not relative or not transcript or relative in seen:
                continue
            audio_path = (root / "clips" / relative).resolve()
            if not audio_path.is_file():
                continue
            seen.add(relative)
            speaker = str(record.get("client_id") or relative)
            duration = float(record.get("duration_ms") or 0.0) / 1000.0
            rows.append(
                {
                    "id": f"common-voice-{speaker[:16]}-{len(rows):07d}",
                    "audio_path": str(audio_path),
                    "transcript": transcript,
                    "split": stable_split(speaker),
                    "speaker_id": speaker,
                    "source": "nigerian_common_voice",
                    "license": "CC0-1.0",
                    "duration": duration,
                    "is_short_response": is_short_response(transcript, duration),
                    "accent_evidence": accent_evidence.strip(),
                }
            )
    return rows


def librispeech_rows(root: Path) -> list[dict[str, Any]]:
    """Index an OpenSLR LibriSpeech tree as the general-English retention set."""
    rows: list[dict[str, Any]] = []
    for transcript_path in sorted(root.rglob("*.trans.txt")):
        for line in transcript_path.read_text(encoding="utf-8").splitlines():
            utterance_id, separator, transcript = line.partition(" ")
            if not separator or not transcript.strip():
                continue
            audio_path = next(
                (
                    transcript_path.parent / f"{utterance_id}{suffix}"
                    for suffix in AUDIO_SUFFIXES
                    if (transcript_path.parent / f"{utterance_id}{suffix}").is_file()
                ),
                None,
            )
            if not audio_path:
                continue
            speaker = utterance_id.split("-", 1)[0]
            duration = _audio_duration(audio_path)
            rows.append(
                {
                    "id": f"librispeech-{utterance_id}",
                    "audio_path": str(audio_path.resolve()),
                    "transcript": " ".join(transcript.split()),
                    "split": stable_split(speaker),
                    "speaker_id": speaker,
                    "source": "general_english_retention",
                    "license": "CC-BY-4.0",
                    "duration": duration,
                    "is_short_response": is_short_response(transcript, duration),
                }
            )
    return rows


def _gold_audio_paths(path: Path | None) -> set[str]:
    if not path:
        return set()
    return {
        str(Path(str(record.get("audio_path") or "")).resolve())
        for record in load_records(path)
        if record.get("audio_path")
    }


def sabi_corrected_rows(root: Path, gold_manifest: Path | None) -> list[dict[str, Any]]:
    """Export human-approved, explicitly consented call-turn corrections."""
    held_out_audio = _gold_audio_paths(gold_manifest)
    rows: list[dict[str, Any]] = []
    for sidecar in sorted(root.glob("call_*.json")):
        try:
            call = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        call_uuid = str(call.get("call_uuid") or sidecar.stem.removeprefix("call_"))
        for turn in call.get("turns") or []:
            index = int(turn.get("turn_index", -1))
            user = turn.get("user") or {}
            correction = user.get("stt_correction") or {}
            if correction.get("consent_for_model_training") is not True:
                continue
            if str(correction.get("review_status") or "").lower() not in {"approved", "reviewed"}:
                continue
            transcript = " ".join(str(correction.get("transcript") or "").split())
            audio_value = str(user.get("audio_path") or "")
            audio_path = Path(audio_value)
            if not audio_path.is_absolute():
                audio_path = root / "call_turns" / call_uuid / f"user_turn_{index:02d}.wav"
            audio_path = audio_path.resolve()
            if not transcript or not audio_path.is_file() or str(audio_path) in held_out_audio:
                continue
            duration = float(user.get("audio_seconds") or _audio_duration(audio_path))
            rows.append(
                {
                    "id": f"sabi-{call_uuid}-turn-{index:02d}",
                    "audio_path": str(audio_path),
                    "transcript": transcript,
                    "split": "train",
                    "speaker_id": str(call.get("student_id") or call.get("phone_number") or call_uuid),
                    "source": "sabi_corrected",
                    "license": "SABI-PRIVATE-CONSENTED",
                    "duration": duration,
                    "is_short_response": is_short_response(transcript, duration),
                    "consent_for_model_training": True,
                    "review_status": "approved",
                    "reviewed_by": str(correction.get("reviewed_by") or ""),
                    "reviewed_at": correction.get("reviewed_at"),
                }
            )
    return rows


def _write(name: str, rows: Iterable[dict[str, Any]], output_dir: Path) -> int:
    materialized = list(rows)
    output_path = output_dir / f"{name}.jsonl"
    write_jsonl(output_path, materialized)
    print(f"{name}: {len(materialized)} rows -> {output_path}")
    return len(materialized)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--common-voice-root", type=Path)
    parser.add_argument("--librispeech-root", type=Path)
    parser.add_argument("--sabi-root", type=Path)
    parser.add_argument("--gold-manifest", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not any((args.common_voice_root, args.librispeech_root, args.sabi_root)):
        parser.error("provide at least one source root")
    if args.common_voice_root:
        _write("nigerian_common_voice", common_voice_rows(args.common_voice_root), args.output_dir)
    if args.librispeech_root:
        _write("general_english_retention", librispeech_rows(args.librispeech_root), args.output_dir)
    if args.sabi_root:
        _write(
            "sabi_corrected",
            sabi_corrected_rows(args.sabi_root, args.gold_manifest),
            args.output_dir,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
