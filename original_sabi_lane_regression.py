#!/usr/bin/env python3
"""Regression checks for the isolated Original Sabi + Gemini comparison lane."""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

os.environ.setdefault("SABI_SHARED_AUDIO_DIR", tempfile.mkdtemp(prefix="sabi-original-regression-"))

import voice_realtime
from original_sabi_prompt import ORIGINAL_SABI_FIRST_MESSAGE, ORIGINAL_SABI_SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parent


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def context_block(dialplan: str, name: str) -> str:
    marker = f"[{name}]"
    start = dialplan.index(marker)
    next_context = dialplan.find("\n[", start + len(marker))
    return dialplan[start : next_context if next_context >= 0 else len(dialplan)]


def main() -> int:
    ok = True
    canonical = ROOT.parent / "curriculum-app" / "docs" / "elevenlabs-agent-prompt.md"
    canonical_text = canonical.read_text(encoding="utf-8")
    first_message = canonical_text.split(
        '## FIRST MESSAGE (paste into "First Message" field)\n\n', 1
    )[1].split("\n\n---", 1)[0]
    canonical_system = canonical_text.split(
        '## SYSTEM PROMPT (paste into "System Prompt" field — everything below this line)\n\n', 1
    )[1].split("\n\n---", 1)[0]
    ok &= check("first_message_matches_canonical_exactly", ORIGINAL_SABI_FIRST_MESSAGE == first_message)
    ok &= check("system_prompt_matches_canonical_exactly", ORIGINAL_SABI_SYSTEM_PROMPT == canonical_system)

    original_source = inspect.getsource(voice_realtime.RealtimeCall.run_original_sabi)
    ok &= check(
        "original_lane_uses_gemini_stt_and_canonical_llm",
        "self.transcribe_pcm(" in original_source
        and "self.llm.generate_with_system_prompt(" in original_source,
    )
    ok &= check(
        "original_lane_bypasses_current_learning_engine",
        "analyze_session(" not in original_source
        and "assess_turn(" not in original_source
        and "find_or_create_student(" not in original_source
        and "save_phone_session(" not in original_source,
    )
    ok &= check(
        "original_lane_keeps_raw_gemini_text",
        "normalized_text=raw_text" in original_source
        and "_normalize_transcript_for_lesson(" not in original_source,
    )

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dialplan = (ROOT / "asterisk" / "extensions.conf").read_text(encoding="utf-8")
    original_context = context_block(dialplan, "sabi-callback-original-run")
    public_context = context_block(dialplan, "sabi-callback-run")
    ok &= check(
        "third_listener_is_isolated_on_9021",
        'SABI_ORIGINAL_AUDIOSOCKET_PORT", "9021"' in main_source
        and 'conversation_style="original"' in main_source
        and 'SABI_ORIGINAL_TTS_PRIMARY", "elevenlabs"' in main_source
        and '"127.0.0.1:9021:9021"' in compose,
    )
    ok &= check(
        "original_callback_routes_only_to_9021",
        "AudioSocket(${AS_UUID},sabi:9021)" in original_context
        and "mode=callback-original" in original_context,
    )
    ok &= check(
        "original_callback_waits_for_answer_media",
        original_context.index("Answer()")
        < original_context.index("Wait(1)")
        < original_context.index("AudioSocket(${AS_UUID},sabi:9021)"),
    )
    ok &= check(
        "public_callback_route_unchanged",
        "AudioSocket(${AS_UUID},sabi:9020)" in public_context
        and "sabi:9021" not in public_context,
    )
    ok &= check(
        "protected_original_callback_endpoint_exists",
        '@app.post("/admin/asterisk/direct-call-original")' in main_source
        and 'context="sabi-callback-original"' in main_source,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
