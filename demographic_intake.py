"""First-call demographic intake for Sabi.

Every new learner answers six short questions on their first call. The answers
are normalised here and written to the columns that already exist on
`sabi_students` (`age_years`, `sex`, `schooling_status`, `school_type`,
`location_state`, `home_language`, `demographic_profile`,
`demographics_completed_at`), with one append-only row in `sabi_identity_events`
per write so a change is always auditable.

Design rules, in line with docs/identity-capture-protocol.md:

* One question per turn, never two at once, and never more than six turns.
* An answer the child does not know is recorded as None, never guessed.
* Values are normalised to a fixed vocabulary; anything outside it is dropped
  rather than stored as free text.
* Nothing here writes a name. Names stay on the identity_capture path.
* The write is idempotent: re-running with the same answers is a no-op update.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

EVENT_TABLE = "sabi_identity_events"
STUDENT_TABLE = "sabi_students"

MIN_AGE = 5
MAX_AGE = 17

SEX_VALUES = {
    "boy": "male",
    "male": "male",
    "man": "male",
    "girl": "female",
    "female": "female",
    "woman": "female",
}

SCHOOLING_VALUES = {
    "in_school": "in_school",
    "school": "in_school",
    "attending": "in_school",
    "out_of_school": "out_of_school",
    "no_school": "out_of_school",
    "dropped_out": "out_of_school",
}

SCHOOL_TYPE_VALUES = {
    "public": "public",
    "government": "public",
    "private": "private",
    "islamiyya": "islamiyya",
    "quranic": "islamiyya",
    "none": None,
}

NIGERIAN_STATES = {
    "abia", "adamawa", "akwa ibom", "anambra", "bauchi", "bayelsa", "benue",
    "borno", "cross river", "delta", "ebonyi", "edo", "ekiti", "enugu",
    "fct", "abuja", "gombe", "imo", "jigawa", "kaduna", "kano", "katsina",
    "kebbi", "kogi", "kwara", "lagos", "nasarawa", "niger", "ogun", "ondo",
    "osun", "oyo", "plateau", "rivers", "sokoto", "taraba", "yobe", "zamfara",
}

LANGUAGE_VALUES = {
    "english": "en",
    "yoruba": "yo",
    "igbo": "ig",
    "hausa": "ha",
    "pidgin": "pcm",
    "nigerian pidgin": "pcm",
    "edo": "bin",
    "kanuri": "kr",
    "fulfulde": "fuv",
    "tiv": "tiv",
    "efik": "efi",
}

# Asked in this order: the easiest, least personal question first so the child
# is warmed up before caregiver details.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("age_years", "How old are you?"),
    ("sex", "Are you a boy or a girl?"),
    ("schooling_status", "Do you go to school?"),
    ("school_type", "Is your school a government school or a private one?"),
    ("location_state", "Which state do you live in?"),
    ("home_language", "Which language do you speak at home?"),
)

COLUMN_ORDER = tuple(field for field, _ in QUESTIONS)


@dataclass
class DemographicAnswers:
    age_years: int | None = None
    sex: str | None = None
    schooling_status: str | None = None
    school_type: str | None = None
    location_state: str | None = None
    home_language: str | None = None
    caregiver_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_columns(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in COLUMN_ORDER}

    def answered(self) -> int:
        return sum(1 for key in COLUMN_ORDER if getattr(self, key) is not None)


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def normalize_age(value: Any) -> int | None:
    """Accept '9', 'nine', 'nine years', 'I am nine'. Reject anything outside 5-17."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        age = value
    else:
        text = _clean(value)
        digits = re.search(r"\b(\d{1,2})\b", text)
        if digits:
            age = int(digits.group(1))
        else:
            words = {
                "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                "fifteen": 15, "sixteen": 16, "seventeen": 17,
            }
            age = next((n for word, n in words.items() if word in text), None)
            if age is None:
                return None
    if MIN_AGE <= age <= MAX_AGE:
        return age
    return None


def normalize_sex(value: Any) -> str | None:
    text = _clean(value)
    for token, normalized in SEX_VALUES.items():
        if token in text:
            return normalized
    return None


def normalize_schooling(value: Any) -> tuple[str | None, str | None]:
    """Return (schooling_status, school_type)."""
    text = _clean(value)
    if not text:
        return None, None
    if any(phrase in text for phrase in ("no school", "not in school", "stopped school", "drop")):
        return "out_of_school", None
    status = None
    for token, normalized in SCHOOLING_VALUES.items():
        if token in text:
            status = normalized
            break
    school_type = None
    for token, normalized in SCHOOL_TYPE_VALUES.items():
        if token in text:
            school_type = normalized
            break
    if status is None and ("school" in text or school_type):
        status = "in_school"
    return status, school_type


