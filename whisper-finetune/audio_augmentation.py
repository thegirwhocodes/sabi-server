#!/usr/bin/env python3
"""Phone-channel and real-noise augmentation for Sabi STT fine-tuning.

The production carrier sends 8 kHz PCMA/PCMU audio in 20 ms AudioSocket
frames.  This module reproduces that path instead of approximating G.711 with
an arbitrary logarithmic curve.  Real, licensed noise recordings can be
placed under ``data/noise/<category>/`` and are mixed on the fly.
"""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np


LOGGER = logging.getLogger("whisper-finetune.augmentation")
NOISE_CATEGORIES = ("market", "generator", "chatter", "television", "baby", "connection")
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".flac", ".ogg", ".mp3", ".m4a"}
NOISE_LICENSE_LEDGER = "noise_licenses.jsonl"


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


def licensed_noise_files(
    root: str | Path | None,
    discovered: dict[str, list[str]],
    *,
    require_complete: bool = False,
    allow_noncommercial: bool = False,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """Allow only noise files with explicit, auditable license provenance.

    ``noise_licenses.jsonl`` lives at the noise root. Each row must contain
    ``path`` (relative to the root), ``source_url``, ``license``, and the
    boolean ``commercial_use_allowed``. Unlisted files are ignored in
    exploratory runs and block complete runs.
    """
    approved = {category: [] for category in NOISE_CATEGORIES}
    provenance: dict[str, object] = {
        "ledger": None,
        "licenses": {},
        "approved_files": 0,
        "ignored_unlicensed_files": sum(len(paths) for paths in discovered.values()),
        "contains_noncommercial_noise": False,
    }
    if not root:
        if require_complete:
            raise RuntimeError("licensed noise root is required for a complete training run")
        return approved, provenance

    base = Path(root).resolve()
    ledger = base / NOISE_LICENSE_LEDGER
    provenance["ledger"] = str(ledger)
    if not ledger.is_file():
        if require_complete:
            raise RuntimeError(f"required noise license ledger is missing: {ledger}")
        return approved, provenance

    discovered_paths = {
        Path(path).resolve(): category
        for category, paths in discovered.items()
        for path in paths
    }
    seen: set[Path] = set()
    licenses: Counter[str] = Counter()
    contains_noncommercial = False
    for line_number, raw_line in enumerate(ledger.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{ledger}:{line_number}: invalid JSON: {exc}") from exc
        relative_path = str(row.get("path") or "").strip()
        source_url = str(row.get("source_url") or "").strip()
        license_name = str(row.get("license") or "").strip()
        commercial_allowed = row.get("commercial_use_allowed")
        if not relative_path or not source_url or not license_name or not isinstance(commercial_allowed, bool):
            raise ValueError(
                f"{ledger}:{line_number}: path, source_url, license, and boolean "
                "commercial_use_allowed are required"
            )
        path = (base / relative_path).resolve()
        if base not in path.parents:
            raise ValueError(f"{ledger}:{line_number}: path escapes noise root: {relative_path}")
        if path in seen:
            raise ValueError(f"{ledger}:{line_number}: duplicate noise path: {relative_path}")
        seen.add(path)
        category = discovered_paths.get(path)
        if category is None:
            if require_complete:
                raise ValueError(f"{ledger}:{line_number}: file is missing or unsupported: {relative_path}")
            continue
        declared_category = str(row.get("category") or category).strip()
        if declared_category != category:
            raise ValueError(
                f"{ledger}:{line_number}: category {declared_category!r} does not match folder {category!r}"
            )
        if not commercial_allowed and not allow_noncommercial:
            continue
        if not commercial_allowed:
            contains_noncommercial = True
        approved[category].append(str(path))
        licenses[license_name] += 1

    unlisted = sorted(str(path) for path in discovered_paths if path not in seen)
    if require_complete and unlisted:
        preview = ", ".join(unlisted[:5])
        raise RuntimeError(f"noise files missing from {ledger}: {preview}")
    if require_complete:
        missing = missing_noise_categories(approved)
        if missing:
            raise RuntimeError(
                "required licensed noise categories have no approved files: " + ", ".join(missing)
            )

    provenance.update({
        "licenses": dict(sorted(licenses.items())),
        "approved_files": sum(len(paths) for paths in approved.values()),
        "ignored_unlicensed_files": len(unlisted),
        "contains_noncommercial_noise": contains_noncommercial,
    })
    return approved, provenance


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
    import audioop

    pcm = np.asarray(
        np.clip(np.asarray(audio_8k, dtype=np.float32), -1.0, 1.0) * 32767.0,
        dtype="<i2",
    )
    normalized_law = str(law or "alaw").strip().lower()
    if normalized_law in {"alaw", "a-law", "pcma"}:
        encoded = audioop.lin2alaw(pcm.tobytes(), 2)
        decoded = audioop.alaw2lin(encoded, 2)
    elif normalized_law in {"ulaw", "mu-law", "mulaw", "pcmu"}:
        encoded = audioop.lin2ulaw(pcm.tobytes(), 2)
        decoded = audioop.ulaw2lin(encoded, 2)
    else:
        raise ValueError(f"unsupported G.711 law: {law}")
    return np.frombuffer(decoded, dtype="<i2").astype(np.float32) / 32768.0


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
