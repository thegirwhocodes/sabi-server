"""Shadow numeric-STT sidecar for Sabi's Gemini Live phone lane.

Gemini Live owns the conversation: voice activity detection, turn boundaries,
barge-in and speech. It also mis-renders short Nigerian 8 kHz answers — the
archived Oluremi/Gideon replays showed "thirty" transcribed as "Tati" while the
model's own reasoning still extracted 30.

This module runs Groq Whisper and local faster-whisper over the *same* canonical
clip after a learner turn closes, records what each engine heard, and writes an
auditable record. It is deliberately Phase 1 of
``docs/PARALLEL_STT_FOR_GEMINI_LIVE_RESEARCH_2026-08-07.md``:

* shadow only — nothing here can change Sabi's reply, grade, or timing;
* numeric turns only — the item's answer contract must expect a number;
* votes carry no question, operands or expected answer, so recognition cannot be
  biased toward the answer we are trying to verify;
* a result that lands after its turn is no longer current is kept for the audit
  and marked stale, never applied.

Phase 3 (letting agreement grade the answer) stays off until the labelled
Nigerian PSTN bake-off clears the precision gate.
"""

from __future__ import annotations

import json
import logging
import re
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


logger = logging.getLogger("sabi.numeric_sidecar")

SIDECAR_VERSION = "shadow-1"


def _words(text: str) -> list[str]:
    """Lowercase word tokens, punctuation dropped, for comparing transcripts."""
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _same_words(left: str, right: str) -> bool | None:
    """Whether two transcripts of the same audio heard the same thing.

    One containing the other counts as agreement: the re-hearers return "thirty"
    where Gemini returns "thirty naira", and that is the same hearing, not a
    mis-hear. A word one side has and the other lacks - "Oluwaseun" against
    "Louis Sean" - is a real disagreement. Punctuation and casing are ignored.

    None when either side has no words, because silence is an abstention rather
    than a disagreement.
    """
    a, b = set(_words(left)), set(_words(right))
    if not a or not b:
        return None
    return a <= b or b <= a



def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def sidecar_enabled() -> bool:
    return _env_flag("SABI_NUMERIC_SIDECAR_ENABLED", "1")


def sidecar_mode() -> str:
    """Only ``shadow`` is implemented; anything else is refused, not guessed."""
    mode = os.getenv("SABI_NUMERIC_SIDECAR_MODE", "shadow").strip().lower() or "shadow"
    if mode != "shadow":
        logger.warning(
            "Numeric sidecar mode %r is not implemented; staying in shadow mode. "
            "Grading on consensus requires the Phase 2 bake-off precision gate.",
            mode,
        )
    return "shadow"


def decision_deadline_seconds() -> float:
    return max(0.2, float(os.getenv("SABI_NUMERIC_SIDECAR_DEADLINE_SECONDS", "1.5")))


def collection_timeout_seconds() -> float:
    return max(
        decision_deadline_seconds(),
        float(os.getenv("SABI_NUMERIC_SIDECAR_COLLECTION_TIMEOUT_SECONDS", "30")),
    )


def max_pending_jobs() -> int:
    return max(1, int(os.getenv("SABI_NUMERIC_SIDECAR_MAX_PENDING", "4")))


def record_dir(audio_dir: Path | str | None = None) -> Path:
    base = Path(
        os.getenv("SABI_NUMERIC_SIDECAR_DIR", "")
        or Path(audio_dir or os.getenv("SABI_SHARED_AUDIO_DIR", "/shared/audio"))
        / "numeric_sidecar"
    )
    return base


_executor_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


