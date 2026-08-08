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
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import logging
import os
import re
from pathlib import Path
import subprocess
import tempfile
import threading
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
PARALLEL_CONSENSUS_PROVIDERS = {
    "parallel_consensus",
    "groq_whisper_consensus",
    "consensus",
}

# Gemini receives only a safe course/topic label plus a literal-transcription
# instruction. Enumerating possible complaints, names, or answers made the
# generative audio model copy those suggestions onto short but audible clips.
# The downstream tutor LLM—not STT—decides whether literal speech is an answer,
# complaint, repeat request, or unrelated phrase.
GEMINI_RESPONSE_CONTEXT = (
    "Reply with only the exact words audibly spoken in this recording. "
    "Do not answer the lesson question, infer, complete, paraphrase, or invent words."
)

NUMERACY_CONTEXT_LABELS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("naira", "kobo", "money", "price", "prices", "cost", "costs", "pay", "paid", "spend", "spent", "change", "fare", "budget"), "naira"),
    (("sweet", "sweets", "candy", "candies"), "sweets"),
    (("finger", "fingers"), "fingers"),
    (("pure water", "water sachet", "water sachets"), "pure water"),
    (("groundnut", "groundnuts"), "groundnuts"),
    (("mango", "mangoes"), "mangoes"),
    (("orange", "oranges"), "oranges"),
    (("biscuit", "biscuits"), "biscuits"),
    (("plantain", "plantains"), "plantains"),
    (("tomato", "tomatoes"), "tomatoes"),
    (("pepper", "peppers"), "peppers"),
    (("notebook", "notebooks", "exercise book", "exercise books", "book", "books"), "books"),
    (("egg", "eggs"), "eggs"),
    (("bread",), "bread"),
    (("garri",), "garri"),
    (("rice",), "rice"),
    (("oil",), "oil"),
    (("coin", "coins"), "coins"),
    (("bag", "bags"), "bags"),
    (("tray", "trays"), "trays"),
)


def _context_sections(context: str) -> tuple[str, str]:
    """Return the exact tutor turn first and curriculum metadata second."""
    raw = " ".join(str(context or "").split())
    marker = "Exact recent tutor prompt:"
    if marker in raw:
        metadata, exact = raw.split(marker, 1)
        return _plain_text(exact), _plain_text(metadata)
    return _plain_text(raw), ""


def _contains_context_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text))


def _numeracy_context_label(context: str) -> str:
    exact, metadata = _context_sections(context)
    for source in (exact, metadata):
        # A person noun alone is not a lesson topic. In particular, the
        # onboarding greeting calls Sabi a "learning friend"; treating that
        # as fair-sharing context incorrectly biases the learner-name turn.
        # Require an actual sharing/grouping cue before adding this label.
        if any(
            cue in source
            for cue in (
                "share", "shared", "sharing", "equally", "equal groups",
                "each get", "each person gets", "between them",
            )
        ):
            return "fair sharing"
        for phrases, label in NUMERACY_CONTEXT_LABELS:
            if any(_contains_context_phrase(source, phrase) for phrase in phrases):
                return label
        if any(
            cue in source
            for cue in (
                "what number", "which number", "count", "comes after", "comes before",
                "bigger", "smaller", "plus", "minus", "times", "divide", "division",
                "addition", "subtraction", "multiplication",
            )
        ):
            return "numbers"
    return ""