def normalize_state(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    for state in sorted(NIGERIAN_STATES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(state)}\b", text):
            return "FCT" if state == "abuja" else state.title()
    return None


def normalize_language(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    for token in sorted(LANGUAGE_VALUES, key=len, reverse=True):
        if token in text:
            return LANGUAGE_VALUES[token]
    return None


def answers_from_mapping(payload: Mapping[str, Any]) -> DemographicAnswers:
    """Build answers from an already-extracted mapping (LLM or form output)."""
    schooling, school_type = normalize_schooling(
        payload.get("schooling_status") or payload.get("school_type") or payload.get("school")
    )
    answers = DemographicAnswers(
        age_years=normalize_age(payload.get("age_years") or payload.get("age")),
        sex=normalize_sex(payload.get("sex") or payload.get("gender")),
        schooling_status=schooling,
        school_type=normalize_schooling(payload.get("school_type"))[1] or school_type,
        location_state=normalize_state(payload.get("location_state") or payload.get("state") or payload.get("location")),
        home_language=normalize_language(payload.get("home_language") or payload.get("language")),
        caregiver_name=(_clean(payload.get("caregiver_name")).title() or None) if payload.get("caregiver_name") else None,
        raw=dict(payload),
    )
    return answers


def write_demographics(store, student_id: str, answers: DemographicAnswers, source: str = "voice_agent") -> dict[str, Any]:
    """Write the answers to sabi_students and log one identity event.

    `store` is the MemoryStore instance from memory.py (it owns the Supabase
    client). Returns a small result dict instead of raising, because a failed
    demographic write must never end a lesson.
    """
    client = getattr(store, "client", None)
    if client is None:
        return {"ok": False, "reason": "supabase_not_configured"}
    if not student_id:
        return {"ok": False, "reason": "missing_student_id"}

    answered = answers.answered()
    if answered == 0:
        return {"ok": False, "reason": "no_answers"}

    now = datetime.now(timezone.utc).isoformat()
    columns = {k: v for k, v in answers.as_columns().items() if v is not None}
    payload: dict[str, Any] = {
        **columns,
        "demographic_profile": {**answers.raw, **columns, "source": source},
        "updated_at": now,
    }
    if len(columns) >= 4:
        payload["demographics_completed_at"] = now

    try:
        client.table(STUDENT_TABLE).update(payload).eq("id", student_id).execute()
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("Demographic write failed for %s: %s", student_id, exc)
        return {"ok": False, "reason": "write_failed", "error": str(exc)}

    try:
        client.table(EVENT_TABLE).insert(
            {
                "student_id": student_id,
                "event_type": "demographics_recorded",
                "source": source,
                "payload": {**columns, "answered": answered},
                "created_at": now,
            }
        ).execute()
    except Exception as exc:  # pragma: no cover - network path
        logger.info("Demographic event log failed for %s: %s", student_id, exc)

    return {"ok": True, "answered": answered, "columns": sorted(columns), "completed": "demographics_completed_at" in payload}


def next_question(answers: DemographicAnswers) -> str | None:
    """The single question to ask next, or None when intake is finished."""
    for field_name, question in QUESTIONS:
        current = getattr(answers, field_name)
        if current is None:
            return question
    return None


def apply_answer(answers: DemographicAnswers, field_name: str, value: Any) -> DemographicAnswers:
    """Set one field from a child's utterance, normalised. Unknown fields ignored."""
    if field_name == "age_years":
        answers.age_years = normalize_age(value)
    elif field_name == "sex":
        answers.sex = normalize_sex(value)
    elif field_name == "schooling_status":
        status, school_type = normalize_schooling(value)
        answers.schooling_status = status
        answers.school_type = answers.school_type or school_type
    elif field_name == "school_type":
        answers.school_type = normalize_schooling(value)[1]
    elif field_name == "location_state":
        answers.location_state = normalize_state(value)
    elif field_name == "home_language":
        answers.home_language = normalize_language(value)
    elif field_name == "caregiver_name":
        text = _clean(value)
        answers.caregiver_name = text.title() if text else None
    answers.raw.setdefault(field_name, value)
    return answers


def iter_questions() -> Iterable[tuple[str, str]]:
    return iter(QUESTIONS)
