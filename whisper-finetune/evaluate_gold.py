#!/usr/bin/env python3
"""Evaluate faster-whisper models on a private, held-out Sabi call manifest.

Manifest format (keep the real file off GitHub):
[
  {"id": "call-a-turn-00", "audio_path": "/absolute/clip.wav", "truth": "hello"}
]

Example:
  python evaluate_gold.py gold.json \
    --model base=small --model candidate=/path/to/candidate/ct2 --device cuda
"""

from __future__ import annotations

import argparse
import gc
import json
import re
from pathlib import Path

from faster_whisper import WhisperModel
from jiwer import wer


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def parse_model(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("models must use LABEL=MODEL_OR_PATH")
    label, model = value.split("=", 1)
    if not label or not model:
        raise argparse.ArgumentTypeError("models must use LABEL=MODEL_OR_PATH")
    return label, model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model", action="append", type=parse_model, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = json.loads(args.manifest.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest must be a non-empty JSON list")

    report = {"manifest": str(args.manifest), "cases": len(cases), "models": {}}
    for label, model_path in args.model:
        compute_type = "float16" if args.device == "cuda" else "int8"
        model = WhisperModel(model_path, device=args.device, compute_type=compute_type)
        rows = []
        references = []
        hypotheses = []

        for case in cases:
            audio_path = Path(case["audio_path"])
            if not audio_path.is_file():
                raise FileNotFoundError(audio_path)
            segments, info = model.transcribe(
                str(audio_path), language="en", beam_size=5, vad_filter=False
            )
            heard = " ".join(segment.text.strip() for segment in segments).strip()
            truth_norm = normalize(case["truth"])
            heard_norm = normalize(heard)
            references.append(truth_norm)
            hypotheses.append(heard_norm)
            rows.append(
                {
                    "id": case["id"],
                    "truth": case["truth"],
                    "heard": heard,
                    "exact": heard_norm == truth_norm,
                    "language_probability": info.language_probability,
                }
            )

        exact = sum(row["exact"] for row in rows)
        report["models"][label] = {
            "model": model_path,
            "exact": exact,
            "total": len(rows),
            "exact_accuracy": exact / len(rows),
            "wer": wer(references, hypotheses),
            "results": rows,
        }
        del model
        gc.collect()

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
