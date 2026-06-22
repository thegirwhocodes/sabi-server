#!/usr/bin/env python3
"""Regression check that FastAGI calls persist learner state.

The production line now uses AudioSocket for barge-in, but the FastAGI fallback
must not silently teach a child and then forget the call.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types

os.environ.setdefault("SABI_SHARED_AUDIO_DIR", "/tmp/sabi-shared-audio")

sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=lambda *args, **kwargs: None))

import voice_asterisk


class FakeReader:
    def __init__(self, lines: list[str]):
        self.lines = [line.encode("utf-8") for line in lines]

    async def readline(self) -> bytes:
        if not self.lines:
            return b""
        return self.lines.pop(0)


class FakeWriter:
    def __init__(self):
        self.commands: list[str] = []
        self.closed = False

    def get_extra_info(self, _name: str):
        return ("127.0.0.1", 4573)

    def write(self, data: bytes) -> None:
        self.commands.append(data.decode("utf-8").strip())

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeMemory:
    def __init__(self):
        self.saved: list[dict] = []
        self.cleared: list[str] = []
        self.state = {
            "course": "numeracy",
            "phase": "onboarding",
            "onboarding_status": "complete",
            "diagnostic_status": "not_started",
            "current_module": 0,
            "current_week": 1,
            "current_lesson": 1,
            "active_skill": "diagnostic",
            "literacy": {"diagnostic_status": "not_started"},
        }

    async def find_or_create_student(self, phone_number: str):
        return {"id": "student-agi", "name": "Remi", "current_module": 0, "phone_number": phone_number}

    async def get_effective_learning_state(self, _student: dict):
        return dict(self.state)

    async def save_phone_session(self, **kwargs):
        self.saved.append(kwargs)

    def clear_call(self, call_id: str):
        self.cleared.append(call_id)


class FakeSTT:
    def transcribe(self, _path: str):
        return {"text": "twenty one", "confidence": 0.95}


class FakeLLM:
    async def generate(self, **_kwargs):
        return "Good try, now I know where we should start. Let's count one, two, three together."


async def fake_tts_and_convert(_tts, _text: str, prefix: str) -> str:
    return f"/tmp/sabi_{prefix}"


async def run_check() -> int:
    reader = FakeReader(
        [
            "agi_callerid: +19995550123\n",
            "\n",
            "200 result=0\n",  # greeting STREAM FILE
            "200 result=0\n",  # RECORD FILE
            "200 result=0\n",  # response STREAM FILE
            "200 result=1\n",  # HANGUP
        ]
    )
    writer = FakeWriter()
    memory = FakeMemory()

    original_tts = voice_asterisk.tts_and_convert
    original_exists = voice_asterisk.os.path.exists
    original_unlink = voice_asterisk.os.unlink
    original_max_turns = voice_asterisk.MAX_TURNS
    try:
        voice_asterisk.tts_and_convert = fake_tts_and_convert
        voice_asterisk.os.path.exists = lambda path: str(path).endswith(".wav")
        voice_asterisk.os.unlink = lambda _path: None
        voice_asterisk.MAX_TURNS = 1
        await voice_asterisk.handle_agi_call(reader, writer, FakeSTT(), FakeLLM(), object(), memory)
    finally:
        voice_asterisk.tts_and_convert = original_tts
        voice_asterisk.os.path.exists = original_exists
        voice_asterisk.os.unlink = original_unlink
        voice_asterisk.MAX_TURNS = original_max_turns

    ok = True

    def check(name: str, condition: bool, details: object = "") -> None:
        nonlocal ok
        if condition:
            print(f"PASS {name}")
        else:
            ok = False
            print(f"FAIL {name} - {details}")

    check("writer_closed", writer.closed)
    check("hangup_command_sent", any(command == "HANGUP" for command in writer.commands), writer.commands)
    check("call_state_cleared", len(memory.cleared) == 1, memory.cleared)
    check("session_saved_once", len(memory.saved) == 1, memory.saved)
    if memory.saved:
        saved = memory.saved[0]
        messages = saved.get("messages") or []
        check("saved_channel_fastagi", saved.get("channel") == "asterisk_fastagi", saved)
        check("saved_phone", saved.get("phone_number") == "+19995550123", saved)
        check("saved_starting_state", saved.get("starting_learning_state", {}).get("course") == "numeracy", saved)
        check(
            "saved_transcript_has_user_and_sabi",
            any(message.get("role") == "user" and message.get("content") == "twenty one" for message in messages)
            and any(message.get("role") == "assistant" and "Good try" in message.get("content", "") for message in messages),
            messages,
        )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_check()))
