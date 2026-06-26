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
    ok &= check("literacy_prompt_preserves_short_sounds", "Preserve short phonics answers" in source and "Do not force short sound answers" in source)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
