"""
Student memory management for Sabi voice server.
Connects to the same Supabase instance as the Next.js app.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client

from learning_state import analyze_session, build_learning_state_prompt, default_learning_state, merge_learning_state
from phone_utils import normalize_phone_number, phone_lookup_variants
from secret_loader import get_secret

logger = logging.getLogger("sabi.memory")

MODULE_NAMES = {
    0: "diagnostic",
    1: "counting",
    2: "addition",
    3: "subtraction",
    4: "multiplication",
    5: "division",
    6: "word_problems",
    7: "completed",
}

OPTIONAL_STUDENT_COLUMNS = {
    "current_module",
    "current_topic",
    "skills",
    "phone_number_normalized",
    "learning_state",
    "baseline_status",
    "diagnostic_results",
    "current_week",
    "current_lesson",
    "tarl_level",
}

OPTIONAL_SESSION_COLUMNS = {
    "topics_covered",
    "recommended_module",
    "phone_number",
    "call_sid",
    "channel",
}


class StudentMemory:
    def __init__(self):
        url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            logger.warning("Supabase not configured. Memory disabled.")
            self.client = None
        else:
            self.client = create_client(url, key)
            logger.info("Supabase connected for student memory.")

        # In-memory call state (conversation history during active calls)
        self._call_messages: dict[str, list[dict]] = {}

    def get_call_messages(self, call_id: str) -> list[dict]:
        """Get conversation history for an active call."""
        return self._call_messages.get(call_id, [])

    def set_call_messages(self, call_id: str, messages: list[dict]):
        """Update conversation history for an active call."""
        self._call_messages[call_id] = messages

    def clear_call(self, call_id: str):
        """Clear call state after call ends."""
        self._call_messages.pop(call_id, None)

    async def save_phone_session(
        self,
        student_id: str,
        phone_number: str,
        call_id: str,
        messages: list[dict],
        duration_seconds: int,
        channel: str = "asterisk_audiosocket",
    ):
        """Persist a completed PBX/AudioSocket phone session for monitoring."""
        if not self.client or not student_id or not messages:
            return

        cleaned_messages = [
            {
                "role": message.get("role"),
                "content": message.get("content", ""),
            }
            for message in messages
            if message.get("role") in {"user", "assistant"}
        ]
        if not cleaned_messages:
            return

        user_turns = sum(1 for message in cleaned_messages if message["role"] == "user")
        assistant_turns = sum(1 for message in cleaned_messages if message["role"] == "assistant")
        summary = (
            f"Phone lesson completed with {user_turns} child turn"
            f"{'s' if user_turns != 1 else ''} and {assistant_turns} Sabi turn"
            f"{'s' if assistant_turns != 1 else ''}."
        )

        try:
            student_result = self.client.table("sabi_students").select("*").eq(
                "id", student_id
            ).execute()
            student = student_result.data[0] if student_result.data else {}
            current_module = student.get("current_module", 0) or 0
            module_name = MODULE_NAMES.get(current_module, "diagnostic")
            stats = analyze_session(student, cleaned_messages)
            summary = stats.summary or summary
            normalized_phone = normalize_phone_number(phone_number)

            session_payload = {
                "student_id": student_id,
                "messages": cleaned_messages,
                "summary": summary,
                "correct_count": stats.correct_count,
                "wrong_count": stats.wrong_count,
                "duration_seconds": duration_seconds,
                "topics_covered": stats.topics_covered or [module_name],
                "recommended_module": stats.recommended_module,
                "phone_number": normalized_phone,
                "call_sid": call_id,
                "channel": channel,
            }

            try:
                self.client.table("sabi_sessions").insert(session_payload).execute()
            except Exception as exc:
                # Older DBs may not have the pre-pilot monitoring columns yet.
                if not _mentions_any_column(exc, OPTIONAL_SESSION_COLUMNS):
                    raise
                fallback_payload = {
                    key: value
                    for key, value in session_payload.items()
                    if key not in OPTIONAL_SESSION_COLUMNS
                }
                self.client.table("sabi_sessions").insert(fallback_payload).execute()

            existing_skills = student.get("skills") if isinstance(student.get("skills"), dict) else {}
            merged_skills = dict(existing_skills or {})
            for skill, score in (stats.skills or {}).items():
                merged_skills[skill] = max(float(merged_skills.get(skill, 0) or 0), float(score))

            update_payload = {
                "name": stats.child_name or student.get("name"),
                "total_sessions": (student.get("total_sessions") or 0) + 1,
                "total_correct": (student.get("total_correct") or 0) + stats.correct_count,
                "total_wrong": (student.get("total_wrong") or 0) + stats.wrong_count,
                "current_level": stats.current_level,
                "current_module": stats.recommended_module,
                "current_topic": MODULE_NAMES.get(stats.recommended_module, "diagnostic"),
                "skills": merged_skills,
                "learning_state": stats.learning_state,
                "baseline_status": "done" if stats.learning_state.get("diagnostic_status") == "done" else student.get("baseline_status", "not_started"),
                "diagnostic_results": (
                    stats.learning_state.get("diagnostic_results")
                    if current_module == 0
                    else student.get("diagnostic_results")
                ),
                "current_week": stats.learning_state.get("current_week", 1),
                "current_lesson": stats.learning_state.get("current_lesson", 1),
                "tarl_level": stats.learning_state.get("tarl_level", 0),
                "last_session_summary": summary,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            update_payload = {key: value for key, value in update_payload.items() if value is not None}
            self._update_student_with_fallback(student_id, update_payload)

            logger.info(
                "Saved phone session student=%s phone=%s call_id=%s duration=%ss turns=%s correct=%s wrong=%s module=%s",
                student_id,
                normalized_phone,
                call_id,
                duration_seconds,
                user_turns,
                stats.correct_count,
                stats.wrong_count,
                stats.recommended_module,
            )
        except Exception as e:
            logger.error("Failed to save phone session call_id=%s: %s", call_id, e)

    async def find_or_create_student(self, phone_number: str) -> dict:
        """Find existing student by phone or create new one."""
        if not self.client:
            return {"id": "demo", "name": None, "current_module": 0, "is_new": True}

        normalized_phone = normalize_phone_number(phone_number)
        variants = phone_lookup_variants(phone_number)

        row = self._lookup_student_by_phone(normalized_phone, variants)
        if row:
            return {**row, "is_new": False}

        # Create new student (only columns that exist in the table)
        insert_payload = {
            "phone_number": normalized_phone,
            "phone_number_normalized": normalized_phone,
            "current_level": "beginner",
            "current_module": 0,
            "current_topic": "diagnostic",
            "skills": {},
            "learning_state": default_learning_state(),
            "baseline_status": "not_started",
            "current_week": 1,
            "current_lesson": 1,
            "tarl_level": 0,
            "total_sessions": 0,
            "total_correct": 0,
            "total_wrong": 0,
        }
        try:
            result = self._insert_student_with_fallback(insert_payload)
        except Exception as exc:
            # If another call created this learner between our lookup and
            # insert, recover the existing row instead of failing the lesson.
            if _is_duplicate_key_error(exc):
                row = self._lookup_student_by_phone(normalized_phone, variants)
                if row:
                    logger.info("Recovered existing student after duplicate phone insert: %s", normalized_phone)
                    return {**row, "is_new": False}
            raise

        if result and result.data and len(result.data) > 0:
            return {**result.data[0], "is_new": True}
        row = self._lookup_student_by_phone(normalized_phone, variants)
        if row:
            return {**row, "is_new": False}
        return {"id": "new", "name": None, "current_module": 0, "is_new": True}

    async def get_student_context(self, student_id: str) -> str:
        """
        Load student memory context for LLM system prompt.
        Same format as the Next.js app's getStudentMemory().
        """
        if not self.client:
            return ""

        try:
            # Get student
            student_result = self.client.table("sabi_students").select("*").eq(
                "id", student_id
            ).execute()

            if not student_result or not student_result.data or len(student_result.data) == 0:
                return ""

            student = student_result.data[0]
            current_module = student.get("current_module", 0)
            module_name = MODULE_NAMES.get(current_module, "diagnostic")
            learning_prompt = build_learning_state_prompt(student)

            # Get recent sessions. On the current thin Supabase schema, module
            # state may only exist inside historical transcripts, so we replay
            # them oldest-to-newest to reconstruct continuation state.
            sessions_result = self.client.table("sabi_sessions").select(
                "summary, correct_count, wrong_count, created_at, messages"
            ).eq("student_id", student_id).order(
                "created_at", desc=True
            ).limit(20).execute()

            sessions = sessions_result.data or []
            effective_state = self._effective_state_from_student_and_sessions(student, sessions)
            effective_module = int(effective_state.get("current_module") or current_module or 0)
            module_name = MODULE_NAMES.get(effective_module, module_name)
            student_for_prompt = {**student, "learning_state": effective_state, "current_module": effective_module}
            learning_prompt = build_learning_state_prompt(student_for_prompt)

            # New student
            if effective_module == 0 and not sessions:
                name = student.get("name")
                if name:
                    return f"""

