#!/usr/bin/env python3
"""Regression checks for the fail-open STT cleaning front end."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from audio_cleaner import AudioCleaner


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "raw.wav"
        source.write_bytes(b"RIFF-not-real-but-disabled-does-not-decode")
        with AudioCleaner(enabled=False).prepare(str(source)) as (prepared, metadata):
            ok &= check(
                "disabled_cleaner_is_zero_touch",
                prepared == str(source) and metadata["applied"] is False and metadata["backend"] == "off",
                metadata,
            )
        with AudioCleaner(enabled=True, backend="invalid").prepare(str(source)) as (prepared, metadata):
            ok &= check(
                "cleaner_errors_fail_open_to_raw_audio",
                prepared == str(source) and metadata["applied"] is False and "error" in metadata,
                metadata,
            )

    before = os.environ.get("SABI_STT_DENOISE")
    os.environ["SABI_STT_DENOISE"] = "0"
    try:
        ok &= check("production_default_is_off", AudioCleaner.from_env().enabled is False)
    finally:
        if before is None:
            os.environ.pop("SABI_STT_DENOISE", None)
        else:
            os.environ["SABI_STT_DENOISE"] = before
    print("PASS all audio-cleaner regressions" if ok else "FAIL audio-cleaner regressions")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
