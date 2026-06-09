"""
Put currency BEFORE "naira" so TTS reads naturally ("thirty naira"),
not "naira thirty" (from naive ₦ → "naira 30").

Keep logic aligned with: curriculum-app/lib/voice/normalize-money-for-speech.ts
"""

import re

_NAIRA_then_DIGITS = re.compile(r"\bnaira\s+(\d[\d,]*(?:\.\d+)?)\b", re.I)

_NAIRA_then_TENS_COMPOUND = re.compile(
    r"\bnaira\s+((?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:-(?:one|two|three|four|five|six|seven|eight|nine))?)\b",
    re.I,
)

_NAIRA_then_TEENS = re.compile(
    r"\bnaira\s+(ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b",
    re.I,
)

_NAIRA_then_SINGLE = re.compile(
    r"\bnaira\s+(one|two|three|four|five|six|seven|eight|nine)\b"
    r"(?!\s+hundred)(?!\s+thousand)",
    re.I,
)


def normalize_money_for_speech(raw: str) -> str:
    s = raw

    def _amount_after_naira_symbol(m: re.Match) -> str:
        num = m.group(1).replace(",", "")
        return f"{num} naira"

    s = re.sub(r"₦\s*(\d[\d,]*(?:\.\d+)?)\b", _amount_after_naira_symbol, s)
    s = s.replace("₦", "naira")

    def _flip_digits(m: re.Match) -> str:
        return f"{m.group(1).replace(',', '')} naira"

    s = _NAIRA_then_DIGITS.sub(_flip_digits, s)
    s = _NAIRA_then_TENS_COMPOUND.sub(lambda m: f"{m.group(1)} naira", s)
    s = _NAIRA_then_TEENS.sub(lambda m: f"{m.group(1)} naira", s)
    s = _NAIRA_then_SINGLE.sub(lambda m: f"{m.group(1)} naira", s)

    s = re.sub(r"\s{2,}", " ", s)
    return s
