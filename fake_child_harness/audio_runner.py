from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

from .audio_mixer import build_phone_noise_case
from .child_simulator import SimulatedTurn
from .evaluator import TurnEvaluation, evaluate_turn, summarize_evaluations
from .report import write_regression_case_suggestions


def run_audio_harness(
    *,
    cases_path: Path,
    output_root: Path,
    seed: int,
    transcribe: bool,
    stt_provider: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    run_id = f"audiofake-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    case_rows = load_cases(cases_path)
    if limit is not None:
        case_rows = case_rows[:limit]

    stt = _build_stt(stt_provider) if transcribe else None
    audio_cases: list[dict[str, Any]] = []
    turns: list[SimulatedTurn] = []
    evaluations: list[TurnEvaluation] = []

    for index, case in enumerate(case_rows, start=1):
        audio_case = _prepare_audio_case(
            case,
            index=index,
            cases_dir=cases_path.parent,
            run_dir=run_dir,
            seed=seed,
        )
        stt_result = _transcribe_or_use_fixture(
            case,
            audio_path=audio_case.get("mixed_wav"),
            transcribe=transcribe,
            stt=stt,
        )
        turn = _turn_from_case(case, index=index, stt_result=stt_result)
        audio_case["stt"] = stt_result
        audio_case["evaluation_input"] = turn.to_dict()
        audio_cases.append(audio_case)
        turns.append(turn)
        evaluations.append(evaluate_turn(turn))

    summary = summarize_evaluations(evaluations)
    summary["audio_cases"] = len(audio_cases)
    summary["transcribed_cases"] = sum(1 for case in audio_cases if case["stt"].get("source") == "transcribed")

    metadata = {
        "run_id": run_id,
        "mode": "audio",
        "cases_path": str(cases_path),
        "seed": seed,
        "transcribe": transcribe,
        "stt_provider": stt_provider or "fixture",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _write_json(run_dir / "run_summary.json", {"metadata": metadata, "summary": summary})
    _write_jsonl(run_dir / "audio_cases.jsonl", audio_cases)
    _write_jsonl(run_dir / "turns.jsonl", [turn.to_dict() for turn in turns])
    _write_jsonl(run_dir / "evaluations.jsonl", [item.to_dict() for item in evaluations])
    _write_jsonl(run_dir / "failures.jsonl", [item.to_dict() for item in evaluations if item.failure_type])
    write_audio_report(run_dir / "audio_report.md", run_id=run_id, metadata=metadata, summary=summary, audio_cases=audio_cases, evaluations=evaluations)
    write_regression_case_suggestions(run_dir / "regression_cases_to_add.md", evaluations)
    return {"run_dir": str(run_dir), "metadata": metadata, "summary": summary}


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("cases"), list):
        rows = data["cases"]
    else:
        raise ValueError("audio cases file must be a JSON list or an object with a 'cases' list")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"case {index} must be an object")
        missing = [key for key in ("child_id", "prompt", "item_id", "expected_answers", "child_answer_text") if key not in row]
        if missing:
            raise ValueError(f"case {index} missing required keys: {', '.join(missing)}")
    return rows


