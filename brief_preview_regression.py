#!/usr/bin/env python3
"""Regressions for the demoted TaRL-brief preview lane.

This lane must stay off production: an empty SABI_BRIEF_PREVIEW_PHONES list
routes nobody, including unknown caller IDs.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "SABI_SHARED_AUDIO_DIR",
    str(Path(tempfile.gettempdir()) / "sabi-brief-preview-regression"),
)

from diagnostic_flow import (
    CANONICAL_MARKET_ADDITION_PROMPT,
    NUMERACY_DIAGNOSTIC_ITEMS,
    build_opening_turn,
)
from learning_state import (
    analyze_session,
    brief_preview_prompt_block,
)
from phone_utils import phone_uses_brief_preview, phone_uses_gemini_live
from voice_realtime import _course_state_for_phone


PREVIEW_PHONE = "+18604367048"
OTHER_PHONE = "+2348123456789"


def check(name: str, condition: bool, detail: object = "") -> bool:
    print(("PASS" if condition else "FAIL"), name, "" if condition else detail)
    return bool(condition)


def _with_env(values: dict[str, str], fn):
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        return fn()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    ok = True
    ok &= check(
        "empty_allowlist_matches_nobody",
        not phone_uses_brief_preview(PREVIEW_PHONE, "")
        and not phone_uses_brief_preview("unknown", "")
        and not phone_uses_brief_preview(None, ""),
    )
    ok &= check(
        "listed_number_normalizes",
        phone_uses_brief_preview("1 (860) 436-7048", PREVIEW_PHONE)
        and not phone_uses_brief_preview(OTHER_PHONE, PREVIEW_PHONE),
    )
    ok &= check(
        "default_env_is_off",
        _with_env(
            {
                "SABI_BRIEF_PREVIEW_PHONES": "",
                "SABI_GEMINI_LIVE_ALL": "1",
                "SABI_GEMINI_LIVE_EXCLUDE_PHONES": "",
            },
            lambda: not phone_uses_brief_preview(PREVIEW_PHONE)
            and phone_uses_gemini_live(PREVIEW_PHONE)
            and phone_uses_gemini_live(OTHER_PHONE)
            and phone_uses_gemini_live("unknown"),
        ),
    )
    ok &= check(
        "preview_phone_skips_gemini_live",
        _with_env(
            {
                "SABI_BRIEF_PREVIEW_PHONES": PREVIEW_PHONE,
                "SABI_GEMINI_LIVE_ALL": "1",
                "SABI_GEMINI_LIVE_EXCLUDE_PHONES": "",
            },
            lambda: phone_uses_brief_preview(PREVIEW_PHONE)
            and not phone_uses_gemini_live(PREVIEW_PHONE)
            and phone_uses_gemini_live(OTHER_PHONE),
        ),
    )

    preview_state = _course_state_for_phone(
        PREVIEW_PHONE,
        {"course": "literacy", "current_module": 2, "literacy": {"diagnostic_status": "done"}},
    )
    production_state = _with_env(
        {"SABI_BRIEF_PREVIEW_PHONES": ""},
        lambda: _course_state_for_phone(
            PREVIEW_PHONE,
            {"course": "literacy", "current_module": 2, "literacy": {"diagnostic_status": "done"}},
        ),
    )
    ok &= check(
        "preview_does_not_force_numeracy",
        _with_env(
            {"SABI_BRIEF_PREVIEW_PHONES": PREVIEW_PHONE},
            lambda: _course_state_for_phone(
                PREVIEW_PHONE,
                {"course": "literacy", "current_module": 2, "literacy": {"diagnostic_status": "done"}},
            ).get("course")
            == "literacy"
            and _course_state_for_phone(
                PREVIEW_PHONE,
                {"course": "literacy", "current_module": 2, "literacy": {"diagnostic_status": "done"}},
            ).get("brief_preview")
            is True,
        ),
        preview_state,
    )
    ok &= check(
        "production_course_state_untouched",
        production_state.get("course") == "literacy"
        and not production_state.get("brief_preview"),
        production_state,
    )

    unnamed = build_opening_turn(
        {"brief_preview": True, "name": ""},
        {"brief_preview": True, "course": "numeracy", "current_module": 0},
    )
    ok &= check(
        "first_call_asks_name_enthusiastically",
        "What is your name?" in unnamed and "Sabi" in unnamed,
        unnamed,
    )

    game = build_opening_turn(
        {"brief_preview": True, "name": "Adaeze"},
        {"brief_preview": True, "course": "numeracy", "current_module": 0, "diagnostic_status": "not_started"},
    )
    ok &= check(
        "named_first_call_starts_game_not_school",
        "not a test" in game.lower()
        and NUMERACY_DIAGNOSTIC_ITEMS[0].prompt in game
        and "do you go to school" not in game.lower()
        and "sell anything" not in game.lower(),
        game,
    )

    remembered = build_opening_turn(
        {"brief_preview": True, "name": "Adaeze"},
        {
            "brief_preview": True,
            "course": "numeracy",
            "current_module": 2,
            "diagnostic_status": "done",
            "active_skill": "addition",
        },
    )
    ok &= check(
        "returning_caller_remembered_and_continued",
        "Adaeze" in remembered
        and "remember you" in remembered
        and "where we left off" in remembered,
        remembered,
    )

    production_opening = build_opening_turn(
        {"name": "Adaeze"},
        {"course": "numeracy", "current_module": 0, "diagnostic_status": "not_started", "onboarding_status": "needs_school"},
    )
    ok &= check(
        "production_opening_still_asks_school",
        "do you go to school" in production_opening.lower(),
        production_opening,
    )

    bump_messages = [
        {"role": "assistant", "content": "Tomatoes cost twenty naira. Peppers cost ten naira. How much altogether?"},
        {"role": "user", "content": "three"},
        {"role": "assistant", "content": "You buy bread for forty naira and eggs for twenty naira. How much altogether?"},
        {"role": "user", "content": "eight"},
    ]
    preview_stats = analyze_session(
        {
            "brief_preview": True,
            "learning_state": {
                "brief_preview": True,
                "course": "numeracy",
                "current_module": 2,
                "diagnostic_status": "done",
                "active_skill": "addition",
            },
            "current_module": 2,
        },
        bump_messages,
    )
    production_stats = analyze_session(
        {
            "learning_state": {
                "course": "numeracy",
                "current_module": 2,
                "diagnostic_status": "done",
                "active_skill": "addition",
            },
            "current_module": 2,
        },
        bump_messages,
    )
    ok &= check(
        "preview_two_wrongs_drop_a_module",
        preview_stats.learning_state.get("current_module") == 1
        and "Bump down" in str(preview_stats.learning_state.get("next_step") or ""),
        preview_stats.learning_state.get("current_module"),
    )
    ok &= check(
        "production_two_wrongs_do_not_drop_module",
        production_stats.learning_state.get("current_module") == 2,
        production_stats.learning_state.get("current_module"),
    )

    prompt = brief_preview_prompt_block({"brief_preview": True})
    ok &= check(
        "preview_prompt_has_canonical_market_example",
        CANONICAL_MARKET_ADDITION_PROMPT in prompt
        and "not a test, just a game" in prompt
        and brief_preview_prompt_block({}) == "",
        prompt[:200],
    )

    env_example = Path(__file__).with_name(".env.example").read_text()
    ok &= check(
        "env_example_defaults_preview_empty",
        "SABI_BRIEF_PREVIEW_PHONES=" in env_example
        and "SABI_BRIEF_PREVIEW_SIMULATOR=0" in env_example,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
