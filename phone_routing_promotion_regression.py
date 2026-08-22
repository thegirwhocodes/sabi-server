#!/usr/bin/env python3
"""Focused regression for Gemini-by-default phone routing and safe rollback."""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path

os.environ.setdefault(
    "SABI_SHARED_AUDIO_DIR",
    str(Path(tempfile.gettempdir()) / "sabi-phone-routing-promotion-regression"),
)

import gemini_live
import voice_realtime
from phone_utils import phone_uses_gemini_live


def check(name: str, condition: bool, detail: object = "") -> bool:
    print(("PASS" if condition else "FAIL"), name, "" if condition else detail)
    return bool(condition)


def route(raw: str | None, *, all_mode: str, allow: str = "", exclude: str = "") -> bool:
    keys = {
        "SABI_GEMINI_LIVE_ALL": all_mode,
        "SABI_GEMINI_LIVE_PHONES": allow,
        "SABI_GEMINI_LIVE_EXCLUDE_PHONES": exclude,
    }
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ.update(keys)
        return phone_uses_gemini_live(raw)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def exercise_setup_failure() -> dict[str, object]:
    events: dict[str, object] = {"packet_reads": 0, "live": False, "old": False}
    call_uuid = uuid.uuid4()

    class Writer:
        def get_extra_info(self, _name):
            return ("regression", 9020)

        def close(self):
            events["closed"] = True

    class Call:
        def __init__(self, call_id, *_args, **_kwargs):
            self.call_uuid = call_id
            self.phone = "+2348123456789"
            self.conversation_style = "current"

        async def run(self):
            events["old"] = True

        async def run_original_sabi(self):
            events["original"] = True

    class LiveRunner:
        def __init__(self, _call):
            events["live"] = True

        async def run(self):
            raise gemini_live.GeminiLiveSetupError("intentional setup failure")

    async def read_packet(_reader):
        events["packet_reads"] = int(events["packet_reads"]) + 1
        return voice_realtime.AUDIO_TYPE_UUID, call_uuid.bytes

    originals = (
        voice_realtime.RealtimeCall,
        voice_realtime._read_packet,
        gemini_live.GeminiLiveCallRunner,
    )
    old_all = os.environ.get("SABI_GEMINI_LIVE_ALL")
    old_exclude = os.environ.get("SABI_GEMINI_LIVE_EXCLUDE_PHONES")
    voice_realtime.RealtimeCall = Call
    voice_realtime._read_packet = read_packet
    gemini_live.GeminiLiveCallRunner = LiveRunner
    os.environ["SABI_GEMINI_LIVE_ALL"] = "1"
    os.environ["SABI_GEMINI_LIVE_EXCLUDE_PHONES"] = ""
    try:
        await voice_realtime.handle_audiosocket_call(
            object(), Writer(), None, None, None, None, tts_primary="chatterbox_only"
        )
    finally:
        (
            voice_realtime.RealtimeCall,
            voice_realtime._read_packet,
            gemini_live.GeminiLiveCallRunner,
        ) = originals
        if old_all is None:
            os.environ.pop("SABI_GEMINI_LIVE_ALL", None)
        else:
            os.environ["SABI_GEMINI_LIVE_ALL"] = old_all
        if old_exclude is None:
            os.environ.pop("SABI_GEMINI_LIVE_EXCLUDE_PHONES", None)
        else:
            os.environ["SABI_GEMINI_LIVE_EXCLUDE_PHONES"] = old_exclude
    return events


def main() -> int:
    ok = True
    ok &= check(
        "all-mode routes Nigerian, US, and unknown callers",
        all(route(phone, all_mode="1") for phone in ("+2348123456789", "+14155550123", "unknown", None)),
    )
    ok &= check(
        "all-mode exclusion uses old path",
        not route("+234 812 345 6789", all_mode="1", exclude="+2348123456789")
        and route("+14155550123", all_mode="1", exclude="+2348123456789"),
    )
    ok &= check(
        "global rollback restores allowlist semantics",
        route("+18604367048", all_mode="0", allow="+18604367048")
        and not route("+2348123456789", all_mode="0", allow="+18604367048")
        and not route("unknown", all_mode="0", allow="+18604367048"),
    )
    events = asyncio.run(exercise_setup_failure())
    ok &= check(
        "setup failure falls back before caller media is consumed",
        events["live"] is True and events["old"] is True and events["packet_reads"] == 1,
        events,
    )
    source = Path(__file__).with_name("voice_realtime.py").read_text()
    ok &= check(
        "old pipeline remains deployed",
        "except GeminiLiveSetupError" in source
        and source.count("await call.run()") >= 2
        and "tts_primary=tts_primary" in source,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
