"""
Fuzzy answer matching for children's spoken responses.
Handles number words, near-misses, and partial matches
from Whisper STT transcriptions of Nigerian children's speech.
"""

import re
from typing import Optional

# Number word → digit mapping (supports Nigerian English variations)
WORD_TO_NUM = {
    "zero": 0, "oh": 0,
    "one": 1, "won": 1, "wan": 1,
    "two": 2, "too": 2, "to": 2, "tu": 2,
    "three": 3, "tree": 3, "tri": 3,
    "four": 4, "for": 4, "fo": 4,
    "five": 5, "fife": 5, "fi": 5,
    "six": 6, "sick": 6, "sik": 6,
    "seven": 7, "sevin": 7,
    "eight": 8, "ate": 8, "ait": 8,
    "nine": 9, "nain": 9,
    "ten": 10, "tin": 10,
    "eleven": 11, "elevin": 11,
    "twelve": 12, "twelf": 12,
    "thirteen": 13, "tirteen": 13,
    "fourteen": 14, "forteen": 14,
    "fifteen": 15, "fiftin": 15,
    "sixteen": 16, "sixtin": 16,
    "seventeen": 17, "seventin": 17,
    "eighteen": 18, "eightin": 18,
    "nineteen": 19, "nintin": 19,
    "twenty": 20, "twenti": 20, "tweny": 20,
    "thirty": 30, "tirty": 30,
    "forty": 40, "foty": 40,
    "fifty": 50, "fifti": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100, "undred": 100,
}

# Yes/no variations
YES_WORDS = {"yes", "yeah", "yah", "ya", "yep", "uh huh", "ok", "okay", "sure", "ready"}
NO_WORDS = {"no", "nah", "nope", "not really"}


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_number(text: str) -> Optional[int]:
    """
    Extract a number from spoken text.
    Handles: "5", "five", "it's five", "I think 5", "two hundred", etc.
    """
    text = normalize_text(text)

    # Direct digit match
    digits = re.findall(r"\d+", text)
    if digits:
        return int(digits[0])

    # Word-to-number lookup
    words = text.split()
    for word in words:
        if word in WORD_TO_NUM:
            return WORD_TO_NUM[word]

    # Compound numbers: "twenty three" → 23
    for i, word in enumerate(words):
        if word in WORD_TO_NUM and WORD_TO_NUM[word] in (20, 30, 40, 50, 60, 70, 80, 90):
            tens = WORD_TO_NUM[word]
            if i + 1 < len(words) and words[i + 1] in WORD_TO_NUM:
                ones = WORD_TO_NUM[words[i + 1]]
                if 1 <= ones <= 9:
                    return tens + ones
            return tens

    # "a hundred" / "one hundred" / "hundred and twenty"
    if "hundred" in words or "undred" in words:
        return _parse_hundreds(words)

    return None


def _parse_hundreds(words: list[str]) -> Optional[int]:
    """Parse hundreds from word list."""
    result = 100
    # Find position of "hundred"
    for i, w in enumerate(words):
        if w in ("hundred", "undred"):
            # Check for multiplier before
            if i > 0 and words[i - 1] in WORD_TO_NUM:
                result = WORD_TO_NUM[words[i - 1]] * 100
            # Check for remainder after ("and" optional)
            remaining = words[i + 1:]
            if remaining and remaining[0] == "and":
                remaining = remaining[1:]
            if remaining:
                remainder_text = " ".join(remaining)
                remainder = extract_number(remainder_text)
                if remainder is not None:
                    result += remainder
            return result
    return None


def is_yes(text: str) -> bool:
    """Check if response is affirmative."""
    return normalize_text(text) in YES_WORDS or any(
        w in normalize_text(text).split() for w in YES_WORDS
    )


def is_no(text: str) -> bool:
    """Check if response is negative."""
    return normalize_text(text) in NO_WORDS or any(
        w in normalize_text(text).split() for w in NO_WORDS
    )


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def match_answer(child_response: str, expected_answers: list[str], threshold: float = 0.6) -> dict:
    """
    Match a child's spoken response against expected answers.

    Args:
        child_response: STT transcription of child's speech
        expected_answers: List of acceptable answers (e.g., ["2", "two"])
        threshold: Similarity threshold for fuzzy match (0-1)

    Returns:
        {
            "matched": bool,
            "confidence": float (0-1),
            "matched_answer": str or None,
            "extracted_number": int or None,
        }
    """
    response_normalized = normalize_text(child_response)
    child_number = extract_number(child_response)

    best_confidence = 0.0
    best_match = None

    for expected in expected_answers:
        expected_normalized = normalize_text(expected)

        # 1. Exact match
        if response_normalized == expected_normalized:
            return {
                "matched": True,
                "confidence": 1.0,
                "matched_answer": expected,
                "extracted_number": child_number,
            }

        # 2. Number comparison (most important for math lessons)
        expected_number = extract_number(expected)
        if child_number is not None and expected_number is not None:
            if child_number == expected_number:
                return {
                    "matched": True,
                    "confidence": 0.95,
                    "matched_answer": expected,
                    "extracted_number": child_number,
                }

        # 3. Contains match (child says "it is five" when expected is "5")
        if expected_normalized in response_normalized:
            confidence = len(expected_normalized) / max(len(response_normalized), 1)
            confidence = max(confidence, 0.8)  # Boost since it's a substring match
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = expected

        # 4. Response contains expected (child says "speech sound" when expected is "speech sound")
        if response_normalized in expected_normalized:
            confidence = len(response_normalized) / max(len(expected_normalized), 1)
            confidence = max(confidence, 0.7)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = expected

        # 5. Levenshtein distance (fuzzy match for accent/pronunciation differences)
        max_len = max(len(response_normalized), len(expected_normalized), 1)
        distance = levenshtein_distance(response_normalized, expected_normalized)
        similarity = 1.0 - (distance / max_len)
        if similarity > best_confidence:
            best_confidence = similarity
            best_match = expected

    matched = best_confidence >= threshold
    return {
        "matched": matched,
        "confidence": best_confidence,
        "matched_answer": best_match if matched else None,
        "extracted_number": child_number,
    }


def is_counting_sequence(text: str, start: int, end: int) -> bool:
    """
    Check if child is counting in sequence (e.g., "1 2 3 4 5").
    Used for counting-along exercises.
    """
    text = normalize_text(text)
    numbers = []

    # Extract all numbers from the text
    for word in text.split():
        num = extract_number(word)
        if num is not None:
            numbers.append(num)

    if not numbers:
        return False

    # Check if numbers form a sequence from start to end
    expected = list(range(start, end + 1))
    # Allow partial sequences (child may not count every number clearly)
    if len(numbers) >= len(expected) * 0.5:  # At least 50% of expected numbers
        # Check they're in order
        return numbers == sorted(numbers) and numbers[-1] >= start
    return False
