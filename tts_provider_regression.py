#!/usr/bin/env python3
"""Static checks for the active Sabi TTS provider chain."""

from __future__ import annotations

import sys
from pathlib import Path


ACTIVE_FILES = [
    "main.py",
    "voice.py",
    "voice_twilio.py",
    "voice_asterisk.py",
    "docker-compose.yml",
    "load_test.py",
]


def check(name: str, ok: bool, detail: object = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not ok else ""))
    return ok


def main() -> int:
    ok = True
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    asterisk = Path("voice_asterisk.py").read_text(encoding="utf-8")
    main = Path("main.py").read_text(encoding="utf-8")
    voice = Path("voice.py").read_text(encoding="utf-8")
    dialplan = Path("asterisk/extensions.conf").read_text(encoding="utf-8")

    ok &= check("compose_exposes_prod_and_test_audiosockets", '"127.0.0.1:9019:9019"' in compose and '"127.0.0.1:9020:9020"' in compose)
    ok &= check("asterisk_tts_uses_elevenlabs", "synthesize_elevenlabs" in asterisk)
    ok &= check("asterisk_tts_uses_yarngpt_fallback", "synthesize_yarngpt" in asterisk)
    ok &= check("asterisk_tts_uses_chatterbox_test_provider", "synthesize_chatterbox" in asterisk and "chatterbox_only" in asterisk)
    ok &= check("asterisk_unsupported_primary_falls_back", "Unsupported SABI_TTS_PRIMARY" in asterisk)
    ok &= check("rest_tts_uses_provider_chain", "synthesize_phone_tts" in main)
    ok &= check("legacy_at_tts_uses_provider_chain", "synthesize_phone_tts" in voice)
    ok &= check("test_lane_reads_tts_override", "SABI_TTS_TEST_PRIMARY" in main)
    ok &= check("prod_lane_stays_on_9019", "AudioSocket(${AS_UUID},sabi:9019)" in dialplan)
    ok &= check("test_lane_stays_on_9020", "AudioSocket(${AS_UUID},sabi:9020)" in dialplan)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
