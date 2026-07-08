from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import struct
import wave


INT16_MAX = 32767
INT16_MIN = -32768


@dataclass(frozen=True)
class WavAudio:
    sample_rate: int
    samples: tuple[int, ...]

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return len(self.samples) / self.sample_rate


def read_wav_mono_16(path: str | Path) -> WavAudio:
    """Read a PCM WAV file and return mono signed 16-bit samples."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if sample_width != 2:
        raise ValueError(f"{path} must be 16-bit PCM WAV; got sample width {sample_width}")
    if channels <= 0:
        raise ValueError(f"{path} has no audio channels")

    values = struct.unpack(f"<{len(frames) // 2}h", frames)
    if channels == 1:
        return WavAudio(sample_rate=sample_rate, samples=tuple(values))

    mono: list[int] = []
    for index in range(0, len(values), channels):
        mono.append(_clip_int16(round(sum(values[index:index + channels]) / channels)))
    return WavAudio(sample_rate=sample_rate, samples=tuple(mono))


def write_wav_mono_16(path: str | Path, audio: WavAudio) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frames = struct.pack(f"<{len(audio.samples)}h", *[_clip_int16(value) for value in audio.samples])
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(audio.sample_rate)
        handle.writeframes(frames)


def resample_linear(audio: WavAudio, target_rate: int) -> WavAudio:
    if audio.sample_rate == target_rate:
        return audio
    if target_rate <= 0:
        raise ValueError("target_rate must be positive")
    if not audio.samples:
        return WavAudio(sample_rate=target_rate, samples=())

    target_len = max(1, round(len(audio.samples) * target_rate / audio.sample_rate))
    ratio = audio.sample_rate / target_rate
    out: list[int] = []
    for index in range(target_len):
        source = index * ratio
        left = int(math.floor(source))
        right = min(left + 1, len(audio.samples) - 1)
        frac = source - left
        value = audio.samples[left] * (1.0 - frac) + audio.samples[right] * frac
        out.append(_clip_int16(round(value)))
    return WavAudio(sample_rate=target_rate, samples=tuple(out))


def apply_phone_bandpass(audio: WavAudio) -> WavAudio:
    """Apply a simple phone-ish high-pass plus low-pass filter."""
    if not audio.samples:
        return audio
    high_passed = _high_pass(audio.samples, audio.sample_rate, cutoff_hz=300.0)
    low_passed = _low_pass(high_passed, audio.sample_rate, cutoff_hz=3400.0)
    return WavAudio(sample_rate=audio.sample_rate, samples=tuple(_clip_int16(round(v)) for v in low_passed))


def quantize_ulaw_like(audio: WavAudio, levels: int = 256) -> WavAudio:
    """Approximate phone companding artifacts without needing codec libraries."""
    if levels < 16:
        raise ValueError("levels must be at least 16")
    out: list[int] = []
    mu = levels - 1
    for sample in audio.samples:
        x = max(-1.0, min(1.0, sample / INT16_MAX))
        compressed = math.copysign(math.log1p(mu * abs(x)) / math.log1p(mu), x)
        quantized = round((compressed + 1.0) * (levels - 1) / 2.0)
        expanded_input = (quantized * 2.0 / (levels - 1)) - 1.0
        expanded = math.copysign((math.expm1(abs(expanded_input) * math.log1p(mu)) / mu), expanded_input)
        out.append(_clip_int16(round(expanded * INT16_MAX)))
    return WavAudio(sample_rate=audio.sample_rate, samples=tuple(out))


def to_phone_wav(audio: WavAudio, target_rate: int = 8000) -> WavAudio:
    phone = resample_linear(audio, target_rate)
    phone = apply_phone_bandpass(phone)
    return quantize_ulaw_like(phone)


def rms(samples: tuple[int, ...] | list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(float(sample) * float(sample) for sample in samples) / len(samples))


def _low_pass(samples: tuple[int, ...] | list[int], sample_rate: int, cutoff_hz: float) -> list[float]:
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)
    out: list[float] = []
    prev = float(samples[0])
    for sample in samples:
        prev = prev + alpha * (float(sample) - prev)
        out.append(prev)
    return out


def _high_pass(samples: tuple[int, ...] | list[int], sample_rate: int, cutoff_hz: float) -> list[float]:
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)
    out: list[float] = []
    prev_y = 0.0
    prev_x = float(samples[0])
    for sample in samples:
        x = float(sample)
        y = alpha * (prev_y + x - prev_x)
        out.append(y)
        prev_y = y
        prev_x = x
    return out


def _clip_int16(value: float | int) -> int:
    return int(max(INT16_MIN, min(INT16_MAX, round(value))))

