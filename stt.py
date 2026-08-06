"""
Speech-to-Text for Sabi.
Primary: Groq Whisper API (~200ms, 28,800 sec/day free) if GROQ_API_KEY is set.
Optional: Intron Sahara ASR for Nigerian/African accented English testing.
Fallback: Self-hosted faster-whisper (Whisper large-v3 on GPU, ~0.8-1.5s).

Optimizations for Nigerian English:
- initial_prompt bias with Nigerian vocabulary (naira, groundnuts, garri, etc.)
- Tuned VAD for phone-quality audio
"""

import io
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time
import wave

import httpx

from audio_cleaner import AudioCleaner

logger = logging.getLogger("sabi.stt")

INTRON_SYNC_URL = os.getenv(
    "INTRON_STT_SYNC_URL",
    "https://infer.voice.intron.io/file/v1/upload/sync",
)
INTRON_ASYNC_UPLOAD_URL = os.getenv(
    "INTRON_STT_ASYNC_UPLOAD_URL",
    "https://infer.voice.intron.io/file/v1/upload",
)
INTRON_STATUS_URL_TEMPLATE = os.getenv(
    "INTRON_STT_STATUS_URL_TEMPLATE",
    "https://infer.voice.intron.io/file/v1/status/{file_id}",
)
INTRON_TIMEOUT_SECONDS = float(os.getenv("INTRON_STT_TIMEOUT_SECONDS", "8"))
INTRON_ASYNC_MAX_WAIT_SECONDS = float(os.getenv("INTRON_STT_ASYNC_MAX_WAIT_SECONDS", "15"))
INTRON_ASYNC_POLL_INTERVAL_SECONDS = float(os.getenv("INTRON_STT_ASYNC_POLL_INTERVAL_SECONDS", "1.5"))
INTRON_MIN_AUDIO_SECONDS = float(os.getenv("INTRON_STT_MIN_AUDIO_SECONDS", "1.2"))
INTRON_LANGUAGE = os.getenv("INTRON_STT_LANGUAGE", "en")
INTRON_CATEGORY = os.getenv("INTRON_STT_CATEGORY", "file_category_general")

# Whisper prompt bias — providing domain-specific vocabulary in the initial_prompt
# biases the decoder toward recognizing these words correctly.
NIGERIAN_ENGLISH_PROMPT = (
    "Sabi is an AI tutor for children in Lagos, Nigeria. "
    "The child is learning about naira, kobo, groundnuts, pure water, garri, "
    "suya, biscuits, exercise books, bus fare, okada, danfo, keke. "
    "Common words: oya, wahala, sharp sharp, well done, correct, "
    "how much, change, market, mama, papa, auntie, uncle. "
    "Numbers: one, two, three, four, five, six, seven, eight, nine, ten, "
    "twenty, fifty, hundred, thousand. "
    "Math: plus, minus, times, divided by, equals, remainder, total, altogether."
)

LITERACY_ENGLISH_PROMPT = (
    "Sabi teaches foundational literacy to children in Lagos over phone calls. "
    "Transcribe short sounds, letters, syllables, rhymes, and simple words literally. "
    "Examples: m, mmm, s, sss, a, ah, t, p, n, "
    "cat, mat, hat, rat, sat, fat, pat, bat, dog, log, fog, hog, big, dig, pig, mango, moon, market, mama, ball, "
    "syllable, rhyme, beginning sound, ending sound. "
    "Do not change rhyme words into correct, right, wrong, or thank you unless clearly spoken. "
    "Do not force literacy answers into math words or prices."
)


# Number-answer biasing. When the tutor is expecting a numeric answer, prime the
# recognizer toward number words. Validated on real Nigerian-accented calls: it
# recovers answers Whisper otherwise mis-hears ("Thank you" -> "thirty",
# "She's thin" -> "fifteen"). hotwords is the strong lever for local Whisper;
# Groq only takes a prompt, so it gets the priming sentence instead.
NUMBER_HOTWORDS = (
    "zero one two three four five six seven eight nine ten "
    "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
    "twenty thirty forty fifty sixty seventy eighty ninety hundred"
)


WORD_ANSWER_CUES = (
    "another word",
    "say a word",
    "word that rhymes",
    "what else rhymes",
    "think of a word",
    "ends with",
)
SOUND_ANSWER_CUES = (
    "what sound",
    "which sound",
    "sound comes first",
    "sound do you hear",
    "beginning sound",
    "ending sound",
    "at the beginning of",
    "at the start of",
    "say the sound",
    "say ddd",
    "say mmm",
    "say sss",
)
SUSPECT_LITERACY_FEEDBACK = {"correct", "right", "wrong", "thank you", "thanks"}
LITERACY_WORDS = {
    "cat", "mat", "hat", "rat", "sat", "fat", "pat", "bat",
    "dog", "log", "fog", "hog", "big", "dig", "pig",
}

WHISPER_CLI_PROVIDERS = {"whisper_cli", "openai_whisper", "openai-whisper", "cli_whisper"}


