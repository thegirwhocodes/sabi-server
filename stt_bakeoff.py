"""STT bake-off: re-transcribe saved call clips through several models/stacks.

For each given call UUID, this walks every saved CHILD turn clip and runs it
through a set of speech-to-text stacks, recording what each one heard plus its
latency. The production Groq transcript (already stored on the call) is carried
along as the baseline. Output is a single self-contained JSON (transcripts +
base64 of each clip) that a separate dashboard renders side by side.

Read-only: never mutates the original call JSON or the live phone pipeline.

Stacks (no external keys, no torch needed):
    groq         Groq Whisper — production baseline (reused from the call JSON)
    lv3          faster-whisper large-v3 (full model, local)
    lv3_vad      faster-whisper large-v3 + Silero VAD hallucination guard
                 (vad_filter, no_speech_threshold=0.6, min_silence 600ms)
    distil       faster-whisper distil-large-v3 (noisy-condition specialist)

Deepgram Nova-3, Google Chirp, and a DeepFilterNet denoiser front-end are the
other recommended options but need API keys / a torch install; they are listed
in the output as "not run" so the dashboard can show the gap.

Usage (inside the sabi-server container):
    python /app/stt_bakeoff.py <device> <out.json> <call_uuid> [<call_uuid> ...]
    device: cpu | cuda
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

from call_admin import shared_audio_dir, call_turn_dir
from faster_whisper import WhisperModel

STACKS_PLANNED = [
    {"key": "groq", "label": "Groq Whisper (production)", "note": "whisper-large-v3-turbo, cloud — the live baseline"},
    {"key": "lv3", "label": "Whisper large-v3 (local)", "note": "full large-v3, not the turbo Groq runs"},
    {"key": "lv3_vad", "label": "Whisper large-v3 + Silero VAD", "note": "vad_filter + no_speech_threshold=0.6, min_silence 600ms"},
    {"key": "distil", "label": "Distil-Whisper large-v3", "note": "smaller/faster; won the noisy Parliamentary test in research"},
]
STACKS_UNAVAILABLE = [
    {"label": "Deepgram Nova-3", "why": "needs DEEPGRAM_API_KEY (free tier available)"},
    {"label": "Google Chirp / USM", "why": "needs a Google Cloud service account"},
    {"label": "DeepFilterNet → Whisper", "why": "needs a ~2GB torch + deepfilternet install"},
    {"label": "Intron Sahara", "why": "integrator access not working yet"},
]


def _b64_clip(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    return "data:audio/wav;base64," + base64.b64encode(raw).decode("ascii")


def _transcribe(model: WhisperModel, path: str, *, vad: bool) -> tuple[str, int]:
    start = time.time()
    kwargs = dict(language="en", beam_size=5)
    if vad:
        kwargs["vad_filter"] = True
        kwargs["no_speech_threshold"] = 0.6
        kwargs["vad_parameters"] = dict(min_silence_duration_ms=600)
    segments, _info = model.transcribe(path, **kwargs)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text, int((time.time() - start) * 1000)


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    device = sys.argv[1].strip().lower()
    out_path = Path(sys.argv[2])
    call_uuids = sys.argv[3:]
    compute = "float16" if device == "cuda" else "int8"

    print(f"[bakeoff] device={device} compute={compute} calls={len(call_uuids)}", flush=True)
    print("[bakeoff] loading large-v3 ...", flush=True)
    lv3 = WhisperModel("large-v3", device=device, compute_type=compute)
    distil = None
    try:
        print("[bakeoff] loading distil-large-v3 ...", flush=True)
        distil = WhisperModel("distil-large-v3", device=device, compute_type=compute)
    except Exception as exc:  # noqa: BLE001
        print(f"[bakeoff] distil-large-v3 unavailable ({exc}); skipping that stack", flush=True)

    stacks = [s for s in STACKS_PLANNED if not (s["key"] == "distil" and distil is None)]
    root = shared_audio_dir()
    calls_out = []

    for uuid in call_uuids:
        sidecar = root / f"call_{uuid}.json"
        orig = json.loads(sidecar.read_text())
        turn_dir = call_turn_dir(uuid)
        turns_out = []
        prev_assistant = ""
        print(f"[bakeoff] call {uuid}: {len(orig.get('turns', []))} turns", flush=True)

        for turn in orig.get("turns", []):
            idx = int(turn.get("turn_index", len(turns_out)))
            user = turn.get("user") or {}
            flags = turn.get("flags") or []
            mode = "literacy" if "literacy_stt" in flags else "numeric" if "numeric_stt" in flags else "general"
            clip = turn_dir / f"user_turn_{idx:02d}.wav"

            results = {"groq": {"text": user.get("stt_transcript", ""), "latency_ms": None}}
            if clip.exists():
                t, ms = _transcribe(lv3, str(clip), vad=False)
                results["lv3"] = {"text": t, "latency_ms": ms}
                t, ms = _transcribe(lv3, str(clip), vad=True)
                results["lv3_vad"] = {"text": t, "latency_ms": ms}
                if distil is not None:
                    t, ms = _transcribe(distil, str(clip), vad=False)
                    results["distil"] = {"text": t, "latency_ms": ms}
                print(f"  turn {idx} ({mode}): groq={results['groq']['text']!r}  lv3={results['lv3']['text']!r}", flush=True)

            turns_out.append({
                "turn_index": idx,
                "mode": mode,
                "clip_seconds": user.get("audio_seconds"),
                "assistant_prompt": prev_assistant,
                "clip_b64": _b64_clip(clip) if clip.exists() else "",
                "results": results,
            })
            prev_assistant = (turn.get("assistant") or {}).get("tts_text") or ""

        calls_out.append({
            "call_uuid": uuid,
            "phone_number": orig.get("phone_number"),
            "mode": orig.get("mode"),
            "duration_seconds": orig.get("duration_seconds"),
            "end_reason": orig.get("end_reason"),
            "quality_flags": orig.get("quality_flags"),
            "created_at": orig.get("created_at"),
            "turns": turns_out,
        })

    payload = {
        "generated_at": int(time.time()),
        "device": device,
        "stacks": stacks,
        "stacks_unavailable": STACKS_UNAVAILABLE,
        "calls": calls_out,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=True))
    print(f"[bakeoff] wrote {out_path} ({out_path.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
