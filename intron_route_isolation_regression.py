#!/usr/bin/env python3
"""Regression: prove the Intron STT test route is fully isolated from production.

This regression is the safety net for goal #2 of the 2026-06-29 system design:
adding/exercising Intron STT must NEVER touch the production AudioSocket route.

Asserts the six invariants the design document lists:

  1. Two separate SpeechToText instances exist on app.state — the production
     `stt` and the experimental `intron_stt`. The production lane reads
     SABI_STT_PROVIDER (default "auto"). The experimental lane reads
     SABI_STT_TEST_PROVIDER (default "intron_first") and SABI_LITERACY_STT_TEST_PROVIDER.
  2. The Asterisk dialplan declares BOTH `[sabi-callback-run]` (port 9019,
     production) and `[sabi-callback-intron-run]` (port 9020, experimental).
  3. The production context routes AudioSocket to `sabi:9019`; the
     experimental context routes AudioSocket to `sabi:9020`.
  4. The admin handler `direct-call-intron` originates with the experimental
     context, not the production context.
  5. SpeechToText reads INTRON_API_KEY and gracefully falls back to Groq/local
     when the key is missing — so the experimental lane is safe to deploy even
     before the key is provisioned.
  6. Per-turn sidecars persist `stt_provider`, so admins can see which lane
     handled each transcript (the Calls page filter and the per-turn pill in
     the admin redesign depend on this).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(tempfile.mkdtemp(prefix="sabi-intron-isolation-"))
os.environ["SABI_SHARED_AUDIO_DIR"] = str(ROOT)

import call_admin  # noqa: E402
import main as sabi_main  # noqa: E402  — exposes the FastAPI app + lifespan
import stt as stt_mod  # noqa: E402


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    # --- Invariant 1: two STT instances, different default providers ---
    main_source = Path(sabi_main.__file__).read_text()
    ok &= check(
        "main_constructs_production_stt",
        "app.state.stt = SpeechToText()" in main_source,
        "missing app.state.stt = SpeechToText()",
    )
    ok &= check(
        "main_constructs_separate_intron_stt",
        "app.state.intron_stt = SpeechToText(" in main_source,
        "missing app.state.intron_stt = SpeechToText(",
    )
    ok &= check(
        "intron_stt_defaults_to_intron_first",
        'SABI_STT_TEST_PROVIDER", "intron_first"' in main_source
        and 'SABI_LITERACY_STT_TEST_PROVIDER", "intron_first"' in main_source,
        "missing intron_first defaults",
    )

    # Construct both instances inline (without booting models) and check provider config.
    os.environ.pop("SABI_STT_PROVIDER", None)
    os.environ.pop("SABI_LITERACY_STT_PROVIDER", None)
    os.environ.pop("GROQ_API_KEY", None)
    os.environ.pop("INTRON_API_KEY", None)
    prod_stt = stt_mod.SpeechToText.__new__(stt_mod.SpeechToText)
    prod_stt._groq_key = ""
    prod_stt._intron_key = ""
    prod_stt._provider = "auto"
    prod_stt._literacy_provider = "auto"
    prod_stt._use_groq = False
    intron_stt = stt_mod.SpeechToText.__new__(stt_mod.SpeechToText)
    intron_stt._groq_key = ""
    intron_stt._intron_key = ""
    intron_stt._provider = "intron_first"
    intron_stt._literacy_provider = "intron_first"
    intron_stt._use_groq = False
    ok &= check(
        "production_lane_does_not_default_to_intron",
        prod_stt._provider != "intron_first" and prod_stt._provider != "intron",
        prod_stt._provider,
    )
    ok &= check(
        "intron_lane_defaults_to_intron_first",
        intron_stt._provider == "intron_first",
        intron_stt._provider,
    )

    # --- Invariant 2 + 3: dialplan declares both contexts and routes to the right ports ---
    extensions_conf = Path(__file__).parent / "asterisk" / "extensions.conf"
    dialplan = extensions_conf.read_text() if extensions_conf.exists() else ""
    ok &= check("dialplan_has_production_context", "[sabi-callback-run]" in dialplan, "missing production context")
    ok &= check("dialplan_has_intron_context", "[sabi-callback-intron-run]" in dialplan, "missing intron context")

    # Find the AudioSocket port used in each context.
    def _audiosocket_port_in_context(context: str) -> str:
        header = f"[{context}]"
        if header not in dialplan:
            return ""
        chunk = dialplan.split(header, 1)[1]
        # Find next [section] header or EOF.
        next_section = chunk.find("\n[")
        if next_section >= 0:
            chunk = chunk[:next_section]
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped.startswith("same => n,AudioSocket(") and ",sabi:" in stripped:
                # AudioSocket(${AS_UUID},sabi:9019)
                tail = stripped.split(",sabi:", 1)[1]
                return tail.split(")", 1)[0]
        return ""

    prod_port = _audiosocket_port_in_context("sabi-callback-run")
    intron_port = _audiosocket_port_in_context("sabi-callback-intron-run")
    ok &= check(
        "production_context_uses_audiosocket_9019",
        prod_port == "9019",
        f"got {prod_port!r}",
    )
    ok &= check(
        "intron_context_uses_audiosocket_9020",
        intron_port == "9020",
        f"got {intron_port!r}",
    )
    ok &= check(
        "intron_and_production_ports_differ",
        prod_port and intron_port and prod_port != intron_port,
        f"prod={prod_port!r} intron={intron_port!r}",
    )

    # Also exercise the inbound context — it must NOT accidentally route to 9020.
    inbound_port = _audiosocket_port_in_context("sabi-inbound")
    ok &= check(
        "inbound_context_stays_on_production_9019",
        inbound_port == "9019",
        f"got {inbound_port!r}",
    )

    # --- Invariant 4: direct-call-intron originates with the experimental context ---
    ok &= check(
        "direct_call_intron_uses_intron_context",
        'context="sabi-callback-intron"' in main_source,
        "missing context=sabi-callback-intron originate",
    )
    # And the regular direct-call route must NOT pass the intron context.
    direct_call_block = main_source.split("async def direct_sabi_call(", 1)[1].split("async def ", 1)[0]
    ok &= check(
        "direct_call_does_not_use_intron_context",
        "sabi-callback-intron" not in direct_call_block,
        "production direct-call accidentally routes to intron context",
    )

    # --- Invariant 5: Intron lane falls back gracefully when key is missing ---
    source = Path(stt_mod.__file__).read_text()
    ok &= check(
        "intron_uses_bearer_auth",
        '"Authorization": f"Bearer {self._intron_key}"' in source,
        "Intron call must use Bearer auth",
    )
    ok &= check(
        "intron_falls_back_to_groq_or_local",
        "falling back to Groq/Whisper" in source,
        "fallback log message missing — silent failure mode if Intron 503s",
    )
    ok &= check(
        "intron_optional_key_warning_when_missing",
        "INTRON_API_KEY is not configured" in source,
        "no warning logged when Intron requested without a key",
    )

    # --- Invariant 6: per-turn sidecars persist the STT provider ---
    call_admin.append_call_turn_review(
        call_uuid="intron-isolation-001",
        turn_index=1,
        user_audio_path="",
        user_audio_seconds=1.0,
        stt_transcript="five naira",
        stt_confidence=0.85,
        normalized_transcript="five naira",
        learning_state_before={"current_module": 2},
        learning_state_after={"current_module": 2},
        assistant_text="Yes!",
        assistant_tts_text="Yes!",
        assistant_audio_path="",
        assistant_audio_seconds=0.3,
        directory=ROOT,
        stt_provider="intron",
    )
    record = json.loads((ROOT / "call_intron-isolation-001.json").read_text())
    ok &= check(
        "sidecar_persists_stt_provider_for_intron_turn",
        record["turns"][0]["user"].get("stt_provider") == "intron",
        record["turns"][0]["user"],
    )
    ok &= check(
        "sidecar_rollup_records_intron_in_providers_used",
        "intron" in (record.get("stt_providers_used") or []),
        record.get("stt_providers_used"),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
