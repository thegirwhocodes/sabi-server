"""Regression for the Gemini multimodal STT provider.

Covers the universal curriculum prompt, safe course/topic labels, payload
construction + response parsing, and strict failure behavior. Runs with no GPU/network:
httpx.post is monkeypatched and faster-whisper is never loaded (a GROQ key is
present so the local model is skipped).
"""

import os
import re
import tempfile
import wave

os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["SABI_STT_PROVIDER"] = "gemini_first"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
# The synthetic fixture is silence. Disable the independent VAD pre-gate so
# this regression deterministically exercises provider routing on every host.
os.environ["SABI_STT_VAD_GATE"] = "0"

import httpx

from stt import SpeechToText, _expects_name, build_gemini_curriculum_prompt


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

# ---- universal curriculum prompt ----
sweets_prompt, sweets_course, sweets_label = build_gemini_curriculum_prompt(
    "Lesson metadata: course=numeracy; lesson_title=Subtraction. "
    "Exact recent tutor prompt: You have two sweets and give one away. How many sweets are left?"
)
check("sweets turn is numeracy", sweets_course == "numeracy")
check("sweets unit is preserved", sweets_label == "sweets" and "numeracy lesson in sweets" in sweets_prompt)
check("answer prompt excludes name and introduction", "saying their name" not in sweets_prompt and "introducing themselves" not in sweets_prompt)
check("universal prompt explicitly names Sabi", "name of the AI, Sabi" in sweets_prompt)
check("universal prompt includes can't-hear complaint", "can't hear the agent" in sweets_prompt)
check("universal prompt includes normal human phrase", "some other normal human phrase" in sweets_prompt)
check(
    "universal prompt never leaks operands",
    not re.search(r"\b(?:one|two)\b", sweets_prompt.lower()),
)

literacy_universal, literacy_course, literacy_label = build_gemini_curriculum_prompt(
    "Lesson metadata: course=literacy; lesson_title=Beginning Sounds. "
    "Exact recent tutor prompt: What sound comes first at the start of dog?",
    mode="literacy",
)
check("literacy turn is literacy", literacy_course == "literacy")
check("literacy topic is preserved", literacy_label == "beginning sounds")
check("literacy prompt uses same human alternatives", "name of the AI, Sabi" in literacy_universal and "can't hear" in literacy_universal)
check("literacy prompt never leaks example word", "dog" not in literacy_universal.lower())
check("literacy answer prompt excludes name priming", "saying their name" not in literacy_universal and "introducing themselves" not in literacy_universal)

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
    check("default timeout allows Flash-Lite to finish", captured["timeout"] == 5.5)
    parts = captured["payload"]["contents"][0]["parts"]
    check("audio part sent inline", "inlineData" in parts[0])
    check("curriculum prompt in payload", "walking through a numeracy lesson" in parts[1]["text"])
    check("ordinary answer payload excludes name priming", "saying their name" not in parts[1]["text"])
    check("prompt keeps exact response instruction", "Reply with their response" in parts[1]["text"])
    check(
        "every prompt allows Sabi, complaints, can't-hear, and ordinary speech",
        all(
            phrase in parts[1]["text"]
            for phrase in ("name of the AI, Sabi", "quality of the call or lesson", "can't hear the agent", "normal human phrase")
        ),
    )
    check(
        "minimal thinking is explicit for latency",
        captured["payload"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal",
    )
    check("provider latency recorded", result["provider_latency_seconds"] >= 0)
    os.remove(wav)

    # The live Gemini lane must receive every captured phone clip. A separate
    # local VAD used to reject short real answers before Gemini saw them.
    os.environ["SABI_STT_VAD_GATE"] = "1"
    os.environ["SABI_GEMINI_STT_BYPASS_VAD"] = "1"
    vad_wav = _tiny_wav()
    vad_was_called = {"value": False}

    def rejecting_vad(_path):
        vad_was_called["value"] = True
        return False

    sst._has_speech = rejecting_vad
    vad_result = sst._transcribe_prepared(
        vad_wav,
        mode="general",
        context="What is your name?",
    )
    check("Gemini receives clips even when local VAD would reject them", vad_result["text"] == "thirty")
    check("local VAD is not invoked on Gemini turns", not vad_was_called["value"])
    check("Gemini turn records the VAD bypass", vad_result["vad_bypassed_for_gemini"] is True)
    original_provider = sst._provider
    sst._provider = "auto"
    non_gemini_result = sst._transcribe_prepared(vad_wav, mode="general")
    check("non-Gemini providers retain the local VAD gate", non_gemini_result.get("vad_gated") is True)
    sst._provider = original_provider
    os.remove(vad_wav)

    os.environ["SABI_GEMINI_STT_PROMPT_MODE"] = "lesson_exact"
    exact_prompt = sst._gemini_prompt("What is your name?", mode="general")
    check("exact AI Studio prompt configurable", "Reply with their responses" in exact_prompt)
    os.environ.pop("SABI_GEMINI_STT_PROMPT_MODE", None)

    literacy_prompt = sst._gemini_prompt(
        "Lesson metadata: course=literacy; skill=phonemic_awareness_beginning. "
        "Exact recent tutor prompt: What sound starts dog?",
        mode="literacy",
    )
    check("global noisy-phone prompt is on the literacy turn", "noisy 8kHz phone call" in literacy_prompt)
    check("literacy course is explicit", "walking through a literacy lesson" in literacy_prompt)
    check("beginning-sound topic is explicit", "in beginning sounds" in literacy_prompt)
    check("curriculum prompt does not leak exact tutor question", "dog" not in literacy_prompt.lower())

    naira_prompt = sst._gemini_prompt(
        "Lesson metadata: course=numeracy; skill=subtraction. "
        "Exact recent tutor prompt: You have five naira and spend three. How much is left?",
        mode="general",
    )
    check("naira context is explicit", "numeracy lesson in naira" in naira_prompt)
    check("naira prompt keeps exact response instruction", "Reply with their response" in naira_prompt)
    check("global noisy-phone prompt is on the naira turn", "noisy 8kHz phone call" in naira_prompt)
    check("naira tag does not leak operands", "five" not in naira_prompt and "three" not in naira_prompt)
    check("naira answer turn excludes name priming", "saying their name" not in naira_prompt)

    name_prompt = sst._gemini_prompt("What is your name?", mode="general")
    check("global noisy-phone prompt is on the name turn", "noisy 8kHz phone call" in name_prompt)
    check("name turn keeps broad name context", "saying their name" in name_prompt)
    check("name turn keeps introduction context", "introducing themselves" in name_prompt)
    check("name turn explicitly allows calling Sabi", "name of the AI, Sabi" in name_prompt)
    greeting_name_prompt = sst._gemini_prompt(
        "Lesson metadata: course=numeracy; skill=market numeracy. "
        "Exact recent tutor prompt: Hello! I'm Sabi, your learning friend. What is your name?",
        mode="general",
    )
    check(
        "learning-friend greeting is not mislabeled as fair sharing",
        "in fair sharing" not in greeting_name_prompt,
    )
    sharing_prompt = sst._gemini_prompt(
        "Lesson metadata: course=numeracy; skill=division. "
        "Exact recent tutor prompt: Share six mangoes equally between two friends. How many does each get?",
        mode="general",
    )
    check("real sharing question keeps fair-sharing tag", "in fair sharing" in sharing_prompt)

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
