#!/usr/bin/env python3
"""Regression checks for Sabi learner identity and adaptive state."""

from __future__ import annotations

import sys
import types

sys.modules.setdefault(
    "supabase",
    types.SimpleNamespace(create_client=lambda *args, **kwargs: None),
)

from diagnostic_flow import (
    analyze_diagnostic_progress,
    analyze_literacy_diagnostic_progress,
    build_instructional_route_prompt,
    build_opening_turn,
)
from learning_state import analyze_session, extract_child_name
from memory import StudentMemory
from phone_utils import normalize_phone_number, phone_lookup_variants


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

    opening = build_opening_turn(
        {"name": "Remi", "current_module": 2, "current_topic": "addition"},
        {"current_module": 2, "active_skill": "addition", "diagnostic_status": "done"},
    )
    ok &= check("returning_opening_uses_name", "Welcome back, Remi" in opening, opening)
    ok &= check("returning_opening_no_name_request", "your name" not in opening.lower(), opening)

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

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
