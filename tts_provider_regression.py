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
    active_source = "\n".join(Path(path).read_text(encoding="utf-8") for path in ACTIVE_FILES)
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    asterisk = Path("voice_asterisk.py").read_text(encoding="utf-8")
    main = Path("main.py").read_text(encoding="utf-8")
    voice = Path("voice.py").read_text(encoding="utf-8")

    ok &= check("active_path_has_no_chatterbox_refs", "chatterbox" not in active_source.lower())
    ok &= check("compose_has_no_chatterbox_service", "sabi-chatterbox" not in compose and "chatterbox-tts" not in compose)
    ok &= check("asterisk_tts_uses_elevenlabs", "synthesize_elevenlabs" in asterisk)
    ok &= check("asterisk_tts_uses_yarngpt_fallback", "synthesize_yarngpt" in asterisk)
    ok &= check("asterisk_unsupported_primary_falls_back", "Unsupported SABI_TTS_PRIMARY" in asterisk)
    ok &= check("rest_tts_uses_provider_chain", "synthesize_phone_tts" in main)
    ok &= check("legacy_at_tts_uses_provider_chain", "synthesize_phone_tts" in voice)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
