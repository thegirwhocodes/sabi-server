#!/usr/bin/env python3
"""Regressions for the demoted browser phone mimic."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SABI_SHARED_AUDIO_DIR", "/tmp/sabi-preview-call-regression")

from preview_call import (
    DEFAULT_PHONE,
    FLASH_SECONDS,
    PREVIEW_CALLBACK_MODE,
    encode_audiosocket_packet,
    iter_frames,
    resample_pcm16,
    simulator_disabled_payload,
    simulator_enabled,
    render_preview_call_page,
)
from voice_realtime import AUDIO_TYPE_PCM_8K, FRAME_BYTES


def check(name: str, condition: bool, detail: object = "") -> bool:
    print(("PASS" if condition else "FAIL"), name, "" if condition else detail)
    return bool(condition)


def main() -> int:
    ok = True
    ok &= check("simulator_default_off", not simulator_enabled("0") and not simulator_enabled(""))
    ok &= check("simulator_flag_on", simulator_enabled("1") and simulator_enabled("true"))
    status, payload = simulator_disabled_payload()
    ok &= check(
        "disabled_is_404_not_public",
        status == 404
        and "not a production route" in payload["error"].lower(),
    )

    html = render_preview_call_page()
    ok &= check(
        "page_mimics_flash_callback",
        "hang up" in html.lower()
        and "callback" in html.lower()
        and str(int(FLASH_SECONDS)) in html
        and DEFAULT_PHONE in html
        and "/admin/preview-call/ws" in html,
    )

    sine = bytes([0, 64, 0, 0] * 8000)  # 16000 samples of 16-bit at 16 kHz ~ 1s
    out = resample_pcm16(sine, 16000, 8000)
    ok &= check(
        "downsample_16k_to_8k_halves_samples",
        abs(len(out) // 2 - 8000) <= 2,
        len(out) // 2,
    )
    ok &= check("identity_resample", resample_pcm16(b"\x01\x00\x02\x00", 8000, 8000) == b"\x01\x00\x02\x00")

    packet = encode_audiosocket_packet(AUDIO_TYPE_PCM_8K, b"\x00" * FRAME_BYTES)
    ok &= check(
        "audiosocket_frame_matches_phone_path",
        packet[0] == AUDIO_TYPE_PCM_8K
        and int.from_bytes(packet[1:3], "big") == FRAME_BYTES
        and len(packet) == 3 + FRAME_BYTES,
    )
    frames = list(iter_frames(b"\x01\x00" * 10, FRAME_BYTES))
    ok &= check("frames_are_padded_to_20ms", len(frames) == 1 and len(frames[0]) == FRAME_BYTES)

    realtime = Path("voice_realtime.py").read_text()
    main_src = Path("main.py").read_text()
    env = Path(".env.example").read_text()
    ok &= check(
        "preview_callback_skips_gemini_live",
        'call.mode == "preview_callback"' in realtime
        and 'elif phone_uses_gemini_live(call.phone)' in realtime,
    )
    ok &= check(
        "preview_callback_stamps_brief_preview",
        'self.mode == "preview_callback"' in realtime
        and 'effective_state["brief_preview"] = True' in realtime,
        PREVIEW_CALLBACK_MODE,
    )
    ok &= check(
        "route_is_admin_and_flag_gated",
        '@app.get("/admin/preview-call")' in main_src
        and '@app.websocket("/admin/preview-call/ws")' in main_src
        and "if not simulator_enabled()" in main_src
        and "from preview_call import" in main_src,
    )
    ok &= check(
        "env_keeps_simulator_off",
        "SABI_BRIEF_PREVIEW_SIMULATOR=0" in env
        and "SABI_PREVIEW_AUDIOSOCKET_PORT=9019" in env,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
