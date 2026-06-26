#!/usr/bin/env python3
"""Static checks for optional STT provider wiring."""

from __future__ import annotations

import sys
from pathlib import Path


def check(name: str, ok: bool, detail: object = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not ok else ""))
    return ok


def main() -> int:
    source = Path("stt.py").read_text(encoding="utf-8")
    ok = True
    ok &= check("intron_is_optional", "SABI_STT_PROVIDER" in source and "SABI_LITERACY_STT_PROVIDER" in source)
    ok &= check("intron_uses_bearer_auth", '"Authorization": f"Bearer {self._intron_key}"' in source)
    ok &= check("intron_uses_file_sync_endpoint", "https://infer.voice.intron.io/file/v1/upload/sync" in source)
    ok &= check("intron_falls_back_to_whisper", "falling back to Groq/Whisper" in source)
    ok &= check("literacy_prompt_preserves_short_sounds", "Transcribe short sounds" in source and "Do not force literacy answers" in source)
    ok &= check("literacy_prompt_protects_rhyme_words", "rat, sat, fat" in source and "correct, right, wrong" in source)
    ok &= check("stt_prompt_uses_recent_tutor_context", "Recent tutor prompt for this exact child answer" in source)
    ok &= check("literacy_salvages_suspicious_feedback_words", "local_literacy_salvage" in source)
    realtime = Path("voice_realtime.py").read_text(encoding="utf-8")
    ok &= check("numeric_prompts_bypass_literacy_stt", "_stt_mode_for_turn" in realtime and "numeric_stt" in realtime)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
