from __future__ import annotations

import argparse
from pathlib import Path
import random

from .phone_codec import WavAudio, read_wav_mono_16, rms, to_phone_wav, write_wav_mono_16


NOISE_SNR_DB = {
    "clean": None,
    "home": 15.0,
    "busy_compound": 8.0,
    "lagos_market": 3.0,
    "brutal_market": -3.0,
}


def mix_with_noise(
    speech: WavAudio,
    noise: WavAudio | None,
    *,
    snr_db: float | None,
    seed: int = 20260706,
) -> WavAudio:
    """Mix speech with looping noise at the requested signal-to-noise ratio."""
    if noise is None or snr_db is None or not noise.samples:
        return speech
    if noise.sample_rate != speech.sample_rate:
        noise = to_phone_wav(noise, target_rate=speech.sample_rate)

    rng = random.Random(seed)
    start = rng.randrange(0, max(1, len(noise.samples)))
    noise_samples = _loop_slice(noise.samples, len(speech.samples), start)
    speech_rms = rms(speech.samples) or 1.0
    noise_rms = rms(noise_samples) or 1.0
    target_noise_rms = speech_rms / (10.0 ** (snr_db / 20.0))
    noise_scale = target_noise_rms / noise_rms

    mixed: list[int] = []
    for speech_sample, noise_sample in zip(speech.samples, noise_samples):
        mixed.append(_clip_int16(speech_sample + noise_sample * noise_scale))
    return WavAudio(sample_rate=speech.sample_rate, samples=tuple(mixed))


def build_phone_noise_case(
    *,
    speech_wav: str | Path,
    output_wav: str | Path,
    noise_wav: str | Path | None = None,
    noise_level: str = "lagos_market",
    seed: int = 20260706,
    target_rate: int = 8000,
) -> dict:
    speech = to_phone_wav(read_wav_mono_16(speech_wav), target_rate=target_rate)
    noise = to_phone_wav(read_wav_mono_16(noise_wav), target_rate=target_rate) if noise_wav else None
    snr_db = NOISE_SNR_DB.get(noise_level)
    if noise_level not in NOISE_SNR_DB:
        raise ValueError(f"unknown noise_level {noise_level!r}; expected one of {sorted(NOISE_SNR_DB)}")
    mixed = mix_with_noise(speech, noise, snr_db=snr_db, seed=seed)
    write_wav_mono_16(output_wav, mixed)
    return {
        "output_wav": str(output_wav),
        "noise_level": noise_level,
        "snr_db": snr_db,
        "sample_rate": mixed.sample_rate,
        "duration_seconds": round(mixed.duration_seconds, 3),
        "speech_wav": str(speech_wav),
        "noise_wav": str(noise_wav) if noise_wav else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a phone-band noisy WAV for Sabi fake-child tests.")
    parser.add_argument("--speech-wav", required=True)
    parser.add_argument("--output-wav", required=True)
    parser.add_argument("--noise-wav")
    parser.add_argument("--noise-level", default="lagos_market", choices=sorted(NOISE_SNR_DB))
    parser.add_argument("--seed", type=int, default=20260706)
    args = parser.parse_args()

    result = build_phone_noise_case(
        speech_wav=args.speech_wav,
        noise_wav=args.noise_wav,
        output_wav=args.output_wav,
        noise_level=args.noise_level,
        seed=args.seed,
    )
    print(result)


def _loop_slice(samples: tuple[int, ...], length: int, start: int) -> list[int]:
    return [samples[(start + index) % len(samples)] for index in range(length)]


def _clip_int16(value: float | int) -> int:
    return int(max(-32768, min(32767, round(value))))


if __name__ == "__main__":
    main()