def _expects_number(context: str) -> bool:
    """True when the recent tutor prompt is asking for a numeric answer, so STT
    should be biased toward number words. Reuses the same numeric-context
    detector the transcript normalizer uses. Fail-safe: returns False on any
    error so biasing never breaks a normal transcription."""
    if not context:
        return False
    try:
        from transcript_normalizer import has_numeric_lesson_context

        return has_numeric_lesson_context([{"role": "assistant", "content": str(context)}])
    except Exception:
        return False


def _looks_number_like(text: str) -> bool:
    """True when the transcript parses to a number (so no numeric salvage needed)."""
    if not text:
        return False
    try:
        from answer_matcher import extract_number

        return extract_number(text) is not None
    except Exception:
        return False


def _clean_prompt_context(context: str, limit: int = 220) -> str:
    cleaned = " ".join(str(context or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


def _plain_text(text: str) -> str:
    return " ".join(str(text or "").lower().replace("-", " ").strip(" .,!?:;").split())


def _expects_literacy_word_answer(context: str) -> bool:
    normalized = _plain_text(context)
    return any(cue in normalized for cue in WORD_ANSWER_CUES)


def _expects_literacy_sound_answer(context: str) -> bool:
    normalized = _plain_text(context)
    return any(cue in normalized for cue in SOUND_ANSWER_CUES)


def _expects_naira_answer(context: str) -> bool:
    normalized = _plain_text(context)
    return any(token in normalized.split() for token in ("naira", "kobo", "money", "price", "change"))


def _is_suspect_literacy_feedback(text: str, context: str) -> bool:
    return _expects_literacy_word_answer(context) and _plain_text(text) in SUSPECT_LITERACY_FEEDBACK


def _is_short_literacy_word(text: str) -> bool:
    normalized = _plain_text(text)
    return normalized in LITERACY_WORDS or (normalized.isalpha() and 1 <= len(normalized) <= 5)


def _expects_name(context: str) -> bool:
    """True when the tutor just asked the child for their name, so Gemini can be
    told to expect a (often Nigerian) name rather than a generic phrase."""
    normalized = _plain_text(context)
    if not normalized:
        return False
    return any(
        cue in normalized
        for cue in (
            "your name",
            "what is your name",
            "whats your name",
            "tell me your name",
            "who is this",
            "who am i speaking",
            "what should i call you",
            "what can i call you",
        )
    )


class SpeechToText:
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        provider: str | None = None,
        literacy_provider: str | None = None,
    ):
        """
        Initialize STT. Uses Groq Whisper API if GROQ_API_KEY is available
        (much faster: ~200ms vs ~1s local). Falls back to self-hosted faster-whisper.

        Args:
            model_size: Local Whisper model size (only used if Groq not available).
                - "medium" — faster (~0.8s), good accuracy (~5GB VRAM)
                - "large-v3" — slower (~1.5s), best accuracy (~6GB VRAM)
            device: "cuda" for GPU, "cpu" for CPU-only (local fallback only)
        """
        # Re-load GROQ_API_KEY now that secret_loader is definitely available
        from secret_loader import get_secret
        self._groq_key = get_secret("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")
        self._intron_key = get_secret("INTRON_API_KEY") or os.getenv("INTRON_API_KEY", "")
        # Gemini multimodal audio STT. In the Aug 2026 gold-clip bake-off,
        # gemini-3.5-flash-lite with a lesson-context hint recovered warbled
        # Nigerian names AND numbers ("thirty", "fifteen", "My name is Gideon")
        # that every Whisper variant turned to garbage. Enabled by setting
        # SABI_STT_PROVIDER=gemini or gemini_first. Both are strict: failures
        # become an unclear-audio retry. Only gemini_fallback changes models.
        self._gemini_key = get_secret("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        self._gemini_model = (
            os.getenv("SABI_GEMINI_STT_MODEL", "gemini-3.5-flash-lite").strip()
            or "gemini-3.5-flash-lite"
        )
        # Reuse one connection across turns so every short child answer does
        # not pay a fresh DNS/TCP/TLS setup cost.
        self._gemini_http = httpx.Client(
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )
        env_provider = os.getenv("SABI_STT_PROVIDER", "auto")
        self._provider = (provider or env_provider).strip().lower() or "auto"
        env_literacy_provider = os.getenv("SABI_LITERACY_STT_PROVIDER", self._provider)
        self._literacy_provider = (
            literacy_provider or env_literacy_provider
        ).strip().lower() or self._provider
        self._model_size = os.getenv("SABI_LOCAL_WHISPER_MODEL_SIZE", model_size).strip() or model_size
        self._device = os.getenv("SABI_LOCAL_WHISPER_DEVICE", device).strip() or device
        self._audio_cleaner = AudioCleaner.from_env()

        if self._groq_key and self._provider != "local":
            self._use_groq = True
            logger.info("STT: Groq Whisper API (fast, ~200ms)")
        else:
            self._use_groq = False
        if self._provider in {"intron", "intron_first"} or self._literacy_provider in {"intron", "intron_first"}:
            logger.info(
                "STT: Intron Sahara ASR configured for provider=%s literacy_provider=%s available=%s",
                self._provider,
                self._literacy_provider,
                bool(self._intron_key),
            )
        if self._provider in WHISPER_CLI_PROVIDERS or self._literacy_provider in WHISPER_CLI_PROVIDERS:
            logger.info("STT: Homebrew/openai-whisper CLI configured for local harness probes")
        configured_providers = {self._provider, self._literacy_provider}
        providers_without_eager_local_fallback = {
            "gemini",
            "gemini_first",
            "gemini_fallback",
            "intron",
            "intron_first",
            *WHISPER_CLI_PROVIDERS,
        }
        if (
            not self._use_groq
            and configured_providers.isdisjoint(providers_without_eager_local_fallback)
        ):
            self._load_local_model(model_size, device)

    def _load_local_model(self, model_size: str | None = None, device: str | None = None) -> None:
        if hasattr(self, "_model"):
            return
        model_size = model_size or self._model_size
        device = device or self._device
        try:
            logger.info(f"STT: Loading local Whisper {model_size} on {device}...")
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
            )
            logger.info(f"STT: Local Whisper {model_size} loaded.")
        except Exception:
            logger.exception("STT: Failed to load local Whisper fallback")
            raise

    def _has_speech(self, audio_path: str) -> bool:
        """Silero VAD pre-gate.

        Returns False when the clip contains no speech above threshold, so pure
        noise / dead air never reaches the STT model — which otherwise
        hallucinates fluent text ("Subtitles by the Amara.org community",
        "Thank you") on a crying-baby or silent turn. Confirmed on real Sabi
        calls: gates the dead-air turns, keeps every real (even quiet/short)
        child answer.

        Fail-open: any error (missing dep, decode failure) returns True, so a
        real answer is never dropped because the guard broke. Disable entirely
        with SABI_STT_VAD_GATE=0.
        """
        if os.getenv("SABI_STT_VAD_GATE", "1").strip().lower() in {"0", "false", "no", "off"}:
            return True
        try:
            from faster_whisper.audio import decode_audio
            from faster_whisper.vad import VadOptions, get_speech_timestamps

            audio = decode_audio(audio_path, sampling_rate=16000)
            options = VadOptions(
                onset=float(os.getenv("SABI_STT_VAD_ONSET", "0.5")),
                min_silence_duration_ms=int(os.getenv("SABI_STT_VAD_MIN_SILENCE_MS", "500")),
                speech_pad_ms=int(os.getenv("SABI_STT_VAD_SPEECH_PAD_MS", "200")),
            )
            has_speech = bool(get_speech_timestamps(audio, options))
            if not has_speech:
                logger.info("STT VAD gate: no speech in %s — skipping model call", audio_path)
            return has_speech
        except Exception:
            logger.exception("STT VAD gate failed; passing audio through (fail-open)")
            return True

    def transcribe(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """Clean a phone clip once, then use the configured STT/fallback stack."""
        with self._audio_cleaner.prepare(audio_path) as (prepared_path, cleaning):
            result = self._transcribe_prepared(prepared_path, mode=mode, context=context)
            result["audio_cleaning"] = cleaning
            return result

    def _transcribe_prepared(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)

        Returns:
            dict with 'text' and 'confidence' keys
        """
        provider = self._provider_for_mode(mode)
        primary_error: Exception | None = None

        # VAD pre-gate: skip the STT model entirely on no-speech audio so a
        # crying baby / dead air can never be transcribed into a hallucination.
        # Returns empty text, which the caller already handles as "say that
        # again" — no invented words ever reach the tutor.
        if not self._has_speech(audio_path):
            return {
                "text": "",
                "confidence": 0.0,
                "language": "en",
                "duration_seconds": 0.0,
                "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
                "provider": provider,
                "no_speech": True,
                "vad_gated": True,
            }
        if provider in {"gemini", "gemini_first", "gemini_fallback"}:
            if self._gemini_key:
                try:
                    return self._transcribe_gemini(audio_path, mode=mode, context=context)
                except Exception as e:
                    primary_error = e
                    if provider != "gemini_fallback":
                        logger.warning("Strict Gemini STT failed (%s); returning an unclear turn for retry", e)
                        return {
                            "text": "",
                            "confidence": 0.0,
                            "language": "en",
                            "duration_seconds": 0.0,
                            "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
                            "provider": "gemini",
                            "gemini_model": self._gemini_model,
                            "provider_error": f"{e.__class__.__name__}: {_safe_error_text(e)}",
                        }
                    logger.warning("Gemini STT failed (%s), falling back to Groq/Whisper", e)
            else:
                if provider != "gemini_fallback":
                    logger.error("Strict Gemini STT requested but GEMINI_API_KEY is not configured")
                    return {
                        "text": "",
                        "confidence": 0.0,
                        "language": "en",
                        "duration_seconds": 0.0,
                        "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
                        "provider": "gemini",
                        "gemini_model": self._gemini_model,
                        "provider_error": "GEMINI_API_KEY is not configured",
                    }
                logger.warning("Gemini STT requested but GEMINI_API_KEY is not configured; using Groq/Whisper")
        if provider in {"intron", "intron_first"}:
            if self._intron_key:
                try:
                    return self._transcribe_intron(audio_path, mode=mode)
                except Exception as e:
                    primary_error = e
                    logger.warning("Intron STT failed (%s), falling back to Groq/Whisper", e)
            else:
                logger.warning("Intron STT requested but INTRON_API_KEY is not configured; using Groq/Whisper")
        if provider == "local":
            return self._transcribe_local(audio_path, mode=mode, context=context)
        if provider in WHISPER_CLI_PROVIDERS:
            return self._transcribe_whisper_cli(audio_path, mode=mode, context=context)
        if self._use_groq:
            fallback = self._transcribe_groq(audio_path, mode=mode, context=context)
            if primary_error is not None:
                fallback["fallback_from"] = provider
                fallback["fallback_reason"] = (
                    f"{primary_error.__class__.__name__}: {_safe_error_text(primary_error)}"
                )
            return fallback
        try:
            fallback = self._transcribe_local(audio_path, mode=mode, context=context)
            if primary_error is not None:
                fallback["fallback_from"] = provider
                fallback["fallback_reason"] = (
                    f"{primary_error.__class__.__name__}: {_safe_error_text(primary_error)}"
                )
            return fallback
        except Exception as fallback_error:
            if primary_error is not None:
                raise RuntimeError(
                    "STT providers failed: "
                    f"primary {provider}={primary_error.__class__.__name__}: {_safe_error_text(primary_error)}; "
                    f"fallback local={fallback_error.__class__.__name__}: {_safe_error_text(fallback_error)}"
                ) from fallback_error
            raise

    def _provider_for_mode(self, mode: str) -> str:
        if str(mode or "").lower() == "literacy":
            return self._literacy_provider
        return self._provider

    def _prompt_for_mode(self, mode: str, context: str = "") -> str:
        prompt = LITERACY_ENGLISH_PROMPT if str(mode or "").lower() == "literacy" else NIGERIAN_ENGLISH_PROMPT
        recent_context = _clean_prompt_context(context)
        if recent_context:
            prompt = (
                f"{prompt} Recent tutor prompt for this exact child answer: {recent_context}. "
                "Use that context only to resolve unclear short phone audio; keep the child's words literal."
            )
        return prompt

    def _gemini_shape_hint(self, context: str) -> str:
        """Closed-vocab hint derived from the LESSON state (never the answer).

        This is the mode that won the Jul 2026 gold-clip bake-off: telling
        Gemini the expected SHAPE of the answer (number / single word / name)
        sharply improves recovery of warbled Nigerian child speech, while a
        bare "transcribe this" prompt does not.
        """
        control_rule = (
            "A control request always overrides the expected answer type: if the child says they "
            "did not hear, asks Sabi to repeat the question, asks for help, or asks to switch subjects, "
            "transcribe that request literally and in full. Never turn a control request into a guessed answer. "
        )
        if _expects_number(context):
            return (
                f"{control_rule}Otherwise, the child is answering a maths question with a NUMBER. "
                "For an actual answer, reply with only the number they said (as digits or a number word)."
            )
        if _expects_literacy_sound_answer(context):
            return (
                f"{control_rule}Otherwise, the child is answering with one short speech sound or letter "
                "sound, such as d, ddd, b, or bbb. Preserve that sound literally; never convert it into "
                "a number word or a tutor-feedback word."
            )
        if _expects_literacy_word_answer(context):
            return (
                f"{control_rule}Otherwise, the child is reading or sounding out a single English word. "
                "For an actual answer, reply with only that one word."
            )
        if _expects_name(context):
            return (
                f"{control_rule}Otherwise, the child is saying their name, often a Nigerian name such "
                "as Gideon, Oluremi, or Chukwuemeka. For an actual answer, reply with only the name."
            )
        return f"{control_rule}Transcribe exactly what the child said. Reply with only the transcript."

    def _gemini_tagged_prompt(self, context: str, mode: str = "general") -> str:
        """Choose a compact lesson tag without ever supplying the answer.

        This reproduces the prompt pattern that correctly recovered `d` and
        `2 naira` from the Aug 5 phone clips. The exact tutor question is used
        locally to select the tag, but is not sent to Gemini, avoiding answer
        leakage and prompt-induced hallucination.
        """
        global_prompt = os.getenv(
            "SABI_GEMINI_STT_GLOBAL_PROMPT",
            "A Nigerian child on a noisy 8kHz phone call",
        ).strip()
        normalized = _plain_text(context)
        if _expects_name(context):
            turn_tag = "is saying their name. Reply with their response."
        elif _expects_number(context) and _expects_naira_answer(context):
            turn_tag = "is responding to a numeracy question in naira. Reply with their response."
        elif _expects_number(context):
            turn_tag = "is responding to a numeracy question. Reply with their response."
        elif _expects_literacy_sound_answer(context) or "phonemic" in normalized or "phonics" in normalized:
            if "ending" in normalized or "at the end" in normalized:
                sound_type = "one spoken ending letter sound"
            elif any(cue in normalized for cue in ("beginning", "at the start", "comes first", "sound starts")):
                sound_type = "one spoken beginning letter sound"
            else:
                sound_type = "one short spoken English sound"
            turn_tag = (
                f"is responding with {sound_type} to a literacy phonemics question. "
                "Reply with the sound they say."
            )
        elif _expects_literacy_word_answer(context) or "rhyme" in normalized:
            turn_tag = "is responding to a literacy word question. Reply with their response."
        elif str(mode or "").lower() == "literacy":
            turn_tag = "is responding to a literacy question. Reply with their response."
        else:
            turn_tag = "is responding during a lesson. Reply with their response."
        return self._append_gemini_control_context(f"{global_prompt} {turn_tag}")

    @staticmethod
    def _append_gemini_control_context(prompt: str) -> str:
        """Keep non-answer speech available to Gemini on every lesson turn."""
        control_context = os.getenv(
            "SABI_GEMINI_STT_CONTROL_CONTEXT",
            (
                "This could also be a complaint about the quality of the call or lesson, "
                "or the child calling your name."
            ),
        ).strip()
        return f"{prompt.strip()} {control_context}".strip()

    def _gemini_prompt(self, context: str, mode: str = "general") -> str:
        """Build the audio prompt without ever including the expected answer.

        ``tagged`` is the production-safe default: it sends only a compact
        response category selected from lesson state, never the answer. The
        more verbose ``shape`` mode combines the noisy-phone framing with an
        answer type and exact question context. The
        ``lesson_exact`` canary reproduces the exact AI Studio wording that
        first recovered the full Oluremi/Gideon calls. It is intentionally
        configurable because the generative audio model is prompt-sensitive.
        """
        lesson_prompt = os.getenv(
            "SABI_GEMINI_STT_LESSON_PROMPT",
            "A Nigerian child on a noisy 8kHz phone call is saying their name, "
            "introducing themselves and walking through a numeracy lesson. "
            "Reply with their responses",
        ).strip()
        recent_context = _clean_prompt_context(context, limit=800)
        prompt_mode = os.getenv("SABI_GEMINI_STT_PROMPT_MODE", "tagged").strip().lower()
        if prompt_mode == "lesson_exact":
            return self._append_gemini_control_context(lesson_prompt)
        if prompt_mode == "tagged":
            return self._gemini_tagged_prompt(context, mode=mode)
        if prompt_mode == "lesson_plus_shape":
            context_line = f" Current lesson and exact tutor-question context: {recent_context}." if recent_context else ""
            return self._append_gemini_control_context(
                f"{lesson_prompt}.{context_line} {self._gemini_shape_hint(context)}"
            )
        lesson_kind = "literacy" if str(mode or "").lower() == "literacy" else "numeracy or general"
        preamble = (
            "This audio is a Nigerian child speaking English on a noisy, low-quality "
            f"8kHz telephone call during a {lesson_kind} lesson. This is one turn from a longer "
            "conversation, and background noise is likely. "
        )
        if recent_context:
            preamble += (
                f"Current lesson and exact tutor-question context: {recent_context}. "
                "The supplied audio contains the child's response, not the tutor's question. "
            )
        return self._append_gemini_control_context(preamble + self._gemini_shape_hint(context))

    def _transcribe_gemini(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """Transcribe via Gemini multimodal audio (3.5 Flash-Lite by default).

        Sends the clip inline with a lesson-response tag. Raises on failure;
        strict Gemini providers turn that failure into an unclear-audio retry,
        while the explicitly configured gemini_fallback provider may change
        to Groq/local.
        """
        import base64

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        ext = Path(audio_path).suffix.lower()
        mime = "audio/mpeg" if ext in (".mp3", ".m4a") else "audio/wav"
        prompt = self._gemini_prompt(context, mode=mode)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._gemini_model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inlineData": {"mimeType": mime, "data": base64.b64encode(audio_bytes).decode()}},
                        {"text": prompt},
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": int(os.getenv("SABI_GEMINI_STT_MAX_TOKENS", "64")),
                "thinkingConfig": {
                    "thinkingLevel": os.getenv("SABI_GEMINI_STT_THINKING_LEVEL", "minimal").strip().lower()
                    or "minimal",
                },
            },
        }
        started = time.monotonic()
        response = self._gemini_http.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._gemini_key,
            },
            timeout=float(os.getenv("SABI_GEMINI_STT_TIMEOUT", "5.5")),
        )
        provider_latency_seconds = time.monotonic() - started
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {str(data)[:200]}")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise RuntimeError("Gemini returned empty transcript")
        return {
            "text": text,
            "confidence": 0.9,
            "language": "en",
            "duration_seconds": 0.0,
            "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
            "provider": "gemini",
            "gemini_model": self._gemini_model,
            "gemini_prompt_mode": os.getenv("SABI_GEMINI_STT_PROMPT_MODE", "tagged").strip().lower(),
            "provider_latency_seconds": round(provider_latency_seconds, 3),
            "usage_metadata": data.get("usageMetadata") or {},
        }

    def _transcribe_intron(self, audio_path: str, mode: str = "general") -> dict:
        """Transcribe via Intron Sahara ASR. Keep optional until real-call A/B testing."""
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        ext = Path(audio_path).suffix.lower() or ".wav"
        mime = "audio/mpeg" if ext in (".mp3", ".m4a") else "audio/wav"
        filename = Path(audio_path).name or f"audio{ext}"
        audio_bytes = _pad_short_wav_for_intron(audio_bytes, ext=ext)
        form_data = {
            "audio_file_name": filename,
            "use_diarization": "FALSE",
            "use_language_asr_input": INTRON_LANGUAGE,
            "use_category": INTRON_CATEGORY,
        }

        response = httpx.post(
            INTRON_SYNC_URL,
            headers={"Authorization": f"Bearer {self._intron_key}"},
            files={"audio_file_blob": (filename, audio_bytes, mime)},
            data=form_data,
            timeout=INTRON_TIMEOUT_SECONDS,
        )
        if response.status_code == 503:
            data = _safe_json(response)
            raise RuntimeError(f"Intron sync still processing file_id={_extract_intron_file_id(data)}")
        if response.status_code == 403 and _should_try_intron_async(response):
            logger.info("Intron sync denied for non-integrator key; using async upload/status flow")
            data = self._transcribe_intron_async(
                audio_bytes=audio_bytes,
                filename=filename,
                mime=mime,
                form_data=form_data,
            )
        else:
            response.raise_for_status()
            data = response.json()
        text = _extract_intron_text(data)
        return {
            "text": text,
            "confidence": 0.84 if text else 0.0,
            "language": INTRON_LANGUAGE,
            "duration_seconds": _extract_intron_duration(data),
            "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
            "provider": "intron",
            "intron_status": _extract_intron_processing_status(data),
        }

    def _transcribe_intron_async(
        self,
        audio_bytes: bytes,
        filename: str,
        mime: str,
        form_data: dict,
    ) -> dict:
        upload_response = httpx.post(
            INTRON_ASYNC_UPLOAD_URL,
            headers={"Authorization": f"Bearer {self._intron_key}"},
            files={"audio_file_blob": (filename, audio_bytes, mime)},
            data=form_data,
            timeout=INTRON_TIMEOUT_SECONDS,
        )
        upload_response.raise_for_status()
        upload_data = upload_response.json()
        file_id = _extract_intron_file_id(upload_data)
        if not file_id or file_id == "unknown":
            raise RuntimeError(f"Intron async upload missing file_id: {_safe_json_excerpt(upload_data)}")

        deadline = time.monotonic() + max(1.0, INTRON_ASYNC_MAX_WAIT_SECONDS)
        last_data: dict = upload_data
        while time.monotonic() < deadline:
            status_url = INTRON_STATUS_URL_TEMPLATE.format(file_id=file_id)
            status_response = httpx.get(
                status_url,
                headers={"Authorization": f"Bearer {self._intron_key}"},
                timeout=INTRON_TIMEOUT_SECONDS,
            )
            if status_response.status_code == 429:
                retry_after = _retry_after_seconds(status_response, default=INTRON_ASYNC_POLL_INTERVAL_SECONDS)
                if time.monotonic() + retry_after >= deadline:
                    status_response.raise_for_status()
                time.sleep(retry_after)
                continue
            status_response.raise_for_status()
            last_data = status_response.json()
            if _intron_file_transcribed(last_data):
                return last_data
            if _intron_file_failed(last_data):
                raise RuntimeError(f"Intron async failed for file_id={file_id}: {_safe_json_excerpt(last_data)}")
            time.sleep(max(0.2, INTRON_ASYNC_POLL_INTERVAL_SECONDS))
        raise RuntimeError(f"Intron async timed out file_id={file_id}: {_safe_json_excerpt(last_data)}")

    def _transcribe_groq(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """Transcribe via Groq Whisper API (~200ms, free tier: 28,800 sec/day)."""
        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            # Detect file extension for MIME type
            ext = Path(audio_path).suffix.lower()
            mime = "audio/mpeg" if ext in (".mp3", ".m4a") else "audio/wav"
            filename = f"audio{ext}"

            response = httpx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._groq_key}"},
                files={"file": (filename, audio_bytes, mime)},
                data={
                    "model": "whisper-large-v3",
                    "language": "en",
                    "prompt": self._prompt_for_mode(mode, context=context),
                    "response_format": "verbose_json",
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()

            text = data.get("text", "").strip()
            # Groq verbose_json doesn't return per-segment logprob — use 0.8 default
            # if text is non-empty (Groq has high accuracy)
            confidence = 0.82 if text else 0.0

            result = {
                "text": text,
                "confidence": confidence,
                "language": data.get("language", "en"),
                "duration_seconds": round(data.get("duration", 0.0), 1),
                "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
                "provider": "groq",
            }
            if str(mode or "").lower() == "literacy" and _is_suspect_literacy_feedback(text, context):
                try:
                    alt = self._transcribe_local(audio_path, mode=mode, context=context)
                    alt_text = alt.get("text", "")
                    if alt_text and _plain_text(alt_text) != _plain_text(text) and _is_short_literacy_word(alt_text):
                        alt["provider"] = "local_literacy_salvage"
                        alt["salvaged_from"] = text
                        return alt
                except Exception as salvage_error:
                    logger.warning("Literacy salvage STT failed (%s); using Groq result", salvage_error)
            # Numeric salvage: Groq can't take hotwords, so when a number answer
            # is expected but Groq didn't hear one, retry on local Whisper with
            # number-word hotwords (validated to recover "thirty"/"fifteen" that
            # Groq renders as "Thank you"/"She's thin").
            if _expects_number(context) and not _looks_number_like(text):
                try:
                    alt = self._transcribe_local(audio_path, mode=mode, context=context)
                    alt_text = alt.get("text", "")
                    if alt_text and _looks_number_like(alt_text):
                        alt["provider"] = "local_numeric_salvage"
                        alt["salvaged_from"] = text
                        return alt
                except Exception as salvage_error:
                    logger.warning("Numeric salvage STT failed (%s); using Groq result", salvage_error)
            return result

        except httpx.HTTPStatusError as e:
            logger.warning(
                "Groq STT failed (%s %s: %s), falling back to local Whisper",
                e.response.status_code,
                e.request.url,
                e.response.text[:500],
            )
            if not hasattr(self, "_model"):
                self._load_local_model("large-v3", "cuda")
            return self._transcribe_local(audio_path, mode=mode, context=context)
        except Exception as e:
            logger.warning(f"Groq STT failed ({e}), falling back to local Whisper")
            # Lazy-load local model if not already loaded
            if not hasattr(self, "_model"):
                self._load_local_model("large-v3", "cuda")
            return self._transcribe_local(audio_path, mode=mode, context=context)

    def _transcribe_local(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """Transcribe using self-hosted faster-whisper (GPU)."""
        self._load_local_model()
        numeric = _expects_number(context)
        # On numeric-answer turns, bias with number-word hotwords and DROP the
        # verbose prompt: hotwords alone reliably recovers "thirty"/"fifteen",
        # while keeping the prompt makes short clips echo it back verbatim.
        segments, info = self._model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            initial_prompt=None if numeric else self._prompt_for_mode(mode, context=context),
            hotwords=NUMBER_HOTWORDS if numeric else None,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 650 if str(mode or "").lower() == "literacy" else 500,
                "speech_pad_ms": 320 if str(mode or "").lower() == "literacy" else 200,
            },
        )

        full_text = ""
        total_confidence = 0.0
        segment_count = 0

        for segment in segments:
            full_text += segment.text
            confidence = min(1.0, max(0.0, 1.0 + segment.avg_logprob))
            total_confidence += confidence
            segment_count += 1

        avg_confidence = total_confidence / max(segment_count, 1)

        return {
            "text": full_text.strip(),
            "confidence": round(avg_confidence, 3),
            "language": info.language,
            "duration_seconds": round(info.duration, 1),
            "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
            "provider": "local_whisper",
        }

    def _transcribe_whisper_cli(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """Transcribe using the Homebrew/openai-whisper CLI for local harness probes."""
        cli_path = os.getenv("SABI_WHISPER_CLI_PATH", "whisper").strip() or "whisper"
        model = os.getenv("SABI_WHISPER_CLI_MODEL", "tiny.en").strip() or "tiny.en"
        device = os.getenv("SABI_WHISPER_CLI_DEVICE", "cpu").strip() or "cpu"
        timeout = float(os.getenv("SABI_WHISPER_CLI_TIMEOUT_SECONDS", "120"))
        threads = os.getenv("SABI_WHISPER_CLI_THREADS", "").strip()
        use_prompt = os.getenv("SABI_WHISPER_CLI_INITIAL_PROMPT", "0").strip().lower() in {"1", "true", "yes", "on"}
        with tempfile.TemporaryDirectory(prefix="sabi-whisper-cli-") as tmpdir:
            output_dir = Path(tmpdir)
            cmd = [
                cli_path,
                audio_path,
                "--model",
                model,
                "--device",
                device,
                "--language",
                "en",
                "--task",
                "transcribe",
                "--output_format",
                "txt",
                "--output_dir",
                str(output_dir),
                "--verbose",
                "False",
                "--fp16",
                "False",
                "--condition_on_previous_text",
                "False",
                "--temperature",
                "0",
                "--best_of",
                "1",
                "--beam_size",
                "1",
            ]
            if threads:
                cmd.extend(["--threads", threads])
            if use_prompt:
                cmd.extend(["--initial_prompt", self._prompt_for_mode(mode, context=context)])
            try:
                completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    "whisper CLI timed out after "
                    f"{timeout:g}s: stdout={_safe_subprocess_text(error.stdout)} "
                    f"stderr={_safe_subprocess_text(error.stderr)}"
                ) from error
            if completed.returncode != 0:
                raise RuntimeError(
                    "whisper CLI failed: "
                    f"stdout={_safe_subprocess_text(completed.stdout)} "
                    f"stderr={_safe_subprocess_text(completed.stderr)}"
                )
            txt_path = output_dir / f"{Path(audio_path).stem}.txt"
            if not txt_path.exists():
                matches = list(output_dir.glob("*.txt"))
                txt_path = matches[0] if matches else txt_path
            text = txt_path.read_text().strip() if txt_path.exists() else ""
        return {
            "text": text,
            "confidence": 0.7 if text else 0.0,
            "language": "en",
            "duration_seconds": _audio_duration_seconds(audio_path),
            "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
            "provider": "whisper_cli",
            "model": model,
            "initial_prompt": use_prompt,
        }


def _safe_json(response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_json_excerpt(data: dict, limit: int = 500) -> str:
    try:
        import json
        return json.dumps(data, sort_keys=True)[:limit]
    except Exception:
        return str(data)[:limit]


def _should_try_intron_async(response) -> bool:
    text = str(getattr(response, "text", "") or "").lower()
    return (
        "integrator account" in text
        or "access-key error" in text
        or "permission denied" in text
    )


def _retry_after_seconds(response, default: float = 1.5) -> float:
    raw = ""
    try:
        raw = response.headers.get("Retry-After", "")
        value = float(raw)
    except Exception:
        value = default
    return max(0.5, min(value, 10.0))


def _safe_error_text(error: Exception, limit: int = 300) -> str:
    return " ".join(str(error).split())[:limit]


def _safe_subprocess_text(value, limit: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return " ".join(str(value).split())[-limit:]


def _audio_duration_seconds(audio_path: str) -> float:
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
        return round(frames / rate, 1) if rate else 0.0
    except Exception:
        return 0.0


def _pad_short_wav_for_intron(audio_bytes: bytes, ext: str) -> bytes:
    if ext.lower() != ".wav" or INTRON_MIN_AUDIO_SECONDS <= 0:
        return audio_bytes
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as source:
            params = source.getparams()
            frames = source.readframes(source.getnframes())
            frame_count = source.getnframes()
            frame_rate = source.getframerate()
            sample_width = source.getsampwidth()
            channels = source.getnchannels()
        if not frame_rate or not channels or not sample_width:
            return audio_bytes
        target_frames = int(INTRON_MIN_AUDIO_SECONDS * frame_rate)
        if frame_count >= target_frames:
            return audio_bytes
        missing_frames = target_frames - frame_count
        silence = b"\x00" * missing_frames * channels * sample_width
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setparams(params)
            target.writeframes(frames + silence)
        return output.getvalue()
    except Exception as error:
        logger.warning("Could not pad short WAV for Intron (%s); sending original audio", error)
        return audio_bytes


def _extract_intron_text(data: dict) -> str:
    """Handle small response-shape variations without making the call path brittle."""
    for key in ("text", "transcript", "transcription", "audio_transcript"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("results", "result", "data"):
        value = data.get(key)
        if isinstance(value, dict):
            text = _extract_intron_text(value)
            if text:
                return text
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    text = _extract_intron_text(item)
                    if text:
                        parts.append(text)
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            if parts:
                return " ".join(parts).strip()
    return ""


def _extract_intron_duration(data: dict) -> float:
    """Return audio duration from the response shape used by Intron file sync."""
    for key in ("duration", "duration_seconds", "processed_audio_duration_in_seconds"):
        value = data.get(key)
        if value not in (None, ""):
            try:
                return round(float(value), 1)
            except (TypeError, ValueError):
                pass
    for key in ("results", "result", "data"):
        value = data.get(key)
        if isinstance(value, dict):
            duration = _extract_intron_duration(value)
            if duration:
                return duration
    return 0.0


def _extract_intron_processing_status(data: dict) -> str:
    for key in ("processing_status", "file_status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = data.get("data")
    if isinstance(nested, dict):
        nested_status = _extract_intron_processing_status(nested)
        if nested_status:
            return nested_status
    value = data.get("status")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _intron_file_transcribed(data: dict) -> bool:
    return bool(_extract_intron_text(data))


def _intron_file_failed(data: dict) -> bool:
    status = _extract_intron_processing_status(data).upper()
    return any(word in status for word in ("FAILED", "ERROR", "CANCELLED"))


def _extract_intron_file_id(data: dict) -> str:
    """Return the file id from an Intron sync timeout/status response."""
    for key in ("file_id", "id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_intron_file_id(nested)
    return "unknown"