def _literacy_context_label(context: str) -> str:
    exact, metadata = _context_sections(context)
    source = f"{exact} {metadata}".strip()
    if "environmental sound" in source or ("noise" in source and "sound" in source):
        return "environmental and speech sounds"
    if any(cue in source for cue in ("beginning sound", "first sound", "sound starts", "sound comes first", "at the start")):
        return "beginning sounds"
    if any(cue in source for cue in ("ending sound", "last sound", "sound at the end", "ends with")):
        return "ending sounds"
    if "rhyme" in source or "rhyming" in source:
        return "rhyming words"
    if "syllable" in source or "word parts" in source:
        return "syllables"
    if any(cue in source for cue in ("blend", "sounds make", "put it together")):
        return "blended sounds and words"
    if any(cue in source for cue in ("segment", "breaking words", "break the word")):
        return "segmented sounds"
    if any(cue in source for cue in ("deleting", "delete the", "without the first", "without the last")):
        return "sound deletion"
    if any(cue in source for cue in ("substitution", "changing the sound", "change the first", "change the last", "change the middle")):
        return "sound substitution"
    if any(cue in source for cue in ("letter sound", "letter s", "letters make", "spell a short word")):
        return "letter sounds and spoken words"
    if any(cue in source for cue in ("story", "what did", "who ran", "retell", "main idea", "comprehension")):
        return "story comprehension"
    if any(cue in source for cue in ("sentence", "grammar", "tense", "adjective", "comparative", "superlative")):
        return "spoken sentences"
    if any(cue in source for cue in ("vocabulary", "body parts", "family", "community", "market words", "animals", "weather", "nature")):
        return "spoken vocabulary"
    if _expects_literacy_sound_answer(context):
        return "spoken sounds"
    if _expects_literacy_word_answer(context):
        return "spoken words"
    return ""


def _curriculum_course(context: str, mode: str) -> str:
    normalized = _plain_text(context)
    if "course=literacy" in normalized or str(mode or "").lower() == "literacy":
        return "literacy"
    if "course=numeracy" in normalized or _expects_number(context):
        return "numeracy"
    if any(cue in normalized for cue in ("phonemic", "phonics", "rhyme", "syllable", "letter sound", "story comprehension")):
        return "literacy"
    return "numeracy"


def build_gemini_curriculum_prompt(context: str, mode: str = "general") -> tuple[str, str, str]:
    """Build the tagged prompt, mentioning names only on actual name turns."""
    course = _curriculum_course(context, mode)
    label = _literacy_context_label(context) if course == "literacy" else _numeracy_context_label(context)
    global_prompt = os.getenv(
        "SABI_GEMINI_STT_GLOBAL_PROMPT",
        "A Nigerian child on a noisy 8kHz phone call",
    ).strip()
    lesson = f"a {course} lesson" + (f" in {label}" if label else "")
    activity = (
        f"is saying their name, introducing themselves and walking through {lesson}"
        if _expects_name(context)
        else f"is walking through {lesson}"
    )
    prompt = (
        f"{global_prompt} {activity}. "
        f"{GEMINI_RESPONSE_CONTEXT}"
    ).strip()
    return prompt, course, label


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


def _consensus_key(text: str, *, numeric_context: bool) -> tuple[str, int | None]:
    """Return a conservative agreement key for two independent transcripts.

    On a numeric-answer turn the spoken number is the semantic answer. Object
    nouns are deliberately excluded from agreement, so ``two mangoes`` and
    ``two apples`` agree on the value two without teaching the STT system the
    expected answer. On every other turn both engines must return the same
    normalized words.
    """
    normalized = _plain_text(text)
    if not normalized:
        return "", None
    if numeric_context:
        try:
            from answer_matcher import extract_number

            number = extract_number(normalized)
        except Exception:
            number = None
        if number is not None:
            return f"number:{int(number)}", int(number)
    return f"text:{normalized}", None


def _numeric_candidates(text: str) -> list[int]:
    """Return distinct complete numeric values without guessing a final answer."""
    try:
        from numeric_grading import extract_numbers

        return list(dict.fromkeys(int(value) for value in extract_numbers(text)))
    except Exception:
        return []


def _segment_value(segment, name: str):
    if isinstance(segment, dict):
        return segment.get(name)
    return getattr(segment, name, None)


