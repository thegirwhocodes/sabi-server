#!/usr/bin/env python3
"""Regression checks for Sabi learner identity and adaptive state."""

from __future__ import annotations

import asyncio
import os
import sys
import types

os.environ.setdefault("SABI_SHARED_AUDIO_DIR", "/tmp/sabi-shared-audio")

sys.modules.setdefault(
    "supabase",
    types.SimpleNamespace(create_client=lambda *args, **kwargs: None),
)
sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(AsyncClient=lambda *args, **kwargs: None, Client=lambda *args, **kwargs: None),
)

from diagnostic_flow import (
    analyze_diagnostic_progress,
    analyze_literacy_diagnostic_progress,
    build_instructional_route_prompt,
    build_opening_turn,
)
from curriculum_path import (
    advance_learning_state_after_mastery,
    advance_numeracy_state_after_mastery,
    build_curriculum_path_prompt,
    resolve_literacy_lesson,
)
from learning_state import analyze_session, extract_child_name
from memory import StudentMemory, _learning_state_snapshot_message, learner_key_for
from phone_utils import normalize_phone_number, phone_lookup_variants
from voice_asterisk import (
    MIN_LESSON_SECONDS,
    MIN_WRAP_USER_TURNS,
    TARGET_WRAP_SECONDS,
    build_call_control_messages,
    is_premature_wrap_response,
    should_prompt_wrap_up,
    should_wrap_up,
)


class FakeSupabaseError(Exception):
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = ""
        self.hint = ""


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload = None
        self.filters: list[tuple[str, str, object]] = []

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, values))
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def execute(self):
        if self.table_name != "sabi_students":
            return FakeResult([])
        if self.operation == "select":
            rows = self.client.rows
            for op, column, value in self.filters:
                if column == "phone_number_normalized" and not self.client.has_normalized_column:
                    raise FakeSupabaseError("column sabi_students.phone_number_normalized does not exist", "42703")
                if column in self.client.missing_columns:
                    raise FakeSupabaseError(f"column sabi_students.{column} does not exist", "42703")
                if op == "eq":
                    rows = [row for row in rows if row.get(column) == value]
                elif op == "in":
                    rows = [row for row in rows if row.get(column) in value]
            return FakeResult([dict(row) for row in rows])
        if self.operation == "update":
            for op, column, value in self.filters:
                if column == "phone_number_normalized" and not self.client.has_normalized_column:
                    raise FakeSupabaseError("column sabi_students.phone_number_normalized does not exist", "42703")
                if column in self.client.missing_columns:
                    raise FakeSupabaseError(f"column sabi_students.{column} does not exist", "42703")
            for key in self.payload or {}:
                if key == "phone_number_normalized" and not self.client.has_normalized_column:
                    raise FakeSupabaseError("column sabi_students.phone_number_normalized does not exist", "42703")
                if key in self.client.missing_columns:
                    raise FakeSupabaseError(f"column sabi_students.{key} does not exist", "42703")
            updated = []
            for row in self.client.rows:
                match = all(row.get(column) == value for _, column, value in self.filters)
                if match:
                    row.update(self.payload or {})
                    updated.append(dict(row))
            return FakeResult(updated)
        if self.operation == "insert":
            payload = dict(self.payload or {})
            for key in payload:
                if key == "phone_number_normalized" and not self.client.has_normalized_column:
                    raise FakeSupabaseError("column sabi_students.phone_number_normalized does not exist", "42703")
                if key in self.client.missing_columns:
                    raise FakeSupabaseError(f"column sabi_students.{key} does not exist", "42703")
            if self.client.race_duplicate_row is not None:
                self.client.rows.append(dict(self.client.race_duplicate_row))
                self.client.race_duplicate_row = None
                raise FakeSupabaseError("duplicate key value violates unique constraint idx_sabi_students_phone", "23505")
            phone = payload.get("phone_number")
            learner_key = payload.get("learner_key")
            if learner_key and any(row.get("learner_key") == learner_key for row in self.client.rows):
                raise FakeSupabaseError("duplicate key value violates unique constraint idx_sabi_students_learner_key", "23505")
            if self.client.unique_phone and phone and any(row.get("phone_number") == phone for row in self.client.rows):
                raise FakeSupabaseError("duplicate key value violates unique constraint idx_sabi_students_phone", "23505")
            payload.setdefault("id", f"fake-{len(self.client.rows) + 1}")
            self.client.rows.append(payload)
            return FakeResult([dict(payload)])
        return FakeResult([])


