#!/usr/bin/env python3
"""Regression checks for the mid-call feedback hotkey.

A frustrated caller (or tester) can press a DTMF hotkey (default the star key)
at ANY point during the lesson. Sabi stops talking, ends the lesson, and opens
the open-ended feedback space -- so the person who would otherwise just hang up
has a way to say what went wrong.

This proves, without a live PBX call:
  - _consume_feedback_hotkey latches the hotkey digit and re-queues other
    digits (so the numeric keypad fallback still works).
  - wait_for_utterance bails immediately once the hotkey is latched.
  - "feedback_hotkey" is an offer-eligible end reason.
  - record_feedback_note(hotkey=True) uses the warm hotkey prompt, records the
    note EVEN when the passive feedback mode is restricted, and tags it.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import tempfile
from collections import deque
from pathlib import Path


ROOT = Path(tempfile.mkdtemp(prefix="sabi-feedback-hotkey-"))
os.environ["SABI_SHARED_AUDIO_DIR"] = str(ROOT)
# Deliberately restrict the passive end-of-call offer so we can prove the
# hotkey is honored regardless of mode.
os.environ["SABI_FEEDBACK_MODE"] = "testers"
os.environ["SABI_FEEDBACK_TEST_NUMBERS"] = ""

import voice_realtime  # noqa: E402


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return bool(condition)


class FakeSTT:
    def transcribe(self, path: str) -> dict:
        return {"text": "This is annoying, Sabi kept mishearing me.", "confidence": 0.9}


class FakeMemory:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def save_call_feedback(self, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeHotkeyCall:
    """Minimal fixture for record_feedback_note with hotkey=True."""

    def __init__(self) -> None:
        self.call_uuid = "hotkey-regression-001"
        self.call_id = self.call_uuid
        # NOT a tester number, and mode=testers -> passive offer would be OFF.
        self.phone = "+2348000000000"
        self.mode = "inbound"
        self.attempt = 1
        self.hungup = False
        self.feedback_hotkey_pressed = True
        self.prompt_calls: list[tuple[str, str]] = []
        self.played_pcm_lengths: list[int] = []
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.dtmf_queue: asyncio.Queue = asyncio.Queue()
        self.stt = FakeSTT()
        self.memory = FakeMemory()

    async def synthesize_pcm(self, text: str, label: str) -> bytes:
        self.prompt_calls.append((label, text))
        return b"\0" * voice_realtime.FRAME_BYTES

    async def play_pcm(self, pcm: bytes) -> None:
        self.played_pcm_lengths.append(len(pcm))

    def drain_audio(self) -> None:
        while True:
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def wait_for_optional_utterance(self, timeout_seconds, rms_telemetry=None, **kwargs):
        if rms_telemetry is not None:
            rms_telemetry.update({
                "peak_rms": 500,
                "mean_rms": 260,
                "frames_observed": 120,
                "frames_above_threshold": 80,
                "ended_reason": "speech_captured",
                "time_to_first_speech_ms": 1500,
            })
        return struct.pack("<h", 1700) * voice_realtime.SAMPLE_RATE


def _new_call() -> voice_realtime.RealtimeCall:
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "hotkey-internal"
    call.audio_queue = asyncio.Queue()
    call.dtmf_queue = asyncio.Queue()
    call.pre_roll = deque(maxlen=0)
    call.hungup = False
    call.end_reason = "unknown"
    call.feedback_hotkey_pressed = False
    return call


async def run_consume_check() -> tuple[bool, dict]:
    """Hotkey latches; a non-hotkey digit is re-queued for keypad fallback."""
    call = _new_call()
    await call.dtmf_queue.put("5")
    await call.dtmf_queue.put(voice_realtime.FEEDBACK_HOTKEY_DIGIT)
    pressed = call._consume_feedback_hotkey()
    leftover = []
    while True:
        try:
            leftover.append(call.dtmf_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return (
        pressed is True
        and call.feedback_hotkey_pressed is True
        and leftover == ["5"]
    ), {"pressed": pressed, "leftover": leftover}


async def run_wait_bails_check() -> tuple[bool, dict]:
    """wait_for_utterance returns immediately once the hotkey is latched."""
    call = _new_call()
    call.feedback_hotkey_pressed = True
    # No audio queued: if it did not bail it would block forever.
    pcm = await asyncio.wait_for(
        voice_realtime.RealtimeCall.wait_for_utterance(call),
        timeout=1.0,
    )
    return pcm is None, {"pcm": pcm}


class FakeLLM:
    def __init__(self, reply: str = "I am sorry it felt that way."):
        self.reply = reply

    async def generate(self, **kwargs) -> str:
        return self.reply


async def run_midcall(answer_text: str, note: str = "I am frustrated that Sabi could not hear me."):
    """Drive handle_mid_call_feedback with fakes; return (result, messages)."""
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "midcall"
    call.call_id = "midcall"
    call.phone = "+2348000000000"
    call.mode = "inbound"
    call.attempt = 1
    call.hungup = False
    call.feedback_hotkey_pressed = False
    call.feedback_captured = False
    call.llm = FakeLLM()
    call.memory = object()  # only passed through to the (fake) LLM
    spoken: list[str] = []

    async def fake_record(*a, **k):
        call.feedback_captured = True
        return note

    async def fake_synth(text, label):
        spoken.append(text)
        return b"\0" * voice_realtime.FRAME_BYTES

    async def fake_play(pcm, **k):
        return None

    async def fake_wait(**k):
        return b"x" * voice_realtime.FRAME_BYTES

    async def fake_trans(pcm, turn, *a, **k):
        return {"text": answer_text}

    call.record_feedback_note = fake_record
    call.synthesize_pcm = fake_synth
    call.play_pcm_with_barge = fake_play
    call.play_pcm = fake_play
    call.wait_for_utterance = fake_wait
    call.transcribe_pcm = fake_trans

    messages = [{"role": "assistant", "content": "Let's count to five."}]
    result = await voice_realtime.RealtimeCall.handle_mid_call_feedback(
        call, "sid", {"course": "numeracy"}, messages,
        module=1, course="numeracy", trigger="hotkey",
    )
    return result, messages, spoken


async def run_midcall_empty():
    """No note left -> reassure and resume (True)."""
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "midcall-empty"
    call.call_id = "midcall-empty"
    call.hungup = False
    call.feedback_captured = False

    async def fake_record(*a, **k):
        return ""

    async def fake_synth(text, label):
        return b"\0" * voice_realtime.FRAME_BYTES

    async def fake_play(pcm, **k):
        return None

    call.record_feedback_note = fake_record
    call.synthesize_pcm = fake_synth
    call.play_pcm_with_barge = fake_play
    return await voice_realtime.RealtimeCall.handle_mid_call_feedback(
        call, "sid", {}, [], module=0, course="numeracy", trigger="hotkey",
    )


def main() -> int:
    ok = True

    # _wants_to_continue_lesson decisions.
    ok &= check("continue_on_yes", voice_realtime._wants_to_continue_lesson("yes keep going"))
    ok &= check("continue_on_engaged_answer", voice_realtime._wants_to_continue_lesson("let's do more math"))
    ok &= check("stop_on_no", not voice_realtime._wants_to_continue_lesson("no"))
    ok &= check("stop_on_stop_phrase", not voice_realtime._wants_to_continue_lesson("I am done, stop"))
    ok &= check("stop_on_empty", not voice_realtime._wants_to_continue_lesson(""))

    # Mid-call flow: continue path.
    cont_result, cont_msgs, cont_spoken = asyncio.run(run_midcall("yes let's keep going"))
    ok &= check("midcall_continue_returns_true", cont_result is True, cont_result)
    ok &= check(
        "midcall_ack_includes_continue_question",
        any(voice_realtime.FEEDBACK_CONTINUE_QUESTION_TEXT in s for s in cont_spoken),
        cont_spoken,
    )
    ok &= check(
        "midcall_ack_uses_llm_empathy_reply",
        any("I am sorry it felt that way." in s for s in cont_spoken),
        cont_spoken,
    )
    ok &= check(
        "midcall_ack_and_answer_added_to_messages",
        any(voice_realtime.FEEDBACK_CONTINUE_QUESTION_TEXT in m.get("content", "") for m in cont_msgs)
        and any(m["role"] == "user" and "keep going" in m["content"] for m in cont_msgs),
        cont_msgs,
    )

    # Mid-call flow: stop path.
    stop_result, _, _ = asyncio.run(run_midcall("no, I want to stop now"))
    ok &= check("midcall_stop_returns_false", stop_result is False, stop_result)

    # Mid-call flow: empty note resumes.
    empty_result = asyncio.run(run_midcall_empty())
    ok &= check("midcall_empty_note_resumes", empty_result is True, empty_result)

    ok &= check(
        "hotkey_digit_configured",
        voice_realtime.FEEDBACK_HOTKEY_DIGIT == "*",
        voice_realtime.FEEDBACK_HOTKEY_DIGIT,
    )
    ok &= check(
        "hotkey_is_offer_eligible_end_reason",
        "feedback_hotkey" in voice_realtime.FEEDBACK_OFFER_END_REASONS
        and voice_realtime._should_offer_feedback(
            None, [{"role": "assistant", "content": "hi"}], False, "feedback_hotkey"
        ),
    )
    ok &= check(
        "hotkey_announce_present_in_greeting_text",
        bool(voice_realtime.FEEDBACK_HOTKEY_ANNOUNCE_TEXT)
        and "star" in voice_realtime.FEEDBACK_HOTKEY_ANNOUNCE_TEXT.lower(),
    )

    consume_ok, consume_detail = asyncio.run(run_consume_check())
    ok &= check("hotkey_latches_and_requeues_other_digits", consume_ok, consume_detail)

    bail_ok, bail_detail = asyncio.run(run_wait_bails_check())
    ok &= check("wait_for_utterance_bails_on_hotkey", bail_ok, bail_detail)

    # record_feedback_note honors the hotkey even though mode=testers and this
    # phone is not a tester (passive offer would be disabled).
    ok &= check(
        "passive_offer_disabled_for_this_phone",
        not voice_realtime._feedback_enabled_for_phone("+2348000000000"),
        voice_realtime.FEEDBACK_MODE,
    )
    call = FakeHotkeyCall()
    asyncio.run(
        voice_realtime.RealtimeCall.record_feedback_note(
            call,
            student_id="student-hotkey",
            learning_state={"course": "numeracy", "current_module": 2},
            requested_by_caller=True,
            hotkey=True,
        )
    )
    sidecar_path = ROOT / f"feedback_{call.call_uuid}.json"
    metadata = json.loads(sidecar_path.read_text()) if sidecar_path.exists() else {}
    hotkey_prompt = call.prompt_calls[0][1] if call.prompt_calls else ""

    ok &= check(
        "hotkey_records_note_despite_restricted_mode",
        metadata.get("ended_reason") == "speech_captured"
        and (ROOT / f"feedback_{call.call_uuid}.wav").exists()
        and bool(call.memory.calls),
        metadata,
    )
    ok &= check(
        "hotkey_uses_warm_hotkey_prompt",
        hotkey_prompt == voice_realtime.FEEDBACK_HOTKEY_PROMPT_TEXT
        and "listening" in hotkey_prompt.lower(),
        hotkey_prompt,
    )
    ok &= check(
        "hotkey_note_is_tagged",
        "hotkey" in metadata.get("tags", []),
        metadata.get("tags"),
    )
    ok &= check(
        "hotkey_flag_reset_after_recording",
        call.feedback_hotkey_pressed is False,
        call.feedback_hotkey_pressed,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
