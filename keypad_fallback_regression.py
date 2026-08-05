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
    call.feedback_hotkey_pressed = False
    call.dtmf_queue = asyncio.Queue()
    for digit in digits:
        await call.dtmf_queue.put(digit)
    return await voice_realtime.RealtimeCall.wait_for_keypad_digits(
        call,
        timeout_seconds=1,
        max_digits=max_digits,
        terminators={"#", "*"},
    )


async def _immediate_numeric_answer(
    digits: list[str],
    *,
    speech: bytes | None = None,
) -> tuple[bytes | None, str | None]:
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "keypad-immediate-regression"
    call.hungup = False
    call.feedback_hotkey_pressed = False
    call.dtmf_queue = asyncio.Queue()

    async def wait_for_utterance(**_kwargs: object) -> bytes | None:
        if speech is not None:
            return speech
        await asyncio.sleep(10)
        return None

    call.wait_for_utterance = wait_for_utterance

    async def enter_digits() -> None:
        await asyncio.sleep(0.01)
        for digit in digits:
            await call.dtmf_queue.put(digit)

    producer = asyncio.create_task(enter_digits())
    try:
        return await voice_realtime.RealtimeCall.wait_for_numeric_or_utterance(
            call,
            end_silence_frames=2,
            speech_threshold=100,
        )
    finally:
        await producer


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
    immediate_audio, immediate_digits = asyncio.run(_immediate_numeric_answer(["4", "5", "#"]))
    ok &= check(
        "numeric_turn_accepts_keypad_without_stt_failure_first",
        immediate_audio is None and immediate_digits == "45",
        {"audio": immediate_audio, "digits": immediate_digits},
    )
    speech_audio, speech_digits = asyncio.run(_immediate_numeric_answer([], speech=b"spoken-answer"))
    ok &= check(
        "numeric_turn_still_accepts_speech",
        speech_audio == b"spoken-answer" and speech_digits is None,
        {"audio": speech_audio, "digits": speech_digits},
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
    ok &= check(
        "one_time_announcement_explains_keypad_and_hash",
        "keypad" in voice_realtime.KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT.lower()
        and "hash" in voice_realtime.KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT.lower(),
        voice_realtime.KEYPAD_NUMERIC_ANNOUNCEMENT_TEXT,
    )
    repeat_variants = [
        "I didn't hear the question, repeat it",
        "I did not hear you, Sabi.",
        "Can you say that again?",
        "Please repeat the question.",
        "What was the question?",
        "Come again.",
    ]
    ok &= check(
        "repeat_control_phrases_detected",
        all(voice_realtime._looks_like_repeat_request(text) for text in repeat_variants),
        repeat_variants,
    )
    ok &= check(
        "real_number_answers_are_not_repeat_requests",
        not any(voice_realtime._looks_like_repeat_request(text) for text in ["2", "twenty", "four mangoes"]),
    )
    short_barge = dict(
        utterance_seconds=0.92,
        utterance_from_barge=True,
        numeric_stt_context=True,
        keypad_text=None,
        text="20",
        already_reprompted=False,
    )
    ok &= check(
        "short_numeric_barge_is_reprompted_without_grading",
        voice_realtime._should_reprompt_short_numeric_barge(**short_barge),
        short_barge,
    )
    ok &= check(
        "short_barge_followup_cannot_loop_forever",
        not voice_realtime._should_reprompt_short_numeric_barge(
            **{**short_barge, "already_reprompted": True}
        ),
    )
    ok &= check(
        "normal_length_numeric_barge_can_be_graded",
        not voice_realtime._should_reprompt_short_numeric_barge(
            **{**short_barge, "utterance_seconds": 1.5}
        ),
    )
    ok &= check(
        "keypad_number_bypasses_short_audio_guard",
        not voice_realtime._should_reprompt_short_numeric_barge(
            **{**short_barge, "keypad_text": "40"}
        ),
    )
    ok &= check(
        "repeat_replays_latest_question_only",
        voice_realtime._last_question_for_repeat(
            [{"role": "assistant", "content": "Good try. You have six groundnuts. How many are left?"}]
        ) == "How many are left?",
    )
    switched_context = voice_realtime._recent_assistant_stt_context(
        [
            {
                "role": "assistant",
                "content": "You have five naira and spend three naira. How much is left?",
            }
        ],
        {
            "course": "literacy",
            "current_module": 3,
            "current_lesson": 1,
            "active_skill": "subtraction",
            "literacy": {"current_module": 1, "active_skill": "phonemic_awareness_beginning"},
        },
    )
    ok &= check(
        "spoken_switch_to_numeracy_updates_stt_lesson_context",
        "course=numeracy" in switched_context and "skill=subtraction" in switched_context,
        switched_context,
    )
    latest_only_context = voice_realtime._recent_assistant_stt_context(
        [
            {"role": "assistant", "content": "What is your name?"},
            {"role": "user", "content": "Naomi"},
            {"role": "assistant", "content": "What sound comes first in dog?"},
        ],
        {"course": "literacy", "literacy": {"active_skill": "phonemic_awareness_beginning"}},
    )
    ok &= check(
        "stt_context_contains_only_latest_tutor_turn",
        "dog" in latest_only_context.lower() and "your name" not in latest_only_context.lower(),
        latest_only_context,
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
