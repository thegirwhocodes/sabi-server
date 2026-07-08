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
    "five": 5, "fine": 5, "fife": 5, "fi": 5,
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

CANONICAL_NUMBER_WORDS = {
    "zero", "oh",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty",
    "seventy", "eighty", "ninety", "hundred",
}
NUMBER_FILLER_WORDS = {"a", "and"}

# Observed whole-answer STT/accent variants from real Sabi phone tests. Keep
# these match-only so STT numeric salvage still retries on these transcripts.
KNOWN_NUMERIC_MISHEARS = {
    "tati": 30,
    "shes thin": 15,
    "shusin": 15,
}

# Yes/no variations
YES_WORDS = {"yes", "yeah", "yah", "ya", "yep", "uh huh", "ok", "okay", "sure", "ready"}
NO_WORDS = {"no", "nah", "nope", "not really"}


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = text.replace("-", " ")
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _requires_exact_short_text_match(expected_normalized: str) -> bool:
    """Short literacy answers like "s" or "sat" cannot use fuzzy matching."""
    compact = expected_normalized.replace(" ", "")
    words = expected_normalized.split()
    return bool(compact and len(compact) <= 4 and (len(words) <= 2 or all(len(word) == 1 for word in words)))


def _contains_whole_phrase(response_normalized: str, expected_normalized: str) -> bool:
    pattern = r"(?:^|\s)" + re.escape(expected_normalized) + r"(?:\s|$)"
    return bool(re.search(pattern, response_normalized))


def _is_m_sound_variant(response_normalized: str, expected_normalized: str) -> bool:
    """Accept noisy STT variants for the isolated /m/ sound without matching mango."""
    if expected_normalized not in {"m", "mmm"}:
        return False
    compact = response_normalized.replace(" ", "")
    if 1 <= len(compact) <= 8 and set(compact) == {"m"}:
        return True
    tokens = response_normalized.split()
    return bool(tokens) and len(tokens) <= 4 and all(token in {"m", "mm", "mmm", "mmmm", "em", "meh"} for token in tokens)


def _extract_expected_number(text: str) -> Optional[int]:
    """Parse expected numeric answers without treating STT variants as numbers."""
    normalized = normalize_text(text)
    if re.search(r"\d+", normalized):
        return extract_number(normalized)
    words = normalized.split()
    if not words:
        return None
    if not any(word in CANONICAL_NUMBER_WORDS for word in words):
        return None
    if any(word not in CANONICAL_NUMBER_WORDS and word not in NUMBER_FILLER_WORDS for word in words):
        return None
    return extract_number(normalized)


def _extract_child_number_for_match(text: str) -> Optional[int]:
    """Parse child answers, including observed whole-answer numeric mishears."""
    number = extract_number(text)
    if number is not None:
        return number
    return KNOWN_NUMERIC_MISHEARS.get(normalize_text(text))


def extract_number(text: str) -> Optional[int]:
    """
    Extract a number from spoken text.
    Handles: "5", "five", "it's five", "I think 5", "two hundred", etc.
    """
    text = normalize_text(text)
    if text == "sent one":
        return 7

    # Direct digit match. Avoid embedded ordinals/noise like "30th egg"; those
    # are common Whisper artifacts in market noise and should not become 30.
    digits = re.findall(r"(?<![a-z0-9])\d+(?:,\d{3})*(?![a-z0-9])", text)
    if digits:
        return int(digits[0].replace(",", ""))

    words = text.split()

    # "a hundred" / "one hundred" / "hundred and twenty"
    if "hundred" in words or "undred" in words:
        return _parse_hundreds(words)

    # Compound numbers: "twenty three" -> 23. Check this before single-word
    # lookup so "thirty seven" does not get truncated to 30.
    for i, word in enumerate(words):
        if word in WORD_TO_NUM and WORD_TO_NUM[word] in (20, 30, 40, 50, 60, 70, 80, 90):
            tens = WORD_TO_NUM[word]
            if i + 1 < len(words) and words[i + 1] in WORD_TO_NUM:
                ones = WORD_TO_NUM[words[i + 1]]
                if 1 <= ones <= 9:
                    return tens + ones
            return tens

    # Word-to-number lookup
    for word in words:
        if word in WORD_TO_NUM:
            return WORD_TO_NUM[word]

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
    child_number = _extract_child_number_for_match(child_response)
    expected_numbers = {
        value
        for value in (_extract_expected_number(expected) for expected in expected_answers)
        if value is not None
    }

    if not response_normalized:
        return {
            "matched": False,
            "confidence": 0.0,
            "matched_answer": None,
            "extracted_number": child_number,
        }

    # For numeric answers, near misses are pedagogically meaningful. Do not let
    # fuzzy string matching accept "155" for "156" or "sixteen" for "fifteen".
    if child_number is not None and expected_numbers:
        if child_number in expected_numbers:
            for expected in expected_answers:
                if extract_number(expected) == child_number:
                    return {
                        "matched": True,
                        "confidence": 0.95,
                        "matched_answer": expected,
                        "extracted_number": child_number,
                    }
        return {
            "matched": False,
            "confidence": 0.0,
            "matched_answer": None,
            "extracted_number": child_number,
        }

    if expected_numbers:
        return {
            "matched": False,
            "confidence": 0.0,
            "matched_answer": None,
            "extracted_number": child_number,
        }

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

        if _requires_exact_short_text_match(expected_normalized):
            if _is_m_sound_variant(response_normalized, expected_normalized):
                confidence = 0.95
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = expected
                continue
            if _contains_whole_phrase(response_normalized, expected_normalized):
                confidence = len(expected_normalized) / max(len(response_normalized), 1)
                confidence = max(confidence, 0.9)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = expected
            continue

        # 2. Contains match (child says "cat sound" when expected is "cat")
        if expected_normalized in response_normalized:
            confidence = len(expected_normalized) / max(len(response_normalized), 1)
            confidence = max(confidence, 0.8)  # Boost since it's a substring match
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = expected

        # 3. Response contains expected (child says "speech sound" when expected is "speech sound")
        if len(response_normalized.replace(" ", "")) >= 4 and response_normalized in expected_normalized:
            confidence = len(response_normalized) / max(len(expected_normalized), 1)
            confidence = max(confidence, 0.7)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = expected

        # 4. Levenshtein distance (fuzzy match for accent/pronunciation differences)
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
