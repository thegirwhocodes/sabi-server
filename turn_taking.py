"""Self-hosted conversational turn detection for Sabi phone calls.

ElevenLabs' managed agent sits an audio-control layer in front of ASR: voice
activity detection decides whether the input is speech, echo/background guards
reject audio that should not interrupt playback, and a learned endpoint model
decides whether a pause means the caller is finished.  This module recreates
that separation while keeping Asterisk, Sabi's curriculum runtime, and Gemini
STT under our control.

The two learned components are deliberately independent:

* Silero VAD v5 is already shipped by ``faster-whisper`` and supplies speech
  probabilities for the strict interruption gate and the permissive listening
  gate.
* Pipecat Smart Turn v3.2 is an open, audio-native endpoint classifier.  It is
  queried only after silence, so it does not add work to every 20 ms frame.

All model failures are explicit.  Interruptions fail closed (Sabi keeps
speaking); normal post-prompt listening fails open (a child is never silenced
because an optional guard failed); endpointing falls back to the existing
silence timeout.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


logger = logging.getLogger("sabi.turn_taking")

SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
MODEL_SAMPLE_RATE = 16000
SILERO_WINDOW_SAMPLES = 512

TURN_GATE_ENABLED = os.getenv("SABI_TURN_GATE_ENABLED", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
SMART_TURN_ENABLED = os.getenv("SABI_SMART_TURN_ENABLED", "1").strip().lower() in {
    "1", "true", "yes", "on",
}

INTERRUPTION_VAD_ONSET = float(os.getenv("SABI_INTERRUPTION_VAD_ONSET", "0.68"))
INTERRUPTION_MIN_SPEECH_MS = int(os.getenv("SABI_INTERRUPTION_MIN_SPEECH_MS", "320"))
INTERRUPTION_MIN_AUDIO_MS = int(os.getenv("SABI_INTERRUPTION_MIN_AUDIO_MS", "420"))
INTERRUPTION_ECHO_THRESHOLD = float(os.getenv("SABI_INTERRUPTION_ECHO_THRESHOLD", "0.62"))
INTERRUPTION_PREFILTER_RMS = int(os.getenv("SABI_INTERRUPTION_PREFILTER_RMS", "180"))
INTERRUPTION_EVAL_INTERVAL_MS = int(os.getenv("SABI_INTERRUPTION_EVAL_INTERVAL_MS", "160"))
INTERRUPTION_CANDIDATE_RESET_MS = int(os.getenv("SABI_INTERRUPTION_CANDIDATE_RESET_MS", "420"))

LISTENING_VAD_ONSET = float(os.getenv("SABI_LISTENING_VAD_ONSET", "0.38"))
LISTENING_MIN_SPEECH_MS = int(os.getenv("SABI_LISTENING_MIN_SPEECH_MS", "64"))

SMART_TURN_COMPLETE_THRESHOLD = float(os.getenv("SABI_SMART_TURN_COMPLETE_THRESHOLD", "0.50"))
SMART_TURN_MIN_AUDIO_MS = int(os.getenv("SABI_SMART_TURN_MIN_AUDIO_MS", "650"))
SMART_TURN_MAX_AUDIO_SECONDS = int(os.getenv("SABI_SMART_TURN_MAX_AUDIO_SECONDS", "8"))
SMART_TURN_MAX_EXTENSION_MS = int(os.getenv("SABI_SMART_TURN_MAX_EXTENSION_MS", "2400"))
SMART_TURN_MODEL_PATH = Path(
    os.getenv("SABI_SMART_TURN_MODEL", "/app/models/smart-turn-v3.2-cpu.onnx")
)


@dataclass(frozen=True)
class SpeechEvidence:
    accepted: bool
    duration_ms: int
    max_probability: float
    mean_probability: float
    longest_speech_ms: int
    speech_ratio: float
    reason: str

    def log_fields(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InterruptionDecision:
    accepted: bool
    reason: str
    speech: SpeechEvidence
    echo_similarity: float

    def log_fields(self) -> dict:
        fields = asdict(self)
        fields["speech"] = self.speech.log_fields()
        return fields


@dataclass(frozen=True)
class EndpointDecision:
    available: bool
    complete: bool | None
    probability: float | None
    reason: str

    def log_fields(self) -> dict:
        return asdict(self)


def _duration_ms(pcm_8k: bytes) -> int:
    return int(len(pcm_8k) * 1000 / (SAMPLE_RATE * SAMPLE_WIDTH))


def _pcm8k_to_float16k(pcm_8k: bytes):
    """Convert 8 kHz signed-linear PCM to normalized 16 kHz float32."""
    import numpy as np

    if not pcm_8k:
        return np.zeros(0, dtype=np.float32)
    even_pcm = pcm_8k[: len(pcm_8k) - (len(pcm_8k) % SAMPLE_WIDTH)]
    samples = np.frombuffer(even_pcm, dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 1:
        return np.repeat(samples, 2)
    # The model rate is exactly 2x the telephony rate. Linear interpolation is
    # deterministic and avoids Python's removed-in-3.13 ``audioop`` module.
    upsampled = np.empty(samples.size * 2, dtype=np.float32)
    upsampled[::2] = samples
    upsampled[1:-1:2] = (samples[:-1] + samples[1:]) * 0.5
    upsampled[-1] = samples[-1]
    return upsampled


def _longest_true_run(values) -> int:
    best = current = 0
    for value in values:
        if bool(value):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


class ManagedTurnDetector:
    """Lazy, shared learned detector used by every realtime call."""

    def __init__(self) -> None:
        self._silero_model = None
        self._endpoint_session = None
        self._feature_extractor = None
        # The underlying ONNX sessions are fast but share internal state in a
        # few runtime versions.  Serialize model calls across concurrent calls.
        self._silero_lock = threading.Lock()
        self._endpoint_lock = threading.Lock()

    def _get_silero_model(self):
        if self._silero_model is None:
            from faster_whisper.vad import get_vad_model

            self._silero_model = get_vad_model()
        return self._silero_model

    def speech_evidence(
        self,
        pcm_8k: bytes,
        *,
        onset: float,
        min_speech_ms: int,
    ) -> SpeechEvidence:
        """Return Silero speech evidence for a complete candidate buffer."""
        import numpy as np

        duration_ms = _duration_ms(pcm_8k)
        if not TURN_GATE_ENABLED:
            return SpeechEvidence(True, duration_ms, 1.0, 1.0, duration_ms, 1.0, "gate_disabled")
        if not pcm_8k:
            return SpeechEvidence(False, 0, 0.0, 0.0, 0, 0.0, "empty_audio")

        try:
            audio = _pcm8k_to_float16k(pcm_8k)
            remainder = audio.size % SILERO_WINDOW_SAMPLES
            if remainder:
                audio = np.pad(audio, (0, SILERO_WINDOW_SAMPLES - remainder))
            if audio.size < SILERO_WINDOW_SAMPLES:
                audio = np.pad(audio, (0, SILERO_WINDOW_SAMPLES - audio.size))

            with self._silero_lock:
                probabilities = self._get_silero_model()(audio.reshape(1, -1)).squeeze(0)
            probabilities = np.asarray(probabilities, dtype=np.float32).reshape(-1)
            speech_mask = probabilities >= onset
            longest_windows = _longest_true_run(speech_mask)
            window_ms = int(SILERO_WINDOW_SAMPLES * 1000 / MODEL_SAMPLE_RATE)
            longest_speech_ms = min(duration_ms, longest_windows * window_ms)
            speech_ratio = float(np.count_nonzero(speech_mask) / max(1, probabilities.size))
            accepted = longest_speech_ms >= min_speech_ms
            return SpeechEvidence(
                accepted=accepted,
                duration_ms=duration_ms,
                max_probability=round(float(probabilities.max(initial=0.0)), 4),
                mean_probability=round(float(probabilities.mean()) if probabilities.size else 0.0, 4),
                longest_speech_ms=longest_speech_ms,
                speech_ratio=round(speech_ratio, 4),
                reason="speech" if accepted else "insufficient_learned_speech",
            )
        except Exception as exc:
            logger.exception("Silero turn gate failed")
            return SpeechEvidence(
                False,
                duration_ms,
                0.0,
                0.0,
                0,
                0.0,
                f"detector_error:{type(exc).__name__}",
            )

    def listening_speech(self, pcm_8k: bytes) -> SpeechEvidence:
        """Permissive post-prompt speech test that keeps short child sounds."""
        return self.speech_evidence(
            pcm_8k,
            onset=LISTENING_VAD_ONSET,
            min_speech_ms=LISTENING_MIN_SPEECH_MS,
        )

    @staticmethod
    def echo_similarity(inbound_pcm: bytes, outbound_reference_pcm: bytes) -> float:
        """Estimate whether inbound audio is delayed leakage of Sabi's speech.

        The outbound reference covers the most recently transmitted audio.  A
        normalized sliding correlation is calculated after aggressive
        downsampling; this tolerates delay and level changes without assuming a
        fixed handset echo path.
        """
        import numpy as np

        if _duration_ms(inbound_pcm) < 160 or not outbound_reference_pcm:
            return 0.0
        inbound = np.frombuffer(inbound_pcm[: len(inbound_pcm) // 2 * 2], dtype="<i2").astype(np.float32)
        outbound = np.frombuffer(
            outbound_reference_pcm[: len(outbound_reference_pcm) // 2 * 2], dtype="<i2"
        ).astype(np.float32)
        # Downsampling makes the sliding comparison inexpensive and retains the
        # speech envelope that handset echo preserves most reliably.
        inbound = inbound[::4]
        outbound = outbound[::4]
        if inbound.size < 32 or outbound.size < inbound.size:
            return 0.0
        inbound = inbound - inbound.mean()
        inbound_norm = float(np.linalg.norm(inbound))
        if inbound_norm < 1e-6:
            return 0.0
        correlations = np.correlate(outbound - outbound.mean(), inbound, mode="valid")
        squared = (outbound - outbound.mean()) ** 2
        cumulative = np.concatenate((np.zeros(1, dtype=np.float64), np.cumsum(squared, dtype=np.float64)))
        window_energy = cumulative[inbound.size :] - cumulative[: -inbound.size]
        denominators = np.sqrt(np.maximum(window_energy, 1e-9)) * inbound_norm
        similarities = np.abs(correlations) / np.maximum(denominators, 1e-9)
        return round(float(np.clip(similarities.max(initial=0.0), 0.0, 1.0)), 4)

    def evaluate_interruption(
        self,
        candidate_pcm: bytes,
        outbound_reference_pcm: bytes,
    ) -> InterruptionDecision:
        """Strict gate used only while Sabi is speaking."""
        duration_ms = _duration_ms(candidate_pcm)
        if duration_ms < INTERRUPTION_MIN_AUDIO_MS:
            speech = SpeechEvidence(
                False,
                duration_ms,
                0.0,
                0.0,
                0,
                0.0,
                "candidate_too_short",
            )
            return InterruptionDecision(False, "candidate_too_short", speech, 0.0)

        speech = self.speech_evidence(
            candidate_pcm,
            onset=INTERRUPTION_VAD_ONSET,
            min_speech_ms=INTERRUPTION_MIN_SPEECH_MS,
        )
        if not speech.accepted:
            return InterruptionDecision(False, speech.reason, speech, 0.0)

        similarity = self.echo_similarity(candidate_pcm, outbound_reference_pcm)
        if similarity >= INTERRUPTION_ECHO_THRESHOLD:
            return InterruptionDecision(False, "acoustic_echo", speech, similarity)
        return InterruptionDecision(True, "intentional_foreground_speech", speech, similarity)

    def _get_endpoint_runtime(self):
        if self._endpoint_session is None or self._feature_extractor is None:
            if not SMART_TURN_MODEL_PATH.is_file():
                raise FileNotFoundError(str(SMART_TURN_MODEL_PATH))
            import onnxruntime as ort
            from faster_whisper.feature_extractor import FeatureExtractor

            options = ort.SessionOptions()
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.inter_op_num_threads = 1
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._endpoint_session = ort.InferenceSession(
                str(SMART_TURN_MODEL_PATH),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            self._feature_extractor = FeatureExtractor(chunk_length=SMART_TURN_MAX_AUDIO_SECONDS)
        return self._endpoint_session, self._feature_extractor

    def endpoint_complete(self, pcm_8k: bytes) -> EndpointDecision:
        """Ask Smart Turn whether the caller's pause is a completed turn."""
        if not SMART_TURN_ENABLED:
            return EndpointDecision(False, None, None, "smart_turn_disabled")
        if _duration_ms(pcm_8k) < SMART_TURN_MIN_AUDIO_MS:
            # Smart Turn's authors explicitly discourage very short inputs.
            # Single phonemes and short numeric answers use silence endpointing.
            return EndpointDecision(False, None, None, "audio_too_short_for_smart_turn")

        try:
            import numpy as np

            audio = _pcm8k_to_float16k(pcm_8k)
            target_samples = SMART_TURN_MAX_AUDIO_SECONDS * MODEL_SAMPLE_RATE
            if audio.size > target_samples:
                audio = audio[-target_samples:]
            elif audio.size < target_samples:
                audio = np.pad(audio, (target_samples - audio.size, 0))
            # Match the reference inference path: left-pad to eight seconds,
            # then normalize the entire array before Whisper feature extraction.
            audio = (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)

            with self._endpoint_lock:
                session, extractor = self._get_endpoint_runtime()
                features = extractor(audio, padding=160, chunk_length=SMART_TURN_MAX_AUDIO_SECONDS)
                features = np.asarray(features[:, :800], dtype=np.float32)[None, ...]
                output = session.run(None, {"input_features": features})[0]
            probability = float(np.asarray(output).reshape(-1)[0])
            return EndpointDecision(
                True,
                probability >= SMART_TURN_COMPLETE_THRESHOLD,
                round(probability, 4),
                "model_prediction",
            )
        except Exception as exc:
            logger.exception("Smart Turn endpoint detector failed")
            return EndpointDecision(False, None, None, f"detector_error:{type(exc).__name__}")


@lru_cache(maxsize=1)
def get_managed_turn_detector() -> ManagedTurnDetector:
    return ManagedTurnDetector()
