#!/usr/bin/env python3
"""Regression checks for optional end-of-call voice feedback capture.

This exercises the AudioSocket feedback path without a live PBX call. It proves
that the pilot feedback prompt can collect audio, write a review sidecar, and
persist the metadata through the same method production uses.

Covers the post-2026-06-29 behavior:
  - Longer default wait (25s) so testers can gather thoughts.
  - Lower RMS threshold (220) so softer voices register.
  - Audible "go" cue beep before the recording window opens.
  - One automatic retry when the first window times out with no speech.
  - DTMF skip digit ("1" by default) short-circuits the wait.
  - A sidecar is ALWAYS written, even with no captured audio, including
    ended_reason / time_to_first_speech_ms / rms_telemetry so admins can see
    why a window closed.
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


class _BaseFakeCall:
    """Minimal fixture mirroring the attributes record_feedback_note touches."""

    def __init__(self, uuid_suffix: str) -> None:
        self.call_uuid = f"fb-regression-{uuid_suffix}"
        self.call_id = self.call_uuid
        self.phone = "+2348033374126"
        self.mode = "inbound"
        self.attempt = 1
        self.hungup = False
        self.prompt_calls: list[tuple[str, str]] = []
        self.played_pcm_lengths: list[int] = []
        self.wait_calls: list[dict] = []
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.dtmf_queue: asyncio.Queue = asyncio.Queue()
        self.drain_count = 0
        self.stt = FakeSTT()
        self.memory = FakeMemory()

    async def synthesize_pcm(self, text: str, label: str) -> bytes:
        self.prompt_calls.append((label, text))
        return b"\0" * voice_realtime.FRAME_BYTES

    async def play_pcm(self, pcm: bytes) -> None:
        self.played_pcm_lengths.append(len(pcm))

    def drain_audio(self) -> None:
        self.drain_count += 1
        while True:
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                return


class FakeFeedbackCall(_BaseFakeCall):
    """Speaker leaves a clear note on the first attempt."""

    def __init__(self) -> None:
        super().__init__("001")

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
        dtmf_skip_digit: str | None = None,
        rms_telemetry: dict | None = None,
    ) -> bytes:
        self.wait_calls.append({
            "timeout_seconds": timeout_seconds,
            "max_frames": max_frames,
            "end_silence_frames": end_silence_frames,
            "speech_threshold": speech_threshold,
            "dtmf_skip_digit": dtmf_skip_digit,
        })
        if rms_telemetry is not None:
            rms_telemetry.update({
                "peak_rms": 540,
                "mean_rms": 285,
                "frames_observed": 200,
                "frames_above_threshold": 187,
                "ended_reason": "speech_captured",
                "time_to_first_speech_ms": 3450,
                "wait_seconds_used": 3.5,
            })
        return struct.pack("<h", 1800) * voice_realtime.SAMPLE_RATE


class FakeFeedbackHangupCall(_BaseFakeCall):
    """Channel closes during recording — partial PCM must still be saved."""

    def __init__(self) -> None:
        super().__init__("hangup")

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
        dtmf_skip_digit: str | None = None,
        rms_telemetry: dict | None = None,
    ) -> bytes:
        self.wait_calls.append({"timeout_seconds": timeout_seconds})
        self.hungup = True
        if rms_telemetry is not None:
            rms_telemetry.update({
                "peak_rms": 600,
                "mean_rms": 310,
                "frames_observed": 90,
                "frames_above_threshold": 60,
                "ended_reason": "channel_closed",
                "time_to_first_speech_ms": 1200,
            })
        return struct.pack("<h", 1900) * voice_realtime.SAMPLE_RATE


class FakeFeedbackRetryCall(_BaseFakeCall):
    """First window times out with no speech; second window captures a note."""

    def __init__(self) -> None:
        super().__init__("retry")
        self._attempt = 0

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
        dtmf_skip_digit: str | None = None,
        rms_telemetry: dict | None = None,
    ):
        self._attempt += 1
        self.wait_calls.append({"timeout_seconds": timeout_seconds, "attempt": self._attempt})
        if self._attempt == 1:
            if rms_telemetry is not None:
                rms_telemetry.update({
                    "peak_rms": 110,
                    "mean_rms": 70,
                    "frames_observed": 1250,
                    "frames_above_threshold": 0,
                    "ended_reason": "wait_timeout",
                    "time_to_first_speech_ms": None,
                })
            return None
        if rms_telemetry is not None:
            rms_telemetry.update({
                "peak_rms": 480,
                "mean_rms": 240,
                "frames_observed": 90,
                "frames_above_threshold": 55,
                "ended_reason": "speech_captured",
                "time_to_first_speech_ms": 1900,
            })
        return struct.pack("<h", 1600) * voice_realtime.SAMPLE_RATE


class FakeFeedbackDtmfSkipCall(_BaseFakeCall):
    """Caller presses 1 to skip the feedback window."""

    def __init__(self) -> None:
        super().__init__("dtmf-skip")

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
        dtmf_skip_digit: str | None = None,
        rms_telemetry: dict | None = None,
    ):
        self.wait_calls.append({"dtmf_skip_digit": dtmf_skip_digit})
        if rms_telemetry is not None:
            rms_telemetry.update({
                "peak_rms": 100,
                "mean_rms": 60,
                "frames_observed": 40,
                "frames_above_threshold": 0,
                "ended_reason": "dtmf_skipped",
                "time_to_first_speech_ms": None,
            })
        return None


class FakeFeedbackTimeoutCall(_BaseFakeCall):
    """Both windows time out — sidecar must record why."""

    def __init__(self) -> None:
        super().__init__("timeout")

    async def wait_for_optional_utterance(
        self,
        timeout_seconds: int,
        max_frames: int | None = None,
        end_silence_frames: int | None = None,
        speech_threshold: int | None = None,
        dtmf_skip_digit: str | None = None,
        rms_telemetry: dict | None = None,
    ):
        self.wait_calls.append({"timeout_seconds": timeout_seconds})
        if rms_telemetry is not None:
            rms_telemetry.update({
                "peak_rms": 95,
                "mean_rms": 50,
                "frames_observed": 1250,
                "frames_above_threshold": 0,
                "ended_reason": "wait_timeout",
                "time_to_first_speech_ms": None,
            })
        return None


async def _run(
    call: _BaseFakeCall,
    learning_state: dict | None = None,
    *,
    requested_by_caller: bool = False,
) -> dict:
    await voice_realtime.RealtimeCall.record_feedback_note(
        call,
        student_id=f"student-{call.call_uuid}",
        learning_state=learning_state or {"course": "numeracy", "current_module": 2},
        requested_by_caller=requested_by_caller,
    )
    sidecar = ROOT / f"feedback_{call.call_uuid}.json"
    return json.loads(sidecar.read_text()) if sidecar.exists() else {}


async def run_optional_wait_window_check() -> tuple[bool, dict]:
    """The wait-to-start timeout must not cap an in-progress voice note."""
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "optional-window-regression"
    call.audio_queue = asyncio.Queue()
    call.dtmf_queue = asyncio.Queue()
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


async def run_dtmf_skip_check() -> tuple[bool, dict]:
    """A pre-queued DTMF skip digit returns immediately without consuming audio."""
    call = object.__new__(voice_realtime.RealtimeCall)
    call.call_uuid = "dtmf-skip-regression"
    call.audio_queue = asyncio.Queue()
    call.dtmf_queue = asyncio.Queue()
    call.pre_roll = deque(maxlen=0)
    call.hungup = False
    call.end_reason = "unknown"
    call.set_end_reason = lambda reason: setattr(call, "end_reason", reason)

    await call.dtmf_queue.put("1")
    telemetry: dict = {}
    started_at = time.monotonic()
    pcm = await voice_realtime.RealtimeCall.wait_for_optional_utterance(
        call,
        timeout_seconds=10,
        max_frames=8,
        end_silence_frames=3,
        dtmf_skip_digit="1",
        rms_telemetry=telemetry,
    )
    elapsed = time.monotonic() - started_at
    return (
        pcm is None
        and telemetry.get("ended_reason") == "dtmf_skipped"
        and elapsed < 0.5
    ), {
        "pcm": pcm,
        "elapsed_seconds": round(elapsed, 3),
        "telemetry": telemetry,
    }


def main() -> int:
    ok = True

    # 1. Tuned defaults — protect against silent regressions in the env-var defaults.
    ok &= check(
        "feedback_wait_window_at_least_25s",
        voice_realtime.FEEDBACK_WAIT_SECONDS >= 25,
        voice_realtime.FEEDBACK_WAIT_SECONDS,
    )
    ok &= check(
        "feedback_speech_rms_at_most_240",
        voice_realtime.FEEDBACK_SPEECH_RMS_THRESHOLD <= 240,
        voice_realtime.FEEDBACK_SPEECH_RMS_THRESHOLD,
    )
    ok &= check(
        "feedback_end_silence_at_least_5500ms",
        voice_realtime.FEEDBACK_END_SILENCE_MS >= 5500,
        voice_realtime.FEEDBACK_END_SILENCE_MS,
    )
    ok &= check(
        "feedback_retry_enabled_by_default",
        voice_realtime.FEEDBACK_RETRY_ENABLED is True,
        voice_realtime.FEEDBACK_RETRY_ENABLED,
    )
    ok &= check(
        "feedback_dtmf_skip_digit_configured",
        voice_realtime.FEEDBACK_DTMF_SKIP_DIGIT == "1",
        voice_realtime.FEEDBACK_DTMF_SKIP_DIGIT,
    )
    ok &= check(
        "feedback_go_cue_enabled",
        voice_realtime.FEEDBACK_GO_CUE_MS > 0,
        voice_realtime.FEEDBACK_GO_CUE_MS,
    )

    # 2. Gate enabled for any phone when mode=all.
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
    ok &= check(
        "feedback_request_intent_detected",
        voice_realtime._looks_like_feedback_request("Please let me leave feedback about the call")
        and voice_realtime._looks_like_feedback_request("I want to complain")
        and voice_realtime._looks_like_feedback_request("Can I leave a voice note?"),
    )
    ok &= check(
        "feedback_request_intent_rejects_lesson_answer",
        not voice_realtime._looks_like_feedback_request("five naira and three naira makes eight"),
    )
    ok &= check(
        "feedback_offer_allows_requested_even_without_student_id",
        voice_realtime._should_offer_feedback(
            None,
            [{"role": "assistant", "content": "hello"}],
            False,
            "feedback_requested",
        ),
    )
    ok &= check(
        "feedback_offer_blocks_after_hangup",
        not voice_realtime._should_offer_feedback(
            "student-1",
            [{"role": "assistant", "content": "hello"}],
            True,
            "feedback_requested",
        ),
    )

    # 3. Happy path: prompt → go cue → speech captured → audio + transcript + sidecar.
    call = FakeFeedbackCall()
    metadata = asyncio.run(_run(call))
    audio_path = ROOT / f"feedback_{call.call_uuid}.wav"
    saved = call.memory.calls[0] if call.memory.calls else {}

    ok &= check(
        "feedback_prompt_played",
        any(label == "rt_feedback_prompt" for label, _ in call.prompt_calls),
        call.prompt_calls,
    )
    ok &= check(
        "feedback_go_cue_played_after_prompt",
        len(call.played_pcm_lengths) >= 2 and call.played_pcm_lengths[1] > 0,
        call.played_pcm_lengths,
    )
    ok &= check(
        "feedback_does_not_directly_drain_after_go_cue",
        call.drain_count == 1,
        call.drain_count,
    )
    ok &= check(
        "feedback_wait_passes_dtmf_skip_digit",
        call.wait_calls and call.wait_calls[0].get("dtmf_skip_digit") == voice_realtime.FEEDBACK_DTMF_SKIP_DIGIT,
        call.wait_calls,
    )
    ok &= check(
        "feedback_wait_uses_runtime_window",
        call.wait_calls
        and call.wait_calls[0].get("timeout_seconds") == voice_realtime.FEEDBACK_WAIT_SECONDS
        and call.wait_calls[0].get("speech_threshold") == voice_realtime.FEEDBACK_SPEECH_RMS_THRESHOLD,
        call.wait_calls,
    )
    ok &= check(
        "feedback_audio_written",
        audio_path.exists() and audio_path.stat().st_size > 44,
        audio_path,
    )
    ok &= check(
        "feedback_sidecar_has_telemetry",
        metadata.get("ended_reason") == "speech_captured"
        and metadata.get("time_to_first_speech_ms") == 3450
        and metadata.get("rms_telemetry", {}).get("peak") == 540
        and metadata.get("prompt_played_seconds") is not None,
        metadata,
    )
    ok &= check(
        "feedback_sidecar_has_transcript_and_metadata",
        metadata.get("transcript", "").startswith("The call was clear")
        and metadata.get("duration_seconds") == 1
        and metadata.get("tags") == ["open_voice_note"],
        metadata,
    )
    ok &= check(
        "feedback_saved_to_memory_with_telemetry",
        saved.get("student_id", "").startswith("student-fb-regression-001")
        and saved.get("participant_type") == "tester"
        and saved.get("consent_recorded") is True
        and saved.get("metadata", {}).get("ended_reason") == "speech_captured",
        saved,
    )

    requested_call = FakeFeedbackCall()
    requested_call.call_uuid = "fb-regression-requested"
    requested_call.call_id = requested_call.call_uuid
    requested_metadata = asyncio.run(_run(requested_call, requested_by_caller=True))
    requested_prompt = requested_call.prompt_calls[0][1] if requested_call.prompt_calls else ""
    ok &= check(
        "feedback_requested_prompt_is_short_and_direct",
        requested_metadata.get("ended_reason") == "speech_captured"
        and "After the beep" in requested_prompt
        and len(requested_prompt) < len(voice_realtime.FEEDBACK_PROMPT_TEXT),
        requested_prompt,
    )

    # 4. Channel-closed mid-recording still persists the partial PCM.
    hangup_call = FakeFeedbackHangupCall()
    hangup_metadata = asyncio.run(_run(hangup_call))
    ok &= check(
        "feedback_partial_note_saved_after_channel_close",
        hangup_metadata.get("duration_seconds") == 1
        and (ROOT / f"feedback_{hangup_call.call_uuid}.wav").exists()
        and hangup_call.memory.calls
        and hangup_metadata.get("ended_reason") == "channel_closed",
        hangup_metadata,
    )

    # 5. Retry: first attempt times out, second attempt captures.
    retry_call = FakeFeedbackRetryCall()
    retry_metadata = asyncio.run(_run(retry_call))
    ok &= check(
        "feedback_retries_once_after_timeout",
        len(retry_call.wait_calls) == 2,
        retry_call.wait_calls,
    )
    ok &= check(
        "feedback_retry_does_not_directly_drain_after_go_cue",
        retry_call.drain_count == 1,
        retry_call.drain_count,
    )
    ok &= check(
        "feedback_retry_prompt_played",
        any(label == "rt_feedback_retry" for label, _ in retry_call.prompt_calls),
        retry_call.prompt_calls,
    )
    ok &= check(
        "feedback_retry_success_sidecar",
        retry_metadata.get("ended_reason") == "speech_captured"
        and len(retry_metadata.get("wait_attempts", [])) == 2
        and retry_metadata.get("wait_attempts", [{}])[0].get("metrics", {}).get("ended_reason") == "wait_timeout",
        retry_metadata,
    )

    # 6. DTMF skip writes a sidecar but no audio.
    dtmf_call = FakeFeedbackDtmfSkipCall()
    dtmf_metadata = asyncio.run(_run(dtmf_call))
    ok &= check(
        "feedback_dtmf_skip_writes_no_audio_sidecar",
        dtmf_metadata.get("ended_reason") == "dtmf_skipped"
        and dtmf_metadata.get("duration_seconds") == 0
        and not (ROOT / f"feedback_{dtmf_call.call_uuid}.wav").exists()
        and "no_audio:dtmf_skipped" in dtmf_metadata.get("tags", []),
        dtmf_metadata,
    )

    # 7. Total timeout (both attempts silent) still writes a sidecar with the reason.
    timeout_call = FakeFeedbackTimeoutCall()
    timeout_metadata = asyncio.run(_run(timeout_call))
    ok &= check(
        "feedback_total_timeout_writes_diagnostic_sidecar",
        timeout_metadata.get("ended_reason") == "wait_timeout"
        and timeout_metadata.get("duration_seconds") == 0
        and len(timeout_call.wait_calls) == 2  # first attempt + retry
        and "no_audio:wait_timeout" in timeout_metadata.get("tags", []),
        timeout_metadata,
    )

    # 8. wait_for_optional_utterance internal: pre-queued speech is captured fast.
    optional_window_ok, optional_window_detail = asyncio.run(run_optional_wait_window_check())
    ok &= check(
        "feedback_wait_window_does_not_cap_active_note",
        optional_window_ok,
        optional_window_detail,
    )

    # 9. wait_for_optional_utterance internal: DTMF skip short-circuits before audio.
    dtmf_skip_ok, dtmf_skip_detail = asyncio.run(run_dtmf_skip_check())
    ok &= check(
        "feedback_wait_dtmf_skip_short_circuits",
        dtmf_skip_ok,
        dtmf_skip_detail,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