## STUDENT CONTEXT: NEW STUDENT — RUN DIAGNOSTIC
- Name: {name}
- This is their FIRST session ever.
- current_module: 0 (needs diagnostic)
- Greet them by name. Run the DIAGNOSTIC flow as a game, not a test.
- Do NOT ask their name — you already know it.
{learning_prompt}"""
                return """

## STUDENT CONTEXT: BRAND NEW
- current_module: 0 (needs diagnostic)
- First message: greet warmly, ask their name, then run diagnostic."""

            # Returning student
            if sessions:
                last_session = sessions[0]
                time_since = self._time_since(last_session.get("created_at", ""))
                diagnostic_status = effective_state.get("diagnostic_status", "not_started")
                onboarding_status = effective_state.get("onboarding_status", "needs_name")

                if effective_module == 0 and diagnostic_status != "done":
                    return f"""

## STUDENT CONTEXT: RETURNING STUDENT — RESUME ONBOARDING/BASELINE
- Name: {student.get('name', 'Student')}
- Sessions completed: {student.get('total_sessions', 0)}
- Last session ({time_since}): {last_session.get('summary', 'No summary')}
- Current module: 0 (baseline not complete)
- Onboarding status: {onboarding_status}
- Diagnostic status: {diagnostic_status}

## INSTRUCTIONS FOR THIS SESSION:
- Do NOT restart from the beginning.
- Do NOT ask their name if a name is already known.
- Resume the exact next pending step: school question, market/family question, or the next baseline diagnostic game item.
- Keep it warm and low-pressure: this is a game, not a test.
{learning_prompt}"""

                skills = student.get("skills", {})
                skills_str = "\n".join(
                    f"  - {k}: {round(float(v) * 100)}%"
                    for k, v in skills.items()
                    if isinstance(v, (int, float))
                ) if skills else "  No per-skill data yet"

                prev_sessions = "; ".join(
                    s.get("summary", "") for s in sessions[1:4] if s.get("summary")
                )

                return f"""

