#!/usr/bin/env python3
"""Audit and replay archived caller audio through the current Gemini Live path.

This harness is intentionally isolated from telephony and Supabase.  It uses
the production ``GeminiLiveCallRunner`` with a small in-memory call/memory
adapter, reads only the caller-side Asterisk track, discards generated playback,
and writes sanitized JSON results.  The live AudioSocket listeners and learner
records are never touched.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import time
from typing import Any
import uuid
import wave


SAMPLE_RATE = 8_000
SAMPLE_WIDTH = 2
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * FRAME_MS // 1_000
SPEECH_RMS = 220

JULY_TEST_CALL_IDS = (
    "341e0f5f-1def-45e3-bba5-0d3a7585a6fc",
    "2a8232e7-fb0a-4bb6-aa50-f64e662b97a6",
    "1088e5d4-255e-440c-b267-1a4f07ec6617",
    "b2e0ff90-35c8-454e-afe2-69b576f4f67f",
    "894b6040-7c47-4058-8ca6-9d0d21ed53cc",
    "be48a49b-8121-476f-bb9b-83d849a135f0",
    "e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be",
)

REPEAT_PROMPT_MARKERS = (
    "say it again",
    "say that again",
    "say the answer again",
    "say just the answer",
    "tell me again",
    "repeat that",
    "repeat the answer",
    "can you repeat",
    "could you repeat",
    "didn't hear",
    "did not hear",
    "didn't quite hear",
    "did not quite hear",
    "can't hear",
    "cannot hear",
    "one more time",
)


def _rms(pcm: bytes) -> int:
    usable = len(pcm) - len(pcm) % 2
    if usable <= 0:
        return 0
    samples = struct.unpack(f"<{usable // 2}h", pcm[:usable])
    return int(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))


def _wav_metrics(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
            SAMPLE_RATE,
            1,
            SAMPLE_WIDTH,
        ):
            raise ValueError(f"Unsupported WAV format: {path}")
        pcm = wav.readframes(wav.getnframes())

    frames = [pcm[offset : offset + FRAME_BYTES] for offset in range(0, len(pcm), FRAME_BYTES)]
    frame_rms = [_rms(frame) for frame in frames]
    trailing_silence_frames = 0
    for frame in reversed(frames):
        if _rms(frame) >= SPEECH_RMS:
            break
        trailing_silence_frames += 1
    tail_200ms = pcm[-SAMPLE_RATE * SAMPLE_WIDTH // 5 :]
    tail_500ms = pcm[-SAMPLE_RATE * SAMPLE_WIDTH // 2 :]
    return {
        "duration_seconds": round(len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH), 3),
        "trailing_silence_ms": trailing_silence_frames * FRAME_MS,
        "tail_200ms_rms": _rms(tail_200ms),
        "tail_500ms_rms": _rms(tail_500ms),
        "ends_in_speech": bool(tail_200ms and _rms(tail_200ms) >= SPEECH_RMS),
        "speech_frame_ratio": round(
            sum(value >= SPEECH_RMS for value in frame_rms) / max(1, len(frame_rms)),
            4,
        ),
        "max_frame_rms": max(frame_rms, default=0),
        "p95_frame_rms": (
            sorted(frame_rms)[min(len(frame_rms) - 1, int(len(frame_rms) * 0.95))]
            if frame_rms
            else 0
        ),
    }


def _write_pcm_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


def _read_pcm_wav(path: Path | str | None) -> bytes:
    if not path:
        return b""
    source = Path(path)
    if not source.exists():
        return b""
    with wave.open(str(source), "rb") as wav:
        return wav.readframes(wav.getnframes())


def _mix_pcm(left: bytes, right: bytes) -> bytes:
    sample_count = max(len(left), len(right), FRAME_BYTES) // 2
    padded_left = left.ljust(sample_count * 2, b"\x00")
    padded_right = right.ljust(sample_count * 2, b"\x00")
    left_samples = struct.unpack(f"<{sample_count}h", padded_left[: sample_count * 2])
    right_samples = struct.unpack(f"<{sample_count}h", padded_right[: sample_count * 2])
    mixed = [
        max(-32_768, min(32_767, left_value + right_value))
        for left_value, right_value in zip(left_samples, right_samples)
    ]
    return struct.pack(f"<{sample_count}h", *mixed)


def _safe_archive_id(path: Path) -> str:
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:12]
    date = path.name[:8] if path.name[:8].isdigit() else "undated"
    return f"archive_{date}_{digest}"


def _repetition_metrics(record: dict[str, Any]) -> dict[str, Any]:
    turns = record.get("turns") or []
    repeat_prompt_turns: list[int] = []
    heard: list[tuple[int, str]] = []
    for offset, turn in enumerate(turns):
        turn_index = int(turn.get("turn_index") if turn.get("turn_index") is not None else offset)
        assistant_text = " ".join(
            str((turn.get("assistant") or {}).get("text") or "").lower().split()
        )
        if any(marker in assistant_text for marker in REPEAT_PROMPT_MARKERS):
            repeat_prompt_turns.append(turn_index)
        user = turn.get("user") or {}
        user_text = " ".join(
            str(
                user.get("normalized_transcript")
                or user.get("stt_transcript")
                or turn.get("normalized_text")
                or ""
            )
            .lower()
            .split()
        )
        if user_text:
            heard.append((turn_index, user_text))

    repeated_pairs: list[list[int]] = []
    for (left_index, left), (right_index, right) in zip(heard, heard[1:]):
        if right_index - left_index > 2:
            continue
        shorter = min(len(left), len(right))
        similar = SequenceMatcher(None, left, right).ratio() >= 0.78
        if shorter >= 2 and similar:
            repeated_pairs.append([left_index, right_index])
    return {
        "repeat_prompt_count": len(repeat_prompt_turns),
        "repeat_prompt_turns": repeat_prompt_turns,
        "consecutive_repeat_count": len(repeated_pairs),
        "consecutive_repeat_turn_pairs": repeated_pairs,
        "repetition_score": len(repeat_prompt_turns) * 3 + len(repeated_pairs),
    }


def discover_archive(audio_root: Path) -> list[dict[str, Any]]:
    calls_dir = audio_root / "calls"
    json_by_recording: dict[str, tuple[Path, dict[str, Any]]] = {}
    review_records: list[tuple[Path, dict[str, Any]]] = []
    for json_path in audio_root.glob("call_*.json"):
        if json_path.name.endswith("-lwreplay.json"):
            continue
        try:
            record = json.loads(json_path.read_text())
        except (OSError, ValueError):
            continue
        mode = str(record.get("mode") or "").lower()
        if "replay" in mode:
            continue
        review_records.append((json_path, record))
        recording = Path(str((record.get("hangup_event") or {}).get("recording") or "")).name
        if recording:
            json_by_recording[recording] = (json_path, record)

    rows: list[dict[str, Any]] = []
    for rx_path in sorted(calls_dir.glob("*_rx-network.wav")):
        mixed_name = rx_path.name.replace("_rx-network.wav", ".wav")
        metadata = json_by_recording.get(mixed_name)
        if metadata is None:
            # A bridge/container failure can prevent Asterisk's hangup webhook
            # from attaching the recording path. Match those orphan tracks by
            # PBX start epoch, call-review creation time and duration.
            epoch_match = re.search(r"_(\d{10})\.\d+_rx-network\.wav$", rx_path.name)
            start_epoch = int(epoch_match.group(1)) if epoch_match else 0
            rx_duration = _wav_metrics(rx_path)["duration_seconds"]
            candidates = []
            for candidate_path, candidate in review_records:
                if (candidate.get("hangup_event") or {}).get("recording"):
                    continue
                created_at = float(candidate.get("created_at") or 0)
                duration = float(candidate.get("duration_seconds") or 0)
                start_delta = abs(created_at - start_epoch)
                duration_delta = abs(duration - rx_duration)
                if start_delta <= 90 and duration_delta <= 5:
                    candidates.append(
                        (start_delta + duration_delta, candidate_path, candidate)
                    )
            if candidates:
                _score, candidate_path, candidate = min(candidates, key=lambda item: item[0])
                metadata = (candidate_path, candidate)
        record = metadata[1] if metadata else {}
        json_path = metadata[0] if metadata else None
        call_uuid = str(record.get("call_uuid") or "")
        public_id = call_uuid if call_uuid else _safe_archive_id(rx_path)
        tx_path = rx_path.with_name(rx_path.name.replace("_rx-network.wav", "_tx-sabi.wav"))
        rx_metrics = _wav_metrics(rx_path)
        tx_metrics = _wav_metrics(tx_path) if tx_path.exists() else None
        end_reason = str(record.get("end_reason") or "")
        severe_metadata_end = any(
            marker in end_reason.lower()
            for marker in (
                "connectionreset",
                "channel_closed",
                "gemini_live_error",
                "max_call",
                "exception",
                "failed",
            )
        )
        ends_during_audio = bool(
            rx_metrics["ends_in_speech"]
            or (tx_metrics and tx_metrics["ends_in_speech"])
        )
        short_after_activity = bool(
            rx_metrics["duration_seconds"] < 20
            and int(record.get("user_turns") or 0) > 0
        )
        reasons = []
        if severe_metadata_end:
            reasons.append("metadata_failure")
        if rx_metrics["ends_in_speech"]:
            reasons.append("learner_audio_at_end")
        if tx_metrics and tx_metrics["ends_in_speech"]:
            reasons.append("sabi_audio_at_end")
        if short_after_activity:
            reasons.append("short_after_learner_activity")
        rows.append(
            {
                "archive_id": public_id,
                "call_uuid": call_uuid or None,
                "date": rx_path.name[:8],
                "mode": record.get("mode"),
                "duration_seconds": record.get("duration_seconds") or rx_metrics["duration_seconds"],
                "captured_user_turns": record.get("user_turns"),
                "review_turns": len(record.get("turns") or []),
                "end_reason": end_reason or None,
                "rx": rx_metrics,
                "tx": tx_metrics,
                "likely_abrupt": bool(severe_metadata_end or ends_during_audio or short_after_activity),
                "abrupt_reasons": reasons,
                "repetition": _repetition_metrics(record),
                # Private runtime fields are stripped before writing reports.
                "_rx_path": str(rx_path),
                "_json_path": str(json_path) if json_path else None,
            }
        )
    return rows


def sanitized(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


class _FakeWriter:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class _ReplayMemory:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None

    async def find_or_create_student(self, _phone: str) -> dict[str, Any]:
        return {
            "id": "archive-replay-student",
            "name": "Learner",
            "total_sessions": 1,
            "current_module": 4,
            "needs_identity_confirmation": False,
        }

    async def get_effective_learning_state(self, _student: dict[str, Any]) -> dict[str, Any]:
        return {
            "course": "numeracy",
            "phase": "lesson",
            "current_module": 4,
            "current_week": 12,
            "current_lesson": 1,
            "active_skill": "multiplication",
            "diagnostic_status": "complete",
            "scaffold_depth": 0,
            "next_step": "Introduce multiplication as small equal groups.",
            "grading_evidence": {"skills": {}},
        }

    async def save_phone_session(self, **kwargs: Any) -> dict[str, Any]:
        self.saved = kwargs
        return {"scorecard": kwargs.get("authoritative_score"), "teacher_note": None}

    def clear_call(self, _call_id: str) -> None:
        return None


class _LiveStatus:
    def __init__(self, rows: list[dict[str, Any]], output_dir: Path) -> None:
        self.output_dir = output_dir
        self.started_at = time.time()
        self.calls: dict[str, dict[str, Any]] = {
            row["archive_id"]: {
                "archive_id": row["archive_id"],
                "date": row["date"],
                "source_duration_seconds": row["duration_seconds"],
                "repeat_prompt_count": row["repetition"]["repeat_prompt_count"],
                "likely_abrupt": row["likely_abrupt"],
                "abrupt_reasons": row["abrupt_reasons"],
                "status": "pending",
                "turns": [],
                "error": None,
            }
            for row in rows
        }
        self.write()

    def mark_running(self, archive_id: str) -> None:
        self.calls[archive_id]["status"] = "running"
        self.calls[archive_id]["started_at"] = time.time()
        self.write()

    def add_turn(self, archive_id: str, turn: dict[str, Any]) -> None:
        self.calls[archive_id]["turns"].append(turn)
        self.calls[archive_id]["last_update_at"] = time.time()
        self.write()

    def mark_complete(self, archive_id: str, *, error: str | None, elapsed: float) -> None:
        self.calls[archive_id]["status"] = "failed" if error else "complete"
        self.calls[archive_id]["error"] = error
        self.calls[archive_id]["elapsed_seconds"] = elapsed
        self.calls[archive_id]["completed_at"] = time.time()
        self.write()

    def write(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        calls = list(self.calls.values())
        payload = {
            "started_at": self.started_at,
            "updated_at": time.time(),
            "summary": {
                "total": len(calls),
                "pending": sum(call["status"] == "pending" for call in calls),
                "running": sum(call["status"] == "running" for call in calls),
                "complete": sum(call["status"] == "complete" for call in calls),
                "failed": sum(call["status"] == "failed" for call in calls),
                "turns": sum(len(call["turns"]) for call in calls),
            },
            "calls": calls,
        }
        temporary = self.output_dir / "live_status.tmp"
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        temporary.replace(self.output_dir / "live_status.json")


class _ReplayCall:
    def __init__(
        self,
        row: dict[str, Any],
        *,
        speed: float,
        grace_seconds: float,
        live_status: _LiveStatus,
        output_dir: Path,
    ) -> None:
        source_uuid = row.get("call_uuid") or str(uuid.uuid5(uuid.NAMESPACE_URL, row["archive_id"]))
        self.call_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"gemini-live-replay:{source_uuid}"))
        self.call_id = self.call_uuid
        self.source_archive_id = row["archive_id"]
        self.source_path = Path(row["_rx_path"])
        self.phone = "+15555550199"
        self.mode = "isolated_archive_replay"
        self.attempt = 1
        self.memory = _ReplayMemory()
        self.audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=1_500)
        self.writer = _FakeWriter()
        self.hungup = False
        self.end_reason = "unknown"
        self.last_tts_provider = ""
        self.speed = max(0.1, speed)
        self.grace_seconds = max(1.0, grace_seconds)
        self.live_status = live_status
        self.output_dir = output_dir
        self.review_turns: list[dict[str, Any]] = []
        self.output_audio_bytes = 0
        self._latest_sabi_frame = bytes(FRAME_BYTES)
        self.live_mix_path = self.output_dir / "live_mix.raw"

    def set_end_reason(self, reason: str) -> None:
        if self.end_reason == "unknown":
            self.end_reason = reason

    async def read_loop(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with wave.open(str(self.source_path), "rb") as wav, self.live_mix_path.open(
            "wb", buffering=0
        ) as observer:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
                SAMPLE_RATE,
                1,
                SAMPLE_WIDTH,
            ):
                raise ValueError(f"Unsupported replay WAV: {self.source_path}")
            while not self.hungup:
                frame = wav.readframes(SAMPLE_RATE * FRAME_MS // 1_000)
                if not frame:
                    break
                observer.write(_mix_pcm(frame, self._latest_sabi_frame))
                self._latest_sabi_frame = bytes(FRAME_BYTES)
                await self.audio_queue.put(frame)
                await asyncio.sleep((FRAME_MS / 1_000) / self.speed)
        # Preserve the same audio-domain silence needed by automatic VAD, then
        # allow Gemini to finish its final response before closing the stream.
            grace_frames = max(50, int(self.grace_seconds * 1_000 / FRAME_MS))
            for frame_index in range(grace_frames):
                silence = bytes(FRAME_BYTES)
                observer.write(_mix_pcm(silence, self._latest_sabi_frame))
                self._latest_sabi_frame = bytes(FRAME_BYTES)
                if frame_index < 50:
                    await self.audio_queue.put(silence)
                await asyncio.sleep((FRAME_MS / 1_000) / self.speed)
        await self.audio_queue.put(None)

    async def send_pcm_frame(self, frame: bytes) -> None:
        self.output_audio_bytes += len(frame)
        self._latest_sabi_frame = frame

    async def send_hangup(self) -> None:
        return None

    def persist_turn_review(self, **kwargs: Any) -> None:
        transcript = kwargs.get("transcript") or {}
        turn_index = int(kwargs.get("turn") or 0)
        turn_audio_dir = self.output_dir / "audio" / "turns"
        learner_pcm = _read_pcm_wav(kwargs.get("user_audio_path"))
        sabi_pcm = bytes(kwargs.get("assistant_pcm") or b"")
        learner_name = f"{self.source_archive_id}-turn-{turn_index:02d}-learner.wav"
        sabi_name = f"{self.source_archive_id}-turn-{turn_index:02d}-sabi.wav"
        exchange_name = f"{self.source_archive_id}-turn-{turn_index:02d}-exchange.wav"
        if learner_pcm:
            _write_pcm_wav(turn_audio_dir / learner_name, learner_pcm)
        if sabi_pcm:
            _write_pcm_wav(turn_audio_dir / sabi_name, sabi_pcm)
        if learner_pcm or sabi_pcm:
            pause = bytes(int(SAMPLE_RATE * SAMPLE_WIDTH * 0.4))
            _write_pcm_wav(
                turn_audio_dir / exchange_name,
                learner_pcm + pause + sabi_pcm,
            )
        turn = {
            "turn": turn_index,
            "heard": transcript.get("text"),
            "assistant": kwargs.get("assistant_text"),
            "tool_events": (transcript.get("ensemble_results") or {}).get(
                "gemini_live_tools"
            ),
            "flags": kwargs.get("flags"),
            "timings": kwargs.get("timings"),
            "learner_audio_url": (
                f"audio/turns/{learner_name}" if learner_pcm else None
            ),
            "sabi_audio_url": f"audio/turns/{sabi_name}" if sabi_pcm else None,
            "exchange_audio_url": (
                f"audio/turns/{exchange_name}" if learner_pcm or sabi_pcm else None
            ),
        }
        self.review_turns.append(turn)
        self.live_status.add_turn(self.source_archive_id, turn)
        print(
            json.dumps(
                {
                    "archive_id": self.source_archive_id,
                    "turn": turn["turn"],
                    "heard": turn["heard"],
                    "assistant": turn["assistant"],
                    "flags": turn["flags"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )


async def replay_one(
    row: dict[str, Any],
    *,
    speed: float,
    grace_seconds: float,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    live_status: _LiveStatus,
) -> dict[str, Any]:
    from gemini_live import GEMINI_LIVE_MODEL, GEMINI_LIVE_VOICE, GeminiLiveCallRunner

    async with semaphore:
        started = time.monotonic()
        live_status.mark_running(row["archive_id"])
        call = _ReplayCall(
            row,
            speed=speed,
            grace_seconds=grace_seconds,
            live_status=live_status,
            output_dir=output_dir,
        )
        runner = GeminiLiveCallRunner(call)
        error = None
        try:
            await runner.run()
        except Exception as exc:  # retain one failed replay without stopping the batch
            error = f"{type(exc).__name__}: {exc}"
        result = {
            "source": sanitized(row),
            "pipeline": {
                "model": GEMINI_LIVE_MODEL,
                "voice": GEMINI_LIVE_VOICE,
                "runner": "GeminiLiveCallRunner",
                "audio_rate_hz": SAMPLE_RATE,
                "speed": speed,
            },
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "end_reason": call.end_reason,
            "error": error,
            "turns_heard": len(call.review_turns),
            "turns": call.review_turns,
            "messages": runner.messages,
            "tool_score": runner.tools.authoritative_session_score() if runner.tools else None,
            "usage_metadata": runner.usage_metadata,
            "generated_audio_seconds": round(
                call.output_audio_bytes / (SAMPLE_RATE * SAMPLE_WIDTH), 3
            ),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{row['archive_id']}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
        )
        live_status.mark_complete(
            row["archive_id"],
            error=error,
            elapsed=result["elapsed_seconds"],
        )
        print(
            json.dumps(
                {
                    "archive_id": row["archive_id"],
                    "elapsed_seconds": result["elapsed_seconds"],
                    "turns_heard": result["turns_heard"],
                    "end_reason": result["end_reason"],
                    "error": error,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return result


async def replay_many(
    rows: list[dict[str, Any]],
    *,
    speed: float,
    grace_seconds: float,
    concurrency: int,
    output_dir: Path,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    _export_learner_audio(rows, output_dir)
    _write_dashboard(output_dir)
    live_status = _LiveStatus(rows, output_dir)
    results = await asyncio.gather(
        *(
            replay_one(
                row,
                speed=speed,
                grace_seconds=grace_seconds,
                output_dir=output_dir,
                semaphore=semaphore,
                live_status=live_status,
            )
            for row in rows
        )
    )
    (output_dir / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True)
    )
    return results


def _export_learner_audio(rows: list[dict[str, Any]], output_dir: Path) -> None:
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        destination = audio_dir / f"{row['archive_id']}.wav"
        if not destination.exists():
            shutil.copyfile(row["_rx_path"], destination)


def _write_dashboard(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sabi · Gemini Live Replay</title>
  <style>
    :root { --ink:#221d17; --muted:#71675b; --ivory:#fbf6e9; --card:#fffdf7;
      --gold:#b88a25; --line:#e4d8bc; --green:#28745a; --red:#a6453d; --blue:#315b8b; }
    * { box-sizing:border-box; } body { margin:0; background:var(--ivory); color:var(--ink);
      font:15px/1.45 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    header { position:sticky; top:0; z-index:2; padding:22px 28px 18px; color:#fff;
      background:linear-gradient(115deg,#211a11,#4b3517); box-shadow:0 5px 22px #33240d26; }
    h1 { margin:0 0 3px; font:700 25px/1.2 Georgia,serif; letter-spacing:.2px; }
    .sub { color:#eadcb9; } main { padding:22px 28px 46px; max-width:1500px; margin:auto; }
    .stats { display:grid; grid-template-columns:repeat(5,minmax(110px,1fr)); gap:11px; margin-bottom:18px; }
    .stat { background:var(--card); border:1px solid var(--line); border-radius:13px; padding:13px 15px; }
    .stat b { display:block; font-size:23px; color:var(--gold); } .stat span { color:var(--muted); }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(390px,1fr)); gap:15px; }
    .call { background:var(--card); border:1px solid var(--line); border-radius:15px; overflow:hidden;
      box-shadow:0 7px 20px #5d461318; }
    .callhead { display:flex; justify-content:space-between; gap:14px; padding:14px 16px;
      border-bottom:1px solid var(--line); background:#fff9e9; }
    .title { font-weight:750; } .meta { font-size:12px; color:var(--muted); margin-top:3px; }
    .status { height:max-content; padding:4px 9px; border-radius:999px; font-size:11px; font-weight:800;
      text-transform:uppercase; letter-spacing:.5px; background:#eee7d8; color:#6b5d47; }
    .player { padding:10px 14px 0; } audio { width:100%; height:36px; }
    .running { background:#dbe8f8; color:var(--blue); animation:pulse 1.2s infinite; }
    .complete { background:#dcefe8; color:var(--green); } .failed { background:#f5deda; color:var(--red); }
    @keyframes pulse { 50% { opacity:.55; } } .turns { max-height:450px; overflow:auto; padding:12px 14px; }
    .turn { margin:0 0 11px; padding:11px 12px; border-radius:11px; background:#f7f0df; }
    .who { font-size:11px; color:var(--gold); font-weight:800; text-transform:uppercase; letter-spacing:.6px; }
    .heard { font-weight:680; margin:3px 0 8px; } .reply { color:#514a40; }
    .flags { margin-top:7px; font-size:11px; color:var(--muted); } .empty { color:var(--muted); padding:12px 2px; }
    .error { color:var(--red); padding:12px 14px; } @media(max-width:700px) {
      main,header { padding-left:14px; padding-right:14px; } .stats { grid-template-columns:repeat(2,1fr); }
      .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body><header><h1>Sabi · Gemini Live historical replay</h1>
  <div class="sub">Exact 8 kHz caller audio · current production prompt, VAD, tools and Kore voice · isolated from live calls</div>
</header><main><section class="stats" id="stats"></section><section class="grid" id="calls"></section></main>
<script>
const esc = s => String(s ?? '').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
const short = id => id.startsWith('archive_') ? id : id.slice(0,8);
function miniPlayer(label,url){ return url?`<div class="who" style="margin-top:7px">${label}</div><audio controls preload="metadata" src="${esc(url)}"></audio>`:''; }
function turnHtml(t){ const tools=(t.tool_events||[]).map(x=>x.name).join(', '); return `<div class="turn">
  <div class="who">Learner · turn ${esc(t.turn)}</div><div class="heard">${esc(t.heard||'[no transcript]')}</div>
  <div class="who">Sabi</div><div class="reply">${esc(t.assistant||'[no spoken response]')}</div>
  ${miniPlayer('Play learner turn',t.learner_audio_url)}${miniPlayer('Play Sabi reply',t.sabi_audio_url)}
  ${miniPlayer('Play learner → Sabi exchange',t.exchange_audio_url)}
  <div class="flags">${esc((t.flags||[]).join(' · '))}${tools?' · tools: '+esc(tools):''}</div></div>`; }
async function refresh(){ try { const d=await fetch('live_status.json?'+Date.now()).then(r=>r.json());
  const s=d.summary; document.getElementById('stats').innerHTML=[['Total',s.total],['Running',s.running],['Complete',s.complete],['Failed',s.failed],['Turns heard',s.turns]]
    .map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
  document.getElementById('calls').innerHTML=d.calls.map(c=>`<article class="call"><div class="callhead"><div>
    <div class="title">Call ${esc(short(c.archive_id))}</div><div class="meta">${esc(c.date)} · ${esc(c.source_duration_seconds)}s
    ${c.repeat_prompt_count?' · historical repeats '+esc(c.repeat_prompt_count):''}${c.likely_abrupt?' · abrupt-end candidate':''}</div></div>
    <span class="status ${esc(c.status)}">${esc(c.status)}</span></div>${c.error?`<div class="error">${esc(c.error)}</div>`:''}
    <div class="player"><div class="who">Original learner-side phone audio</div>
    <audio controls preload="metadata" src="audio/${encodeURIComponent(c.archive_id)}.wav"></audio></div>
    <div class="turns">${c.turns.length?c.turns.map(turnHtml).join(''):'<div class="empty">Waiting for the first learner turn…</div>'}</div></article>`).join('');
} catch(e){} } refresh(); setInterval(refresh,1000);
</script></body></html>"""
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-root", type=Path, default=Path("/shared/audio"))
    parser.add_argument("--output-dir", type=Path, default=Path("/results"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--manifest", type=Path)

    replay = subparsers.add_parser("replay")
    replay.add_argument(
        "--cohort",
        choices=("july", "abrupt", "expanded", "all"),
        default="july",
    )
    replay.add_argument("--call-id", action="append", default=[])
    replay.add_argument("--speed", type=float, default=1.0)
    replay.add_argument("--grace-seconds", type=float, default=4.0)
    replay.add_argument("--concurrency", type=int, default=3)
    replay.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = discover_archive(args.audio_root)
    if args.command == "inventory":
        payload = [sanitized(row) for row in rows]
        manifest = args.manifest or (args.output_dir / "archive_inventory.json")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        print(
            json.dumps(
                {
                    "recordings": len(rows),
                    "likely_abrupt": sum(bool(row["likely_abrupt"]) for row in rows),
                    "with_review_json": sum(bool(row["call_uuid"]) for row in rows),
                    "manifest": str(manifest),
                },
                sort_keys=True,
            )
        )
        return

    by_id = {row["archive_id"]: row for row in rows}
    if args.call_id:
        missing = sorted(set(args.call_id) - set(by_id))
        if missing:
            raise SystemExit(f"Unknown call IDs: {', '.join(missing)}")
        selected = [by_id[call_id] for call_id in args.call_id]
    elif args.cohort == "july":
        selected = [by_id[call_id] for call_id in JULY_TEST_CALL_IDS if call_id in by_id]
    elif args.cohort == "abrupt":
        selected = [row for row in rows if row["likely_abrupt"]]
    elif args.cohort == "expanded":
        selected_ids = set(JULY_TEST_CALL_IDS)
        selected = [
            row
            for row in rows
            if row["likely_abrupt"] or row["archive_id"] in selected_ids
        ]
    else:
        selected = rows
    if args.limit > 0:
        selected = selected[: args.limit]
    print(
        json.dumps(
            {
                "selected": len(selected),
                "cohort": args.cohort,
                "speed": args.speed,
                "concurrency": args.concurrency,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    asyncio.run(
        replay_many(
            selected,
            speed=args.speed,
            grace_seconds=args.grace_seconds,
            concurrency=args.concurrency,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    main()