class FakeSupabaseClient:
    def __init__(
        self,
        rows=None,
        has_normalized_column=False,
        missing_columns=None,
        race_duplicate_row=None,
        unique_phone=True,
    ):
        self.rows = list(rows or [])
        self.has_normalized_column = has_normalized_column
        self.missing_columns = set(missing_columns or [])
        self.race_duplicate_row = race_duplicate_row
        self.unique_phone = unique_phone

    def table(self, table_name: str):
        return FakeQuery(self, table_name)


def check(name: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"{mark:4} {name}{' - ' + detail if detail else ''}")
    return condition


def main() -> int:
    ok = True

    ok &= check(
        "normalize_ng_local",
        normalize_phone_number("08033374126") == "+2348033374126",
    )
    ok &= check(
        "normalize_ng_plus",
        normalize_phone_number("+234 803 337 4126") == "+2348033374126",
    )
    ok &= check(
        "lookup_variants",
        "08033374126" in phone_lookup_variants("+2348033374126"),
    )

    thin_memory = StudentMemory.__new__(StudentMemory)
    thin_memory.client = FakeSupabaseClient(
        rows=[
            {
                "id": "existing-phone",
                "phone_number": "08033374126",
                "name": "Remi",
                "total_sessions": 2,
                "created_at": "2026-06-01T00:00:00+00:00",
            }
        ],
        has_normalized_column=False,
        missing_columns={
            "current_module",
            "current_topic",
            "skills",
            "learning_state",
            "baseline_status",
            "diagnostic_results",
            "current_week",
            "current_lesson",
            "tarl_level",
        },
    )
    thin_lookup = asyncio.run(thin_memory.find_or_create_student("+2348033374126"))
    ok &= check(
        "thin_schema_lookup_reuses_existing_phone",
        thin_lookup["id"] == "existing-phone"
        and thin_lookup["is_new"] is False
        and thin_memory.client.rows[0]["phone_number"] == "+2348033374126",
        f"{thin_lookup} rows={thin_memory.client.rows}",
    )

    race_memory = StudentMemory.__new__(StudentMemory)
    race_memory.client = FakeSupabaseClient(
        rows=[],
        has_normalized_column=False,
        missing_columns={
            "current_module",
            "current_topic",
            "skills",
            "learning_state",
            "baseline_status",
            "diagnostic_results",
            "current_week",
            "current_lesson",
            "tarl_level",
        },
        race_duplicate_row={
            "id": "race-winner",
            "phone_number": "+2348033374126",
            "name": None,
            "total_sessions": 0,
            "created_at": "2026-06-01T00:00:00+00:00",
        },
    )
    race_lookup = asyncio.run(race_memory.find_or_create_student("08033374126"))
    ok &= check(
        "duplicate_insert_recovers_existing_student",
        race_lookup["id"] == "race-winner"
        and race_lookup["is_new"] is False
        and len(race_memory.client.rows) == 1,
        f"{race_lookup} rows={race_memory.client.rows}",
    )

    shared_phone_memory = StudentMemory.__new__(StudentMemory)
    shared_phone_memory.client = FakeSupabaseClient(
        rows=[
            {
                "id": "remi-row",
                "phone_number": "+2348033374126",
                "phone_number_normalized": "+2348033374126",
                "name": "Remi",
                "child_name_normalized": "remi",
                "learner_key": learner_key_for("+2348033374126", "Remi"),
                "total_sessions": 4,
                "created_at": "2026-06-01T00:00:00+00:00",
            },
            {
                "id": "amara-row",
                "phone_number": "+2348033374126",
                "phone_number_normalized": "+2348033374126",
                "name": "Amara",
                "child_name_normalized": "amara",
                "learner_key": learner_key_for("+2348033374126", "Amara"),
                "total_sessions": 1,
                "created_at": "2026-06-02T00:00:00+00:00",
            },
        ],
        has_normalized_column=True,
        unique_phone=False,
    )
    shared_lookup = asyncio.run(shared_phone_memory.find_or_create_student("+2348033374126"))
    ok &= check(
        "shared_phone_prompts_for_child_identity",
        shared_lookup["id"] == "remi-row"
        and shared_lookup.get("needs_identity_confirmation") is True
        and set(shared_lookup.get("shared_phone_profiles") or []) == {"Remi", "Amara"},
        f"{shared_lookup}",
    )
    remi_lookup = asyncio.run(shared_phone_memory.find_or_create_student("+2348033374126", child_name="Remi"))
    ok &= check(
        "shared_phone_same_child_reuses_named_profile",
        remi_lookup["id"] == "remi-row" and remi_lookup["is_new"] is False,
        f"{remi_lookup}",
    )
    tola_lookup = asyncio.run(shared_phone_memory.find_or_create_student("+2348033374126", child_name="Tola"))
    ok &= check(
        "shared_phone_direct_child_name_creates_missing_profile",
        tola_lookup["id"] not in {"remi-row", "amara-row"}
        and tola_lookup["name"] == "Tola"
        and tola_lookup["is_new"] is True
        and tola_lookup["learner_key"] == learner_key_for("+2348033374126", "Tola"),
        f"{tola_lookup}",
    )

    split_memory = StudentMemory.__new__(StudentMemory)
    split_memory.client = FakeSupabaseClient(
        rows=[
            {
                "id": "chidi-row",
                "phone_number": "+2348033374126",
                "phone_number_normalized": "+2348033374126",
                "name": "Chidi",
                "child_name_normalized": "chidi",
                "learner_key": learner_key_for("+2348033374126", "Chidi"),
                "total_sessions": 3,
                "created_at": "2026-06-01T00:00:00+00:00",
            },
        ],
        has_normalized_column=True,
        unique_phone=False,
    )
    amara_row = split_memory._resolve_student_for_session(
        current_student=split_memory.client.rows[0],
        normalized_phone="+2348033374126",
        variants=phone_lookup_variants("+2348033374126"),
        child_name="Amara",
    )
    ok &= check(
        "shared_phone_different_child_creates_separate_profile",
        amara_row["id"] != "chidi-row"
        and amara_row["name"] == "Amara"
        and amara_row["learner_key"] == learner_key_for("+2348033374126", "Amara")
        and split_memory.client.rows[0]["name"] == "Chidi"
        and len(split_memory.client.rows) == 2,
        f"amara={amara_row} rows={split_memory.client.rows}",
    )

    snapshot_memory = StudentMemory.__new__(StudentMemory)
    snapshot_state = {
        "course": "numeracy",
        "phase": "guided_practice",
        "diagnostic_status": "done",
        "current_module": 3,
        "current_week": 9,
        "current_lesson": 2,
        "tarl_level": 3,
        "active_skill": "subtraction",
        "wrong_streak": 1,
        "scaffold_depth": 1,
        "literacy": {"diagnostic_status": "not_started", "current_module": 1},
    }
    replayed_snapshot = snapshot_memory._effective_state_from_student_and_sessions(
        {"id": "thin-student", "name": "Remi"},
        [
            {
                "created_at": "2026-06-22T20:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "You have fifteen naira and spend eight. How much is left?"},
                    {"role": "user", "content": "seven"},
                    _learning_state_snapshot_message(snapshot_state),
                ],
            }
        ],
    )
    ok &= check(
        "session_snapshot_replay_preserves_module",
        replayed_snapshot["current_module"] == 3
        and replayed_snapshot["active_skill"] == "subtraction"
        and replayed_snapshot["scaffold_depth"] == 1
        and replayed_snapshot["literacy"]["current_module"] == 1,
        str(replayed_snapshot),
    )

    student = {
        "current_module": 2,
        "current_topic": "addition",
        "learning_state": {
            "current_module": 2,
            "active_skill": "addition",
            "correct_streak": 0,
            "wrong_streak": 1,
            "scaffold_depth": 0,
        },
    }
    messages = [
        {"role": "assistant", "content": "You buy pure water for ten naira and biscuits for five naira. How much altogether?"},
        {"role": "user", "content": "twelve naira"},
        {"role": "assistant", "content": "Almost. Let's try smaller. What is one plus one?"},
        {"role": "user", "content": "three"},
    ]
    stats = analyze_session(student, messages)
    ok &= check("wrong_count", stats.wrong_count == 2, f"got {stats.wrong_count}")
    ok &= check(
        "bump_down_scaffold",
        stats.learning_state["wrong_streak"] >= 3 and stats.learning_state["scaffold_depth"] >= 1,
        str(stats.learning_state),
    )
    ok &= check(
        "module_not_advanced_on_wrong",
        stats.recommended_module <= 2,
        f"module={stats.recommended_module}",
    )

    messages_correct = [
        {"role": "assistant", "content": "You buy pure water for ten naira and biscuits for five naira. How much altogether?"},
        {"role": "user", "content": "fifteen naira"},
    ]
    stats_correct = analyze_session({"current_module": 2, "current_topic": "addition"}, messages_correct)
    ok &= check("correct_count", stats_correct.correct_count == 1, f"got {stats_correct.correct_count}")
    ok &= check("wrong_zero", stats_correct.wrong_count == 0, f"got {stats_correct.wrong_count}")

    mastery_messages = [
        {"role": "assistant", "content": "You have ten naira and spend four naira. How much is left?"},
        {"role": "user", "content": "six naira"},
        {"role": "assistant", "content": "Good. You have fifteen naira and spend eight naira. How much is left?"},
        {"role": "user", "content": "seven"},
        {"role": "assistant", "content": "Sharp. Thirteen minus five. How much is left?"},
        {"role": "user", "content": "eight"},
    ]
    mastery_stats = analyze_session(
        {
            "current_module": 3,
            "learning_state": {
                "current_module": 3,
                "current_week": 9,
                "current_lesson": 2,
                "active_skill": "subtraction",
                "diagnostic_status": "done",
            },
        },
        mastery_messages,
    )
    ok &= check(
        "mastery_does_not_jump_module_mid_call",
        mastery_stats.recommended_module == 3 and mastery_stats.should_advance,
        str(mastery_stats.learning_state),
    )
    advanced_state = advance_numeracy_state_after_mastery(mastery_stats.learning_state)
    ok &= check(
        "mastery_advances_next_lesson_for_next_call",
        advanced_state["current_module"] == 3
        and advanced_state["current_week"] == 9
        and advanced_state["current_lesson"] == 3
        and "Lesson 3" in advanced_state["next_step"],
        str(advanced_state),
    )
    path_prompt = build_curriculum_path_prompt(
        {
            "current_module": 3,
            "current_week": 9,
            "current_lesson": 2,
            "active_skill": "subtraction",
            "diagnostic_status": "done",
        },
        3,
    )
    ok &= check(
        "curriculum_path_pins_exact_lesson",
        "Global Lesson 34" in path_prompt
        and "Think addition for subtraction" in path_prompt
        and "Do not jump to the next module" in path_prompt,
        path_prompt,
    )

    literacy_state = {
        "course": "literacy",
        "literacy": {
            "diagnostic_status": "done",
            "current_phase": 1,
            "current_module": 5,
            "current_week": 11,
            "current_lesson": 2,
            "active_skill": "advanced_phonemic_awareness",
        },
    }
    literacy_lesson = resolve_literacy_lesson(literacy_state)
    literacy_prompt = build_curriculum_path_prompt(literacy_state, course="literacy")
    ok &= check(
        "literacy_path_pins_exact_script_lesson",
        literacy_lesson["lesson_code"] == "42b"
        and "Changing the Last Sound" in literacy_prompt
        and "pure sounds" in literacy_prompt
        and "Do not claim print reading mastery" in literacy_prompt,
        literacy_prompt,
    )
    advanced_literacy = advance_learning_state_after_mastery(literacy_state)
    ok &= check(
        "literacy_mastery_advances_next_lesson_for_next_call",
        advanced_literacy["literacy"]["current_module"] == 5
        and advanced_literacy["literacy"]["current_week"] == 11
        and advanced_literacy["literacy"]["current_lesson"] == 3
        and "Lesson 3" in advanced_literacy["literacy"]["next_step"],
        str(advanced_literacy),
    )
    literacy_completed_stats = analyze_session(
        {"learning_state": literacy_state},
        [
            {"role": "assistant", "content": "Today we are changing the last sound in cat. Say cat."},
            {"role": "user", "content": "cat"},
            {"role": "assistant", "content": "Good. Change the last sound to d. What word?"},
            {"role": "user", "content": "cad"},
            {"role": "assistant", "content": "Today you learned to listen for the last sound. Next time we will change the middle sound."},
        ],
    )
    ok &= check(
        "completed_literacy_lesson_marks_advance",
        literacy_completed_stats.should_advance
        and literacy_completed_stats.learning_state["literacy"]["current_lesson"] == 2,
        str(literacy_completed_stats),
    )

    opening = build_opening_turn(
        {"name": "Remi", "current_module": 2, "current_topic": "addition"},
        {"current_module": 2, "active_skill": "addition", "diagnostic_status": "done"},
    )
    ok &= check("returning_opening_uses_name", "Welcome back, Remi" in opening, opening)
    ok &= check("returning_opening_no_name_request", "your name" not in opening.lower(), opening)

    shared_phone_opening = build_opening_turn(
        {
            "name": "Remi",
            "current_module": 2,
            "needs_identity_confirmation": True,
            "shared_phone_profiles": ["Remi", "Amara"],
        },
        {"current_module": 2, "active_skill": "addition", "diagnostic_status": "done"},
    )
    ok &= check(
        "shared_phone_opening_asks_identity",
        "your name" in shared_phone_opening.lower()
        and "more than one learner" in shared_phone_opening.lower(),
        shared_phone_opening,
    )

    unplaced_opening = build_opening_turn(
        {"name": "Remi", "current_module": 0},
        {"current_module": 0, "diagnostic_status": "not_started"},
    )
    ok &= check("unplaced_opening_starts_context", "do you go to school" in unplaced_opening.lower(), unplaced_opening)
    ok &= check("unplaced_opening_not_math_first", "twenty-nine" not in unplaced_opening.lower(), unplaced_opening)

    after_name_messages = [
        {"role": "assistant", "content": "Hello! I'm Sabi, your learning friend. Sabi means to know, and together, we're going to know so much! What is your name?"},
        {"role": "user", "content": "My name is Remi"},
    ]
    route = build_instructional_route_prompt(after_name_messages, current_module=0)
    ok &= check("onboarding_route_after_name", "do you go to school" in route.lower(), route)

    after_school_messages = [
        *after_name_messages,
        {"role": "assistant", "content": "Remi! I like that name. I will remember you on this number. Tell me, do you go to school?"},
        {"role": "user", "content": "yes"},
    ]
    route_after_school = build_instructional_route_prompt(after_school_messages, current_module=0)
    ok &= check("onboarding_route_after_school", "market" in route_after_school.lower(), route_after_school)

    after_market_messages = [
        *after_school_messages,
        {"role": "assistant", "content": "Do you help your family at the market, or do you sell anything?"},
        {"role": "user", "content": "I help my mum sell groundnuts"},
    ]
    route_after_market = build_instructional_route_prompt(after_market_messages, current_module=0)
    ok &= check("diagnostic_route_after_onboarding", "What number comes after twenty-nine?" in route_after_market, route_after_market)

    diagnostic_messages = [
        {"role": "assistant", "content": "Let's play a quick number game. What number comes after twenty-nine?"},
        {"role": "user", "content": "thirty"},
    ]
    progress = analyze_diagnostic_progress(diagnostic_messages)
    ok &= check("diagnostic_correct_in_progress", progress["status"] == "in_progress", str(progress))
    ok &= check("diagnostic_next_after_99", progress["next_item"]["id"] == "count_after_99", str(progress))

    diagnostic_wrong = [
        {"role": "assistant", "content": "Let's play a quick number game. What number comes after twenty-nine?"},
        {"role": "user", "content": "twenty one"},
    ]
    progress_wrong = analyze_diagnostic_progress(diagnostic_wrong)
    stats_wrong_diagnostic = analyze_session({"current_module": 0}, diagnostic_wrong)
    ok &= check("diagnostic_wrong_places", progress_wrong["status"] == "placed", str(progress_wrong))
    ok &= check(
        "diagnostic_wrong_module_week",
        stats_wrong_diagnostic.learning_state["current_module"] == 1
        and stats_wrong_diagnostic.learning_state["current_week"] == 1
        and stats_wrong_diagnostic.learning_state["diagnostic_status"] == "done",
        str(stats_wrong_diagnostic.learning_state),
    )

    ok &= check(
        "name_prompt_accepts_real_name",
        extract_child_name([
            {"role": "assistant", "content": "What is your name?"},
            {"role": "user", "content": "Naomi"},
        ]) == "Naomi",
    )
    ok &= check(
        "name_prompt_rejects_non_name",
        extract_child_name([
            {"role": "assistant", "content": "What is your name?"},
            {"role": "user", "content": "Thank you"},
        ]) is None,
    )

    memory = StudentMemory.__new__(StudentMemory)
    historical_state = memory._effective_state_from_student_and_sessions(
        {"id": "demo", "current_level": "beginner"},
        [
            {
                "created_at": "2026-06-01T10:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "Let's play a quick number game. What number comes after twenty-nine?"},
                    {"role": "user", "content": "twenty one"},
                ],
            },
            {
                "created_at": "2026-06-02T10:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "You have two groundnuts and get one more groundnut. How many groundnuts now?"},
                    {"role": "user", "content": "three"},
                ],
            },
        ],
    )
    ok &= check(
        "history_replay_keeps_placement_after_later_session",
        historical_state["current_module"] == 1
        and historical_state["diagnostic_status"] == "done"
        and historical_state["active_skill"] == "counting",
        str(historical_state),
    )

    name_only_state = memory._effective_state_from_student_and_sessions(
        {"id": "demo", "current_level": "beginner"},
        [
            {
                "created_at": "2026-06-01T09:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "Hello! I'm Sabi, your learning friend. What is your name?"},
                    {"role": "user", "content": "My name is Remi"},
                ],
            }
        ],
    )
    name_only_opening = build_opening_turn(
        {"name": "Remi", "current_level": "beginner"},
        name_only_state,
    )
    ok &= check(
        "resume_after_name_asks_school",
        name_only_state["onboarding_status"] == "needs_school"
        and "do you go to school" in name_only_opening.lower(),
        f"{name_only_state} | {name_only_opening}",
    )

    school_done_state = memory._effective_state_from_student_and_sessions(
        {"id": "demo", "name": "Remi", "current_level": "beginner"},
        [
            {
                "created_at": "2026-06-01T09:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "Hello! I'm Sabi, your learning friend. What is your name?"},
                    {"role": "user", "content": "My name is Remi"},
                    {"role": "assistant", "content": "Remi! I like that name. I will remember you on this number. Tell me, do you go to school?"},
                    {"role": "user", "content": "yes"},
                ],
            }
        ],
    )
    school_done_opening = build_opening_turn(
        {"name": "Remi", "current_level": "beginner"},
        school_done_state,
    )
    ok &= check(
        "resume_after_school_asks_market",
        school_done_state["onboarding_status"] == "needs_market"
        and "market" in school_done_opening.lower(),
        f"{school_done_state} | {school_done_opening}",
    )

    onboarding_done_state = memory._effective_state_from_student_and_sessions(
        {"id": "demo", "name": "Remi", "current_level": "beginner"},
        [
            {
                "created_at": "2026-06-01T09:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "Hello! I'm Sabi, your learning friend. What is your name?"},
                    {"role": "user", "content": "My name is Remi"},
                    {"role": "assistant", "content": "Remi! I like that name. I will remember you on this number. Tell me, do you go to school?"},
                    {"role": "user", "content": "yes"},
                    {"role": "assistant", "content": "Do you help your family at the market, or do you sell anything?"},
                    {"role": "user", "content": "I help my mum sell rice"},
                ],
            }
        ],
    )
    onboarding_done_opening = build_opening_turn(
        {"name": "Remi", "current_level": "beginner"},
        onboarding_done_state,
    )
    ok &= check(
        "resume_after_onboarding_starts_diagnostic",
        onboarding_done_state["onboarding_status"] == "complete"
        and "number game" in onboarding_done_opening.lower()
        and "do you go to school" not in onboarding_done_opening.lower(),
        f"{onboarding_done_state} | {onboarding_done_opening}",
    )

    diagnostic_in_progress_state = memory._effective_state_from_student_and_sessions(
        {"id": "demo", "name": "Remi", "current_level": "beginner"},
        [
            {
                "created_at": "2026-06-01T09:00:00+00:00",
                "messages": [
                    {"role": "assistant", "content": "Hello! I'm Sabi, your learning friend. What is your name?"},
                    {"role": "user", "content": "My name is Remi"},
                    {"role": "assistant", "content": "Remi! I like that name. I will remember you on this number. Tell me, do you go to school?"},
                    {"role": "user", "content": "yes"},
                    {"role": "assistant", "content": "Do you help your family at the market, or do you sell anything?"},
                    {"role": "user", "content": "I sell groundnuts"},
                    {"role": "assistant", "content": "Let's play a quick number game. What number comes after twenty-nine?"},
                    {"role": "user", "content": "thirty"},
                ],
            }
        ],
    )
    diagnostic_in_progress_opening = build_opening_turn(
        {"name": "Remi", "current_level": "beginner"},
        diagnostic_in_progress_state,
    )
    ok &= check(
        "resume_diagnostic_next_item",
        diagnostic_in_progress_state["diagnostic_status"] == "in_progress"
        and "ninety-nine" in diagnostic_in_progress_opening.lower(),
        f"{diagnostic_in_progress_state} | {diagnostic_in_progress_opening}",
    )

    inferred_from_non_diagnostic = analyze_session(
        {"current_module": 0},
        [
            {"role": "assistant", "content": "A mango costs three naira. You buy four mangoes. How much do you pay?"},
            {"role": "user", "content": "twelve naira"},
        ],
    ).learning_state
    ok &= check(
        "nonzero_inferred_module_marks_diagnostic_done",
        inferred_from_non_diagnostic["current_module"] == 4
        and inferred_from_non_diagnostic["diagnostic_status"] == "done"
        and inferred_from_non_diagnostic["phase"] == "first_mini_lesson",
        str(inferred_from_non_diagnostic),
    )

    literacy_after_name = [
        {"role": "assistant", "content": "Hello! What is your name?"},
        {"role": "user", "content": "My name is Remi"},
    ]
    literacy_route = build_instructional_route_prompt(literacy_after_name, current_module=0, course="literacy")
    ok &= check(
        "literacy_route_after_name",
        "do you go to school" in literacy_route.lower(),
        literacy_route,
    )

    literacy_after_onboarding = [
        *literacy_after_name,
        {"role": "assistant", "content": "Remi! I like that name. I will remember you on this number. Tell me, do you go to school?"},
        {"role": "user", "content": "not now"},
        {"role": "assistant", "content": "Do you help your family at the market, or do you sell anything?"},
        {"role": "user", "content": "yes, sometimes"},
    ]
    literacy_route_ready = build_instructional_route_prompt(literacy_after_onboarding, current_module=0, course="literacy")
    ok &= check(
        "literacy_route_after_onboarding",
        "What sound do you hear at the very beginning of the word ball?" in literacy_route_ready,
        literacy_route_ready,
    )

    literacy_correct = [
        {"role": "assistant", "content": "Let's play a sound game. What sound do you hear at the very beginning of the word ball? Ball."},
        {"role": "user", "content": "buh"},
    ]
    literacy_progress = analyze_literacy_diagnostic_progress(literacy_correct)
    ok &= check(
        "literacy_correct_in_progress",
        literacy_progress["status"] == "in_progress"
        and literacy_progress["next_item"]["id"] == "lit_rhyme_cat_hat",
        str(literacy_progress),
    )

    literacy_wrong = [
        {"role": "assistant", "content": "Let's play a sound game. What sound do you hear at the very beginning of the word ball? Ball."},
        {"role": "user", "content": "cat"},
    ]
    literacy_wrong_progress = analyze_literacy_diagnostic_progress(literacy_wrong)
    literacy_stats = analyze_session({"learning_state": {"course": "literacy"}}, literacy_wrong)
    literacy_state = literacy_stats.learning_state["literacy"]
    ok &= check(
        "literacy_wrong_places",
        literacy_wrong_progress["status"] == "placed"
        and literacy_state["diagnostic_status"] == "done"
        and literacy_state["current_module"] == 1
        and literacy_state["current_week"] == 1,
        str(literacy_stats.learning_state),
    )

    early_wrap_messages = [{"role": "assistant", "content": "Hi."}]
    for index in range(7):
        early_wrap_messages.append({"role": "user", "content": f"answer {index}"})
        early_wrap_messages.append({"role": "assistant", "content": f"question {index}"})
    early_wrap_response = "You have done really well today. Next time we will try bigger numbers."
    ok &= check(
        "early_wrap_language_does_not_end_call",
        is_premature_wrap_response(early_wrap_response, 7, MIN_LESSON_SECONDS - 30)
        and not should_wrap_up(early_wrap_messages, early_wrap_response, elapsed_seconds=MIN_LESSON_SECONDS - 30),
        early_wrap_response,
    )

    planned_wrap_messages = [{"role": "assistant", "content": "Hi."}]
    for index in range(MIN_WRAP_USER_TURNS):
        planned_wrap_messages.append({"role": "user", "content": f"answer {index}"})
        planned_wrap_messages.append({"role": "assistant", "content": f"question {index}"})
    planned_wrap_response = "Well done today. Next time we will try bigger numbers."
    ok &= check(
        "planned_wrap_window_can_end_call",
        should_prompt_wrap_up(MIN_WRAP_USER_TURNS, TARGET_WRAP_SECONDS)
        and should_wrap_up(planned_wrap_messages, planned_wrap_response, elapsed_seconds=TARGET_WRAP_SECONDS),
        planned_wrap_response,
    )

    continue_instruction = build_call_control_messages(7, MIN_LESSON_SECONDS - 30)
    ok &= check(
        "continue_instruction_before_minimum_lesson_length",
        bool(continue_instruction)
        and continue_instruction[0]["role"] == "system"
        and "Do not wrap up" in continue_instruction[0]["content"],
        str(continue_instruction),
    )

    goodbye_messages = [
        {"role": "assistant", "content": "Try one more."},
        {"role": "user", "content": "bye Sabi"},
    ]
    ok &= check(
        "caller_goodbye_still_ends_immediately",
        should_wrap_up(goodbye_messages, "Okay, bye!", elapsed_seconds=30),
        str(goodbye_messages),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
