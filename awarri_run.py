"""Run Awarri's NCAIR1/NigerianAccentedEnglish (fine-tuned Whisper-Small) over
the saved child clips of one or more calls, so it can be added to the STT
bake-off comparison.

Runs on the server HOST (not the container) inside the stt-compare venv, reading
clips straight from the shared-audio Docker volume. CPU only — no GPU contention.

Usage:
    python awarri_run.py <model_id> <volume_data_dir> <out.json> <call_uuid> [...]

    model_id: NCAIR1/NigerianAccentedEnglish (gated, needs HF token)
              rishabbahal/whisper-small-nigerian-accent (ungated proxy)
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import librosa
import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor

TURN_RE = re.compile(r"user_turn_(\d+)\.wav$")


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    model_id = sys.argv[1]
    data_dir = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    call_uuids = sys.argv[4:]

    # NOTE: the transformers pipeline() helper hangs on this stack (transformers
    # 5.13), so load the processor + model directly and call generate ourselves.
    torch.set_num_threads(4)
    print(f"[awarri] loading {model_id} (Whisper-Small, CPU) ...", flush=True)
    proc = WhisperProcessor.from_pretrained(model_id)
    model = WhisperForConditionalGeneration.from_pretrained(model_id)
    model.eval()

    def transcribe(audio) -> str:
        feats = proc(audio, sampling_rate=16000, return_tensors="pt").input_features
        with torch.no_grad():
            ids = model.generate(feats, language="en", task="transcribe", max_new_tokens=128)
        return proc.batch_decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()

    results: dict[str, dict[str, dict]] = {}
    for uuid in call_uuids:
        turn_dir = data_dir / "call_turns" / uuid
        clips = sorted(
            turn_dir.glob("user_turn_*.wav"),
            key=lambda p: int(TURN_RE.search(p.name).group(1)),
        )
        print(f"[awarri] call {uuid}: {len(clips)} child clips", flush=True)
        per_call: dict[str, dict] = {}
        for clip in clips:
            idx = int(TURN_RE.search(clip.name).group(1))
            audio, _sr = librosa.load(str(clip), sr=16000, mono=True)
            start = time.time()
            try:
                text = transcribe(audio)
            except Exception as exc:  # noqa: BLE001
                text = f"[error: {exc}]"
            ms = int((time.time() - start) * 1000)
            per_call[str(idx)] = {"text": text, "latency_ms": ms}
            print(f"  turn {idx}: {text!r} ({ms} ms)", flush=True)
        results[uuid] = per_call

    out_path.write_text(json.dumps(results, ensure_ascii=True, indent=2))
    print(f"[awarri] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
