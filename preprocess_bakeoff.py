"""Does audio preprocessing help STT hear the right word?

For each ground-truth-labeled child turn, build three versions of the clip —
  raw      : the original 8 kHz telephony clip
  eq       : high-pass 100 Hz (kill hum) + dynaudnorm AGC (lift quiet voices)
             + a presence boost at ~3.2 kHz (sharpen th/f/t consonants)
  denoise  : spectral-gating noise reduction (noisereduce)
— and run all four STT stacks (Groq large-v3, local large-v3, large-v3+VAD,
Distil-Whisper) on each, then score against the known word.

Read-only; writes only to /shared/audio/pre_tmp + the results JSON. Container-run.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import numpy as np
from scipy.io import wavfile
import noisereduce as nr
import httpx
from faster_whisper import WhisperModel

VOL = "/shared/audio"
TMP = f"{VOL}/pre_tmp"
GROQ_KEY = open("/run/secrets/GROQ_API_KEY").read().strip()

GROUND_TRUTH = {
    "e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be": {1: "my name is gideon", 2: "my name is gideon"},
    "be48a49b-8121-476f-bb9b-83d849a135f0": {0: "my name is oluremi", 4: "thirty", 5: "thirty", 8: "fifteen", 9: "thirty"},
}

EQ_CHAIN = "highpass=f=100,dynaudnorm=g=7,equalizer=f=3200:t=q:w=1.8:g=6"


def make_eq(src: str, dst: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-af", EQ_CHAIN, "-ar", "16000", "-ac", "1", dst],
        check=True, capture_output=True,
    )


def make_denoise(src: str, dst: str) -> None:
    sr, data = wavfile.read(src)
    y = data.astype(np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if data.dtype == np.int16:
        y /= 32768.0
    reduced = nr.reduce_noise(y=y, sr=sr, stationary=False)
    wavfile.write(dst, sr, (np.clip(reduced, -1, 1) * 32767).astype(np.int16))


def groq_tx(path: str) -> str:
    with open(path, "rb") as f:
        r = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": (os.path.basename(path), f, "audio/wav")},
            data={"model": "whisper-large-v3", "response_format": "json", "language": "en"},
            timeout=30,
        )
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


print("[pre] loading local models ...", flush=True)
LV3 = WhisperModel("large-v3", device="cuda", compute_type="float16")
DISTIL = WhisperModel("distil-large-v3", device="cuda", compute_type="float16")


def fw(model, path, vad: bool) -> str:
    kw = dict(language="en", beam_size=5)
    if vad:
        kw.update(vad_filter=True, no_speech_threshold=0.6, vad_parameters=dict(min_silence_duration_ms=600))
    segs, _ = model.transcribe(path, **kw)
    return " ".join(s.text.strip() for s in segs).strip()


def run_stacks(path: str) -> dict:
    return {
        "groq": groq_tx(path),
        "lv3": fw(LV3, path, False),
        "lv3_vad": fw(LV3, path, True),
        "distil": fw(DISTIL, path, False),
    }


def hit(text: str, gt: str) -> bool:
    """Lenient scoring: did the key content word land? (name or number)."""
    t = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
    key = gt.split()[-1] if gt.startswith("my name is") else gt  # gideon / oluremi / thirty / fifteen
    return key in t.split()


os.makedirs(TMP, exist_ok=True)
out: dict = {}
for cu, turns in GROUND_TRUTH.items():
    for idx, gt in sorted(turns.items()):
        raw = f"{VOL}/call_turns/{cu}/user_turn_{idx:02d}.wav"
        eqw = f"{TMP}/{cu[:8]}_{idx}_eq.wav"
        dnw = f"{TMP}/{cu[:8]}_{idx}_dn.wav"
        make_eq(raw, eqw)
        make_denoise(raw, dnw)
        rec = {"ground_truth": gt, "raw": run_stacks(raw), "eq": run_stacks(eqw), "denoise": run_stacks(dnw)}
        # attach per-cell hit flags
        for variant in ("raw", "eq", "denoise"):
            rec[variant] = {k: {"text": v, "hit": hit(v, gt)} for k, v in rec[variant].items()}
        out.setdefault(cu, {})[str(idx)] = rec
        print(f"\n=== {cu[:8]} turn {idx}  truth={gt!r} ===", flush=True)
        for variant in ("raw", "eq", "denoise"):
            marks = " ".join(f"{k}={'✓' if rec[variant][k]['hit'] else '·'}" for k in ("groq", "lv3", "lv3_vad", "distil"))
            print(f"  {variant:8} {marks}   " + " | ".join(f"{k}:{rec[variant][k]['text']!r}" for k in ("groq", "lv3", "lv3_vad", "distil")), flush=True)

json.dump(out, open(f"{VOL}/preprocess_bakeoff.json", "w"), ensure_ascii=True, indent=2)
print(f"\n[pre] wrote {VOL}/preprocess_bakeoff.json", flush=True)
