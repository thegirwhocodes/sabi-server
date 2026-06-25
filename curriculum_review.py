"""Admin-facing curriculum map for Sabi learner progress review."""

from __future__ import annotations

from typing import Any

from curriculum_path import (
    LESSON_TITLES,
    LITERACY_LESSON_TITLES,
    LITERACY_MODULE_NAMES,
    LITERACY_MODULE_PRINCIPLES,
    LITERACY_MODULE_SKILLS,
    LITERACY_MODULE_START,
    MODULE_NAMES,
    MODULE_PRINCIPLES,
    MODULE_SKILLS,
    MODULE_START,
    resolve_literacy_lesson,
    resolve_numeracy_lesson,
)
from learning_state import SCAFFOLD_LADDERS


def build_curriculum_review_map() -> dict[str, Any]:
    """Return the structured path used to interpret learner placement."""
    return {
        "status": "ok",
        "schema": {
            "course": "numeracy or literacy",
            "current_module": "broad skill block",
            "current_week": "module week within the long sequence",
            "current_lesson": "1-4 local lesson slot for the week",
            "tarl_level": "placement level used for broad difficulty",
            "scaffold_depth": "0 means on-level; 1-3 means increasingly concrete repair/bump-down",
            "wrong_streak": "recent consecutive misses that trigger repair or bump-down",
        },
        "bump_down_policy": {
            "depth_0": "teach the planned lesson at the saved level",
            "depth_1": "repair inside the same skill with a smaller or clearer example",
            "depth_2": "bump down to prerequisite representation inside the same skill",
            "depth_3": "deep bump-down: rebuild the foundation with concrete oral/finger/object work",
            "note": (
                "Sabi does not randomly skip the child to another curriculum. "
                "Bump-down changes the teaching move/scaffold first, and only changes module/level "
                "when the learning state rules place the child lower."
            ),
        },
        "numeracy": {
            "modules": [_numeracy_module_record(module) for module in sorted(MODULE_START)],
        },
        "literacy": {
            "modules": [_literacy_module_record(module) for module in sorted(LITERACY_MODULE_START)],
        },
        "scaffold_ladders": [
            {
                "skill": skill,
                "levels": [
                    {
                        "level": index + 1,
                        **step,
                    }
                    for index, step in enumerate(steps)
                ],
            }
            for skill, steps in sorted(SCAFFOLD_LADDERS.items())
        ],
    }


def resolve_position_review(state: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve one learner state into human-readable current positions."""
    state = state or {}
    return {
        "course": state.get("course"),
        "numeracy": resolve_numeracy_lesson(state),
        "literacy": resolve_literacy_lesson(state),
        "scaffold_depth": state.get("scaffold_depth"),
        "wrong_streak": state.get("wrong_streak"),
        "active_skill": state.get("active_skill"),
        "next_step": state.get("next_step"),
    }


def _numeracy_module_record(module: int) -> dict[str, Any]:
    meta = MODULE_START[module]
    start_global = int(meta["global"])
    lesson_count = int(meta["weeks"]) * 4
    lessons = []
    for offset in range(lesson_count):
        global_lesson = start_global + offset
        lessons.append(
            {
                "global_lesson": global_lesson,
                "week": int(meta["week"]) + offset // 4,
                "lesson": offset % 4 + 1,
                "title": LESSON_TITLES.get(global_lesson, "Untitled lesson"),
            }
        )
    return {
        "module": module,
        "module_name": MODULE_NAMES.get(module),
        "active_skill": MODULE_SKILLS.get(module),
        "start_week": meta.get("week"),
        "week_count": meta.get("weeks"),
        "principle": MODULE_PRINCIPLES.get(module),
        "lessons": lessons,
    }


def _literacy_module_record(module: int) -> dict[str, Any]:
    meta = LITERACY_MODULE_START[module]
    start_global = int(meta["global"])
    lesson_count = int(meta["weeks"]) * 4
    suffix = str(meta.get("suffix") or "")
    lessons = []
    titles = LITERACY_LESSON_TITLES.get(module, {})
    for offset in range(lesson_count):
        script_lesson = start_global + offset
        lessons.append(
            {
                "script_lesson": script_lesson,
                "lesson_code": f"{script_lesson}{suffix}",
                "phase": meta.get("phase"),
                "week": int(meta["week"]) + offset // 4,
                "lesson": offset % 4 + 1,
                "title": titles.get(script_lesson, "Untitled literacy lesson"),
            }
        )
    return {
        "module": module,
        "module_name": LITERACY_MODULE_NAMES.get(module),
        "active_skill": LITERACY_MODULE_SKILLS.get(module),
        "phase": meta.get("phase"),
        "start_week": meta.get("week"),
        "week_count": meta.get("weeks"),
        "principle": LITERACY_MODULE_PRINCIPLES.get(module),
        "lessons": lessons,
    }
