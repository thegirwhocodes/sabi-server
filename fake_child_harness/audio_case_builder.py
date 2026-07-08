from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable


DEFAULT_NOISE_WAV = Path("../outputs/fake-child-harness/assets/audio/freesound-411123-sabo-yaba-16k.wav")
DEFAULT_TURNS = Path("../outputs/fake-child-harness/full-course-runs/fullcoursefake-20260706T202700923023Z/full_course_turns.jsonl")
DEFAULT_OUTPUT_ROOT = Path("../outputs/fake-child-harness/audio-matrix-cases")
DEFAULT_NOISE_LEVELS = ("lagos_market", "brutal_market")


def build_audio_matrix_cases(
    *,
    turns_path: Path,
    noise_wav: Path,
    output_root: Path,
    limit: int,
    noise_levels: Iterable[str] = DEFAULT_NOISE_LEVELS,
    seed_label: str = "20260706",
) -> dict[str, Any]:
    run_id = f"audiomatrixcases-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = output_root / run_id
    speech_dir = run_dir / "speech"
    speech_dir.mkdir(parents=True, exist_ok=False)

    turns = _select_turns(load_turns(turns_path), limit=limit)
    cases: list[dict[str, Any]] = []
    noise_levels = tuple(noise_levels) or DEFAULT_NOISE_LEVELS
    for index, turn in enumerate(turns, start=1):
        case_id_base = _case_id(turn, index)
        speech_wav = speech_dir / f"{case_id_base}.wav"
        speech_text = str(turn.get("child_answer_text") or "").strip()
        synthesize_speech_wav(speech_text, speech_wav)
        for level in noise_levels:
            case_id = f"{case_id_base}-{level}"
            cases.append(
                {
                    "case_id": case_id,
                    "child_id": str(turn.get("child_id") or "unknown-child"),
                    "call_index": int(turn.get("call_index") or 1),
                    "turn_index": int(turn.get("turn_index") or index),
                    "prompt": str(turn.get("prompt") or ""),
                    "item_id": str(turn.get("item_id") or "unknown_item"),
                    "expected_answers": [str(value) for value in (turn.get("expected_answers") or [])],
                    "ground_truth_correct": bool(turn.get("ground_truth_correct")),
                    "child_answer_text": speech_text,
                    "stt_text": str(turn.get("stt_text") if turn.get("stt_text") is not None else speech_text),
                    "speech_wav": str(speech_wav.resolve()),
                    "noise_wav": str(noise_wav.resolve()),
                    "noise_level": level,
                    "mode": "literacy" if str(turn.get("course") or "").lower() == "literacy" else "general",
                    "context": str(turn.get("prompt") or ""),
                    "notes": [
                        "generated_from_full_course_turn",
                        "synthetic_espeak_or_say_voice_not_child_voice",
                        f"source_turns:{turns_path}",
                        f"source_call_type:{turn.get('call_type')}",
                        f"source_course:{turn.get('course')}",
                    ],
                }
            )

    payload = {
        "version": 1,
        "description": (
            "Generated audio matrix cases from full-course fake-child turns. "
            "Speech is local synthetic TTS, then audio_runner phone-codes and mixes it with raw Yaba/Sabo Lagos noise."
        ),
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "turns_path": str(turns_path),
            "noise_wav": str(noise_wav),
            "seed_label": seed_label,
            "selected_turns": len(turns),
            "cases": len(cases),
            "noise_levels": list(noise_levels),
        },
        "cases": cases,
    }
    cases_path = run_dir / "audio_cases.generated.json"
    cases_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (run_dir / "selected_turns.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in turns))
    return {
        "run_dir": str(run_dir),
        "cases_path": str(cases_path),
        "selected_turns": len(turns),
        "cases": len(cases),
    }


def load_turns(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{line_number} is not an object")
            rows.append(data)
    return rows


def synthesize_speech_wav(text: str, output_wav: Path) -> None:
    if not text:
        raise ValueError("cannot synthesize empty speech text")
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    espeak = shutil.which("espeak")
    if espeak:
        subprocess.run(
            [espeak, "-s", "145", "-v", "en", "-w", str(output_wav), text],
            check=True,
            capture_output=True,
        )
        return

    say = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")
    if say and ffmpeg:
        aiff_path = output_wav.with_suffix(".aiff")
        subprocess.run([say, "-o", str(aiff_path), text], check=True, capture_output=True)
        subprocess.run(
            [ffmpeg, "-y", "-i", str(aiff_path), "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(output_wav)],
            check=True,
            capture_output=True,
        )
        try:
            aiff_path.unlink()
        except OSError:
            pass
        return

    raise RuntimeError("Need either espeak or say+ffmpeg to generate speech WAVs")


def _select_turns(turns: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    candidates = [turn for turn in turns if _usable_turn(turn)]
    buckets: dict[tuple[str, str, bool], list[dict[str, Any]]] = defaultdict(list)
    for turn in candidates:
        buckets[
            (
                str(turn.get("course") or "unknown"),
                _skillish_item(str(turn.get("item_id") or "")),
                bool(turn.get("ground_truth_correct")),
            )
        ].append(turn)

    selected: list[dict[str, Any]] = []
    by_course = {
        "numeracy": [key for key in sorted(buckets) if key[0] == "numeracy"],
        "literacy": [key for key in sorted(buckets) if key[0] == "literacy"],
    }
    quotas = {
        "numeracy": max(1, limit // 2),
        "literacy": max(1, limit - max(1, limit // 2)),
    }
    for course in ("numeracy", "literacy"):
        for key in by_course[course]:
            bucket = buckets[key]
            if bucket:
                selected.append(bucket[0])
            if sum(1 for row in selected if row.get("course") == course) >= quotas[course]:
                break
    if len(selected) >= limit:
        return selected[:limit]

    for key in sorted(buckets):
        bucket = buckets[key]
        if bucket and all(row is not bucket[0] for row in selected):
            selected.append(bucket[0])
        if len(selected) >= limit:
            return selected[:limit]

    # Fill any remaining slots with deterministic spread through the rest.
    seen = {id(row) for row in selected}
    stride = max(1, len(candidates) // max(1, limit * 3))
    for turn in candidates[::stride]:
        if id(turn) in seen:
            continue
        selected.append(turn)
        seen.add(id(turn))
        if len(selected) >= limit:
            break
    return selected[:limit]


def _usable_turn(turn: dict[str, Any]) -> bool:
    answer = str(turn.get("child_answer_text") or "").strip()
    if len(answer) < 2:
        return False
    if answer.lower() in {"", "i don't know", "i dont know"}:
        return False
    expected = turn.get("expected_answers") or []
    if not isinstance(expected, list) or not expected:
        return False
    return bool(turn.get("prompt") and turn.get("item_id"))


def _skillish_item(item_id: str) -> str:
    if item_id.startswith("lit_"):
        parts = item_id.split("_")
        return "_".join(parts[:3]) if len(parts) >= 3 else item_id
    if "_" in item_id:
        return item_id.split("_", 1)[0]
    return item_id


def _case_id(turn: dict[str, Any], index: int) -> str:
    raw = "-".join(
        [
            str(index).zfill(3),
            str(turn.get("child_id") or "child"),
            str(turn.get("call_index") or "call"),
            str(turn.get("turn_index") or "turn"),
            str(turn.get("item_id") or "item"),
        ]
    )
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-") or f"case-{index:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build audio matrix cases from fake-child full-course turns.")
    parser.add_argument("--turns", type=Path, default=DEFAULT_TURNS)
    parser.add_argument("--noise-wav", type=Path, default=DEFAULT_NOISE_WAV)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--noise-levels", default=",".join(DEFAULT_NOISE_LEVELS))
    args = parser.parse_args()

    result = build_audio_matrix_cases(
        turns_path=args.turns,
        noise_wav=args.noise_wav,
        output_root=args.output_root,
        limit=args.limit,
        noise_levels=[value.strip() for value in args.noise_levels.split(",") if value.strip()],
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
