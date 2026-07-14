"""Optional, fail-open DeepFilterNet v3 front end for Sabi phone STT."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


LOGGER = logging.getLogger("sabi.audio_cleaner")
_MODEL_LOCK = threading.Lock()
_MODEL = None
_DF_STATE = None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_deepfilter():
    global _MODEL, _DF_STATE
    with _MODEL_LOCK:
        if _MODEL is None or _DF_STATE is None:
            from df.enhance import init_df

            LOGGER.info("Loading DeepFilterNet v3 speech-enhancement model on CPU")
            _MODEL, _DF_STATE, _ = init_df(
                model_base_dir="DeepFilterNet3",
                post_filter=_truthy(os.getenv("SABI_STT_DENOISE_POSTFILTER", "0")),
                log_level="ERROR",
            )
        return _MODEL, _DF_STATE


class AudioCleaner:
    """Prepare one STT clip, deleting temporary enhanced audio afterwards.

    Disabled by default. Any import, model, decode, or enhancement failure
    returns the original clip so noise suppression can never take calls down.
    """

    def __init__(self, *, enabled: bool = False, backend: str = "deepfilternet"):
        self.enabled = bool(enabled)
        self.backend = str(backend or "deepfilternet").strip().lower()

    @classmethod
    def from_env(cls) -> "AudioCleaner":
        return cls(
            enabled=_truthy(os.getenv("SABI_STT_DENOISE", "0")),
            backend=os.getenv("SABI_STT_DENOISE_BACKEND", "deepfilternet"),
        )

    def _enhance_deepfilter(self, source: str, destination: str) -> None:
        from df.enhance import enhance, load_audio, save_audio

        model, state = _load_deepfilter()
        audio, _ = load_audio(source, sr=state.sr())
        # The PyTorch model/state pair is shared by both production and canary
        # STT objects. Serialize inference because its streaming state is not
        # documented as thread-safe.
        with _MODEL_LOCK:
            enhanced = enhance(model, state, audio, pad=True)
        save_audio(destination, enhanced, state.sr())

    @contextmanager
    def prepare(self, audio_path: str) -> Iterator[tuple[str, dict]]:
        metadata = {
            "enabled": self.enabled,
            "backend": self.backend if self.enabled else "off",
            "applied": False,
            "latency_ms": 0,
        }
        if not self.enabled:
            yield audio_path, metadata
            return

        temporary_path = ""
        start = time.monotonic()
        try:
            if self.backend != "deepfilternet":
                raise ValueError(f"unsupported audio cleaner backend: {self.backend}")
            with tempfile.NamedTemporaryFile(prefix="sabi-clean-", suffix=".wav", delete=False) as handle:
                temporary_path = handle.name
            self._enhance_deepfilter(audio_path, temporary_path)
            if not Path(temporary_path).is_file() or Path(temporary_path).stat().st_size <= 44:
                raise RuntimeError("audio cleaner produced no usable WAV")
            metadata["applied"] = True
            metadata["latency_ms"] = int((time.monotonic() - start) * 1000)
            yield temporary_path, metadata
        except Exception as exc:  # fail-open is required for the live call path
            metadata["error"] = f"{exc.__class__.__name__}: {str(exc)[:180]}"
            metadata["latency_ms"] = int((time.monotonic() - start) * 1000)
            LOGGER.exception("STT denoising failed; using original audio")
            yield audio_path, metadata
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Could not remove temporary denoised file %s", temporary_path)
