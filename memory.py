"""
Student memory management for Sabi voice server.
Connects to the same Supabase instance as the Next.js app.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client

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

    async def find_or_create_student(self, phone_number: str) -> dict:
        """Find existing student by phone or create new one."""
        if not self.client:
            return {"id": "demo", "name": None, "current_module": 0, "is_new": True}

        # Look up existing
        result = self.client.table("sabi_students").select("*").eq(
            "phone_number", phone_number
        ).maybe_single().execute()

        if result.data:
            return {**result.data, "is_new": False}

        # Create new student
        result = self.client.table("sabi_students").insert({
            "phone_number": phone_number,
            "current_module": 0,
            "current_level": "beginner",
            "total_sessions": 0,
            "total_correct": 0,
            "total_wrong": 0,
            "skills": {},
        }).select("*").single().execute()

        return {**result.data, "is_new": True}

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
            ).maybe_single().execute()

            if not student_result.data:
                return ""

            student = student_result.data
            current_module = student.get("current_module", 0)
            module_name = MODULE_NAMES.get(current_module, "diagnostic")

            # Get last 5 sessions
            sessions_result = self.client.table("sabi_sessions").select(
                "summary, correct_count, wrong_count, created_at"
            ).eq("student_id", student_id).order(
                "created_at", desc=True
            ).limit(5).execute()

            sessions = sessions_result.data or []

            # New student
            if current_module == 0 and not sessions:
                name = student.get("name")
                if name:
                    return f"""

## STUDENT CONTEXT: NEW STUDENT — RUN DIAGNOSTIC
- Name: {name}
- This is their FIRST session ever.
- current_module: 0 (needs diagnostic)
- Greet them by name. Run the DIAGNOSTIC flow.
- Do NOT ask their name — you already know it."""
                return """

## STUDENT CONTEXT: BRAND NEW
- current_module: 0 (needs diagnostic)
- First message: greet warmly, ask their name, then run diagnostic."""

            # Returning student
            if sessions:
                last_session = sessions[0]
                time_since = self._time_since(last_session.get("created_at", ""))

                skills = student.get("skills", {})
                skills_str = "\n".join(
                    f"  - {k}: {round(v * 100)}%"
                    for k, v in skills.items()
                ) if skills else "  No per-skill data yet"

                prev_sessions = "; ".join(
                    s.get("summary", "") for s in sessions[1:4] if s.get("summary")
                )

                return f"""

## STUDENT CONTEXT: RETURNING STUDENT
- Name: {student.get('name', 'Student')}
- Sessions completed: {student.get('total_sessions', 0)}
- Current module: {current_module} ({module_name})
- Current level: {student.get('current_level', 'beginner')}
- Last session ({time_since}): {last_session.get('summary', 'No summary')}
- Overall accuracy: {student.get('total_correct', 0)} correct, {student.get('total_wrong', 0)} wrong
- Skills:
{skills_str}
{f'- Previous sessions: {prev_sessions}' if prev_sessions else ''}

## INSTRUCTIONS FOR THIS SESSION:
- Greet {student.get('name', 'the student')} warmly by name. Do NOT ask their name.
- Start with ONE recall question from last session (spaced repetition).
- Then teach Module {current_module} ({module_name}) content.
- Follow the LESSON STRUCTURE: Greeting+Recall → Lesson → Guided Practice → Independent Check → Wrap-up."""

            return ""

        except Exception as e:
            logger.error(f"Memory error: {e}")
            return ""

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