def _rounded_mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _whisper_diagnostics(segments) -> dict:
    """Preserve raw Whisper quality signals instead of inventing confidence."""
    rows = list(segments or [])
    logprobs: list[float] = []
    no_speech: list[float] = []
    compression: list[float] = []
    word_probabilities: list[float] = []
    for segment in rows:
        value = _segment_value(segment, "avg_logprob")
        if value is not None:
            logprobs.append(float(value))
        value = _segment_value(segment, "no_speech_prob")
        if value is not None:
            no_speech.append(float(value))
        value = _segment_value(segment, "compression_ratio")
        if value is not None:
            compression.append(float(value))
        for word in _segment_value(segment, "words") or []:
            probability = _segment_value(word, "probability")
            if probability is not None:
                word_probabilities.append(float(probability))
    return {
        "segment_count": len(rows),
        "avg_logprob": _rounded_mean(logprobs),
        "max_no_speech_prob": round(max(no_speech), 4) if no_speech else None,
        "max_compression_ratio": round(max(compression), 4) if compression else None,
        "min_word_probability": (
            round(min(word_probabilities), 4) if word_probabilities else None
        ),
        "mean_word_probability": _rounded_mean(word_probabilities),
    }


def _numeric_vote_summary(result: dict | None, error: Exception | None = None) -> dict:
    """Build an auditable vote without treating a label as probability."""
    if error is not None:
        return {
            "status": "timeout" if isinstance(error, TimeoutError) else "error",
            "error": f"{error.__class__.__name__}: {_safe_error_text(error)}",
            "numeric_candidates": [],
            "single_numeric_value": None,
        }
    payload = dict(result or {})
    text = " ".join(str(payload.get("text") or "").split())
    candidates = _numeric_candidates(text)
    status = "ok" if len(candidates) == 1 else "multiple_values" if candidates else "empty"
    return {
        "status": status,
        "text": text,
        "numeric_candidates": candidates,
        "single_numeric_value": candidates[0] if len(candidates) == 1 else None,
        "provider": str(payload.get("provider") or ""),
        "model": str(payload.get("model") or ""),
        "latency_seconds": round(float(payload.get("ensemble_latency_seconds") or 0), 3),
        "duration_seconds": round(float(payload.get("duration_seconds") or 0), 3),
        "diagnostics": dict(payload.get("diagnostics") or {}),
    }


