"""Conservative cleanup for phone STT transcripts before lesson grading.

This mirrors curriculum-app/lib/voice/answer-matcher.ts, with one important
addition: ambiguous homophones are only rewritten when the recent tutor prompt
is clearly asking for a number or market-math answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


REAL_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand",
}

NUMERIC_CONTEXT_WORDS = {
    "naira", "kobo", "plus", "minus", "add", "added", "take", "times",
    "equals", "equal", "make", "makes", "left", "change", "altogether",
    "total", "answer", "how", "much", "cost", "costs", "pay", "paid",
    "buy", "bought", "share", "shared", "divide", "divided", "groups",
    "oranges", "mangoes", "groundnuts", "biscuits", "books", "market",
}

UNCONDITIONAL_MISHEARS = {
    "wan": "one", "tu": "two", "tri": "three", "fo": "four",
    "fife": "five", "fi": "five", "sik": "six", "sevin": "seven",
    "ait": "eight", "nain": "nine", "elevin": "eleven", "twelf": "twelve",
    "tirteen": "thirteen", "forteen": "fourteen", "fiftin": "fifteen",
    "sixtin": "sixteen", "seventin": "seventeen", "eightin": "eighteen",
    "nintin": "nineteen", "twenti": "twenty", "tweny": "twenty",
    "tirty": "thirty", "foty": "forty", "fifti": "fifty",
}

CONDITIONAL_MISHEARS = {
    "tree": "three", "for": "four", "to": "two", "too": "two",
    "heaven": "seven", "ate": "eight", "sick": "six", "won": "one",
    "tin": "ten", "oh": "zero",
}

PUNCT = re.compile(r"[^\w\s]")


@dataclass(frozen=True)
class NormalizeResult:
    text: str
    changed: bool
    substitutions: list[tuple[str, str]]


def _tokens(text: str) -> list[str]:
    return [tok for tok in PUNCT.sub(" ", text.lower()).split() if tok]


def _is_number_like(token: str) -> bool:
    return token.isdigit() or token in REAL_NUMBER_WORDS


def _has_numeric_context(text: str) -> bool:
    tokens = _tokens(text)
    if any(_is_number_like(token) for token in tokens):
        return True
    return any(token in NUMERIC_CONTEXT_WORDS for token in tokens)


def _is_numeric_context(tokens: list[str], index: int, force_numeric_context: bool) -> bool:
    for neighbor in (tokens[index - 1] if index > 0 else "", tokens[index + 1] if index + 1 < len(tokens) else ""):
        if not neighbor:
            continue
        if _is_number_like(neighbor) or neighbor in NUMERIC_CONTEXT_WORDS:
            return True
    # If the tutor just asked a numeric question and the child gives only a
    # tiny answer like "for" or "to", treat it as a likely number. Do not apply
    # this to full sentences, where "to" and "for" are usually normal grammar.
    if force_numeric_context and len(tokens) <= 3:
        return True
    return False


def normalize_number_mishears(raw: str, *, force_numeric_context: bool = False) -> NormalizeResult:
    """Normalize likely Nigerian-English number mishears in a transcript."""
    if not raw or not raw.strip():
        return NormalizeResult(text=raw, changed=False, substitutions=[])

    tokens = _tokens(raw)
    substitutions: list[tuple[str, str]] = []
    out: list[str] = []

    for index, token in enumerate(tokens):
        if token in UNCONDITIONAL_MISHEARS:
            replacement = UNCONDITIONAL_MISHEARS[token]
            substitutions.append((token, replacement))
            out.append(replacement)
            continue

        if token in CONDITIONAL_MISHEARS:
            replacement = CONDITIONAL_MISHEARS[token]
            if token == "oh":
                prev_token = tokens[index - 1] if index > 0 else ""
                next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
                if (
                    _is_number_like(prev_token)
                    or _is_number_like(next_token)
                    or (len(tokens) <= 3 and (prev_token in NUMERIC_CONTEXT_WORDS or next_token in NUMERIC_CONTEXT_WORDS))
                    or (force_numeric_context and len(tokens) == 1)
                ):
                    substitutions.append((token, replacement))
                    out.append(replacement)
                    continue
            elif _is_numeric_context(tokens, index, force_numeric_context):
                substitutions.append((token, replacement))
                out.append(replacement)
                continue

        out.append(token)

    if not substitutions:
        return NormalizeResult(text=raw, changed=False, substitutions=[])
    return NormalizeResult(text=" ".join(out), changed=True, substitutions=substitutions)


def normalize_lesson_transcript(text: str, messages: list[dict[str, str]]) -> NormalizeResult:
    """Normalize an STT transcript using the last few tutor prompts as context."""
    recent_assistant = " ".join(
        message.get("content", "")
        for message in messages[-4:]
        if message.get("role") == "assistant"
    ).lower()

    force_numeric_context = _has_numeric_context(recent_assistant)
    result = normalize_number_mishears(text, force_numeric_context=force_numeric_context)
    normalized = result.text
    substitutions = list(result.substitutions)

    if "bag" in recent_assistant:
        bag_fixed = re.sub(r"\b(bugs|bucks)\b", "bags", normalized, flags=re.I)
        if bag_fixed != normalized:
            for bad in re.findall(r"\b(bugs|bucks)\b", normalized, flags=re.I):
                substitutions.append((bad.lower(), "bags"))
            normalized = bag_fixed

    return NormalizeResult(
        text=normalized,
        changed=normalized != text,
        substitutions=substitutions,
    )