## STUDENT CONTEXT: RETURNING STUDENT
- Name: {student.get('name', 'Student')}
- Sessions completed: {student.get('total_sessions', 0)}
- Current module: {effective_module} ({module_name})
- Current level: {student.get('current_level', 'beginner')}
- Last session ({time_since}): {last_session.get('summary', 'No summary')}
- Overall accuracy: {student.get('total_correct', 0)} correct, {student.get('total_wrong', 0)} wrong
- Skills:
{skills_str}
{f'- Previous sessions: {prev_sessions}' if prev_sessions else ''}

## INSTRUCTIONS FOR THIS SESSION:
- Greet {student.get('name', 'the student')} warmly by name. Do NOT ask their name.
- Start with ONE recall question from last session (spaced repetition).
- Then teach Module {effective_module} ({module_name}) content.
- Follow the LESSON STRUCTURE: Greeting+Recall → Lesson → Guided Practice → Independent Check → Wrap-up.
{learning_prompt}"""

            return ""

        except Exception as e:
            logger.error(f"Memory error: {e}")
            return ""

    async def get_effective_learning_state(self, student: dict) -> dict:
        """Return saved learning_state, or infer it from recent session messages."""
        if not self.client:
            return merge_learning_state(student)
        try:
            sessions_result = self.client.table("sabi_sessions").select(
                "messages, created_at"
            ).eq("student_id", student.get("id")).order(
                "created_at", desc=True
            ).limit(20).execute()
            return self._effective_state_from_student_and_sessions(
                student,
                sessions_result.data or [],
            )
        except Exception as exc:
            logger.debug("Could not infer effective learning state: %s", exc)
            return merge_learning_state(student)

    def _effective_state_from_student_and_sessions(self, student: dict, sessions: list[dict]) -> dict:
        state = merge_learning_state(student)
        if student.get("learning_state"):
            return state
        sessions_with_messages = [
            session for session in sessions
            if isinstance(session.get("messages"), list) and session.get("messages")
        ]
        if not sessions_with_messages:
            return state

        for session in sorted(sessions_with_messages, key=lambda row: str(row.get("created_at") or "")):
            try:
                student_for_analysis = {
                    **student,
                    "learning_state": state,
                    "current_module": int(state.get("current_module") or 0),
                }
                inferred = analyze_session(student_for_analysis, session.get("messages") or []).learning_state
                state = {**state, **inferred}
            except Exception as exc:
                logger.debug("Could not infer state from session messages created_at=%s: %s", session.get("created_at"), exc)
        return state

    def _insert_student_with_fallback(self, payload: dict):
        try:
            return self.client.table("sabi_students").insert(payload).execute()
        except Exception as exc:
            if not _mentions_any_column(exc, OPTIONAL_STUDENT_COLUMNS):
                raise
            fallback = {
                key: value for key, value in payload.items()
                if key not in OPTIONAL_STUDENT_COLUMNS
            }
            return self.client.table("sabi_students").insert(fallback).execute()

    def _lookup_student_by_phone(self, normalized_phone: str, variants: list[str]) -> dict | None:
        # Look up existing by normalized column when available, then historic
        # raw variants for rows created before this migration.
        try:
            result = self.client.table("sabi_students").select("*").eq(
                "phone_number_normalized", normalized_phone
            ).execute()
            if result and result.data:
                row = result.data[0]
                self._backfill_phone_identity(row.get("id"), normalized_phone)
                return row
        except Exception as exc:
            if not _mentions_any_column(exc, {"phone_number_normalized"}):
                logger.warning("Phone-normalized lookup failed: %s", exc)

        result = self.client.table("sabi_students").select("*").in_(
            "phone_number", variants
        ).execute()
        if result and result.data and len(result.data) > 0:
            row = _choose_canonical_student(result.data)
            self._backfill_phone_identity(row.get("id"), normalized_phone)
            return row
        return None

    def _update_student_with_fallback(self, student_id: str, payload: dict):
        try:
            return self.client.table("sabi_students").update(payload).eq("id", student_id).execute()
        except Exception as exc:
            if not _mentions_any_column(exc, OPTIONAL_STUDENT_COLUMNS):
                raise
            fallback = {
                key: value for key, value in payload.items()
                if key not in OPTIONAL_STUDENT_COLUMNS
            }
            return self.client.table("sabi_students").update(fallback).eq("id", student_id).execute()

    def _backfill_phone_identity(self, student_id: str | None, normalized_phone: str):
        if not student_id or normalized_phone == "unknown":
            return
        payload = {
            "phone_number": normalized_phone,
            "phone_number_normalized": normalized_phone,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._update_student_with_fallback(student_id, payload)
        except Exception as exc:
            logger.debug("Could not backfill phone identity for %s: %s", student_id, exc)

    @staticmethod
    def _time_since(date_str: str) -> str:
        """Human-readable time since a date."""
        if not date_str:
            return "unknown"
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            diff = datetime.now(timezone.utc) - dt
            minutes = int(diff.total_seconds() / 60)
            if minutes < 60:
                return f"{minutes} minutes ago"
            hours = minutes // 60
            if hours < 24:
                return f"{hours} hours ago"
            days = hours // 24
            return f"{days} day{'s' if days > 1 else ''} ago"
        except (ValueError, TypeError):
            return "recently"


def _error_text(error: Exception) -> str:
    return " ".join(
        str(getattr(error, attr, "") or "")
        for attr in ("message", "details", "hint", "code")
    ) or str(error)


def _mentions_any_column(error: Exception, columns: set[str]) -> bool:
    text = _error_text(error).lower()
    return any(column.lower() in text for column in columns)


def _is_duplicate_key_error(error: Exception) -> bool:
    text = _error_text(error).lower()
    return "23505" in text or "duplicate key" in text or "unique constraint" in text


def _choose_canonical_student(rows: list[dict]) -> dict:
    """Pick the best existing row when historic duplicate phone rows exist."""
    def score(row: dict) -> tuple[int, int, str]:
        total_sessions = int(row.get("total_sessions") or 0)
        has_name = 1 if row.get("name") else 0
        created_at = str(row.get("created_at") or "")
        return (total_sessions, has_name, created_at)

    return sorted(rows, key=score, reverse=True)[0]
