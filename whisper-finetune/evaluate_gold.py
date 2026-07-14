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
import os
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from jiwer import wer
import httpx

for candidate in (Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[1] / "sabi-server"):
    if (candidate / "audio_cleaner.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from audio_cleaner import AudioCleaner


NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100",
}


def normalize(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(NUMBER_WORDS.get(token, token) for token in tokens)


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
    parser.add_argument(
        "--audio-variant",
        action="append",
        choices=("raw", "deepfilternet"),
        help="Evaluate raw and/or DeepFilterNet-cleaned audio (repeatable; default raw)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = json.loads(args.manifest.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest must be a non-empty JSON list")

    variants = args.audio_variant or ["raw"]
    report = {"manifest": str(args.manifest), "cases": len(cases), "models": {}}
    for label, model_path in args.model:
        groq_model = model_path.removeprefix("groq:") if model_path.startswith("groq:") else ""
        if groq_model:
            if not os.getenv("GROQ_API_KEY"):
                raise RuntimeError("GROQ_API_KEY is required for groq: model entries")
            model = None
        else:
            compute_type = "float16" if args.device == "cuda" else "int8"
            model = WhisperModel(model_path, device=args.device, compute_type=compute_type)
        for variant in variants:
            cleaner = AudioCleaner(enabled=variant == "deepfilternet")
            rows = []
            references = []
            hypotheses = []

            for case in cases:
                audio_path = Path(case["audio_path"])
                if not audio_path.is_file():
                    raise FileNotFoundError(audio_path)
                with cleaner.prepare(str(audio_path)) as (prepared_path, cleaning):
                    if groq_model:
                        with open(prepared_path, "rb") as audio_handle:
                            response = httpx.post(
                                "https://api.groq.com/openai/v1/audio/transcriptions",
                                headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                                files={"file": (Path(prepared_path).name, audio_handle, "audio/wav")},
                                data={
                                    "model": groq_model,
                                    "language": "en",
                                    "response_format": "verbose_json",
                                },
                                timeout=30,
                            )
                        response.raise_for_status()
                        payload = response.json()
                        heard = str(payload.get("text") or "").strip()
                        language_probability = payload.get("language_probability")
                    else:
                        segments, info = model.transcribe(
                            prepared_path, language="en", beam_size=5, vad_filter=False
                        )
                        heard = " ".join(segment.text.strip() for segment in segments).strip()
                        language_probability = info.language_probability
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
                        "language_probability": language_probability,
                        "audio_cleaning": cleaning,
                    }
                )

            exact = sum(row["exact"] for row in rows)
            report_label = label if len(variants) == 1 and variant == "raw" else f"{label}@{variant}"
            report["models"][report_label] = {
                "model": model_path,
                "audio_variant": variant,
                "exact": exact,
                "total": len(rows),
                "exact_accuracy": exact / len(rows),
                "wer": wer(references, hypotheses),
                "results": rows,
            }
        if model is not None:
            del model
        gc.collect()

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
