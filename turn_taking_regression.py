#!/usr/bin/env python3
"""Regression probes for Sabi's self-hosted managed-turn replacement.

Run inside the production image so the pinned Silero and Smart Turn ONNX
models are exercised, not mocked.  The tracked Naomi reference recording is a
stable speech fixture; generated zero PCM covers the no-speech path.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

from turn_taking import (
    INTERRUPTION_ECHO_THRESHOLD,
    SMART_TURN_MODEL_PATH,
    get_managed_turn_detector,
)


ROOT = Path(__file__).resolve().parent
SPEECH_FIXTURE = ROOT / "chatterbox-tts" / "reference_audio" / "naomi.wav"


def check(name: str, ok: bool, detail: object) -> bool:
    print(f"{'PASS' if ok else 'FAIL'} {name} - {json.dumps(detail, default=str, sort_keys=True)}")
    return ok


def load_pcm8k(path: Path, max_seconds: float = 3.0) -> bytes:
    import numpy as np

    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.readframes(min(wav.getnframes(), int(rate * max_seconds)))
    if width != 2:
        raise ValueError(f"unsupported sample width: {width}")
    if channels < 1:
        raise ValueError(f"unsupported channel count: {channels}")
    samples = np.frombuffer(frames, dtype="<i2").reshape(-1, channels).mean(axis=1)
    if rate != 8000 and samples.size:
        target_size = max(1, int(round(samples.size * 8000 / rate)))
        positions = np.linspace(0, samples.size - 1, target_size)
        samples = np.interp(positions, np.arange(samples.size), samples)
    return np.clip(samples, -32768, 32767).astype("<i2").tobytes()


def main() -> int:
    detector = get_managed_turn_detector()
    speech_pcm = load_pcm8k(SPEECH_FIXTURE)
    silence_pcm = bytes(len(speech_pcm))

    silence = detector.listening_speech(silence_pcm)
    speech = detector.listening_speech(speech_pcm)
    echo_similarity = detector.echo_similarity(speech_pcm, speech_pcm)
    clean_similarity = detector.echo_similarity(speech_pcm, silence_pcm)
    echo_decision = detector.evaluate_interruption(speech_pcm, speech_pcm)
    clean_decision = detector.evaluate_interruption(speech_pcm, silence_pcm)
    endpoint = detector.endpoint_complete(speech_pcm)

    results = [
        check(
            "smart_turn_model_is_pinned_in_image",
            SMART_TURN_MODEL_PATH.is_file(),
            {"path": SMART_TURN_MODEL_PATH, "size": SMART_TURN_MODEL_PATH.stat().st_size if SMART_TURN_MODEL_PATH.is_file() else 0},
        ),
        check("silence_is_not_speech", not silence.accepted, silence.log_fields()),
        check("tracked_human_voice_is_speech", speech.accepted, speech.log_fields()),
        check(
            "outbound_playback_reference_matches_echo",
            echo_similarity >= INTERRUPTION_ECHO_THRESHOLD,
            {"similarity": echo_similarity, "threshold": INTERRUPTION_ECHO_THRESHOLD},
        ),
        check(
            "silence_reference_does_not_match_voice",
            clean_similarity < INTERRUPTION_ECHO_THRESHOLD,
            {"similarity": clean_similarity, "threshold": INTERRUPTION_ECHO_THRESHOLD},
        ),
        check("matched_playback_is_rejected", not echo_decision.accepted and echo_decision.reason == "acoustic_echo", echo_decision.log_fields()),
        check("foreground_voice_can_interrupt", clean_decision.accepted, clean_decision.log_fields()),
        check(
            "smart_turn_returns_bounded_probability",
            endpoint.available and endpoint.probability is not None and 0.0 <= endpoint.probability <= 1.0,
            endpoint.log_fields(),
        ),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
