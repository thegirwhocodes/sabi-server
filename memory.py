"""
Student memory management for Sabi voice server.
Connects to the same Supabase instance as the Next.js app.
"""

import os
import logging
import json
import re
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client

from curriculum_path import advance_learning_state_after_mastery, build_curriculum_path_prompt
from learning_state import analyze_session, build_learning_state_prompt, default_learning_state, extract_child_name, merge_learning_state
from phone_utils import normalize_phone_number, phone_lookup_variants
from secret_loader import get_secret

logger = logging.getLogger("sabi.memory")

LEARNING_STATE_SNAPSHOT_PREFIX = "SABI_LEARNING_STATE_SNAPSHOT:"
COMPAT_LEARNER_PREFIX = "sabi-phone"

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
    "phone_household_key",
    "child_name_normalized",
    "learner_key",
}

OPTIONAL_SESSION_COLUMNS = {
    "topics_covered",
    "recommended_module",
    "phone_number",
    "call_sid",
    "channel",
}

OPTIONAL_FEEDBACK_COLUMNS = {
    "student_id",
    "phone_number",
    "call_sid",
    "channel",
    "participant_type",
    "consent_recorded",
    "assent_recorded",
    "recording_path",
    "transcript",
    "redacted_transcript",
    "tags",
    "metadata",
    "duration_seconds",
    "network",
    "review_status",
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
        starting_learning_state: Optional[dict] = None,
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
            normalized_phone = normalize_phone_number(phone_number)
            variants = phone_lookup_variants(phone_number)
            spoken_child_name = extract_child_name(cleaned_messages)
            original_student_id = student_id
            if spoken_child_name and student:
                resolved_student = self._resolve_student_for_session(
                    current_student=student,
                    normalized_phone=normalized_phone,
                    variants=variants,
                    child_name=spoken_child_name,
                )
                if resolved_student:
                    student = resolved_student
                    student_id = resolved_student.get("id") or student_id
                    if resolved_student.get("_identity_conflict_unresolved"):
                        logger.warning(
                            "Skipping shared-phone session save because DB still enforces one row per phone. "
                            "Run supabase-sabi-shared-phone-identity.sql. phone=%s current_student=%s child_name=%s",
                            normalized_phone,
                            original_student_id,
                            spoken_child_name,
                        )
                        return
                    if student_id != original_student_id:
                        starting_learning_state = None
                        logger.info(
                            "Resolved shared-phone learner phone=%s old_student=%s new_student=%s child_name=%s",
                            normalized_phone,
                            original_student_id,
                            student_id,
                            spoken_child_name,
                        )
            analysis_student = dict(student or {})
            if isinstance(starting_learning_state, dict) and starting_learning_state:
                analysis_student["learning_state"] = starting_learning_state
                analysis_student["current_module"] = int(
                    starting_learning_state.get("current_module")
                    or student.get("current_module")
                    or 0
                )
            current_module = analysis_student.get("current_module", 0) or 0
            module_name = MODULE_NAMES.get(current_module, "diagnostic")
            stats = analyze_session(analysis_student, cleaned_messages)
            summary = stats.summary or summary
            persisted_learning_state = dict(stats.learning_state or {})
            if stats.should_advance:
                persisted_learning_state = advance_learning_state_after_mastery(persisted_learning_state)
                if persisted_learning_state.get("course") == "literacy":
                    literacy_state = persisted_learning_state.get("literacy") or {}
                    summary = (
                        f"{summary} Next call should continue at Literacy Module "
                        f"{literacy_state.get('current_module')}, Week "
                        f"{literacy_state.get('current_week')}, Lesson "
                        f"{literacy_state.get('current_lesson')}."
                    )
                else:
                    summary = (
                        f"{summary} Next call should continue at Module "
                        f"{persisted_learning_state.get('current_module')}, Week "
                        f"{persisted_learning_state.get('current_week')}, Lesson "
                        f"{persisted_learning_state.get('current_lesson')}."
                    )
            persisted_module = int(persisted_learning_state.get("current_module") or stats.recommended_module or 0)
            persisted_messages = [
                *cleaned_messages,
                _learning_state_snapshot_message(persisted_learning_state),
            ]

            session_payload = {
                "student_id": student_id,
                "messages": persisted_messages,
                "summary": summary,
                "correct_count": stats.correct_count,
                "wrong_count": stats.wrong_count,
                "duration_seconds": duration_seconds,
                "topics_covered": stats.topics_covered or [MODULE_NAMES.get(persisted_module, module_name)],
                "recommended_module": persisted_module,
                "phone_number": normalized_phone,
                "call_sid": call_id,
                "channel": channel,
            }

            try:
                self._insert_with_optional_fallback(
                    "sabi_sessions",
                    session_payload,
                    OPTIONAL_SESSION_COLUMNS,
                )
            except Exception as exc:
                raise

            existing_skills = student.get("skills") if isinstance(student.get("skills"), dict) else {}
            merged_skills = dict(existing_skills or {})
            for skill, score in (stats.skills or {}).items():
                merged_skills[skill] = max(float(merged_skills.get(skill, 0) or 0), float(score))

            identity_name = stats.child_name or spoken_child_name or student.get("name")
            update_payload = {
                **_identity_payload_for_existing_row(student, normalized_phone, identity_name),
                "name": identity_name,
                "total_sessions": (student.get("total_sessions") or 0) + 1,
                "total_correct": (student.get("total_correct") or 0) + stats.correct_count,
                "total_wrong": (student.get("total_wrong") or 0) + stats.wrong_count,
                "current_level": stats.current_level,
                "current_module": persisted_module,
                "current_topic": MODULE_NAMES.get(persisted_module, "diagnostic"),
                "skills": merged_skills,
                "learning_state": persisted_learning_state,
                "baseline_status": "done" if persisted_learning_state.get("diagnostic_status") == "done" else student.get("baseline_status", "not_started"),
                "diagnostic_results": (
                    persisted_learning_state.get("diagnostic_results")
                    if current_module == 0
                    else student.get("diagnostic_results")
                ),
                "current_week": persisted_learning_state.get("current_week", 1),
                "current_lesson": persisted_learning_state.get("current_lesson", 1),
                "tarl_level": persisted_learning_state.get("tarl_level", 0),
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
                persisted_module,
            )
        except Exception as e:
            logger.error("Failed to save phone session call_id=%s: %s", call_id, e)

    async def save_call_feedback(
        self,
        *,
        student_id: str | None,
        phone_number: str,
        call_id: str,
        channel: str,
        participant_type: str,
        recording_path: str,
        transcript: str,
        duration_seconds: int,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        consent_recorded: bool = True,
        assent_recorded: bool = False,
    ) -> None:
        """Persist an optional end-of-call open feedback voice note."""
        if not self.client:
            return
        if not call_id or not recording_path:
            return

        payload = {
            "student_id": student_id,
            "phone_number": normalize_phone_number(phone_number),
            "call_sid": call_id,
            "channel": channel,
            "participant_type": participant_type,
            "consent_recorded": consent_recorded,
            "assent_recorded": assent_recorded,
            "recording_path": recording_path,
            "transcript": transcript,
            "redacted_transcript": _redact_feedback_text(transcript),
            "tags": tags or [],
            "metadata": metadata or {},
            "duration_seconds": duration_seconds,
            "review_status": "new",
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        try:
            self._insert_with_optional_fallback(
                "sabi_call_feedback",
                payload,
                OPTIONAL_FEEDBACK_COLUMNS,
            )
            logger.info("Saved call feedback call_id=%s duration=%ss", call_id, duration_seconds)
        except Exception as exc:
            logger.warning("Could not save call feedback call_id=%s: %s", call_id, exc)

    async def find_or_create_student(self, phone_number: str, child_name: str | None = None) -> dict:
        """Find existing student by phone/name identity or create new one."""
        if not self.client:
            return {"id": "demo", "name": None, "current_module": 0, "is_new": True}

        normalized_phone = normalize_phone_number(phone_number)
        variants = phone_lookup_variants(phone_number)

        if child_name:
            row = self._lookup_student_by_phone_and_name(normalized_phone, variants, child_name)
            if row:
                return {**row, "is_new": False}
            phone_row = self._lookup_student_by_phone(normalized_phone, variants)
            if phone_row:
                resolved = self._resolve_student_for_session(
                    current_student=phone_row,
                    normalized_phone=normalized_phone,
                    variants=variants,
                    child_name=child_name,
                )
                if resolved and not resolved.get("_identity_conflict_unresolved"):
                    return {
                        **resolved,
                        "is_new": resolved.get("id") != phone_row.get("id"),
                    }
                return {**phone_row, "is_new": False}

        row = self._lookup_student_by_phone(normalized_phone, variants)
        if row:
            return {**row, "is_new": False}

        # Create new student (only columns that exist in the table)
        insert_payload = {
            **_phone_identity_payload(normalized_phone, child_name),
            "name": child_name,
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
                row = (
                    self._lookup_student_by_phone_and_name(normalized_phone, variants, child_name)
                    if child_name
                    else self._lookup_student_by_phone(normalized_phone, variants)
                )
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
            curriculum_prompt = build_curriculum_path_prompt(
                effective_state,
                effective_module,
                student_for_prompt.get("course", "numeracy"),
            )

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
{learning_prompt}
{curriculum_prompt}"""
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
{learning_prompt}
{curriculum_prompt}"""

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
{learning_prompt}
{curriculum_prompt}"""

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
                snapshot = _learning_state_snapshot_from_messages(session.get("messages") or [])
                if snapshot:
                    state = _merge_state_snapshot(state, snapshot)
                    continue
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
        return self._insert_with_optional_fallback(
            "sabi_students",
            payload,
            OPTIONAL_STUDENT_COLUMNS,
        )

    def _lookup_student_by_phone(self, normalized_phone: str, variants: list[str]) -> dict | None:
        # Look up existing by normalized column when available, then historic
        # raw variants for rows created before this migration.
        try:
            result = self.client.table("sabi_students").select("*").eq(
                "phone_number_normalized", normalized_phone
            ).execute()
            if result and result.data:
                row = _choose_canonical_student(result.data)
                if not _is_compatibility_learner_row(row, normalized_phone):
                    self._backfill_phone_identity(row.get("id"), normalized_phone)
                return _annotate_shared_phone_profiles(row, result.data)
        except Exception as exc:
            if not _mentions_any_column(exc, {"phone_number_normalized"}):
                logger.warning("Phone-normalized lookup failed: %s", exc)

        result = self.client.table("sabi_students").select("*").in_(
            "phone_number", variants
        ).execute()
        if result and result.data and len(result.data) > 0:
            row = _choose_canonical_student(result.data)
            if not _is_compatibility_learner_row(row, normalized_phone):
                self._backfill_phone_identity(row.get("id"), normalized_phone)
            return _annotate_shared_phone_profiles(row, result.data)
        return None

    def _lookup_student_by_phone_and_name(
        self,
        normalized_phone: str,
        variants: list[str],
        child_name: str | None,
    ) -> dict | None:
        name_key = normalize_child_name_for_identity(child_name)
        if not name_key:
            return None
        learner_key = learner_key_for(normalized_phone, child_name)
        if learner_key:
            try:
                result = self.client.table("sabi_students").select("*").eq(
                    "learner_key", learner_key
                ).execute()
                if result and result.data:
                    return result.data[0]
            except Exception as exc:
                if not _mentions_any_column(exc, {"learner_key"}):
                    logger.warning("Learner-key lookup failed: %s", exc)

        compatibility_key = compatibility_learner_key_for(normalized_phone, child_name)
        if compatibility_key:
            for column in ("browser_id", "phone_number"):
                try:
                    result = self.client.table("sabi_students").select("*").eq(
                        column, compatibility_key
                    ).execute()
                    if result and result.data:
                        return result.data[0]
                except Exception as exc:
                    if not _mentions_any_column(exc, {column}):
                        logger.debug("Compatibility learner lookup failed column=%s: %s", column, exc)

        for row in self._lookup_student_rows_by_phone(normalized_phone, variants):
            row_name_key = (
                normalize_child_name_for_identity(row.get("child_name_normalized"))
                or normalize_child_name_for_identity(row.get("name"))
            )
            if row_name_key == name_key:
                if not _is_compatibility_learner_row(row, normalized_phone):
                    self._backfill_phone_identity(row.get("id"), normalized_phone, child_name)
                return row
        return None

    def _lookup_student_rows_by_phone(self, normalized_phone: str, variants: list[str]) -> list[dict]:
        rows: list[dict] = []
        try:
            result = self.client.table("sabi_students").select("*").eq(
                "phone_number_normalized", normalized_phone
            ).execute()
            rows.extend(result.data or [])
        except Exception as exc:
            if not _mentions_any_column(exc, {"phone_number_normalized"}):
                logger.debug("Phone-normalized multi-row lookup failed: %s", exc)

        try:
            result = self.client.table("sabi_students").select("*").in_(
                "phone_number", variants
            ).execute()
            rows.extend(result.data or [])
        except Exception as exc:
            logger.debug("Phone variant multi-row lookup failed: %s", exc)

        try:
            result = self.client.table("sabi_students").select("*").like(
                "phone_number", f"{normalized_phone}::%"
            ).execute()
            rows.extend(result.data or [])
        except Exception as exc:
            logger.debug("Compatibility phone-key lookup failed: %s", exc)

        try:
            result = self.client.table("sabi_students").select("*").like(
                "browser_id", f"{COMPAT_LEARNER_PREFIX}::{normalized_phone}::%"
            ).execute()
            rows.extend(result.data or [])
        except Exception as exc:
            logger.debug("Compatibility browser-key lookup failed: %s", exc)

        deduped: dict[str, dict] = {}
        for row in rows:
            key = str(row.get("id") or row.get("learner_key") or len(deduped))
            deduped[key] = row
        return list(deduped.values())

    def _resolve_student_for_session(
        self,
        current_student: dict,
        normalized_phone: str,
        variants: list[str],
        child_name: str,
    ) -> dict | None:
        name_key = normalize_child_name_for_identity(child_name)
        if not name_key:
            return current_student
        current_name_key = (
            normalize_child_name_for_identity(current_student.get("child_name_normalized"))
            or normalize_child_name_for_identity(current_student.get("name"))
        )
        if not current_name_key or current_name_key == name_key:
            self._backfill_phone_identity(current_student.get("id"), normalized_phone, child_name)
            updated = dict(current_student)
            updated.update(_phone_identity_payload(normalized_phone, child_name))
            updated["name"] = child_name
            return updated

        named_row = self._lookup_student_by_phone_and_name(normalized_phone, variants, child_name)
        if named_row:
            return named_row

        insert_payload = {
            **_phone_identity_payload(normalized_phone, child_name),
            "name": child_name,
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
            if _is_duplicate_key_error(exc):
                named_row = self._lookup_student_by_phone_and_name(normalized_phone, variants, child_name)
                if named_row:
                    return named_row
                compatibility_row = self._insert_compatibility_named_student(normalized_phone, child_name)
                if compatibility_row:
                    return compatibility_row
                logger.warning(
                    "Shared-phone named learner insert blocked by existing unique phone index; "
                    "run shared-phone identity migration. phone=%s child=%s",
                    normalized_phone,
                    child_name,
                )
                return {**current_student, "_identity_conflict_unresolved": True}
            raise
        if result and result.data:
            return result.data[0]
        return current_student

    def _insert_compatibility_named_student(self, normalized_phone: str, child_name: str) -> dict | None:
        compatibility_key = compatibility_learner_key_for(normalized_phone, child_name)
        if not compatibility_key:
            return None
        payload = {
            "browser_id": f"{COMPAT_LEARNER_PREFIX}::{compatibility_key}",
            "phone_number": compatibility_key,
            "name": child_name,
            "current_level": "beginner",
            "total_sessions": 0,
            "total_correct": 0,
            "total_wrong": 0,
        }
        try:
            result = self.client.table("sabi_students").insert(payload).execute()
            if result and result.data:
                logger.info(
                    "Created compatibility shared-phone learner row phone=%s child=%s",
                    normalized_phone,
                    child_name,
                )
                return result.data[0]
        except Exception as exc:
            if _is_duplicate_key_error(exc):
                return self._lookup_student_by_phone_and_name(
                    normalized_phone,
                    [normalized_phone, compatibility_key],
                    child_name,
                )
            if _mentions_any_column(exc, {"browser_id"}):
                try:
                    result = self.client.table("sabi_students").insert({
                        "phone_number": compatibility_key,
                        "name": child_name,
                        "current_level": "beginner",
                        "total_sessions": 0,
                        "total_correct": 0,
                        "total_wrong": 0,
                    }).execute()
                    if result and result.data:
                        return result.data[0]
                except Exception as fallback_exc:
                    logger.debug("Compatibility learner fallback insert failed: %s", fallback_exc)
            logger.debug("Compatibility learner insert failed: %s", exc)
        return None

    def _update_student_with_fallback(self, student_id: str, payload: dict):
        return self._update_with_optional_fallback(
            "sabi_students",
            payload,
            OPTIONAL_STUDENT_COLUMNS,
            "id",
            student_id,
        )

    def _insert_with_optional_fallback(self, table: str, payload: dict, optional_columns: set[str]):
        remaining_payload = dict(payload)
        removed_columns: set[str] = set()
        while True:
            try:
                return self.client.table(table).insert(remaining_payload).execute()
            except Exception as exc:
                missing = _mentioned_columns(exc, optional_columns) - removed_columns
                if not missing:
                    raise
                removed_columns.update(missing)
                remaining_payload = {
                    key: value
                    for key, value in remaining_payload.items()
                    if key not in missing
                }
                logger.debug(
                    "Retrying %s insert without missing optional columns: %s",
                    table,
                    sorted(missing),
                )

    def _update_with_optional_fallback(
        self,
        table: str,
        payload: dict,
        optional_columns: set[str],
        key_column: str,
        key_value: str,
    ):
        remaining_payload = dict(payload)
        removed_columns: set[str] = set()
        while True:
            try:
                return self.client.table(table).update(remaining_payload).eq(key_column, key_value).execute()
            except Exception as exc:
                missing = _mentioned_columns(exc, optional_columns) - removed_columns
                if not missing:
                    raise
                removed_columns.update(missing)
                remaining_payload = {
                    key: value
                    for key, value in remaining_payload.items()
                    if key not in missing
                }
                logger.debug(
                    "Retrying %s update without missing optional columns: %s",
                    table,
                    sorted(missing),
                )

    def _backfill_phone_identity(self, student_id: str | None, normalized_phone: str, child_name: str | None = None):
        if not student_id or normalized_phone == "unknown":
            return
        payload = {
            **_phone_identity_payload(normalized_phone, child_name),
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
    return bool(_mentioned_columns(error, columns))


def _mentioned_columns(error: Exception, columns: set[str]) -> set[str]:
    text = _error_text(error).lower()
    return {column for column in columns if column.lower() in text}


def _is_duplicate_key_error(error: Exception) -> bool:
    text = _error_text(error).lower()
    return "23505" in text or "duplicate key" in text or "unique constraint" in text


def _redact_feedback_text(text: str) -> str:
    redacted = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[phone]", text or "")
    redacted = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email]", redacted)
    return redacted[:2000]


def _choose_canonical_student(rows: list[dict]) -> dict:
    """Pick the best existing row when historic duplicate phone rows exist."""
    def score(row: dict) -> tuple[int, int, str]:
        total_sessions = int(row.get("total_sessions") or 0)
        has_name = 1 if row.get("name") else 0
        created_at = str(row.get("created_at") or "")
        return (total_sessions, has_name, created_at)

    return sorted(rows, key=score, reverse=True)[0]


def normalize_child_name_for_identity(name: str | None) -> str | None:
    """Stable child-name key for shared family phone profiles."""
    if not name:
        return None
    cleaned = re.sub(r"[^a-z0-9' ]+", " ", str(name).lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" '")
    if not cleaned:
        return None
    ignored = {
        "yes", "no", "okay", "ok", "hello", "hi", "thanks", "thank you",
        "i don't know", "i dont know",
    }
    return None if cleaned in ignored else cleaned


def learner_key_for(normalized_phone: str | None, child_name: str | None) -> str | None:
    phone_key = (normalized_phone or "").strip()
    name_key = normalize_child_name_for_identity(child_name)
    if not phone_key or phone_key == "unknown" or not name_key:
        return None
    return f"{phone_key}::{name_key}"


def compatibility_learner_key_for(normalized_phone: str | None, child_name: str | None) -> str | None:
    return learner_key_for(normalized_phone, child_name)


def _phone_identity_payload(normalized_phone: str, child_name: str | None = None) -> dict:
    payload = {
        "phone_number": normalized_phone,
        "phone_number_normalized": normalized_phone,
        "phone_household_key": normalized_phone,
    }
    child_name_normalized = normalize_child_name_for_identity(child_name)
    if child_name_normalized:
        payload["child_name_normalized"] = child_name_normalized
    learner_key = learner_key_for(normalized_phone, child_name)
    if learner_key:
        payload["learner_key"] = learner_key
    return payload


def _compatibility_identity_payload(normalized_phone: str, child_name: str | None = None) -> dict:
    compatibility_key = compatibility_learner_key_for(normalized_phone, child_name)
    if not compatibility_key:
        return {"phone_number": normalized_phone}
    return {
        "phone_number": compatibility_key,
        "browser_id": f"{COMPAT_LEARNER_PREFIX}::{compatibility_key}",
    }


def _identity_payload_for_existing_row(row: dict, normalized_phone: str, child_name: str | None = None) -> dict:
    if _is_compatibility_learner_row(row, normalized_phone):
        return _compatibility_identity_payload(normalized_phone, child_name or row.get("name"))
    return _phone_identity_payload(normalized_phone, child_name)


def _is_compatibility_learner_row(row: dict, normalized_phone: str) -> bool:
    phone_number = str(row.get("phone_number") or "")
    browser_id = str(row.get("browser_id") or "")
    return (
        phone_number.startswith(f"{normalized_phone}::")
        or browser_id.startswith(f"{COMPAT_LEARNER_PREFIX}::{normalized_phone}::")
    )


def _annotate_shared_phone_profiles(row: dict, rows: list[dict]) -> dict:
    """Mark rows where a phone number already belongs to multiple named learners."""
    names: list[str] = []
    seen: set[str] = set()
    for item in rows:
        name = item.get("name")
        key = (
            normalize_child_name_for_identity(item.get("child_name_normalized"))
            or normalize_child_name_for_identity(name)
        )
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(str(name or key).strip())

    annotated = dict(row)
    if len(names) > 1:
        annotated["shared_phone_profiles"] = names
        annotated["needs_identity_confirmation"] = True
    return annotated


def _learning_state_snapshot_message(state: dict) -> dict:
    return {
        "role": "system",
        "content": LEARNING_STATE_SNAPSHOT_PREFIX + json.dumps(
            state or {},
            separators=(",", ":"),
            sort_keys=True,
        ),
    }


def _learning_state_snapshot_from_messages(messages: list[dict]) -> dict | None:
    for message in reversed(messages or []):
        if message.get("role") != "system":
            continue
        content = str(message.get("content") or "")
        if not content.startswith(LEARNING_STATE_SNAPSHOT_PREFIX):
            continue
        try:
            snapshot = json.loads(content[len(LEARNING_STATE_SNAPSHOT_PREFIX):])
        except json.JSONDecodeError:
            return None
        return snapshot if isinstance(snapshot, dict) else None
    return None


def _merge_state_snapshot(base: dict, snapshot: dict) -> dict:
    merged = {**(base or {}), **(snapshot or {})}
    base_literacy = (base or {}).get("literacy")
    snapshot_literacy = (snapshot or {}).get("literacy")
    if isinstance(base_literacy, dict) or isinstance(snapshot_literacy, dict):
        merged["literacy"] = {
            **(base_literacy if isinstance(base_literacy, dict) else {}),
            **(snapshot_literacy if isinstance(snapshot_literacy, dict) else {}),
        }
    return merged
