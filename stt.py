"""
Speech-to-Text using faster-whisper.
Self-hosted Whisper for Nigerian English transcription.

Optimizations for Nigerian English:
- initial_prompt bias with Nigerian vocabulary (naira, groundnuts, garri, etc.)
- Tuned VAD for phone-quality audio
"""

import logging
from faster_whisper import WhisperModel

logger = logging.getLogger("sabi.stt")

# Whisper prompt bias — providing domain-specific vocabulary in the initial_prompt
# biases the decoder toward recognizing these words correctly.
# This is the single biggest accuracy boost without fine-tuning.
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


class SpeechToText:
    def __init__(self, model_size: str = "large-v3", device: str = "cuda"):
        """
        Initialize Whisper STT.

        Args:
            model_size: Whisper model size. Options:
                - "tiny" (~1GB VRAM, fast, low accuracy)
                - "base" (~1GB VRAM)
                - "small" (~2GB VRAM)
                - "medium" (~5GB VRAM, good balance)
                - "large-v3" (~6GB VRAM, best accuracy for Nigerian English)
            device: "cuda" for GPU, "cpu" for CPU-only
        """
        logger.info(f"Loading Whisper {model_size} on {device}...")
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="float16" if device == "cuda" else "int8",
        )
        logger.info(f"Whisper {model_size} loaded.")

    def transcribe(self, audio_path: str) -> dict:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)

        Returns:
            dict with 'text' and 'confidence' keys
        """
        segments, info = self.model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            initial_prompt=NIGERIAN_ENGLISH_PROMPT,
            vad_filter=True,          # Voice activity detection — trim silence
            vad_parameters={
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 200,
            },
        )

        # Collect all segments
        full_text = ""
        total_confidence = 0.0
        segment_count = 0

        for segment in segments:
            full_text += segment.text
            # avg_logprob is negative; convert to 0-1 confidence
            confidence = min(1.0, max(0.0, 1.0 + segment.avg_logprob))
            total_confidence += confidence
            segment_count += 1

        avg_confidence = total_confidence / max(segment_count, 1)

        return {
            "text": full_text.strip(),
            "confidence": round(avg_confidence, 3),
            "language": info.language,
            "duration_seconds": round(info.duration, 1),
        }
