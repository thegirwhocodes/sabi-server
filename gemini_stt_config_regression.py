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

os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["SABI_STT_PROVIDER"] = "gemini_first"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
# The synthetic fixture is silence. Disable the independent VAD pre-gate so
# this regression deterministically exercises provider routing on every host.
os.environ["SABI_STT_VAD_GATE"] = "0"

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
check(
    "literacy-sound hint",
    "speech sound or letter sound" in shape_hint(None, "What sound comes first at the start of dog?").lower(),
)
check("name hint", "name" in shape_hint(None, "What is your name?").lower())
check("general hint", "Transcribe exactly" in shape_hint(None, "Tell me about your day"))
check(
    "numeric hint preserves repeat requests",
    "Never turn a control request into a guessed answer" in shape_hint(None, "How many are left?"),
)
check(
    "numeric hint names switch-subject requests",
    "asks to switch subjects" in shape_hint(None, "How many mangoes are left?"),
)

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
    # A mounted production secret may take precedence over the test process
    # environment inside Docker. Pin the fake key after construction so this
    # offline regression never depends on host secret-loading order.
    sst._gemini_key = "test-gemini-key"
    sst._gemini_http = type("FakeGeminiClient", (), {"post": staticmethod(fake_post)})()
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
    check("number tag in prompt", "responding to a numeracy question" in parts[1]["text"])
    check("number tag keeps exact response instruction", "Reply with their response." in parts[1]["text"])
    check(
        "every prompt allows complaints or the child calling Sabi",
        parts[1]["text"].endswith(
            "This could also be a complaint about the quality of the call or lesson, or the child calling your name."
        ),
    )
    check(
        "minimal thinking is explicit for latency",
        captured["payload"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal",
    )
    check("provider latency recorded", result["provider_latency_seconds"] >= 0)
    os.remove(wav)

    os.environ["SABI_GEMINI_STT_PROMPT_MODE"] = "lesson_exact"
    exact_prompt = sst._gemini_prompt("What is your name?", mode="general")
    check("exact AI Studio prompt configurable", "Reply with their responses" in exact_prompt)
    check("exact prompt also gets control context", exact_prompt.endswith("or the child calling your name."))
    os.environ.pop("SABI_GEMINI_STT_PROMPT_MODE", None)

    literacy_prompt = sst._gemini_prompt(
        "Lesson metadata: course=literacy; skill=phonemic_awareness_beginning. "
        "Exact recent tutor prompt: What sound starts dog?",
        mode="literacy",
    )
    check("global noisy-phone prompt is on the literacy turn", "noisy 8kHz phone call" in literacy_prompt)
    check("phonemics tag is explicit", "literacy phonemics question" in literacy_prompt)
    check("beginning-sound response type is explicit", "one spoken beginning letter sound" in literacy_prompt)
    check("compact tag does not leak exact tutor question", "dog" not in literacy_prompt.lower())
    check("compact tag contains no example answer", " d, " not in literacy_prompt.lower())

    naira_prompt = sst._gemini_prompt(
        "Lesson metadata: course=numeracy; skill=subtraction. "
        "Exact recent tutor prompt: You have five naira and spend three. How much is left?",
        mode="general",
    )
    check("naira tag is explicit", "numeracy question in naira" in naira_prompt)
    check("naira tag keeps exact response instruction", "Reply with their response." in naira_prompt)
    check("global noisy-phone prompt is on the naira turn", "noisy 8kHz phone call" in naira_prompt)
    check("naira tag does not leak operands", "five" not in naira_prompt and "three" not in naira_prompt)

    name_prompt = sst._gemini_prompt("What is your name?", mode="general")
    check("global noisy-phone prompt is on the name turn", "noisy 8kHz phone call" in name_prompt)
    check("name turn receives only a response-type tag", "saying their name" in name_prompt)
    check("name tag keeps exact response instruction", "Reply with their response." in name_prompt)

    # ---- strict Gemini-first: missing key becomes an unclear turn, not another provider ----
    sst._gemini_key = ""
    wav2 = _tiny_wav()
    out = sst._transcribe_prepared(wav2, mode="general", context="How many are left?")
    check("no-key returns cleanly", isinstance(out, dict) and out.get("text") == "")
    check("no-key remains Gemini, not Groq", out.get("provider") == "gemini")
    os.remove(wav2)

    # ---- strict Gemini: a model timeout becomes an unclear/retry turn, never another provider ----
    strict = SpeechToText(provider="gemini_first", literacy_provider="gemini_first")
    strict._gemini_http = type(
        "TimeoutGeminiClient",
        (),
        {"post": staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))},
    )()
    strict_wav = _tiny_wav()
    strict_out = strict._transcribe_prepared(strict_wav, mode="general", context="How many are left?")
    check("strict Gemini-first timeout does not invoke Groq", strict_out.get("provider") == "gemini")
    check("strict Gemini timeout asks realtime loop to retry", strict_out.get("text") == "")
    os.remove(strict_wav)
finally:
    httpx.post = orig_post

# ---- strict Gemini initializes without Groq or local faster-whisper ----
saved_groq = os.environ.pop("GROQ_API_KEY", None)
try:
    no_fallback = SpeechToText(provider="gemini", literacy_provider="gemini")
    check("strict Gemini does not eagerly load local Whisper", not hasattr(no_fallback, "_model"))
finally:
    if saved_groq is not None:
        os.environ["GROQ_API_KEY"] = saved_groq

print(f"\nPASS: {passed}/{passed} Gemini STT config checks")
