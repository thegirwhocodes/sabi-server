"""Regression: TTS provider chain + Chatterbox canary lane isolation.

Protects the Sabi Costs.md invariant path (phone TTS -> self-hosted Chatterbox
at $0, ElevenLabs as paid fallback) while it is canaried safely:

  1. `synthesize_phone_tts` chain order is correct for every primary:
       chatterbox  -> chatterbox, elevenlabs, yarngpt
       elevenlabs  -> elevenlabs, yarngpt          (production today — UNCHANGED)
       yarngpt     -> yarngpt, elevenlabs
  2. It returns the winning provider NAME (truthy) and None on total failure,
     so legacy boolean call sites keep working.
  3. Fallback works: when chatterbox fails, elevenlabs answers.
  4. The per-call `primary` override beats the global default.
  5. main.py wires SABI_TTS_TEST_PRIMARY ONLY to the test AudioSocket lane;
     the production listener takes no tts_primary (global default).
  6. Per-turn sidecars persist `assistant.tts_provider` and calls roll up
     `tts_providers_used`.

Run: python tts_provider_config_regression.py  (host or in the sabi container)
"""

import asyncio
import inspect
import json
import re
import sys
import tempfile
from pathlib import Path

import voice_asterisk
from call_admin import append_call_turn_review, load_call_record

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


class FakeSynth:
    """Patchable provider that records call order."""

    def __init__(self):
        self.calls: list[str] = []
        self.ok: dict[str, bool] = {"chatterbox": True, "elevenlabs": True, "yarngpt": True}

    def make(self, name: str, needs_tts_arg: bool = False):
        if needs_tts_arg:
            async def synth(tts, text, output_path):
                self.calls.append(name)
                if self.ok[name]:
                    Path(output_path).write_bytes(b"x" * 2048)
                return self.ok[name]
        else:
            async def synth(text, output_path):
                self.calls.append(name)
                if self.ok[name]:
                    Path(output_path).write_bytes(b"x" * 2048)
                return self.ok[name]
        return synth


def run_chain(primary: str | None, ok: dict[str, bool]) -> tuple[str | None, list[str]]:
    fake = FakeSynth()
    fake.ok.update(ok)
    original = (
        voice_asterisk.synthesize_chatterbox,
        voice_asterisk.synthesize_elevenlabs,
        voice_asterisk.synthesize_yarngpt,
    )
    voice_asterisk.synthesize_chatterbox = fake.make("chatterbox")
    voice_asterisk.synthesize_elevenlabs = fake.make("elevenlabs")
    voice_asterisk.synthesize_yarngpt = fake.make("yarngpt", needs_tts_arg=True)
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            provider = asyncio.run(
                voice_asterisk.synthesize_phone_tts(None, "hello", tmp.name, primary=primary)
            )
        return provider, fake.calls
    finally:
        (
            voice_asterisk.synthesize_chatterbox,
            voice_asterisk.synthesize_elevenlabs,
            voice_asterisk.synthesize_yarngpt,
        ) = original


def main() -> int:
    print("TTS provider chain regression")
    print("=" * 56)

    # 1. Chain orders
    provider, calls = run_chain("chatterbox", {})
    check("chatterbox primary wins", provider == "chatterbox" and calls == ["chatterbox"])

    provider, calls = run_chain("elevenlabs", {})
    check("elevenlabs primary unchanged (prod)", provider == "elevenlabs" and calls == ["elevenlabs"])

    provider, calls = run_chain("yarngpt", {})
    check("yarngpt primary order", provider == "yarngpt" and calls == ["yarngpt"])

    # 2/3. Fallbacks
    provider, calls = run_chain("chatterbox", {"chatterbox": False})
    check(
        "chatterbox falls back to elevenlabs",
        provider == "elevenlabs" and calls == ["chatterbox", "elevenlabs"],
        f"got provider={provider} calls={calls}",
    )
    provider, calls = run_chain("chatterbox", {"chatterbox": False, "elevenlabs": False})
    check(
        "chatterbox double-fallback to yarngpt",
        provider == "yarngpt" and calls == ["chatterbox", "elevenlabs", "yarngpt"],
    )
    provider, calls = run_chain("chatterbox", {"chatterbox": False, "elevenlabs": False, "yarngpt": False})
    check("total failure returns falsy None", provider is None)

    # 4. Per-call override beats global (module global is elevenlabs default here)
    provider, calls = run_chain(None, {})
    check(
        "no override -> global default order",
        calls[0] == voice_asterisk.TTS_PRIMARY if voice_asterisk.TTS_PRIMARY in {"chatterbox", "elevenlabs", "yarngpt"} else calls[0] == "elevenlabs",
        f"global={voice_asterisk.TTS_PRIMARY} calls={calls}",
    )

    # 5. Lane isolation in main.py source
    main_src = Path(__file__).parent.joinpath("main.py").read_text()
    test_lane = re.search(r"intron_audiosocket_server = await start_audiosocket_server\((.*?)\n    \)", main_src, re.S)
    prod_lane = re.search(r"\n    audiosocket_server = await start_audiosocket_server\((.*?)\n    \)", main_src, re.S)
    check("test lane reads SABI_TTS_TEST_PRIMARY", bool(test_lane) and "SABI_TTS_TEST_PRIMARY" in test_lane.group(1))
    check("prod lane has NO tts_primary override", bool(prod_lane) and "tts_primary" not in prod_lane.group(1))

    rt_src = Path(__file__).parent.joinpath("voice_realtime.py").read_text()
    check("RealtimeCall threads tts_primary into synthesis", "primary=self.tts_primary" in rt_src)
    check("turn review persists tts_provider", "tts_provider=self.last_tts_provider" in rt_src)

    # 6. Sidecar persistence + rollup (functional)
    with tempfile.TemporaryDirectory() as tmp_dir:
        directory = Path(tmp_dir)
        append_call_turn_review(
            call_uuid="regressiontts01",
            turn_index=0,
            user_audio_path="",
            user_audio_seconds=1.0,
            stt_transcript="ten naira",
            stt_confidence=0.9,
            normalized_transcript="ten naira",
            learning_state_before={},
            learning_state_after={},
            assistant_text="Correct! Ten naira.",
            assistant_tts_text="Correct! Ten naira.",
            assistant_audio_path="",
            assistant_audio_seconds=1.0,
            directory=directory,
            stt_provider="groq",
            tts_provider="chatterbox",
        )
        record = load_call_record(directory / "call_regressiontts01.json")
        turn = (record.get("turns") or [{}])[0]
        check(
            "sidecar turn has assistant.tts_provider",
            (turn.get("assistant") or {}).get("tts_provider") == "chatterbox",
            json.dumps(turn.get("assistant") or {})[:200],
        )
        check("call rolls up tts_providers_used", record.get("tts_providers_used") == ["chatterbox"])

    print("=" * 56)
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
