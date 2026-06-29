#!/usr/bin/env python3
"""Regression checks for optional end-of-call voice feedback capture.

This exercises the AudioSocket feedback path without a live PBX call. It proves
that the pilot feedback prompt can collect audio, write a review sidecar, and
persist the metadata through the same method production uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import tempfile
import time
from collections import deque
from pathlib import Path


ROOT = Path(tempfile.mkdtemp(prefix="sabi-feedback-capture-"))
os.environ["SABI_SHARED_AUDIO_DIR"] = str(ROOT)
os.environ.setdefault("SABI_FEEDBACK_MODE", "all")

import voice_realtime  # noqa: E402


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


class FakeSTT:
    def transcribe(self, path: str) -> dict:
        if not Path(path).exists():
            raise AssertionError(f"feedback audio not written before STT: {path}")
        return {"text": "The call was clear but Sabi marked one correct answer wrong.", "confidence": 0.91}


class FakeMemory:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def save_call_feedback(self, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeFeedbackCall:
    def __init__(self) -> None:
        self.call_uuid = "fb-regression-001"
        self.call_id = self.call_uuid
        self.phone = "+2348033374126"
        self.mode = "inbound"
        self.attempt = 1
        self.hungup = False
        self.prompt_played = False
        self.wait_args: tuple[int, int | None, int | None] | None = None
        self.stt = FakeSTT()
        self.memory = FakeMemory()

    async def synthesize_pcm(self, text: str, label: str) -> bytes:
        self.prompt_text = text
        self.prompt_label = label
        return b"\0" * voice_realtime.FRAME_BYTES

    async def play_pcm(self, pcm: bytes) -> None:
        self.prompt_played = bool(pcm)

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
    ) -> bytes:
        self.wait_args = (timeout_seconds, max_frames, end_silence_frames, speech_threshold)
        # One second of 8 kHz signed-linear audio at a clearly non-silent level.
        return struct.pack("<h", 1800) * voice_realtime.SAMPLE_RATE


class FakeFeedbackHangupCall(FakeFeedbackCall):
    def __init__(self) -> None:
        super().__init__()
        self.call_uuid = "fb-regression-hangup"
        self.call_id = self.call_uuid

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
    ) -> bytes:
        self.wait_args = (timeout_seconds, max_frames, end_silence_frames, speech_threshold)
        self.hungup = True
        return struct.pack("<h", 1900) * voice_realtime.SAMPLE_RATE


async def run_capture() -> tuple[FakeFeedbackCall, dict]:
    call = FakeFeedbackCall()
    await voice_realtime.RealtimeCall.record_feedback_note(
        call,
        student_id="student-feedback-1",
        learning_state={"course": "numeracy", "current_module": 2},
    )
    sidecar = ROOT / "feedback_fb-regression-001.json"
    metadata = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    return call, metadata


async def run_capture_with_hangup() -> tuple[FakeFeedbackHangupCall, dict]:
    call = FakeFeedbackHangupCall()
    await voice_realtime.RealtimeCall.record_feedback_note(
        call,
        student_id="student-feedback-hangup",
        learning_state={"course": "numeracy", "current_module": 2},
    )
    sidecar = ROOT / "feedback_fb-regression-hangup.json"
    metadata = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    return call, metadata


async def run_optional_wait_window_check() -> tuple[bool, dict]:
    """The wait-to-start timeout must not cap an in-progress voice note."""
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "optional-window-regression"
    call.audio_queue = asyncio.Queue()
    call.pre_roll = deque(maxlen=0)
    call.hungup = False
    call.end_reason = "unknown"
    call.set_end_reason = lambda reason: setattr(call, "end_reason", reason)

    loud_frame = struct.pack("<h", voice_realtime.SPEECH_RMS_THRESHOLD + 1000) * (
        voice_realtime.FRAME_BYTES // 2
    )
    await call.audio_queue.put(loud_frame)
    await call.audio_queue.put(loud_frame)

    started_at = time.monotonic()
    pcm = await voice_realtime.RealtimeCall.wait_for_optional_utterance(
        call,
        timeout_seconds=0.05,
        max_frames=8,
        end_silence_frames=3,
    )
    elapsed = time.monotonic() - started_at
    return bool(pcm) and elapsed >= 0.05, {
        "captured": bool(pcm),
        "elapsed_seconds": round(elapsed, 3),
        "pcm_bytes": len(pcm or b""),
        "end_reason": call.end_reason,
    }


def main() -> int:
    ok = True

    ok &= check(
        "feedback_default_enabled_for_pilot",
        voice_realtime.FEEDBACK_MODE in {"all", "pilot", "prepilot", "pre-pilot"},
        voice_realtime.FEEDBACK_MODE,
    )
    ok &= check(
        "feedback_enabled_for_any_phone_when_all",
        voice_realtime._feedback_enabled_for_phone("+2348033374126"),
        voice_realtime.FEEDBACK_MODE,
    )

    call, metadata = asyncio.run(run_capture())
    hangup_call, hangup_metadata = asyncio.run(run_capture_with_hangup())
    optional_window_ok, optional_window_detail = asyncio.run(run_optional_wait_window_check())
    audio_path = ROOT / "feedback_fb-regression-001.wav"
    sidecar_path = ROOT / "feedback_fb-regression-001.json"
    saved = call.memory.calls[0] if call.memory.calls else {}

    ok &= check("feedback_prompt_played", call.prompt_played, getattr(call, "prompt_text", ""))
    ok &= check(
        "feedback_wait_uses_runtime_window",
        call.wait_args == (
            voice_realtime.FEEDBACK_WAIT_SECONDS,
            max(1, int(voice_realtime.FEEDBACK_MAX_SECONDS * 1000 / voice_realtime.FRAME_MS)),
            voice_realtime.FEEDBACK_END_SILENCE_FRAMES,
            voice_realtime.FEEDBACK_SPEECH_RMS_THRESHOLD,
        ),
        call.wait_args,
    )
    ok &= check(
        "feedback_wait_window_does_not_cap_active_note",
        optional_window_ok,
        optional_window_detail,
    )
    ok &= check("feedback_audio_written", audio_path.exists() and audio_path.stat().st_size > 44, audio_path)
    ok &= check("feedback_sidecar_written", sidecar_path.exists(), sidecar_path)
    ok &= check(
        "feedback_sidecar_has_transcript_and_metadata",
        metadata.get("transcript", "").startswith("The call was clear")
        and metadata.get("duration_seconds") == 1
        and metadata.get("student_id") == "student-feedback-1"
        and metadata.get("tags") == ["open_voice_note"],
        metadata,
    )
    ok &= check(
        "feedback_saved_to_memory",
        saved.get("student_id") == "student-feedback-1"
        and saved.get("call_id") == "fb-regression-001"
        and saved.get("participant_type") == "tester"
        and saved.get("recording_path") == str(audio_path)
        and saved.get("consent_recorded") is True,
        saved,
    )
    ok &= check(
        "feedback_partial_note_saved_after_channel_close",
        hangup_metadata.get("student_id") == "student-feedback-hangup"
        and hangup_metadata.get("duration_seconds") == 1
        and (ROOT / "feedback_fb-regression-hangup.wav").exists()
        and hangup_call.memory.calls
        and hangup_call.memory.calls[0].get("call_id") == "fb-regression-hangup",
        hangup_metadata,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
