#!/usr/bin/env python3
"""Regression checks for noisy-audio keypad numeric fallback."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import types

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    sys.modules["httpx"] = types.SimpleNamespace()

os.environ.setdefault("SABI_SHARED_AUDIO_DIR", str(Path(os.getenv("TMPDIR", "/tmp")) / "sabi-keypad-fallback"))

import voice_realtime  # noqa: E402


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


async def _call_with_digits(digits: list[str], *, max_digits: int = 4) -> str | None:
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "keypad-regression"
    call.hungup = False
    call.dtmf_queue = asyncio.Queue()
    for digit in digits:
        await call.dtmf_queue.put(digit)
    return await voice_realtime.RealtimeCall.wait_for_keypad_digits(
        call,
        timeout_seconds=1,
        max_digits=max_digits,
        terminators={"#", "*"},
    )


async def _prompt_flow_with_digits(
    digits_after_prompt: list[str],
    *,
    stale_digits_before_prompt: list[str] | None = None,
) -> tuple[str | None, dict]:
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "keypad-flow-regression"
    call.hungup = False
    call.dtmf_queue = asyncio.Queue()
    events: dict = {"persisted": [], "played": [], "synthesized": []}

    for digit in stale_digits_before_prompt or []:
        await call.dtmf_queue.put(digit)

    async def synthesize_pcm(text: str, label: str) -> bytes:
        events["synthesized"].append({"text": text, "label": label})
        return b"\0" * voice_realtime.FRAME_BYTES

    async def play_pcm(pcm: bytes) -> None:
        events["played"].append(len(pcm))
        for digit in digits_after_prompt:
            await call.dtmf_queue.put(digit)

    def persist_turn_review(**kwargs: object) -> None:
        events["persisted"].append(kwargs)

    call.synthesize_pcm = synthesize_pcm
    call.play_pcm = play_pcm
    call.persist_turn_review = persist_turn_review

    result = await voice_realtime.RealtimeCall.prompt_for_keypad_numeric_answer(
        call,
        turn=3,
        user_audio_path=None,
        transcript={"confidence": 0.04, "stt_latency_seconds": 0.12},
        raw_text="Good luck.",
        normalized_text="Good luck.",
        learning_state_before={"course": "numeracy"},
        turn_flags=["numeric_stt"],
        turn_start=0.0,
    )
    return result, events


def main() -> int:
    ok = True

    ok &= check(
        "collects_digits_until_hash",
        asyncio.run(_call_with_digits(["4", "5", "#"])) == "45",
    )
    ok &= check(
        "collects_digits_until_star",
        asyncio.run(_call_with_digits(["1", "2", "*"])) == "12",
    )
    ok &= check(
        "ignores_non_digit_noise",
        asyncio.run(_call_with_digits(["A", "7", "#"])) == "7",
    )
    ok &= check(
        "empty_before_terminator_returns_none",
        asyncio.run(_call_with_digits(["#"])) is None,
    )
    ok &= check(
        "max_digits_stops_collection",
        asyncio.run(_call_with_digits(["1", "2", "3", "4", "5"], max_digits=3)) == "123",
    )
    ok &= check(
        "keypad_fallback_enabled_by_default",
        voice_realtime.KEYPAD_NUMERIC_FALLBACK_ENABLED is True,
        voice_realtime.KEYPAD_NUMERIC_FALLBACK_ENABLED,
    )
    ok &= check(
        "hash_star_env_alias_maps_to_real_terminators",
        voice_realtime.KEYPAD_NUMERIC_TERMINATORS == {"#", "*"},
        voice_realtime.KEYPAD_NUMERIC_TERMINATORS,
    )
    ok &= check(
        "fallback_prompt_explains_hash_key",
        "hash" in voice_realtime.KEYPAD_NUMERIC_FALLBACK_TEXT.lower(),
        voice_realtime.KEYPAD_NUMERIC_FALLBACK_TEXT,
    )
    flow_result, flow_events = asyncio.run(_prompt_flow_with_digits(["4", "5", "#"]))
    persisted = flow_events["persisted"][0] if flow_events["persisted"] else {}
    ok &= check(
        "prompt_flow_accepts_digits_after_prompt",
        flow_result == "45"
        and bool(flow_events["played"])
        and flow_events["synthesized"][0]["label"] == "rt_keypad_retry",
        {"result": flow_result, "events": flow_events},
    )
    ok &= check(
        "prompt_flow_persists_review_prompt_flags",
        "keypad_numeric_fallback_prompt" in persisted.get("flags", [])
        and "retry_prompt" in persisted.get("flags", [])
        and persisted.get("assistant_text") == voice_realtime.KEYPAD_NUMERIC_FALLBACK_TEXT,
        persisted,
    )
    stale_result, stale_events = asyncio.run(
        _prompt_flow_with_digits(["8", "#"], stale_digits_before_prompt=["9", "#"])
    )
    ok &= check(
        "prompt_flow_drains_stale_digits_before_listening",
        stale_result == "8",
        {"result": stale_result, "events": stale_events},
    )
    timeout_result, timeout_events = asyncio.run(_prompt_flow_with_digits([]))
    ok &= check(
        "prompt_flow_timeout_returns_none_but_persists_prompt",
        timeout_result is None and bool(timeout_events["persisted"]) and bool(timeout_events["played"]),
        {"result": timeout_result, "events": timeout_events},
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
