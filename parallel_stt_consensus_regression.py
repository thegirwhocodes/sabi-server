#!/usr/bin/env python3
"""Offline regression for Groq + local Whisper parallel consensus.

No provider calls or model downloads occur: the three engines are replaced by
deterministic fakes. The checks cover concurrent start, number-authoritative
agreement despite different object nouns, Gemini tie-breaking, and fail-closed
behavior when no two recognizers agree.
"""

from __future__ import annotations

import os
import tempfile
import time
import wave

os.environ["GROQ_API_KEY"] = "test-groq"
os.environ["GEMINI_API_KEY"] = "test-gemini"
os.environ["SABI_STT_VAD_GATE"] = "0"
os.environ["SABI_STT_CONSENSUS_EAGER_LOAD"] = "0"

from stt import SpeechToText


def check(name: str, condition: bool, detail: object = "") -> None:
    assert condition, f"FAIL {name}: {detail}"
    print(f"PASS {name}")


def tiny_wav() -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)
    return path


def engine() -> SpeechToText:
    item = SpeechToText(provider="parallel_consensus", literacy_provider="parallel_consensus")
    item._groq_key = "test-groq"
    item._gemini_key = "test-gemini"
    return item


path = tiny_wav()
try:
    # Different nouns do not overturn an agreed numeric value. Sleeping in
    # both fakes proves they execute concurrently rather than consecutively.
    first = engine()
    starts: dict[str, float] = {}

    def groq(*_args, **_kwargs):
        starts["groq"] = time.monotonic()
        time.sleep(0.12)
        return {"text": "two apples", "confidence": 0.82, "provider": "groq"}

    def local(*_args, **_kwargs):
        starts["local"] = time.monotonic()
        time.sleep(0.12)
        return {"text": "two mangoes", "confidence": 0.78, "provider": "local_whisper"}

    def slow_gemini(*_args, **_kwargs):
        time.sleep(0.4)
        return {"text": "two fries", "confidence": 0.9, "provider": "gemini"}

    first._transcribe_groq = groq
    first._transcribe_local = local
    first._transcribe_gemini = slow_gemini
    started = time.monotonic()
    consensus = first._transcribe_parallel_consensus(
        path,
        context="Each basket has one mango. How many mangoes are there altogether?",
    )
    elapsed = time.monotonic() - started
    check("Groq and local Whisper start together", abs(starts["groq"] - starts["local"]) < 0.05, starts)
    check("consensus returns without waiting for Gemini", elapsed < 0.3, elapsed)
    check("same number overrides different object nouns", consensus["consensus_numeric_value"] == 2, consensus)
    check("consensus is authoritative", consensus["provider"] == "groq_local_whisper_consensus", consensus)
    check("both transcripts remain auditable", consensus["ensemble_results"]["local_whisper"]["text"] == "two mangoes", consensus)

    # When the two Whisper lanes disagree, Gemini remains the explicit decider.
    second = engine()
    second._transcribe_groq = lambda *_args, **_kwargs: {
        "text": "two", "confidence": 0.82, "provider": "groq"
    }
    second._transcribe_local = lambda *_args, **_kwargs: {
        "text": "three", "confidence": 0.72, "provider": "local_whisper"
    }
    second._transcribe_gemini = lambda *_args, **_kwargs: {
        "text": "three mangoes", "confidence": 0.9, "provider": "gemini"
    }
    tie_break = second._transcribe_parallel_consensus(
        path,
        context="How many mangoes are left altogether?",
    )
    check("Gemini resolves disagreement", tie_break["provider"] == "gemini_tiebreak", tie_break)
    check("Gemini literal transcript is preserved", tie_break["text"] == "three mangoes", tie_break)

    # A missing/failed tie-break must not guess which disagreeing engine won.
    third = engine()
    third._transcribe_groq = second._transcribe_groq
    third._transcribe_local = second._transcribe_local
    third._transcribe_gemini = lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("slow"))
    unresolved = third._transcribe_parallel_consensus(
        path,
        context="How many mangoes are left altogether?",
    )
    check("unresolved disagreement fails closed", unresolved["text"] == "", unresolved)
    check("provider errors remain auditable", unresolved["ensemble_results"]["gemini"]["status"] == "error", unresolved)
finally:
    os.unlink(path)

print("PASS parallel STT consensus regression")
