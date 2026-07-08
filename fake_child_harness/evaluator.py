from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from answer_matcher import match_answer, normalize_text
from numeric_grading import extract_numbers, is_confusable_numeric_answer
from transcript_normalizer import (
    is_likely_stt_hallucination_transcript,
    is_non_answer_transcript,
    is_phone_system_transcript,
)

from .child_simulator import SimulatedTurn


LOW_CONFIDENCE_RETRY_THRESHOLD = 0.18


@dataclass(frozen=True)
class TurnEvaluation:
    child_id: str
    call_index: int
    turn_index: int
    item_id: str
    assistant_prompt: str
    expected_answers: tuple[str, ...]
    ground_truth_correct: bool
    grader_matched: bool
    confidence: float
    stt_confidence: float
    failure_type: str | None
    severity: str
    stt_text: str
    child_answer_text: str
    noise_level: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data


def evaluate_turn(turn: SimulatedTurn) -> TurnEvaluation:
    match = match_answer(turn.stt_text, list(turn.expected_answers))
    matched = bool(match.get("matched"))
    failure_type: str | None = None
    severity = "none"
    child_numbers = extract_numbers(turn.stt_text)
    expected_numbers = extract_numbers(" ".join(turn.expected_answers))

    if any(str(note).startswith("stt_error:") for note in turn.notes):
        failure_type = "stt_error"
        severity = "release_blocking"
    elif is_phone_system_transcript(turn.stt_text):
        failure_type = "phone_system_non_answer"
        severity = "watch"
    elif is_non_answer_transcript(turn.stt_text):
        failure_type = "no_speech_or_masked"
        severity = "watch"
    elif is_likely_stt_hallucination_transcript(turn.stt_text):
        failure_type = "no_speech_or_masked"
        severity = "watch"
    elif (
        turn.ground_truth_correct
        and not matched
        and turn.stt_confidence < LOW_CONFIDENCE_RETRY_THRESHOLD
    ):
        failure_type = "no_speech_or_masked"
        severity = "watch"
    elif expected_numbers and not child_numbers and turn.ground_truth_correct:
        failure_type = "no_speech_or_masked"
        severity = "watch"
    elif child_numbers and is_confusable_numeric_answer(expected_numbers, child_numbers):
        failure_type = "ambiguous_numeric_stt"
        severity = "watch"
    elif _looks_like_deletion_prompt_echo(turn, matched):
        failure_type = "prompt_echo_or_deletion_masked"
        severity = "watch"
    elif turn.ground_truth_correct and not matched:
        failure_type = "false_wrong_grading"
        severity = "release_blocking"
    elif not turn.ground_truth_correct and matched and "changed_answer" in turn.notes:
        failure_type = "changed_answer_self_correction"
        severity = "watch"
    elif not turn.ground_truth_correct and matched:
        failure_type = "false_correct_grading"
        severity = "watch"

    return TurnEvaluation(
        child_id=turn.child_id,
        call_index=turn.call_index,
        turn_index=turn.turn_index,
        item_id=turn.item_id,
        assistant_prompt=turn.prompt,
        expected_answers=turn.expected_answers,
        ground_truth_correct=turn.ground_truth_correct,
        grader_matched=matched,
        confidence=float(match.get("confidence") or 0.0),
        stt_confidence=turn.stt_confidence,
        failure_type=failure_type,
        severity=severity,
        stt_text=turn.stt_text,
        child_answer_text=turn.child_answer_text,
        noise_level=turn.noise_level,
        notes=turn.notes,
    )


def _looks_like_deletion_prompt_echo(turn: SimulatedTurn, matched: bool) -> bool:
    """Flag STT prompt echo on deletion tasks as retry-worthy, not a wrong grade."""
    if matched or not turn.ground_truth_correct:
        return False
    if not turn.item_id.startswith("lit_delete_"):
        return False

    transcript = normalize_text(turn.stt_text)
    if not transcript or len(transcript.split()) > 3:
        return False

    prompt = normalize_text(turn.prompt)
    if not _contains_whole_phrase(prompt, transcript):
        return False

    for expected in turn.expected_answers:
        expected_normalized = normalize_text(expected)
        if len(expected_normalized) < 2 or transcript == expected_normalized:
            continue
        if expected_normalized in transcript:
            return True
    return False


def _contains_whole_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?:^|\s)" + re.escape(phrase) + r"(?:\s|$)", text))


def summarize_evaluations(evaluations: list[TurnEvaluation]) -> dict[str, Any]:
    total = len(evaluations)
    failures = [item for item in evaluations if item.failure_type]
    release_blocking = [item for item in failures if item.severity == "release_blocking"]
    false_wrong = [item for item in failures if item.failure_type == "false_wrong_grading"]
    false_correct = [item for item in failures if item.failure_type == "false_correct_grading"]
    phone_system = [item for item in failures if item.failure_type == "phone_system_non_answer"]
    ambiguous_numeric = [item for item in failures if item.failure_type == "ambiguous_numeric_stt"]
    no_speech = [item for item in failures if item.failure_type == "no_speech_or_masked"]
    prompt_echo = [item for item in failures if item.failure_type == "prompt_echo_or_deletion_masked"]
    changed_answer = [item for item in failures if item.failure_type == "changed_answer_self_correction"]
    stt_errors = [item for item in failures if item.failure_type == "stt_error"]
    correct_ground_truth = [item for item in evaluations if item.ground_truth_correct]
    wrong_ground_truth = [item for item in evaluations if not item.ground_truth_correct]

    return {
        "total_turns": total,
        "failures": len(failures),
        "release_blocking_failures": len(release_blocking),
        "false_wrong": len(false_wrong),
        "false_correct": len(false_correct),
        "phone_system_non_answers": len(phone_system),
        "ambiguous_numeric_stt": len(ambiguous_numeric),
        "no_speech_or_masked": len(no_speech),
        "prompt_echo_or_deletion_masked": len(prompt_echo),
        "changed_answer_self_corrections": len(changed_answer),
        "stt_errors": len(stt_errors),
        "ground_truth_correct_turns": len(correct_ground_truth),
        "ground_truth_wrong_turns": len(wrong_ground_truth),
        "false_wrong_rate": _rate(len(false_wrong), len(correct_ground_truth)),
        "false_correct_rate": _rate(len(false_correct), len(wrong_ground_truth)),
        "release_blocking_rate": _rate(len(release_blocking), total),
    }


def _rate(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(count / denominator, 4)
