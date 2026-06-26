"""
Speech-to-Text for Sabi.
Primary: Groq Whisper API (~200ms, 28,800 sec/day free) if GROQ_API_KEY is set.
Fallback: Self-hosted faster-whisper (Whisper large-v3 on GPU, ~0.8-1.5s).

Optimizations for Nigerian English:
- initial_prompt bias with Nigerian vocabulary (naira, groundnuts, garri, etc.)
- Tuned VAD for phone-quality audio
"""

import io
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger("sabi.stt")

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
    "Sabi is teaching foundational literacy to children in Lagos, Nigeria over a phone call. "
    "The child may answer with very short sounds, single letters, syllables, rhymes, or simple words. "
    "Preserve short phonics answers exactly when possible. Important examples: m, mmm, s, sss, a, ah, t, p, n, "
    "cat, mat, hat, mango, moon, market, mama, ball, bat, syllable, rhyme, beginning sound, ending sound. "
    "The tutor may ask: what sound starts mango, do cat and mat rhyme, clap the syllables, blend c a t, say the sound. "
    "Do not force short sound answers into math words or market prices."
)


class SpeechToText:
    def __init__(self, model_size: str = "large-v3", device: str = "cuda"):
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

        if self._groq_key:
            self._use_groq = True
            logger.info("STT: Groq Whisper API (fast, ~200ms)")
        else:
            self._use_groq = False
            logger.info(f"STT: Loading local Whisper {model_size} on {device}...")
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
            )
            logger.info(f"STT: Local Whisper {model_size} loaded.")

    def transcribe(self, audio_path: str, mode: str = "general") -> dict:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)

        Returns:
            dict with 'text' and 'confidence' keys
        """
        if self._use_groq:
            return self._transcribe_groq(audio_path, mode=mode)
        return self._transcribe_local(audio_path, mode=mode)

    def _prompt_for_mode(self, mode: str) -> str:
        return LITERACY_ENGLISH_PROMPT if str(mode or "").lower() == "literacy" else NIGERIAN_ENGLISH_PROMPT

    def _transcribe_groq(self, audio_path: str, mode: str = "general") -> dict:
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
                    "prompt": self._prompt_for_mode(mode),
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

            return {
                "text": text,
                "confidence": confidence,
                "language": data.get("language", "en"),
                "duration_seconds": round(data.get("duration", 0.0), 1),
                "mode": "literacy" if str(mode or "").lower() == "literacy" else "general",
            }

        except Exception as e:
            logger.warning(f"Groq STT failed ({e}), falling back to local Whisper")
            # Lazy-load local model if not already loaded
            if not hasattr(self, "_model"):
                from faster_whisper import WhisperModel
                logger.info("Loading local Whisper large-v3 as fallback...")
                self._model = WhisperModel("large-v3", device="cuda", compute_type="float16")
            return self._transcribe_local(audio_path, mode=mode)

    def _transcribe_local(self, audio_path: str, mode: str = "general") -> dict:
        """Transcribe using self-hosted faster-whisper (GPU)."""
        segments, info = self._model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            initial_prompt=self._prompt_for_mode(mode),
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
        }
