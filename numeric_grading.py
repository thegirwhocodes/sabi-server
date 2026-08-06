"""Deterministic guard for simple numeric answer grading.

The LLM still teaches, but this prevents obvious market-math answers like
"fifty naira" from being marked wrong after STT normalizes them correctly.
"""

import re
from dataclasses import dataclass
from typing import Iterable

from transcript_normalizer import is_non_answer_transcript

SMALL_NUMBERS = {
    "zero": 0,
    "one": 1, "wan": 1,
    "two": 2, "tu": 2,
    "three": 3, "tree": 3, "tri": 3,
    "four": 4, "fo": 4,
    "five": 5, "fine": 5, "fife": 5, "fi": 5,
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

CONFUSABLE_NUMBER_PAIRS = {
    (12, 20), (20, 12),
    (13, 30), (30, 13),
    (14, 40), (40, 14),
    (15, 50), (50, 15),
    (16, 60), (60, 16),
    (17, 70), (70, 17),
    (18, 80), (80, 18),
    (19, 90), (90, 19),
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


def is_confusable_numeric_answer(expected: Iterable[int], observed: Iterable[int]) -> bool:
    """Return true for common STT teen/tens swaps that need confirmation."""
    for expected_value in expected:
        for observed_value in observed:
            if expected_value == observed_value:
                continue
            if (int(expected_value), int(observed_value)) in CONFUSABLE_NUMBER_PAIRS:
                return True
            if _looks_like_dropped_five(expected_value, observed_value):
                return True
    return False


def _looks_like_dropped_five(expected_value: int, observed_value: int) -> bool:
    """Detect phone-STT deleting the final "five" from answers like forty-five."""
    expected_int = int(expected_value)
    observed_int = int(observed_value)
    return 25 <= expected_int <= 95 and expected_int % 10 == 5 and observed_int == expected_int - 5


def _strip_instructional_one_phrases(question: str) -> str:
    lower = question.lower()
    lower = re.sub(r"\bno hints for this one\b", "no hints for this item", lower)
    lower = re.sub(r"\blet'?s do one together\b", "let us do this together", lower)
    lower = re.sub(r"\bdo one together\b", "do this together", lower)
    lower = re.sub(r"\bone together\b", "together", lower)
    lower = re.sub(r"\btry one more\b", "try another", lower)
    lower = re.sub(r"\blet'?s try one more\b", "let us try another", lower)
    lower = re.sub(r"\bone more\s*:", "another:", lower)
    return lower


def _infer_expected_number(question: str) -> int | None:
    lower = _strip_instructional_one_phrases(question)
    numbers = extract_numbers(lower)
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

    unit_price_change = _infer_unit_price_change(lower, numbers)
    if unit_price_change is not None:
        return unit_price_change

    total_spend = _infer_total_spend(lower, numbers)
    if total_spend is not None:
        return total_spend

    if re.search(r"\b(change|left|remain|remaining)\b", lower):
        if len(numbers) == 2:
            return abs(numbers[1] - numbers[0])
        max_value = max(numbers)
        others = list(numbers)
        others.remove(max_value)
        return max_value - sum(others)

    if re.search(r"\b(times|multiply|each|every|groups?\s+of)\b", lower) or (
        re.search(r"\b(cost|costs|costing)\b", lower)
        and re.search(r"\b(buy|buys|bought|purchase|purchases|purchased)\b", lower)
    ):
        if len(numbers) >= 2:
            return numbers[-2] * numbers[-1]

    if re.search(r"\b(share|shared|equally|divide|divided)\b", lower) and len(numbers) >= 2:
        if numbers[1] and numbers[0] % numbers[1] == 0:
            return numbers[0] // numbers[1]

    if re.search(r"\b(altogether|total|together|plus|add|more|in all)\b", lower):
        return sum(numbers)

    return None


def _infer_unit_price_change(question_lower: str, numbers: list[int]) -> int | None:
    """Handle voice-friendly two-step price stories: quantity * unit price, then change."""
    if len(numbers) < 3:
        return None
    if not re.search(r"\b(change|left|remain|remaining)\b", question_lower):
        return None
    if not re.search(r"\b(each|every|per|costs?|costing|at)\b", question_lower):
        return None

    payment = max(numbers)
    cost_numbers = list(numbers)
    cost_numbers.remove(payment)
    if len(cost_numbers) < 2:
        return None

    total_cost = 0
    index = 0
    while index + 1 < len(cost_numbers):
        total_cost += cost_numbers[index] * cost_numbers[index + 1]
        index += 2
    if index < len(cost_numbers):
        total_cost += cost_numbers[index]

    return payment - total_cost


def _infer_total_spend(question_lower: str, numbers: list[int]) -> int | None:
    """Infer total cost for market stories asking what was spent or paid."""
    if not _has_total_cost_intent(question_lower):
        return None
    if re.search(r"\b(change|left|remain|remaining)\b", question_lower):
        return None

    if re.search(r"\b(each|every|per)\b", question_lower):
        return _sum_unit_price_pairs(numbers)

    marked_prices = _extract_marked_prices(question_lower)
    if len(marked_prices) >= 2:
        return sum(marked_prices)
    if len(marked_prices) == 1 and len(numbers) == 1:
        return marked_prices[0]
    if (
        len(marked_prices) == 1
        and len(numbers) >= 2
        and re.search(r"\b(buy|buys|bought|purchase|purchases|purchased)\b", question_lower)
    ):
        return None

    has_budget_number = re.search(r"\b(have|has|had|with|pay with|paid with|give|gives|gave)\b", question_lower)
    if (
        not has_budget_number
        and not re.search(r"\b(buy|buys|bought|purchase|purchases|purchased|costs?|costing)\b", question_lower)
        and re.search(r"\b(spend|spent|pay|paid)\b", question_lower)
        and len(numbers) >= 2
    ):
        return sum(numbers)
    return None


def _has_total_cost_intent(question_lower: str) -> bool:
    return bool(
        re.search(r"\b(how much (?:do|did|will|would)?\s*(?:you|they|we|she|he)?\s*(?:spend|pay)|total cost|cost in all|spend in all|paid in all|altogether|in total|in all)\b", question_lower)
        or (
            re.search(r"\b(spend|spent|pay|paid)\b", question_lower)
            and re.search(r"\b(costs?|costing|for|at)\b", question_lower)
        )
    )


def _extract_marked_prices(question_lower: str) -> list[int]:
    prices: list[int] = []
    pattern = re.compile(
        r"\b(?:for|costs?|costing|at)\s+"
        r"((?:\d+(?:,\d{3})*|[a-z]+)(?:[\s-]+(?:\d+(?:,\d{3})*|[a-z]+)){0,6})\s+naira\b"
    )
    for match in pattern.finditer(question_lower):
        parsed = extract_numbers(match.group(1))
        if parsed:
            prices.extend(parsed)
    return prices


def _sum_unit_price_pairs(numbers: list[int]) -> int | None:
    if len(numbers) < 2:
        return None
    total = 0
    index = 0
    while index + 1 < len(numbers):
        total += numbers[index] * numbers[index + 1]
        index += 2
    if index < len(numbers):
        total += numbers[index]
    return total


def build_numeric_grading_hint(messages: list[dict]) -> str:
    check = analyze_latest_numeric_turn(messages)
    if check.expected is None:
        return ""

    if check.is_correct:
        return f"""

## LATEST NUMERIC ANSWER CHECK
For the latest Sabi question, a deterministic math check gives {check.expected} as the expected answer.
The child's latest answer includes {check.expected}. Treat that answer as correct, acknowledge it, and move on. Do not say it is wrong or almost."""

    if not check.child_numbers:
        return f"""

## LATEST NUMERIC ANSWER CHECK
For the latest Sabi question, a deterministic math check gives {check.expected} as the expected answer.
The latest phone transcript has no usable number in it, so do not mark the child wrong from this transcript alone. If it sounds like the child is asking for help, scaffold the problem. Otherwise say you did not quite hear the answer and ask the child to repeat it."""

    if check.is_correct is None:
        return f"""

## LATEST NUMERIC ANSWER CHECK
For the latest Sabi question, a deterministic math check gives {check.expected} as the expected answer.
The child's latest answer included {check.child_numbers}, but this may be a phone-STT confusion for a nearby number. Do not mark it confidently right or wrong. Ask the child to repeat or confirm the answer once."""

    return f"""

## LATEST NUMERIC ANSWER CHECK
For the latest Sabi question, a deterministic math check gives {check.expected} as the expected answer.
The child's latest answer included {check.child_numbers}, so it appears incorrect.
Do not say "wrong." Acknowledge the attempt, then follow the learner-state bump-down ladder if present; otherwise use smaller numbers, a simpler market story, or a concrete counting step before trying a fresh similar problem."""


def question_expects_numeric_answer(question: str) -> bool:
    """Return true only when the current tutor question has a computable number.

    This is intentionally stricter than broad market/numeracy context. It is
    used for keypad availability, where merely mentioning a number—or asking a
    literacy question containing "how"—must never enable numeric entry.
    """
    return _infer_expected_number(str(question or "")) is not None


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
    if is_non_answer_transcript(child_answer):
        return NumericTurnCheck(expected, [], None, assistant_question, child_answer)
    child_numbers = extract_numbers(child_answer)
    if expected is None:
        return NumericTurnCheck(None, child_numbers, None, assistant_question, child_answer)

    if not child_numbers:
        return NumericTurnCheck(expected, child_numbers, None, assistant_question, child_answer)
    if is_confusable_numeric_answer((expected,), child_numbers):
        return NumericTurnCheck(expected, child_numbers, None, assistant_question, child_answer)

    return NumericTurnCheck(
        expected=expected,
        child_numbers=child_numbers,
        is_correct=expected in child_numbers,
        assistant_question=assistant_question,
        child_answer=child_answer,
    )
