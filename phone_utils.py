"""Phone-number normalization for Sabi learner identity.

Africa's Talking, callback providers, and web forms can represent the same
caller as +234..., 234..., 080..., or with spaces. Sabi's memory must collapse
those into one stable key so a learner continues from the same profile.
"""

from __future__ import annotations

import os
import re


def normalize_phone_number(raw: str | None, default_country_code: str = "234") -> str:
    """Return a best-effort E.164-ish phone number for identity lookup."""
    if not raw:
        return "unknown"

    text = str(raw).strip()
    if not text or text.lower() in {"unknown", "anonymous", "restricted"}:
        return "unknown"

    has_plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return "unknown"

    # Nigerian local mobile/landline format, e.g. 08033374126.
    if digits.startswith("0") and len(digits) >= 10:
        return f"+{default_country_code}{digits[1:]}"

    # International format without plus.
    if digits.startswith(default_country_code):
        return f"+{digits}"

    # NANP callers often arrive as +1..., but sometimes without the plus.
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    # Keep explicit international-ish numbers stable.
    if has_plus:
        return f"+{digits}"

    # Last resort: preserve a plus-prefixed digit key rather than creating
    # multiple rows for punctuation/spaces.
    return f"+{digits}"


def phone_lookup_variants(raw: str | None) -> list[str]:
    """Return likely historic variants for backwards-compatible lookup."""
    normalized = normalize_phone_number(raw)
    variants: list[str] = []
    for value in (normalized, raw or ""):
        value = str(value).strip()
        if value and value not in variants:
            variants.append(value)

    if normalized.startswith("+234"):
        local = "0" + normalized[4:]
        bare = normalized[1:]
        for value in (local, bare):
            if value not in variants:
                variants.append(value)

    return variants


def phone_is_numeracy_only(
    raw: str | None,
    configured: str | None = None,
) -> bool:
    """Return whether this caller is in the numeracy-only experiment.

    The switch is deliberately phone-scoped: literacy remains available for
    every learner not listed in ``SABI_NUMERACY_ONLY_PHONES``. Values are
    normalized before comparison so Twilio punctuation cannot bypass it.
    """
    if configured is None:
        configured = os.getenv("SABI_NUMERACY_ONLY_PHONES", "")
    target = normalize_phone_number(raw)
    if target == "unknown":
        return False
    return target in {
        normalize_phone_number(value)
        for value in re.split(r"[,;\n]+", configured or "")
        if value.strip()
    }


def phone_uses_gemini_live(
    raw: str | None,
    configured: str | None = None,
) -> bool:
    """Return whether this caller is in the persistent Gemini Live canary.

    The allowlist is intentionally separate from the numeracy-only allowlist.
    A learner can remain on the ordinary STT -> text LLM -> TTS pipeline while
    still being numeracy-only, and an empty allowlist fails safely to the
    established AudioSocket route.
    """
    if configured is None:
        configured = os.getenv("SABI_GEMINI_LIVE_PHONES", "")
    target = normalize_phone_number(raw)
    if target == "unknown":
        return False
    return target in {
        normalize_phone_number(value)
        for value in re.split(r"[,;\n]+", configured or "")
        if value.strip()
    }
