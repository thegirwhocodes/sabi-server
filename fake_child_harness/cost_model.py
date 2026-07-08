from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FakePilotCostAssumptions:
    children: int = 100
    calls_per_child: int = 240
    low_minutes_per_call: int = 5
    expected_minutes_per_call: int = 6
    high_minutes_per_call: int = 7
    ai_turns_per_call: int = 7
    ngn_per_usd: float = 1400.0
    groq_whisper_turbo_usd_per_hour: float = 0.04
    groq_whisper_large_usd_per_hour: float = 0.111
    elevenlabs_scribe_usd_per_hour: float = 0.22
    elevenlabs_realtime_stt_usd_per_hour: float = 0.39
    africas_talking_callback_ngn_per_minute: float = 3.0
    toll_free_ngn_per_minute: float = 14.0
    claude_lean_usd_per_call: float = 0.0045
    claude_buffered_usd_per_call: float = 0.01
    self_hosted_server_month_usd: float = 203.0
    elevenlabs_flash_usd_per_1k_chars: float = 0.05
    elevenlabs_multilingual_usd_per_1k_chars: float = 0.10
    africas_talking_google_tts_usd_per_char: float = 0.000008
    low_tts_chars_per_call: int = 1500
    expected_tts_chars_per_call: int = 2500
    high_tts_chars_per_call: int = 5000


def estimate_fake_pilot_cost(assumptions: FakePilotCostAssumptions) -> dict[str, Any]:
    calls = assumptions.children * assumptions.calls_per_child
    minute_band = {
        "low": calls * assumptions.low_minutes_per_call,
        "expected": calls * assumptions.expected_minutes_per_call,
        "high": calls * assumptions.high_minutes_per_call,
    }
    hour_band = {key: minutes / 60.0 for key, minutes in minute_band.items()}
    tts_char_band = {
        "low": calls * assumptions.low_tts_chars_per_call,
        "expected": calls * assumptions.expected_tts_chars_per_call,
        "high": calls * assumptions.high_tts_chars_per_call,
    }

    return {
        "assumptions": asdict(assumptions),
        "scale": {
            "total_calls": calls,
            "total_call_minutes": minute_band,
            "total_audio_hours": {key: round(value, 2) for key, value in hour_band.items()},
            "estimated_ai_turns": calls * assumptions.ai_turns_per_call,
            "estimated_tts_characters": tts_char_band,
        },
        "marginal_offline_synthetic_usd": 0.0,
        "server_reservation_usd": assumptions.self_hosted_server_month_usd,
        "stt_usd": {
            "groq_whisper_turbo": _rate_band(hour_band, assumptions.groq_whisper_turbo_usd_per_hour),
            "groq_whisper_large": _rate_band(hour_band, assumptions.groq_whisper_large_usd_per_hour),
            "elevenlabs_scribe": _rate_band(hour_band, assumptions.elevenlabs_scribe_usd_per_hour),
            "elevenlabs_realtime": _rate_band(hour_band, assumptions.elevenlabs_realtime_stt_usd_per_hour),
        },
        "llm_usd": {
            "claude_lean": _call_rate_band(calls, assumptions.claude_lean_usd_per_call),
            "claude_buffered": _call_rate_band(calls, assumptions.claude_buffered_usd_per_call),
        },
        "tts_usd": {
            "self_hosted_or_yarngpt": {"low": 0.0, "expected": 0.0, "high": 0.0},
            "elevenlabs_flash": _chars_rate_band(tts_char_band, assumptions.elevenlabs_flash_usd_per_1k_chars),
            "elevenlabs_multilingual": _chars_rate_band(tts_char_band, assumptions.elevenlabs_multilingual_usd_per_1k_chars),
            "africas_talking_google_standard": _char_rate_band(tts_char_band, assumptions.africas_talking_google_tts_usd_per_char),
        },
        "telephony_usd": {
            "none_phone_harness": {"low": 0.0, "expected": 0.0, "high": 0.0},
            "africas_talking_callback": _ngn_minute_band(
                minute_band,
                assumptions.africas_talking_callback_ngn_per_minute,
                assumptions.ngn_per_usd,
            ),
            "toll_free_minutes_only": _ngn_minute_band(
                minute_band,
                assumptions.toll_free_ngn_per_minute,
                assumptions.ngn_per_usd,
            ),
        },
        "recommended_run_usd": _sum_bands(
            _rate_band(hour_band, assumptions.groq_whisper_large_usd_per_hour),
            _call_rate_band(calls, assumptions.claude_buffered_usd_per_call),
            {"low": 0.0, "expected": 0.0, "high": 0.0},
            {"low": 0.0, "expected": 0.0, "high": 0.0},
        ),
        "production_like_phone_yarngpt_usd": _sum_bands(
            _rate_band(hour_band, assumptions.groq_whisper_large_usd_per_hour),
            _call_rate_band(calls, assumptions.claude_buffered_usd_per_call),
            {"low": 0.0, "expected": 0.0, "high": 0.0},
            _ngn_minute_band(
                minute_band,
                assumptions.africas_talking_callback_ngn_per_minute,
                assumptions.ngn_per_usd,
            ),
        ),
        "paid_elevenlabs_no_phone_usd": _sum_bands(
            _rate_band(hour_band, assumptions.groq_whisper_large_usd_per_hour),
            _call_rate_band(calls, assumptions.claude_buffered_usd_per_call),
            _chars_rate_band(tts_char_band, assumptions.elevenlabs_flash_usd_per_1k_chars),
            {"low": 0.0, "expected": 0.0, "high": 0.0},
        ),
    }


def _rate_band(values: dict[str, float], rate: float) -> dict[str, float]:
    return {key: round(value * rate, 2) for key, value in values.items()}


def _call_rate_band(calls: int, rate: float) -> dict[str, float]:
    cost = round(calls * rate, 2)
    return {"low": cost, "expected": cost, "high": cost}


def _chars_rate_band(chars: dict[str, int], usd_per_1k: float) -> dict[str, float]:
    return {key: round(value / 1000.0 * usd_per_1k, 2) for key, value in chars.items()}


def _char_rate_band(chars: dict[str, int], usd_per_char: float) -> dict[str, float]:
    return {key: round(value * usd_per_char, 2) for key, value in chars.items()}


def _ngn_minute_band(minutes: dict[str, int], ngn_per_minute: float, ngn_per_usd: float) -> dict[str, float]:
    return {key: round(value * ngn_per_minute / ngn_per_usd, 2) for key, value in minutes.items()}


def _sum_bands(*bands: dict[str, float]) -> dict[str, float]:
    return {
        key: round(sum(float(band.get(key, 0.0)) for band in bands), 2)
        for key in ("low", "expected", "high")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate cost for a fake-child Sabi pilot harness run.")
    parser.add_argument("--children", type=int, default=100)
    parser.add_argument("--calls-per-child", type=int, default=240)
    parser.add_argument("--ngn-per-usd", type=float, default=1400.0)
    parser.add_argument("--expected-tts-chars-per-call", type=int, default=2500)
    args = parser.parse_args()

    assumptions = FakePilotCostAssumptions(
        children=args.children,
        calls_per_child=args.calls_per_child,
        ngn_per_usd=args.ngn_per_usd,
        expected_tts_chars_per_call=args.expected_tts_chars_per_call,
    )
    print(json.dumps(estimate_fake_pilot_cost(assumptions), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
