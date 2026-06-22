#!/usr/bin/env python3
"""Regression checks for Sabi learner-continuity admin review."""

from __future__ import annotations

import asyncio
import sys
import types

sys.modules.setdefault(
    "supabase",
    types.SimpleNamespace(create_client=lambda *args, **kwargs: None),
)

from learning_state import default_learning_state
from memory import StudentMemory, _learning_state_snapshot_message


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.filters: list[tuple[str, str, object]] = []
        self.order_column = ""
        self.order_desc = False
        self.limit_count: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, values))
        return self

    def like(self, column, pattern):
        self.filters.append(("like", column, pattern))
        return self

    def order(self, column, desc=False):
        self.order_column = column
        self.order_desc = bool(desc)
        return self

    def limit(self, count):
        self.limit_count = int(count)
        return self

    def execute(self):
        rows = self.client.tables.get(self.table_name, [])
        for op, column, value in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif op == "in":
                rows = [row for row in rows if row.get(column) in value]
            elif op == "like":
                prefix = str(value).replace("%", "")
                rows = [row for row in rows if str(row.get(column) or "").startswith(prefix)]
        if self.order_column:
            rows = sorted(rows, key=lambda row: str(row.get(self.order_column) or ""), reverse=self.order_desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return FakeResult([dict(row) for row in rows])


class FakeSupabaseClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, table_name: str):
        return FakeQuery(self, table_name)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail else ""))
    return condition


def main() -> int:
    ok = True
    snapshot = default_learning_state()
    snapshot.update(
        {
            "course": "numeracy",
            "phase": "guided_practice",
            "onboarding_status": "complete",
            "diagnostic_status": "done",
            "current_module": 2,
            "current_week": 5,
            "current_lesson": 2,
            "tarl_level": 2,
            "active_skill": "addition",
            "next_step": "Continue Module 2, Week 5, Lesson 2.",
        }
    )

    fake_client = FakeSupabaseClient(
        {
            "sabi_students": [
                {
                    "id": "remi-row",
                    "phone_number": "+2348033374126",
                    "phone_number_normalized": "+2348033374126",
                    "phone_household_key": "+2348033374126",
                    "name": "Remi",
                    "child_name_normalized": "remi",
                    "learner_key": "+2348033374126::remi",
                    "total_sessions": 3,
                    "total_correct": 5,
                    "total_wrong": 2,
                    "current_module": 0,
                    "baseline_status": "done",
                    "created_at": "2026-06-20T10:00:00Z",
                },
                {
                    "id": "amara-row",
                    "phone_number": "+2348033374126::amara",
                    "browser_id": "sabi-phone::+2348033374126::amara",
                    "name": "Amara",
                    "total_sessions": 1,
                    "total_correct": 1,
                    "total_wrong": 0,
                    "current_module": 1,
                    "baseline_status": "done",
                    "created_at": "2026-06-20T11:00:00Z",
                },
            ],
            "sabi_sessions": [
                {
                    "id": "older-session",
                    "student_id": "remi-row",
                    "created_at": "2026-06-20T12:00:00Z",
                    "summary": "Older onboarding session.",
                    "messages": [{"role": "assistant", "content": "Hello Remi"}],
                    "correct_count": 0,
                    "wrong_count": 0,
                    "duration_seconds": 45,
                    "call_sid": "old-call",
                    "phone_number": "+2348033374126",
                    "channel": "asterisk_audiosocket",
                },
                {
                    "id": "latest-session",
                    "student_id": "remi-row",
                    "created_at": "2026-06-21T12:00:00Z",
                    "summary": "Remi practiced addition.",
                    "messages": [
                        {"role": "assistant", "content": "What is two plus two?"},
                        {"role": "user", "content": "Four"},
                        {"role": "assistant", "content": "Good, four is correct."},
                        _learning_state_snapshot_message(snapshot),
                    ],
                    "correct_count": 1,
                    "wrong_count": 0,
                    "duration_seconds": 360,
                    "call_sid": "latest-call",
                    "phone_number": "+2348033374126",
                    "channel": "asterisk_audiosocket",
                    "recommended_module": 2,
                },
                {
                    "id": "amara-session",
                    "student_id": "amara-row",
                    "created_at": "2026-06-21T13:00:00Z",
                    "summary": "Amara started counting.",
                    "messages": [{"role": "user", "content": "Amara"}],
                    "correct_count": 0,
                    "wrong_count": 0,
                    "duration_seconds": 80,
                    "call_sid": "amara-call",
                    "phone_number": "+2348033374126::amara",
                    "channel": "asterisk_audiosocket",
                },
            ],
        }
    )
    memory = StudentMemory()
    memory.client = fake_client

    review = asyncio.run(memory.review_phone_continuity("08033374126", limit=2))
    profiles = review.get("profiles") or []
    remi = profiles[0] if profiles else {}
    remi_sessions = remi.get("recent_sessions") or []

    ok &= check("review_status_ok", review["status"] == "ok", review)
    ok &= check(
        "review_normalizes_local_phone",
        review["normalized_phone"] == "+2348033374126"
        and "08033374126" in review["lookup_variants"],
        review,
    )
    ok &= check(
        "review_lists_shared_phone_profiles",
        review["profile_count"] == 2
        and review["needs_identity_confirmation"] is True
        and {profile["name"] for profile in profiles} == {"Remi", "Amara"},
        review,
    )
    ok &= check(
        "review_reconstructs_effective_lesson_state",
        remi["name"] == "Remi"
        and remi["effective_state"]["current_module"] == 2
        and remi["effective_state"]["current_week"] == 5
        and remi["effective_state"]["current_lesson"] == 2
        and remi["effective_state"]["active_skill"] == "addition",
        remi,
    )
    ok &= check(
        "review_includes_recent_session_evidence",
        len(remi_sessions) == 2
        and remi_sessions[0]["call_sid"] == "latest-call"
        and remi_sessions[0]["has_learning_state_snapshot"] is True
        and remi_sessions[0]["last_child_turn_preview"] == "Four",
        remi_sessions,
    )
    ok &= check(
        "review_preserves_compatibility_profile",
        any(
            profile["name"] == "Amara"
            and profile["phone_number"] == "+2348033374126::amara"
            and profile["browser_id"] == "sabi-phone::+2348033374126::amara"
            for profile in profiles
        ),
        profiles,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
