#!/usr/bin/env python3
"""Phone-channel and real-noise augmentation for Sabi STT fine-tuning.

The production carrier sends 8 kHz PCMA/PCMU audio in 20 ms AudioSocket
frames.  This module reproduces that path instead of approximating G.711 with
an arbitrary logarithmic curve.  Real, licensed noise recordings can be
placed under ``data/noise/<category>/`` and are mixed on the fly.
"""

from __future__ import annotations

import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np


LOGGER = logging.getLogger("whisper-finetune.augmentation")
NOISE_CATEGORIES = ("market", "generator", "chatter", "television", "baby", "connection")
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".flac", ".ogg", ".mp3", ".m4a"}


def discover_noise_files(root: str | Path | None) -> dict[str, list[str]]:
    """Return licensed noise files grouped by required Sabi noise category."""
    if not root:
        return {category: [] for category in NOISE_CATEGORIES}
    base = Path(root)
    return {
        category: sorted(
            str(path)
            for path in (base / category).rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
        )
        for category in NOISE_CATEGORIES
    }


def missing_noise_categories(noise_files: dict[str, list[str]]) -> list[str]:
    return [category for category in NOISE_CATEGORIES if not noise_files.get(category)]


def _mono_float32(audio: np.ndarray) -> np.ndarray:
    value = np.asarray(audio, dtype=np.float32)
    if value.ndim > 1:
        # soundfile uses (frames, channels).
        value = value.mean(axis=1, dtype=np.float32)
    return np.nan_to_num(value, copy=False).astype(np.float32, copy=False)


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if int(source_rate) == int(target_rate):
        return np.asarray(audio, dtype=np.float32)
    import librosa

    return librosa.resample(
        np.asarray(audio, dtype=np.float32),
        orig_sr=int(source_rate),
        target_sr=int(target_rate),
    ).astype(np.float32)


def _phone_bandpass(audio_8k: np.ndarray) -> np.ndarray:
    """Apply the nominal 300–3400 Hz narrowband telephone passband."""
    from scipy.signal import butter, sosfilt

    if len(audio_8k) < 32:
        return audio_8k
    sos = butter(4, (300.0, 3400.0), btype="bandpass", fs=8000, output="sos")
    return sosfilt(sos, audio_8k).astype(np.float32)


def g711_roundtrip(audio_8k: np.ndarray, law: str = "alaw") -> np.ndarray:
    """Round-trip float PCM through the actual G.711 A-law or mu-law codec."""
    import g711

    pcm = np.ascontiguousarray(np.clip(audio_8k, -1.0, 1.0), dtype=np.float32)
    normalized_law = str(law or "alaw").strip().lower()
    if normalized_law in {"alaw", "a-law", "pcma"}:
        return np.asarray(g711.decode_alaw(g711.encode_alaw(pcm)), dtype=np.float32)
    if normalized_law in {"ulaw", "mu-law", "mulaw", "pcmu"}:
        return np.asarray(g711.decode_ulaw(g711.encode_ulaw(pcm)), dtype=np.float32)
    raise ValueError(f"unsupported G.711 law: {law}")


@lru_cache(maxsize=48)
def _read_noise(path: str, target_rate: int = 8000) -> np.ndarray:
    import soundfile as sf

    audio, rate = sf.read(path, dtype="float32", always_2d=False)
    return _resample(_mono_float32(audio), int(rate), target_rate)


def _fit_noise(noise: np.ndarray, length: int, rng: random.Random) -> np.ndarray:
    if length <= 0:
        return np.empty(0, dtype=np.float32)
    if len(noise) == 0:
        return np.zeros(length, dtype=np.float32)
    if len(noise) < length:
        repeats = int(np.ceil(length / len(noise)))
        noise = np.tile(noise, repeats)
    start = rng.randint(0, max(0, len(noise) - length))
    return np.asarray(noise[start : start + length], dtype=np.float32)