def _shared_executor() -> ThreadPoolExecutor:
    """One small pool for every call: local Whisper is the scarce resource."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, int(os.getenv("SABI_NUMERIC_SIDECAR_WORKERS", "2"))),
                thread_name_prefix="sabi-numeric-sidecar",
            )
        return _executor


def expected_number_from_problem(problem: Any) -> int | None:
    """Return the item's expected value only when it is genuinely numeric.

    Accepts either a ``NumeracyProblem`` (``expected``) or a grade-tool result
    (``expected_answer``); anything without a whole-number answer contract
    returns None so the sidecar simply skips the turn.
    """
    if problem is None:
        return None
    if isinstance(problem, dict):
        expected = problem.get("expected", problem.get("expected_answer"))
    else:
        expected = getattr(problem, "expected", getattr(problem, "expected_answer", None))
    try:
        return int(expected)
    except (TypeError, ValueError):
        return None


class NumericSidecar:
    """Per-call shadow collector. Every method is safe to call on any turn."""

    def __init__(
        self,
        call_uuid: str,
        stt: Any,
        *,
        audio_dir: Path | str | None = None,
        deadline_seconds: float | None = None,
        collection_seconds: float | None = None,
    ) -> None:
        self.call_uuid = str(call_uuid)
        self.stt = stt
        self.mode = sidecar_mode()
        self.enabled = bool(sidecar_enabled() and stt is not None)
        self.deadline_seconds = (
            decision_deadline_seconds() if deadline_seconds is None else float(deadline_seconds)
        )
        self.collection_seconds = (
            collection_timeout_seconds() if collection_seconds is None else float(collection_seconds)
        )
        self.record_path = record_dir(audio_dir) / f"{self.call_uuid}.jsonl"
        self._current_turn = -1
        self._pending = 0
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []
        self._corrections: list[dict[str, Any]] = []
        self._dropped_capacity = 0

    # -- turn lifecycle -------------------------------------------------

    def note_current_turn(self, turn_index: int) -> None:
        """Track which turn is live so late results can be marked stale."""
        with self._lock:
            self._current_turn = int(turn_index)

    def submit(
        self,
        *,
        turn_index: int,
        audio_path: Path | str | None,
        gemini_text: str = "",
        expected_answer: int | None = None,
        problem_id: str = "",
        attempt: int = 0,
        prompt_level: str = "",
    ) -> bool:
        """Queue one shadow comparison. Returns False when it is skipped.

        Skipping is normal and must stay silent to the learner: a non-numeric
        turn, a missing recording, a disabled sidecar, or a full queue.
        """
        # Checking whether Sabi HEARD the child correctly needs no answer key:
        # it is Gemini's own transcript against the two re-hearers. The expected
        # answer only decides whether the number was right, which is a separate
        # question, so it is optional here.
        if not self.enabled or not audio_path:
            return False
        path = Path(audio_path)
        if not path.exists() or path.stat().st_size <= 44:
            return False
        with self._lock:
            self._current_turn = max(self._current_turn, int(turn_index))
            if self._pending >= max_pending_jobs():
                self._dropped_capacity += 1
                logger.warning(
                    "Numeric sidecar dropped turn uuid=%s turn=%s: %s jobs already pending",
                    self.call_uuid,
                    turn_index,
                    self._pending,
                )
                return False
            self._pending += 1
        job = {
            "turn_index": int(turn_index),
            "audio_path": str(path),
            "gemini_text": " ".join(str(gemini_text or "").split()),
            "expected_answer": None if expected_answer is None else int(expected_answer),
            "problem_id": str(problem_id or ""),
            "attempt": int(attempt or 0),
            "prompt_level": str(prompt_level or ""),
            "queued_at": time.time(),
        }
        try:
            _shared_executor().submit(self._run_job, job)
        except Exception as exc:  # pool shut down mid-call
            with self._lock:
                self._pending -= 1
            logger.warning("Numeric sidecar could not queue turn %s: %s", turn_index, exc)
            return False
        return True

    # -- worker ---------------------------------------------------------

    def _run_job(self, job: dict[str, Any]) -> None:
        started = time.monotonic()
        try:
            result = self.stt.transcribe_numeric_sidecar(
                job["audio_path"],
                decision_deadline_seconds=self.deadline_seconds,
                collection_timeout_seconds=self.collection_seconds,
            )
        except Exception as exc:
            result = {
                "status": "error",
                "numeric_agreement": False,
                "decision_eligible": False,
                "consensus_numeric_value": None,
                "selection_reason": f"{exc.__class__.__name__}: {exc}",
                "hypothetical_action": "neutral_repeat_error",
                "ensemble_results": {},
            }
        finally:
            with self._lock:
                self._pending = max(0, self._pending - 1)
                current_turn = self._current_turn
        record = self._build_record(job, result, current_turn, started)
        with self._lock:
            self._records.append(record)
            # Naomi's rule: both re-hearers agreed and Sabi heard something
            # else, so Sabi should go with theirs. Queued rather than applied,
            # because this lands ~2s after Sabi has already answered.
            if record["rehearers_agreed"] and record["sabi_heard_it_right"] is False:
                self._corrections.append({
                    "turn_index": record["turn_index"],
                    "heard": record["consensus_text"],
                    "sabi_heard": record["gemini_text"],
                })
        self._write_record(record)
        logger.info(
            "Numeric sidecar uuid=%s turn=%s status=%s heard_right=%s groq=%r %s=%r "
            "consensus=%s expected=%s gemini=%r stale=%s latency=%.2fs",
            self.call_uuid,
            record["turn_index"],
            record["status"],
            {True: "yes", False: "NO", None: "unknown"}[record["sabi_heard_it_right"]],
            record["groq_text"],
            record["second_engine"],
            record["second_text"],
            record["consensus_numeric_value"],
            record["expected_answer"],
            record["gemini_text"],
            record["stale"],
            record["wall_seconds"],
        )

    def _build_record(
        self,
        job: dict[str, Any],
        result: dict[str, Any],
        current_turn: int,
        started: float,
    ) -> dict[str, Any]:
        votes = dict(result.get("ensemble_results") or {})
        engines = list(result.get("engines") or ["groq", "local_whisper"])
        first_name = engines[0]
        second_name = engines[1] if len(engines) > 1 else "local_whisper"
        groq = dict(votes.get(first_name) or {})
        local = dict(votes.get(second_name) or {})
        consensus = result.get("consensus_numeric_value")
        expected = job["expected_answer"]
        agreement_matches_expected = (
            consensus is not None and expected is not None and int(consensus) == int(expected)
        )
        # Naomi's rule, and nothing more than it: if Groq and Azure heard the
        # same thing and Sabi heard something else, Sabi goes with theirs.
        # Otherwise Sabi's own hearing stands. No scores, no thresholds - two
        # transcripts either say the same thing or they do not.
        gemini_text = job["gemini_text"]
        groq_text = groq.get("text", "")
        second_text = local.get("text", "")
        rehearers_agreed = _same_words(groq_text, second_text)
        if rehearers_agreed:
            consensus_text = " ".join(str(groq_text).split())
            sabi_heard_it_right: bool | None = _same_words(gemini_text, groq_text) is True
        else:
            consensus_text = ""
            sabi_heard_it_right = None

        return {
            "sidecar_version": SIDECAR_VERSION,
            "mode": self.mode,
            "call_uuid": self.call_uuid,
            "turn_index": job["turn_index"],
            "problem_id": job["problem_id"],
            "attempt": job["attempt"],
            "prompt_level": job["prompt_level"],
            "expected_answer": expected,
            "gemini_text": job["gemini_text"],
            "status": result.get("status", "unknown"),
            "numeric_agreement": bool(result.get("numeric_agreement")),
            "decision_eligible": bool(result.get("decision_eligible")),
            "consensus_numeric_value": consensus,
            "agreement_matches_expected": agreement_matches_expected,
            "sabi_heard_it_right": sabi_heard_it_right,
            "rehearers_agreed": bool(rehearers_agreed),
            "consensus_text": consensus_text,
            "hypothetical_action": result.get("hypothetical_action", ""),
            "selection_reason": result.get("selection_reason", ""),
            "decision_deadline_seconds": result.get("decision_deadline_seconds"),
            "decision_latency_seconds": result.get("decision_latency_seconds"),
            "collection_latency_seconds": result.get("collection_latency_seconds"),
            "wall_seconds": round(time.monotonic() - started, 3),
            "queued_at": job["queued_at"],
            "audio": dict(result.get("audio") or {}),
            "engines": engines,
            "groq_text": groq.get("text", ""),
            "groq_numeric_candidates": groq.get("numeric_candidates", []),
            "second_engine": second_name,
            "second_text": local.get("text", ""),
            "second_numeric_candidates": local.get("numeric_candidates", []),
            # Kept so older records and the report stay readable when the
            # second vote is the offline engine.
            "local_whisper_text": local.get("text", "") if second_name == "local_whisper" else "",
            # Late results are evidence, never an action: by the time they land
            # the learner has already moved on.
            "stale": bool(job["turn_index"] < int(current_turn)),
            "applied_to_grading": False,
            "ensemble_results": votes,
        }

    def take_correction(self) -> dict[str, Any] | None:
        """Hand back one pending mis-hear, or None. Each is returned once."""
        with self._lock:
            return self._corrections.pop(0) if self._corrections else None

    def _write_record(self, record: dict[str, Any]) -> None:
        try:
            self.record_path.parent.mkdir(parents=True, exist_ok=True)
            with self.record_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception as exc:
            logger.warning(
                "Numeric sidecar could not persist uuid=%s turn=%s: %s",
                self.call_uuid,
                record.get("turn_index"),
                exc,
            )

    # -- reporting ------------------------------------------------------

    def drain(self, timeout_seconds: float = 20.0) -> None:
        """Wait briefly for in-flight jobs so the call summary is complete."""
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            with self._lock:
                if self._pending == 0:
                    return
            time.sleep(0.2)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
            dropped = self._dropped_capacity
            pending = self._pending
        agreed = [row for row in records if row["numeric_agreement"]]
        eligible = [row for row in records if row["decision_eligible"]]
        latencies = [
            row["decision_latency_seconds"]
            for row in records
            if row.get("decision_latency_seconds") is not None
        ]
        return {
            "call_uuid": self.call_uuid,
            "mode": self.mode,
            "turns_measured": len(records),
            "numeric_agreement": len(agreed),
            "decision_eligible": len(eligible),
            # Would the consensus have graded the same value the item expects?
            "agreement_matches_expected": sum(
                1 for row in agreed if row["agreement_matches_expected"]
            ),
            "agreement_conflicts_expected": sum(
                1 for row in agreed if not row["agreement_matches_expected"]
            ),
            "stale_results": sum(1 for row in records if row["stale"]),
            "dropped_for_capacity": dropped,
            "still_pending": pending,
            "max_decision_latency_seconds": max(latencies) if latencies else None,
            "record_path": str(self.record_path),
        }