def write_audio_report(
    path: Path,
    *,
    run_id: str,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    audio_cases: list[dict[str, Any]],
    evaluations: list[TurnEvaluation],
) -> None:
    failure_counts = Counter(item.failure_type for item in evaluations if item.failure_type)
    noise_counts = Counter(item.noise_level for item in evaluations)
    provider_counts = Counter((case.get("stt") or {}).get("provider", "fixture") for case in audio_cases)
    source_counts = Counter((case.get("stt") or {}).get("source", "unknown") for case in audio_cases)
    error_counts = Counter(
        (case.get("stt") or {}).get("error_type")
        for case in audio_cases
        if (case.get("stt") or {}).get("source") == "transcribe_error"
    )
    release_blockers = [item for item in evaluations if item.severity == "release_blocking"]

    lines = [
        f"# Sabi audio fake-child harness report: {run_id}",
        "",
        "## Run",
        "",
        f"- Cases: {len(audio_cases)}",
        f"- Transcribe real audio: {metadata['transcribe']}",
        f"- STT provider: {metadata['stt_provider']}",
        f"- Noise levels: {_format_counter(noise_counts)}",
        f"- STT sources/providers: {_format_counter(provider_counts)}",
        f"- STT result sources: {_format_counter(source_counts)}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Failure Types", ""])
    if failure_counts:
        for key, value in sorted(failure_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "## STT Errors", ""])
    if error_counts:
        for key, value in sorted(error_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "## First Release Blockers", ""])
    if release_blockers:
        for item in release_blockers[:25]:
            lines.append(
                "- "
                f"{item.child_id} call {item.call_index} turn {item.turn_index} "
                f"{item.item_id}: {item.failure_type}; "
                f"child='{item.child_answer_text}' stt='{item.stt_text}'"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Audio Artifacts", ""])
    for case in audio_cases[:50]:
        stt = case.get("stt") or {}
        error = f" error={stt.get('error_type')}: {stt.get('error')}" if stt.get("error_type") else ""
        lines.append(
            "- "
            f"{case['case_id']}: {case.get('mixed_wav') or 'no audio'} "
            f"noise={case.get('noise_level')} stt={stt.get('text', '')!r}{error}"
        )

    path.write_text("\n".join(lines) + "\n")


def _prepare_audio_case(
    case: dict[str, Any],
    *,
    index: int,
    cases_dir: Path,
    run_dir: Path,
    seed: int,
) -> dict[str, Any]:
    case_id = _case_id(case, index)
    noise_level = str(case.get("noise_level") or "lagos_market")
    audio_case: dict[str, Any] = {
        "case_id": case_id,
        "child_id": case["child_id"],
        "call_index": int(case.get("call_index", 1)),
        "turn_index": int(case.get("turn_index", index)),
        "item_id": case["item_id"],
        "noise_level": noise_level,
    }

    if case.get("speech_wav"):
        speech_wav = _resolve_path(cases_dir, case["speech_wav"])
        noise_wav = _resolve_path(cases_dir, case["noise_wav"]) if case.get("noise_wav") else None
        output_wav = run_dir / "mixed_audio" / f"{case_id}.wav"
        mix_metadata = build_phone_noise_case(
            speech_wav=speech_wav,
            noise_wav=noise_wav,
            output_wav=output_wav,
            noise_level=noise_level,
            seed=seed + index,
        )
        audio_case.update(mix_metadata)
        audio_case["mixed_wav"] = str(output_wav)
        return audio_case

    if case.get("mixed_wav"):
        mixed_wav = _resolve_path(cases_dir, case["mixed_wav"])
        audio_case["mixed_wav"] = str(mixed_wav)
        audio_case["speech_wav"] = None
        audio_case["noise_wav"] = case.get("noise_wav")
        return audio_case

    audio_case["mixed_wav"] = None
    audio_case["speech_wav"] = None
    audio_case["noise_wav"] = case.get("noise_wav")
    return audio_case


def _transcribe_or_use_fixture(
    case: dict[str, Any],
    *,
    audio_path: str | None,
    transcribe: bool,
    stt: Any,
) -> dict[str, Any]:
    if transcribe:
        if not audio_path:
            raise ValueError("transcribe=true requires each case to provide speech_wav or mixed_wav")
        try:
            result = stt.transcribe(
                audio_path,
                mode=str(case.get("mode") or "general"),
                context=str(case.get("context") or case.get("prompt") or ""),
            )
        except Exception as exc:
            return {
                "source": "transcribe_error",
                "text": "",
                "confidence": 0.0,
                "provider": str(getattr(stt, "_provider", "unknown") or "unknown"),
                "error_type": exc.__class__.__name__,
                "error": str(exc).splitlines()[-1][:500],
                "raw": {},
            }
        return {
            "source": "transcribed",
            "text": str(result.get("text") or ""),
            "confidence": float(result.get("confidence") or 0.0),
            "provider": str(result.get("provider") or "unknown"),
            "raw": result,
        }

    return {
        "source": "fixture",
        "text": str(case.get("stt_text") if case.get("stt_text") is not None else case["child_answer_text"]),
        "confidence": float(case.get("stt_confidence", 1.0)),
        "provider": "fixture",
        "raw": {},
    }


def _turn_from_case(case: dict[str, Any], *, index: int, stt_result: dict[str, Any]) -> SimulatedTurn:
    expected_answers = tuple(str(value) for value in case["expected_answers"])
    notes = list(case.get("notes") or [])
    notes.append(f"audio_stt_source:{stt_result.get('source')}")
    notes.append(f"audio_stt_provider:{stt_result.get('provider')}")
    if stt_result.get("source") == "transcribe_error":
        notes.append(f"stt_error:{stt_result.get('error_type')}")
    return SimulatedTurn(
        child_id=str(case["child_id"]),
        call_index=int(case.get("call_index", 1)),
        turn_index=int(case.get("turn_index", index)),
        prompt=str(case["prompt"]),
        item_id=str(case["item_id"]),
        expected_answers=expected_answers,
        ground_truth_correct=bool(case.get("ground_truth_correct", True)),
        child_answer_text=str(case["child_answer_text"]),
        stt_text=str(stt_result.get("text") or ""),
        noise_level=str(case.get("noise_level") or "lagos_market"),
        stt_confidence=float(stt_result.get("confidence") or 0.0),
        notes=tuple(notes),
    )


def _build_stt(provider: str | None) -> Any:
    _load_dotenv_if_present()
    from stt import SpeechToText

    return SpeechToText(provider=provider, literacy_provider=provider) if provider else SpeechToText()


def _load_dotenv_if_present(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE lines for local harness runs without printing secrets."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_path(base_dir: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = (base_dir / path).resolve()
    if candidate.exists():
        return candidate
    return Path(value).resolve()


def _case_id(case: dict[str, Any], index: int) -> str:
    raw = str(case.get("case_id") or f"{case.get('child_id', 'child')}-{case.get('item_id', 'item')}-{index}")
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-") or f"case-{index}"


def _format_counter(counter: Counter[str | None]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key or 'none'}={value}" for key, value in sorted(counter.items(), key=lambda item: str(item[0])))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run audio-backed Sabi fake-child cases.")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("../outputs/fake-child-harness/audio-runs"))
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--transcribe", action="store_true", help="Run real STT on mixed WAVs instead of fixture stt_text.")
    parser.add_argument("--stt-provider", help="Optional SpeechToText provider override, e.g. groq, local, intron_first.")
    args = parser.parse_args()

    result = run_audio_harness(
        cases_path=args.cases,
        output_root=args.output_root,
        seed=args.seed,
        transcribe=args.transcribe,
        stt_provider=args.stt_provider,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
