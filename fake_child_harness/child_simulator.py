from __future__ import annotations

from dataclasses import asdict, dataclass
import random
from typing import Any

from diagnostic_flow import NUMERACY_DIAGNOSTIC_ITEMS, DiagnosticItem

from .cohort import FakeChildProfile


NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    24: "twenty four",
    30: "thirty",
    32: "thirty two",
    37: "thirty seven",
    42: "forty two",
    85: "eighty five",
    100: "one hundred",
    120: "one hundred and twenty",
    156: "one hundred and fifty six",
}

NUMBER_CONFUSIONS = {
    "three": ("tree", "free"),
    "four": ("for", "fo"),
    "five": ("fine", "fife"),
    "six": ("sick",),
    "seven": ("sevin",),
    "eight": ("ate",),
    "thirteen": ("thirty",),
    "fifteen": ("fifty",),
    "thirty": ("thirteen",),
    "forty two": ("forty too",),
}


@dataclass(frozen=True)
class SimulatedTurn:
    child_id: str
    call_index: int
    turn_index: int
    prompt: str
    item_id: str
    expected_answers: tuple[str, ...]
    ground_truth_correct: bool
    child_answer_text: str
    stt_text: str
    noise_level: str
    stt_confidence: float = 1.0
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["expected_answers"] = list(self.expected_answers)
        data["notes"] = list(self.notes)
        return data


def simulate_diagnostic_call(
    child: FakeChildProfile,
    *,
    call_index: int,
    seed: int,
    max_turns: int = 7,
) -> list[SimulatedTurn]:
    rng = random.Random(f"{seed}:{child.child_id}:{call_index}")
    turns: list[SimulatedTurn] = []
    items = NUMERACY_DIAGNOSTIC_ITEMS[:max_turns]

    for turn_index, item in enumerate(items, start=1):
        if child.call_behavior == "hangs_up_early" and turn_index > 3 and rng.random() < 0.55:
            break

        answer_text, correct, notes = _answer_for_item(child, item, rng)
        stt_text, stt_notes = corrupt_transcript(answer_text, child, rng)
        turns.append(
            SimulatedTurn(
                child_id=child.child_id,
                call_index=call_index,
                turn_index=turn_index,
                prompt=item.prompt,
                item_id=item.id,
                expected_answers=_expected_answers(item),
                ground_truth_correct=correct,
                child_answer_text=answer_text,
                stt_text=stt_text,
                noise_level=child.noise_level,
                notes=tuple([*notes, *stt_notes]),
            )
        )
    return turns


def corrupt_transcript(answer_text: str, child: FakeChildProfile, rng: random.Random) -> tuple[str, list[str]]:
    notes: list[str] = []
    text = answer_text

    if "carrier_audio" in child.stt_risks and rng.random() < 0.20:
        return "Not available", ["carrier_audio_phrase"]

    if child.call_behavior == "misses_turns" and rng.random() < 0.10:
        return "", ["no_speech"]

    if child.noise_level == "brutal_market" and rng.random() < 0.18:
        return "", ["masked_by_noise"]

    if "short_numbers" in child.stt_risks or child.noise_level in {"lagos_market", "brutal_market"}:
        for source, replacements in NUMBER_CONFUSIONS.items():
            if source in text and rng.random() < _confusion_rate(child.noise_level):
                text = text.replace(source, rng.choice(replacements))
                notes.append(f"number_confusion:{source}")
                break

    if child.temperament == "repeats_answer" or child.call_behavior == "repeats_answer":
        if rng.random() < 0.30:
            text = f"{text}, {text}"
            notes.append("repeated_answer")

    if child.call_behavior == "changes_answer" and rng.random() < 0.18:
        text = f"{text}, no, {rng.choice(['two', 'three', 'five', 'seven'])}"
        notes.append("changed_answer")

    if child.language_profile == "pidgin_influenced_english" and rng.random() < 0.20:
        text = f"na {text}"
        notes.append("pidgin_prefix")

    return text, notes


def _answer_for_item(
    child: FakeChildProfile,
    item: DiagnosticItem,
    rng: random.Random,
) -> tuple[str, bool, list[str]]:
    expected_number = item.expected[0]
    difficulty = max(1, item.fail_tarl_level + 1)
    if child.numeracy_level >= difficulty:
        correct_prob = 0.86
    elif child.numeracy_level + 1 == difficulty:
        correct_prob = 0.42
    else:
        correct_prob = 0.12

    if child.temperament == "guesses":
        correct_prob -= 0.08
    if child.temperament == "eager":
        correct_prob += 0.04
    if child.noise_level in {"lagos_market", "brutal_market"}:
        correct_prob -= 0.03

    correct = rng.random() < max(0.02, min(0.95, correct_prob))
    if correct:
        answer = _number_to_text(expected_number, rng)
        return answer, True, []

    wrong = _nearby_wrong_number(expected_number, rng)
    return _number_to_text(wrong, rng), False, [f"ability_miss:difficulty_{difficulty}"]


def _expected_answers(item: DiagnosticItem) -> tuple[str, ...]:
    values: list[str] = []
    for value in item.expected:
        values.append(str(value))
        values.append(NUMBER_WORDS.get(value, str(value)))
    return tuple(dict.fromkeys(values))


def _nearby_wrong_number(expected: int, rng: random.Random) -> int:
    if expected <= 10:
        options = [n for n in (expected - 2, expected - 1, expected + 1, expected + 2) if n >= 0]
    else:
        options = [max(0, expected - 10), max(0, expected - 1), expected + 1, expected + 10]
    return rng.choice(options)


def _number_to_text(value: int, rng: random.Random) -> str:
    if value in NUMBER_WORDS and rng.random() < 0.82:
        return NUMBER_WORDS[value]
    return str(value)


def _confusion_rate(noise_level: str) -> float:
    return {
        "clean": 0.02,
        "home": 0.05,
        "busy_compound": 0.10,
        "lagos_market": 0.18,
        "brutal_market": 0.30,
    }.get(noise_level, 0.08)