def _ensemble_result_summary(result: dict | None, error: Exception | None = None) -> dict:
    """Persist useful comparison evidence without leaking request payloads."""
    if error is not None:
        return {
            "status": "error",
            "error": f"{error.__class__.__name__}: {_safe_error_text(error)}",
        }
    payload = dict(result or {})
    return {
        "status": "ok" if str(payload.get("text") or "").strip() else "empty",
        "text": str(payload.get("text") or ""),
        "confidence": round(float(payload.get("confidence") or 0), 3),
        "provider": str(payload.get("provider") or ""),
        "latency_seconds": round(float(payload.get("ensemble_latency_seconds") or 0), 3),
    }


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
        self._groq_http = httpx.Client(
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
        self._model_load_lock = threading.Lock()
        self._local_inference_lock = threading.Lock()
        # Reused across turns. When Groq and local Whisper agree, the caller
        # returns immediately; an already-running Gemini tie-break request may
        # finish harmlessly in the background instead of delaying the lesson.
        self._ensemble_executor = ThreadPoolExecutor(
            max_workers=max(3, int(os.getenv("SABI_STT_CONSENSUS_WORKERS", "3"))),
            thread_name_prefix="sabi-stt-consensus",
        )

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
        consensus_configured = not configured_providers.isdisjoint(PARALLEL_CONSENSUS_PROVIDERS)
        consensus_eager_load = os.getenv(
            "SABI_STT_CONSENSUS_EAGER_LOAD", "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if consensus_configured and consensus_eager_load:
            self._load_local_model(model_size, self._device)
        elif (
            not self._use_groq
            and configured_providers.isdisjoint(providers_without_eager_local_fallback)
        ):
            self._load_local_model(model_size, device)

    def _load_local_model(self, model_size: str | None = None, device: str | None = None) -> None:
        if hasattr(self, "_model"):
            return
        with self._model_load_lock:
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
        gemini_provider = provider in {"gemini", "gemini_first", "gemini_fallback"}
        consensus_provider = provider in PARALLEL_CONSENSUS_PROVIDERS
        gemini_bypasses_vad = (
            (gemini_provider or consensus_provider)
            and os.getenv("SABI_GEMINI_STT_BYPASS_VAD", "1").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        # VAD pre-gate: skip the STT model entirely on no-speech audio so a
        # crying baby / dead air can never be transcribed into a hallucination.
        # Returns empty text, which the caller already handles as "say that
        # again" — no invented words ever reach the tutor. Gemini is the one
        # deliberate exception: Naomi's live-call tests require every captured
        # Gemini turn to reach Gemini, because this local VAD rejected real,
        # short phone answers before the selected STT model could hear them.
        if not gemini_bypasses_vad and not self._has_speech(audio_path):
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
        if consensus_provider:
            result = self._transcribe_parallel_consensus(audio_path, mode=mode, context=context)
            result["vad_bypassed_for_gemini"] = gemini_bypasses_vad
            return result
        if gemini_provider:
            if self._gemini_key:
                try:
                    result = self._transcribe_gemini(audio_path, mode=mode, context=context)
                    result["vad_bypassed_for_gemini"] = gemini_bypasses_vad
                    return result
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
                            "gemini_prompt": self._gemini_prompt(context, mode=mode),
                            "gemini_prompt_mode": os.getenv("SABI_GEMINI_STT_PROMPT_MODE", "curriculum").strip().lower(),
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
                        "gemini_prompt": self._gemini_prompt(context, mode=mode),
                        "gemini_prompt_mode": os.getenv("SABI_GEMINI_STT_PROMPT_MODE", "curriculum").strip().lower(),
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

    @staticmethod
    def _timed_provider_call(callable_, *args, **kwargs) -> dict:
        started = time.monotonic()
        result = dict(callable_(*args, **kwargs) or {})
        result["ensemble_latency_seconds"] = round(time.monotonic() - started, 3)
        return result

    @staticmethod
    def _future_result(
        future: Future | None,
        *,
        timeout: float | None = None,
        timeout_label: str = "provider",
    ) -> tuple[dict | None, Exception | None]:
        if future is None:
            return None, RuntimeError("provider is not configured")
        try:
            return dict(future.result(timeout=timeout) or {}), None
        except FutureTimeoutError as exc:
            if future.done():
                return None, exc
            return None, TimeoutError(
                f"{timeout_label} exceeded the {timeout:g}s vote deadline"
            )
        except Exception as exc:
            return None, exc

    def _transcribe_parallel_consensus(
        self,
        audio_path: str,
        mode: str = "general",
        context: str = "",
    ) -> dict:
        """Race Groq and local Whisper, using Gemini only as the tie-breaker.

        Groq and local faster-whisper start at the same instant. If their
        literal words agree—or their numeric values agree on a numeric-answer
        turn—the consensus is authoritative and returns without waiting for
        Gemini. If they disagree, the already-running Gemini request decides.
        A failed tie-break fails closed into the existing repeat prompt.
        """
        started = time.monotonic()
        numeric_context = _expects_number(context)
        futures: dict[str, Future | None] = {
            "groq": None,
            "local_whisper": self._ensemble_executor.submit(
                self._timed_provider_call,
                self._transcribe_local,
                audio_path,
                mode,
                context,
            ),
            "gemini": None,
        }
        if self._groq_key:
            futures["groq"] = self._ensemble_executor.submit(
                self._timed_provider_call,
                self._transcribe_groq,
                audio_path,
                mode,
                context,
                False,
                False,
            )
        if self._gemini_key:
            futures["gemini"] = self._ensemble_executor.submit(
                self._timed_provider_call,
                self._transcribe_gemini,
                audio_path,
                mode,
                context,
            )

        vote_timeout = max(
            0.1,
            float(os.getenv("SABI_STT_LOCAL_VOTE_TIMEOUT", "5.0")),
        )
        groq, groq_error = self._future_result(
            futures["groq"],
            timeout=vote_timeout,
            timeout_label="Groq",
        )
        remaining_vote_seconds = max(
            0.1,
            vote_timeout - (time.monotonic() - started),
        )
        local, local_error = self._future_result(
            futures["local_whisper"],
            timeout=remaining_vote_seconds,
            timeout_label="local Whisper",
        )
        groq_key, groq_number = _consensus_key(
            str((groq or {}).get("text") or ""),
            numeric_context=numeric_context,
        )
        local_key, local_number = _consensus_key(
            str((local or {}).get("text") or ""),
            numeric_context=numeric_context,
        )
        alternatives = {
            "groq": _ensemble_result_summary(groq, groq_error),
            "local_whisper": _ensemble_result_summary(local, local_error),
        }

        if groq_key and groq_key == local_key:
            selected = dict(groq or local or {})
            selected.update({
                "provider": "groq_local_whisper_consensus",
                "confidence": max(
                    0.95,
                    float((groq or {}).get("confidence") or 0),
                    float((local or {}).get("confidence") or 0),
                ),
                "consensus": True,
                "consensus_key": groq_key,
                "consensus_numeric_value": groq_number if groq_number is not None else local_number,
                "selection_reason": "groq_and_local_whisper_agreed",
                "ensemble_results": alternatives,
                "ensemble_latency_seconds": round(time.monotonic() - started, 3),
            })
            gemini_future = futures.get("gemini")
            if gemini_future is not None and not gemini_future.done():
                gemini_future.cancel()
                alternatives["gemini"] = {"status": "not_needed"}
            elif gemini_future is not None:
                gemini, gemini_error = self._future_result(gemini_future)
                alternatives["gemini"] = _ensemble_result_summary(gemini, gemini_error)
            logger.info(
                "STT consensus selected key=%s groq=%r local=%r latency=%.2fs",
                groq_key,
                (groq or {}).get("text"),
                (local or {}).get("text"),
                time.monotonic() - started,
            )
            return selected

        gemini, gemini_error = self._future_result(futures.get("gemini"))
        alternatives["gemini"] = _ensemble_result_summary(gemini, gemini_error)
        if gemini and str(gemini.get("text") or "").strip():
            selected = dict(gemini)
            selected.update({
                "provider": "gemini_tiebreak",
                "consensus": False,
                "selection_reason": "groq_and_local_whisper_disagreed",
                "ensemble_results": alternatives,
                "ensemble_latency_seconds": round(time.monotonic() - started, 3),
            })
            logger.info(
                "STT Gemini tie-break selected groq=%r local=%r gemini=%r latency=%.2fs",
                (groq or {}).get("text"),
                (local or {}).get("text"),
                gemini.get("text"),
                time.monotonic() - started,
            )
            return selected

        logger.warning(
            "STT consensus unresolved groq=%r local=%r gemini_error=%s",
            (groq or {}).get("text"),
            (local or {}).get("text"),
            alternatives["gemini"].get("error") or alternatives["gemini"].get("status"),
        )
        return {
            "text": "",
            "confidence": 0.0,
            "language": "en",
            "duration_seconds": _audio_duration_seconds(audio_path),
            "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
            "provider": "parallel_consensus_unresolved",
            "consensus": False,
            "selection_reason": "no_two_engine_agreement_and_gemini_unavailable",
            "ensemble_results": alternatives,
            "ensemble_latency_seconds": round(time.monotonic() - started, 3),
        }

    def transcribe_numeric_sidecar(
        self,
        audio_path: str,
        *,
        decision_deadline_seconds: float = 1.5,
        collection_timeout_seconds: float = 30.0,
    ) -> dict:
        """Collect independent Groq/local numeric votes for Gemini Live.

        This is deliberately separate from ``parallel_consensus``: it sends no
        question or expected-answer context, never starts another Gemini
        request, never converts log-probability into a fake confidence, and
        abstains unless both engines return the same single numeric value.

        Shadow collection may wait beyond the live decision deadline so Sabi
        can measure CPU latency without delaying the conversation. The result
        records whether the same vote would have been eligible in a live gate.
        """
        started = time.monotonic()
        decision_deadline = max(0.1, float(decision_deadline_seconds))
        collection_timeout = max(decision_deadline, float(collection_timeout_seconds))
        futures: dict[str, Future | None] = {
            "groq": None,
            "local_whisper": self._ensemble_executor.submit(
                self._timed_provider_call,
                self._transcribe_local_numeric_vote,
                audio_path,
            ),
        }
        if self._groq_key:
            futures["groq"] = self._ensemble_executor.submit(
                self._timed_provider_call,
                self._transcribe_groq_numeric_vote,
                audio_path,
            )

        groq, groq_error = self._future_result(
            futures["groq"],
            timeout=collection_timeout,
            timeout_label="Groq numeric sidecar",
        )
        remaining = max(0.1, collection_timeout - (time.monotonic() - started))
        local, local_error = self._future_result(
            futures["local_whisper"],
            timeout=remaining,
            timeout_label="local Whisper numeric sidecar",
        )
        votes = {
            "groq": _numeric_vote_summary(groq, groq_error),
            "local_whisper": _numeric_vote_summary(local, local_error),
        }
        groq_value = votes["groq"].get("single_numeric_value")
        local_value = votes["local_whisper"].get("single_numeric_value")
        numeric_agreement = groq_value is not None and groq_value == local_value
        provider_latencies = [
            float(vote.get("latency_seconds") or 0)
            for vote in votes.values()
            if vote.get("status") == "ok"
        ]
        decision_latency = max(provider_latencies) if len(provider_latencies) == 2 else None
        decision_eligible = bool(
            numeric_agreement
            and decision_latency is not None
            and decision_latency <= decision_deadline
        )
        if decision_eligible:
            status = "agreed"
            selection_reason = "groq_and_local_whisper_agreed_within_deadline"
            hypothetical_action = "accept_consensus_number"
        elif numeric_agreement:
            status = "agreed_late"
            selection_reason = "groq_and_local_whisper_agreed_after_deadline"
            hypothetical_action = "neutral_repeat_deadline"
        elif groq_value is not None and local_value is not None:
            status = "disagreed"
            selection_reason = "groq_and_local_whisper_disagreed"
            hypothetical_action = "neutral_repeat_disagreement"
        else:
            status = "abstained"
            selection_reason = "one_or_both_engines_lacked_one_numeric_value"
            hypothetical_action = "neutral_repeat_abstention"
        return {
            "status": status,
            "mode": "shadow",
            "numeric_agreement": bool(numeric_agreement),
            "decision_eligible": decision_eligible,
            "consensus_numeric_value": int(groq_value) if numeric_agreement else None,
            "decision_deadline_seconds": round(decision_deadline, 3),
            "decision_latency_seconds": (
                round(decision_latency, 3) if decision_latency is not None else None
            ),
            "collection_latency_seconds": round(time.monotonic() - started, 3),
            "selection_reason": selection_reason,
            "hypothetical_action": hypothetical_action,
            "ensemble_results": votes,
        }

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

    def _gemini_prompt(self, context: str, mode: str = "general") -> str:
        """Build the universal curriculum-aware prompt without an answer hint."""
        lesson_prompt = os.getenv(
            "SABI_GEMINI_STT_LESSON_PROMPT",
            "A Nigerian child on a noisy 8kHz phone call is saying their name, "
            "introducing themselves and walking through a numeracy lesson. "
            "Reply with their responses",
        ).strip()
        prompt_mode = os.getenv("SABI_GEMINI_STT_PROMPT_MODE", "curriculum").strip().lower()
        if prompt_mode == "lesson_exact":
            return lesson_prompt
        prompt, _course, _label = build_gemini_curriculum_prompt(context, mode)
        return prompt

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
        _prompt_copy, prompt_course, prompt_label = build_gemini_curriculum_prompt(context, mode)
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
            "gemini_prompt_mode": os.getenv("SABI_GEMINI_STT_PROMPT_MODE", "curriculum").strip().lower(),
            "gemini_prompt": prompt,
            "gemini_prompt_course": prompt_course,
            "gemini_prompt_label": prompt_label,
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

    def _transcribe_groq(
        self,
        audio_path: str,
        mode: str = "general",
        context: str = "",
        allow_local_fallback: bool = True,
        allow_local_salvage: bool = True,
    ) -> dict:
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
            if (
                allow_local_salvage
                and str(mode or "").lower() == "literacy"
                and _is_suspect_literacy_feedback(text, context)
            ):
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
            if allow_local_salvage and _expects_number(context) and not _looks_number_like(text):
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
            if not allow_local_fallback:
                raise
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
            if not allow_local_fallback:
                raise
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
        with self._local_inference_lock:
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