def mix_noise_at_snr(signal: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    signal = np.asarray(signal, dtype=np.float32)
    noise = np.asarray(noise, dtype=np.float32)
    if not len(signal) or not len(noise):
        return signal
    signal_rms = max(float(np.sqrt(np.mean(np.square(signal)))), 1e-5)
    noise_rms = max(float(np.sqrt(np.mean(np.square(noise)))), 1e-5)
    desired_noise_rms = signal_rms / (10.0 ** (float(snr_db) / 20.0))
    return np.clip(signal + noise * (desired_noise_rms / noise_rms), -1.0, 1.0)


def _audiosocket_frames(audio_8k: np.ndarray, rng: random.Random, short_response: bool) -> np.ndarray:
    """Simulate Sabi's 20 ms packetization, pre-roll, and occasional packet loss."""
    frame_samples = 160  # 20 ms at 8 kHz, matching voice_realtime.py.
    leading_frames = rng.randint(0, 4 if short_response else 8)
    trailing_frames = rng.randint(2, 10)
    framed = np.concatenate(
        [
            np.zeros(leading_frames * frame_samples, dtype=np.float32),
            np.asarray(audio_8k, dtype=np.float32),
            np.zeros(trailing_frames * frame_samples, dtype=np.float32),
        ]
    )
    remainder = len(framed) % frame_samples
    if remainder:
        framed = np.pad(framed, (0, frame_samples - remainder))

    frames = framed.reshape(-1, frame_samples)
    # Poor connections generally lose isolated packets. Never drop the first
    # or last speech-adjacent packet and keep the rate low enough that labels
    # remain truthful.
    if len(frames) > 8 and rng.random() < 0.35:
        max_drops = 1 if short_response else min(3, max(1, len(frames) // 35))
        for index in rng.sample(range(2, len(frames) - 2), k=rng.randint(1, max_drops)):
            frames[index] *= rng.uniform(0.0, 0.15)
    return frames.reshape(-1).astype(np.float32)


def telephony_augment(
    audio: np.ndarray,
    sample_rate: int,
    *,
    noise_files: dict[str, list[str]] | None = None,
    short_response: bool = False,
    rng: random.Random | None = None,
) -> np.ndarray:
    """Create a 16 kHz Whisper input that has traversed Sabi's phone path."""
    rng = rng or random
    value = _mono_float32(audio)
    value = _resample(value, int(sample_rate), 16000)
    narrowband = _resample(value, 16000, 8000)
    narrowband = _phone_bandpass(narrowband)

    # AT Nigeria offers PCMA first. Keep a smaller PCMU lane for carrier and
    # interconnect variability.
    law = "alaw" if rng.random() < 0.8 else "ulaw"
    narrowband = g711_roundtrip(narrowband, law=law)

    available = [
        (category, path)
        for category, paths in (noise_files or {}).items()
        for path in paths
    ]
    if available and rng.random() < 0.85:
        _category, path = rng.choice(available)
        real_noise = _fit_noise(_read_noise(path), len(narrowband), rng)
        narrowband = mix_noise_at_snr(narrowband, real_noise, rng.uniform(3.0, 24.0))
    elif rng.random() < 0.55:
        # Keep a fallback for research runs that have not mounted licensed
        # soundscapes yet. Complete runs can require every real category.
        white = np.asarray(
            [rng.gauss(0.0, 1.0) for _ in range(len(narrowband))],
            dtype=np.float32,
        )
        narrowband = mix_noise_at_snr(narrowband, white, rng.uniform(10.0, 28.0))

    narrowband = _audiosocket_frames(narrowband, rng, short_response=short_response)
    gain = rng.uniform(0.45 if short_response else 0.60, 1.20)
    narrowband = np.clip(narrowband * gain, -1.0, 1.0)
    return _resample(narrowband, 8000, 16000)


def flatten_noise_files(noise_files: dict[str, Iterable[str]]) -> list[str]:
    return [path for paths in noise_files.values() for path in paths]
