"""Idempotent, auditable learner name capture for Sabi phone lessons.

Speech-to-text output is evidence, never a value. The rules this module enforces:

1. An utterance is only a *candidate* name if it plausibly is one. Questions,
   greetings, carrier messages, and every STT artifact we have seen in production
   are refused with a reason code.
2. A candidate becomes a *name* only when it is confirmed, either by the child
   repeating it ("is it Ade?") or by a caregiver. Until then the capture carries
   status ``unverified_utterance`` and callers must not treat it as authoritative.
3. Nothing here depends on mutable module state, so re-running it on the same
   transcript always produces the same result. That is what makes the write
   path idempotent: the transcript is the source of truth, not a counter.

Pure stdlib. No imports from the rest of the app, so it can be reused by the
API, the admin tools, and the rehearsal harness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Statuses written to sabi_students.name_status
# ---------------------------------------------------------------------------

STATUS_UNKNOWN = "unknown"
STATUS_REJECTED = "rejected_artifact"
STATUS_UNVERIFIED = "unverified_utterance"
STATUS_CONFIRMED_REPEAT = "confirmed_repeat"
STATUS_CONFIRMED_CAREGIVER = "confirmed_caregiver"
STATUS_REDACTED = "redacted"

TRUSTED_STATUSES = frozenset({STATUS_CONFIRMED_REPEAT, STATUS_CONFIRMED_CAREGIVER})
STORABLE_STATUSES = frozenset({STATUS_CONFIRMED_REPEAT, STATUS_CONFIRMED_CAREGIVER, STATUS_UNVERIFIED})

#: Names that reached production from STT noise. Kept explicit so the same
#: mistake cannot be repeated silently, and so badly stored rows can be flagged.
NAME_ARTIFACTS = frozenset(
    {
        "a speech",
        "speech",
        "what the",
        "what the heck",
        "what",
        "whats your name",
        "uhhh",
        "uhh",
        "um",
        "huh",
        "already",
        "and how",
        "qu significa",
        "ja mann",
        "ja man",
        "alem saci",
        "alem sasi",
        "my name",
        "no name",
        "i dont know",
        "dont know",
        "unknown",
    }
)

#: Words that make an otherwise short utterance not-a-name.
NON_NAME_WORDS = frozenset(
    {
        "yes", "no", "yeah", "nope", "okay", "ok", "hello", "hi", "hey",
        "ready", "thanks", "thank", "sorry", "please", "good", "fine",
        "what", "who", "why", "how", "when", "where", "which", "huh",
        "the", "and", "but", "is", "am", "are", "my", "me", "you", "your",
        "his", "her", "him", "she", "he", "it", "its", "this", "that",
        "whats", "its", "im", "a", "an", "of", "to", "for", "in", "on",
        "numerous", "twelve", "ten", "three", "four", "five",
    }
)

GREETING_PATTERN = re.compile(
    r"\b("
    r"salam|alaikum|alaykum|assalamu|shalom|bonjour|hola|ciao|namaste|"
    r"good (?:morning|afternoon|evening|night)|how are you|how far|"
    r"wetin dey|bawo ni|ndewo|sannu"
    r")\b",
    re.I,
)

CARRIER_PATTERN = re.compile(
    r"\b("
    r"not available|currently unavailable|unavailable|not reachable|"
    r"switched off|line busy|mailbox|voice ?mail|"
    r"leave (?:a )?message|record (?:your )?message|"
    r"finished recording|after the tone|try again later|hang up|"
    r"cannot be completed|call you back later"
    r")\b",
    re.I,
)

_SELF_INTRO_PATTERNS = (
    re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z' -]{0,30})", re.I),
    re.compile(r"\bi am\s+([A-Za-z][A-Za-z' -]{0,30})", re.I),
    re.compile(r"\bi'm\s+([A-Za-z][A-Za-z' -]{0,30})", re.I),
    re.compile(r"\bthis is\s+([A-Za-z][A-Za-z' -]{0,30})", re.I),
    re.compile(r"\bit'?s\s+([A-Za-z][A-Za-z' -]{0,30})", re.I),
)

_CONFIRMATION_QUESTION = re.compile(
    r"(did i hear|is (?:your name|it) |so your name is|your name is\s+\w+\s*\?|right\s*\?)",
    re.I,
)

_YES = re.compile(r"^\s*(yes|yeah|yep|correct|that'?s right|right|exactly|sure|uh huh|i am|i'?m)\b", re.I)
_NO = re.compile(r"^\s*(no|nope|nah|wrong|not really|that'?s wrong)\b", re.I)


@dataclass
class Candidate:
    """One utterance judged against the name-capture rules."""

    text: str
    verdict: str  # 'name_like' | 'artifact' | 'carrier' | 'question' | 'social' | 'empty' | 'malformed'
    reason: str
    name: str | None = None

    @property
    def accepted(self) -> bool:
        return self.verdict == "name_like"


@dataclass
class CaptureResult:
    """Outcome of reading a whole transcript."""

    name: str | None = None
    status: str = STATUS_UNKNOWN
    attempts: int = 0
    confirmed: bool = False
    source: str = "phone_stt"
    rejections: list[tuple[str, str]] = field(default_factory=list)

    @property
    def name_for_storage(self) -> str | None:
        """The value safe to write to sabi_students.name (never an artifact)."""
        if self.status in STORABLE_STATUSES and self.name:
            return self.name
        return None

    @property
    def needs_confirmation(self) -> bool:
        return self.status == STATUS_UNVERIFIED


def _words(text: str) -> list[str]:
    return re.sub(r"[^A-Za-z' ]", " ", str(text or "")).split()


def clean_name(text: str) -> str | None:
    """Title-case a candidate and keep at most two words."""
    cleaned = re.sub(r"[^A-Za-z' -]", "", str(text or "")).strip(" .,'-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return None
    words = cleaned.split()[:2]
    return " ".join(word.capitalize() for word in words)


def _name_shape_ok(candidate: str) -> bool:
    words = candidate.split()
    if not 1 <= len(words) <= 2:
        return False
    for word in words:
        if not 2 <= len(word) <= 20:
            return False
        if word.lower() in NON_NAME_WORDS:
            return False
        if re.search(r"(.)\1{2,}", word.lower()):  # uhhhh
            return False
    return True


def assess_answer(text: str, asked_for_name: bool = True) -> Candidate:
    """Judge a single child utterance that followed a request for their name."""
    raw = str(text or "").strip()
    if not raw:
        return Candidate(raw, "empty", "no speech captured")

    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z' ]", " ", raw.lower())).strip()

    if normalized in NAME_ARTIFACTS:
        return Candidate(raw, "artifact", f"known stt artifact: {normalized!r}")

    if CARRIER_PATTERN.search(raw):
        return Candidate(raw, "carrier", "carrier or voicemail message")

    if not asked_for_name:
        return Candidate(raw, "malformed", "sabi was not asking for a name")

    if "?" in raw or re.match(r"^(what|who|why|how|when|where|which|is it|are you)\b", normalized):
        return Candidate(raw, "question", "child answered with a question")

    if normalized in NON_NAME_WORDS:
        return Candidate(raw, "social", f"greeting or filler: {normalized!r}")

    if GREETING_PATTERN.search(raw):
        return Candidate(raw, "social", "greeting, not a name")

    for pattern in _SELF_INTRO_PATTERNS:
        match = pattern.search(raw)
        if match:
            name = clean_name(match.group(1))
            if name and _name_shape_ok(name) and name.lower() not in NAME_ARTIFACTS:
                return Candidate(raw, "name_like", "self-introduction", name)
            return Candidate(raw, "malformed", "self-introduction without a usable name")

    words = _words(raw)
    if not 1 <= len(words) <= 3:
        return Candidate(raw, "malformed", f"{len(words)} words, not a single name")
    if re.search(r"\d", raw):
        return Candidate(raw, "malformed", "contains digits")

    name = clean_name(raw)
    if not name or not _name_shape_ok(name):
        return Candidate(raw, "malformed", "does not look like a name")
    if name.lower() in NAME_ARTIFACTS:
        return Candidate(raw, "artifact", f"known stt artifact: {name.lower()!r}")

    return Candidate(raw, "name_like", "bare answer to the name question", name)


def is_confirmation_question(text: str) -> bool:
    """True when Sabi is repeating a name back for confirmation."""
    return bool(_CONFIRMATION_QUESTION.search(str(text or "")))


def parse_yes_no(text: str) -> bool | None:
    """Read a confirmation reply. None means the answer was not a yes/no."""
    raw = str(text or "").strip()
    if not raw:
        return None
    if _NO.search(raw):
        return False
    if _YES.search(raw):
        return True
    return None


def confirmation_line(name: str) -> str:
    """What Sabi should say after hearing a candidate name."""
    return f"Did I hear you right, is your name {name}?"


def capture(messages: list[dict[str, str]], max_attempts: int = 2) -> CaptureResult:
    """Derive the learner's name from a transcript deterministically.

    A candidate is only ``confirmed_repeat`` when Sabi asked a confirmation
    question and the child answered yes. Without that turn the best possible
    status is ``unverified_utterance``: usable for continuity, never as the
    trusted identity for research export or caregiver records.
    """
    result = CaptureResult()
    if not messages:
        return result

    pending: Candidate | None = None
    asked_for_name = False
    awaiting_confirmation = False

    for index, message in enumerate(messages):
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")

        if role == "assistant":
            if is_confirmation_question(content):
                awaiting_confirmation = True
                asked_for_name = False
            else:
                awaiting_confirmation = False
                asked_for_name = "your name" in content.lower()
            continue

        if role != "user":
            continue

        if awaiting_confirmation and pending is not None:
            # A correction ("no, my name is Amina") is a new candidate, not a plain no.
            correction = assess_answer(content, asked_for_name=True)
            if correction.accepted and correction.reason == "self-introduction":
                result.rejections.append((pending.text, "child corrected the repeated name"))
                result.attempts += 1
                pending = correction
                awaiting_confirmation = False
                asked_for_name = False
                continue

            answer = parse_yes_no(content)
            if answer is True:
                result.name = pending.name
                result.status = STATUS_CONFIRMED_REPEAT
                result.confirmed = True
                result.attempts = max(result.attempts, 1)
                return result
            if answer is False:
                result.rejections.append((content, "child rejected the repeated name"))
                pending = None
            else:
                # Child answered with a different name instead of yes/no.
                retry = assess_answer(content, asked_for_name=True)
                if retry.accepted:
                    result.rejections.append((pending.text, "child offered a different name"))
                    pending = retry
                    result.attempts += 1
                else:
                    result.rejections.append((content, retry.reason))
            awaiting_confirmation = False
            asked_for_name = False
            continue

        if not asked_for_name:
            continue

        candidate = assess_answer(content, asked_for_name=True)
        if not candidate.accepted:
            result.rejections.append((content, f"{candidate.verdict}: {candidate.reason}"))
            continue

        result.attempts += 1
        if result.attempts > max_attempts:
            break
        pending = candidate
        asked_for_name = False

    if pending is not None:
        result.name = pending.name
        result.status = STATUS_UNVERIFIED
    elif result.rejections:
        result.status = STATUS_REJECTED
    return result


def identity_event_payloads(
    result: CaptureResult,
    student_id: str | None = None,
    call_sid: str | None = None,
) -> list[dict]:
    """Rows for sabi_identity_events describing how this capture was reached."""
    events: list[dict] = []
    for text, reason in result.rejections:
        events.append(
            {
                "student_id": student_id,
                "event_type": "name_rejected",
                "field": "name",
                "new_value": str(text)[:200],
                "source": "phone_stt",
                "actor": "sabi",
                "call_sid": call_sid,
                "reason": reason,
            }
        )
    if result.name:
        events.append(
            {
                "student_id": student_id,
                "event_type": "name_confirmed" if result.confirmed else "name_candidate",
                "field": "name",
                "new_value": result.name,
                "source": result.source,
                "actor": "child" if result.confirmed else "sabi",
                "call_sid": call_sid,
                "reason": f"status={result.status}",
            }
        )
    return events
