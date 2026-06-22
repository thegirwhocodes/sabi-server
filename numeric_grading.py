"""Deterministic guard for simple numeric answer grading.

The LLM still teaches, but this prevents obvious market-math answers like
"fifty naira" from being marked wrong after STT normalizes them correctly.
"""

import re
from dataclasses import dataclass

SMALL_NUMBERS = {
    "zero": 0,
    "one": 1, "wan": 1,
    "two": 2, "tu": 2,
    "three": 3, "tree": 3, "tri": 3,
    "four": 4, "fo": 4,
    "five": 5, "fife": 5, "fi": 5,
    "six": 6, "sick": 6, "sik": 6,
    "seven": 7, "sevin": 7,
    "eight": 8, "ait": 8,
    "nine": 9, "nain": 9,
    "ten": 10, "tin": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}

TENS = {
    "twenty": 20, "twenti": 20, "tweny": 20,
    "thirty": 30, "tirty": 30,
    "forty": 40, "foty": 40,
    "fifty": 50, "fifti": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


@dataclass(frozen=True)
class NumericTurnCheck:
    expected: int | None
    child_numbers: list[int]
    is_correct: bool | None
    assistant_question: str
    child_answer: str


def _tokenize(text: str) -> list[str]:
    text = text.lower().replace("₦", " ").replace("-", " ").replace("/", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    return [token for token in text.split() if token]


def extract_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    current = 0
    in_number = False

    def flush():
        nonlocal current, in_number
        if in_number:
            numbers.append(current)
        current = 0
        in_number = False

    for token in _tokenize(text):
        if re.fullmatch(r"\d+(?:,\d{3})*", token):
            flush()
            numbers.append(int(token.replace(",", "")))
            continue
        if token in SMALL_NUMBERS:
            current += SMALL_NUMBERS[token]
            in_number = True
            continue
        if token in TENS:
            current += TENS[token]
            in_number = True
            continue
        if token == "hundred":
            current = (current or 1) * 100
            in_number = True
            continue
        if token == "thousand":
            current = (current or 1) * 1000
            in_number = True
            continue
        if token == "and" and in_number:
            continue
        flush()
    flush()
    return [value for value in numbers if isinstance(value, int)]


def _infer_expected_number(question: str) -> int | None:
    lower = question.lower()
    numbers = extract_numbers(question)
    if not numbers:
        return None

    after = re.search(r"\bafter\s+(\d+|[a-z -]+)\b", lower)
    if after:
        parsed = extract_numbers(after.group(1))
        if parsed:
            return parsed[0] + 1

    before = re.search(r"\bbefore\s+(\d+|[a-z -]+)\b", lower)
    if before:
        parsed = extract_numbers(before.group(1))
        if parsed:
            return parsed[0] - 1

    if re.search(r"\b(change|left|remain|remaining)\b", lower):
        if len(numbers) == 2:
            return abs(numbers[1] - numbers[0])
        max_value = max(numbers)
        others = list(numbers)
        others.remove(max_value)
        return max_value - sum(others)

    if re.search(r"\b(altogether|total|together|plus|add|more|in all)\b", lower):
        return sum(numbers)

    if re.search(r"\b(share|shared|equally|divide|divided)\b", lower) and len(numbers) >= 2:
        if numbers[1] and numbers[0] % numbers[1] == 0:
            return numbers[0] // numbers[1]

    if re.search(r"\b(times|multiply|each|every)\b", lower) or (
        re.search(r"\bbuy\b", lower)
        or re.search(r"\bbought\b", lower)
        or re.search(r"\bpurchase\b", lower)
    ):
        if len(numbers) >= 2:
            return numbers[-2] * numbers[-1]

    return None


def build_numeric_grading_hint(messages: list[dict]) -> str:
    check = analyze_latest_numeric_turn(messages)
    if check.expected is None or check.is_correct is None:
        return ""

    if check.is_correct:
        return f"""

## LATEST NUMERIC ANSWER CHECK
For the latest Sabi question, a deterministic math check gives {check.expected} as the expected answer.
The child's latest answer includes {check.expected}. Treat that answer as correct, acknowledge it, and move on. Do not say it is wrong or almost."""

    if not check.child_numbers:
        return ""

    return f"""

## LATEST NUMERIC ANSWER CHECK
For the latest Sabi question, a deterministic math check gives {check.expected} as the expected answer.
The child's latest answer included {check.child_numbers}, so it appears incorrect.
Do not say "wrong." Acknowledge the attempt, then bump down one level: use smaller numbers, a simpler market story, or a concrete counting step before trying a fresh similar problem."""


def analyze_latest_numeric_turn(messages: list[dict]) -> NumericTurnCheck:
    user_index = None
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            user_index = index
            break
    if user_index is None:
        return NumericTurnCheck(None, [], None, "", "")

    assistant = None
    for index in range(user_index - 1, -1, -1):
        if messages[index].get("role") == "assistant":
            assistant = messages[index]
            break
    if not assistant:
        return NumericTurnCheck(None, [], None, "", messages[user_index].get("content", ""))

    assistant_question = assistant.get("content", "")
    child_answer = messages[user_index].get("content", "")
    expected = _infer_expected_number(assistant_question)
    child_numbers = extract_numbers(child_answer)
    if expected is None:
        return NumericTurnCheck(None, child_numbers, None, assistant_question, child_answer)

    if not child_numbers:
        return NumericTurnCheck(expected, child_numbers, None, assistant_question, child_answer)

    return NumericTurnCheck(
        expected=expected,
        child_numbers=child_numbers,
        is_correct=expected in child_numbers,
        assistant_question=assistant_question,
        child_answer=child_answer,
    )
