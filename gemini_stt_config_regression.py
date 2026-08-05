"""Regression for the Gemini multimodal STT provider.

Covers: closed-vocab shape hints (number / literacy word / name / general),
name-context detection, Gemini payload construction + response parsing, and
graceful fallback when GEMINI_API_KEY is absent. Runs with no GPU/network:
httpx.post is monkeypatched and faster-whisper is never loaded (a GROQ key is
present so the local model is skipped).
"""

import os
import tempfile
import wave

os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("SABI_STT_PROVIDER", "gemini_first")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import httpx

from stt import SpeechToText, _expects_name

# _gemini_shape_hint is a method; call it unbound (it only reads `context`).
shape_hint = SpeechToText._gemini_shape_hint


def _tiny_wav() -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 1600)  # 0.2s silence
    return path


passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"  ok  {name}")


# ---- name-context detection ----
check("name cue detected", _expects_name("Okay, what is your name?"))
check("name cue variant", _expects_name("Tell me your name after the beep"))
check("non-name not detected", not _expects_name("How many mangoes are left?"))

# ---- closed-vocab shape hints (the mode that won the bake-off) ----
check("number hint", "NUMBER" in shape_hint(None, "How many are left? Count them."))
check("literacy-word hint", "one word" in shape_hint(None, "Can you say a word that rhymes with hat?").lower())
check("name hint", "name" in shape_hint(None, "What is your name?").lower())
check("general hint", shape_hint(None, "Tell me about your day").startswith("Transcribe exactly"))

# ---- payload construction + response parsing ----
captured = {}


def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
    captured["url"] = url
    captured["headers"] = headers or {}
    captured["timeout"] = timeout
    if json is not None:
        captured["payload"] = json

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            # Satisfies both the Gemini parser (candidates) and, on the
            # no-key fallback path, the Groq parser (text/language/duration).
            return {
                "candidates": [{"content": {"parts": [{"text": "thirty"}]}}],
                "text": "thirty",
                "language": "en",
                "duration": 0.2,
            }

    return R()


orig_post = httpx.post
httpx.post = fake_post
try:
    sst = SpeechToText()
    check("gemini key loaded", bool(sst._gemini_key))
    check("default model is 3.5-flash-lite", sst._gemini_model == "gemini-3.5-flash-lite")
    wav = _tiny_wav()
    result = sst._transcribe_gemini(wav, mode="general", context="How many are left?")
    check("gemini result text parsed", result["text"] == "thirty")
    check("gemini provider tagged", result["provider"] == "gemini")
    check("gemini model tagged", result["gemini_model"] == "gemini-3.5-flash-lite")
    check("model in request url", "gemini-3.5-flash-lite:generateContent" in captured["url"])
    check("API key absent from URL", "test-gemini-key" not in captured["url"])
    check("API key sent in header", captured["headers"].get("x-goog-api-key") == "test-gemini-key")
    check("default timeout capped", captured["timeout"] == 3.5)
    parts = captured["payload"]["contents"][0]["parts"]
    check("audio part sent inline", "inlineData" in parts[0])
    check("number hint in prompt", "NUMBER" in parts[1]["text"])
    check("provider latency recorded", result["provider_latency_seconds"] >= 0)
    os.remove(wav)

    os.environ["SABI_GEMINI_STT_PROMPT_MODE"] = "lesson_exact"
    exact_prompt = sst._gemini_prompt("What is your name?")
    check("exact AI Studio prompt configurable", exact_prompt.endswith("Reply with their responses"))
    os.environ.pop("SABI_GEMINI_STT_PROMPT_MODE", None)

    # ---- graceful fallback: no key -> gemini skipped, Groq serves instead ----
    sst._gemini_key = ""
    wav2 = _tiny_wav()
    out = sst._transcribe_prepared(wav2, mode="general", context="How many are left?")
    check("no-key falls back cleanly", isinstance(out, dict) and out.get("text") == "thirty")
    check("no-key fallback used groq, not gemini", out.get("provider") == "groq")
    os.remove(wav2)
finally:
    httpx.post = orig_post

print(f"\nPASS: {passed}/{passed} Gemini STT config checks")
