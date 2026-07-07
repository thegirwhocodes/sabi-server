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


WORD_ANSWER_CUES = (
    "another word",
    "say a word",
    "word that rhymes",
    "what else rhymes",
    "think of a word",
    "ends with",
)
SUSPECT_LITERACY_FEEDBACK = {"correct", "right", "wrong", "thank you", "thanks"}
LITERACY_WORDS = {
    "cat", "mat", "hat", "rat", "sat", "fat", "pat", "bat",
    "dog", "log", "fog", "hog", "big", "dig", "pig",
}

WHISPER_CLI_PROVIDERS = {"whisper_cli", "openai_whisper", "openai-whisper", "cli_whisper"}


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


def _is_suspect_literacy_feedback(text: str, context: str) -> bool:
    return _expects_literacy_word_answer(context) and _plain_text(text) in SUSPECT_LITERACY_FEEDBACK


def _is_short_literacy_word(text: str) -> bool:
    normalized = _plain_text(text)
    return normalized in LITERACY_WORDS or (normalized.isalpha() and 1 <= len(normalized) <= 5)


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
        env_provider = os.getenv("SABI_STT_PROVIDER", "auto")
        self._provider = (provider or env_provider).strip().lower() or "auto"
        env_literacy_provider = os.getenv("SABI_LITERACY_STT_PROVIDER", self._provider)
        self._literacy_provider = (
            literacy_provider or env_literacy_provider
        ).strip().lower() or self._provider
        self._model_size = os.getenv("SABI_LOCAL_WHISPER_MODEL_SIZE", model_size).strip() or model_size
        self._device = os.getenv("SABI_LOCAL_WHISPER_DEVICE", device).strip() or device

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
        if (
            not self._use_groq
            and not (self._intron_key and self._provider in {"intron", "intron_first"})
            and self._provider not in WHISPER_CLI_PROVIDERS
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

    def transcribe(self, audio_path: str, mode: str = "general", context: str = "") -> dict:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)

        Returns:
            dict with 'text' and 'confidence' keys
        """
        provider = self._provider_for_mode(mode)
        primary_error: Exception | None = None
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
            return self._transcribe_groq(audio_path, mode=mode, context=context)
        try:
            return self._transcribe_local(audio_path, mode=mode, context=context)
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
        segments, info = self._model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            initial_prompt=self._prompt_for_mode(mode, context=context),
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
