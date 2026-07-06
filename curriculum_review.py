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
from learning_state import SCAFFOLD_LADDERS, scaffold_ladder_for

NUMERACY_PATH_LABELS = {
    1: "Counting",
    2: "Addition",
    3: "Subtraction",
    4: "Multiply",
    5: "Division",
    6: "Problems",
}

LITERACY_PATH_LABELS = {
    1: "Sounds",
    2: "Words",
    3: "Stories",
    4: "Grammar",
    5: "Sound play",
    6: "Print bridge",
}


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
        "numeracy_path": build_learning_path_graph(state, course="numeracy"),
        "literacy_path": build_learning_path_graph(state, course="literacy"),
        "numeracy_tree": _build_tree(state, "numeracy"),
        "literacy_tree": _build_tree(state, "literacy"),
    }


def _build_tree(state: dict[str, Any], course: str) -> dict[str, Any]:
    from learning_path_tree import build_learning_path_tree

    return build_learning_path_tree(state, course=course)


def build_learning_path_graph(state: dict[str, Any] | None, *, course: str = "numeracy") -> dict[str, Any]:
    """Structured main-line + support-branch path for admin visuals.

    Returns module nodes (past / current / future), the active scaffold ladder
    when the child has been bumped down, and a short preview of upcoming lessons.
    """
    state = state or {}
    if course == "literacy":
        literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
        view_state = {**state, **literacy, "course": "literacy"}
        module_order = sorted(LITERACY_MODULE_START.keys())
        labels = LITERACY_PATH_LABELS
        lesson = resolve_literacy_lesson(view_state)
    else:
        view_state = {**state, "course": "numeracy"}
        module_order = sorted(MODULE_START.keys())
        labels = NUMERACY_PATH_LABELS
        lesson = resolve_numeracy_lesson(view_state)

    current_module = int(view_state.get("current_module") or 0)
    scaffold_depth = int(view_state.get("scaffold_depth") or 0)
    wrong_streak = int(view_state.get("wrong_streak") or 0)
    correct_streak = int(view_state.get("correct_streak") or 0)
    active_skill = str(view_state.get("active_skill") or (lesson or {}).get("module_name") or "")

    if current_module <= 0:
        nodes = [
            {
                "module": 0,
                "label": "Diagnostic",
                "status": "current",
            }
        ] + [
            {"module": module, "label": labels.get(module, f"M{module}"), "status": "future"}
            for module in module_order
        ]
    else:
        nodes = []
        for module in module_order:
            if module < current_module:
                status = "completed"
            elif module == current_module:
                status = "current"
            else:
                status = "future"
            nodes.append(
                {
                    "module": module,
                    "label": labels.get(module, f"M{module}"),
                    "status": status,
                }
            )

    if correct_streak >= 2 and scaffold_depth == 0 and current_module > 0:
        mode = "advancing"
    elif scaffold_depth > 0 or wrong_streak >= 2:
        mode = "support"
    else:
        mode = "on_level"

    ladder_state = view_state.get("scaffold_ladder")
    ladder = ladder_state if isinstance(ladder_state, dict) else scaffold_ladder_for(
        active_skill, scaffold_depth, wrong_streak
    )
    scaffold_steps = []
    canonical = active_skill
    ladder_defs = SCAFFOLD_LADDERS.get(canonical) or []
    if not ladder_defs:
        for skill_key in SCAFFOLD_LADDERS:
            if skill_key in active_skill or active_skill in skill_key:
                ladder_defs = SCAFFOLD_LADDERS[skill_key]
                canonical = skill_key
                break

    active_level = int((ladder or {}).get("level") or scaffold_depth or 0)
    for index, step in enumerate(ladder_defs[:3], start=1):
        step_status = "future"
        if active_level and index < active_level:
            step_status = "completed"
        elif active_level and index == active_level:
            step_status = "current"
        elif scaffold_depth and index <= scaffold_depth and not active_level:
            step_status = "completed" if index < scaffold_depth else "current"
        scaffold_steps.append(
            {
                "level": index,
                "label": ["Repair", "Bump down", "Foundation"][index - 1],
                "teacher_move": step.get("teacher_move"),
                "example_prompt": step.get("example_prompt"),
                "status": step_status,
            }
        )

    scaffold_branch = None
    if scaffold_depth > 0 or (ladder and active_level):
        current_step = next((s for s in scaffold_steps if s["status"] == "current"), scaffold_steps[min(scaffold_depth, 3) - 1] if scaffold_depth else None)
        scaffold_branch = {
            "active_level": active_level or scaffold_depth,
            "skill": (ladder or {}).get("skill") or canonical or active_skill,
            "steps": scaffold_steps,
            "current_move": (ladder or {}).get("teacher_move") or (current_step or {}).get("teacher_move"),
            "rejoin_module": current_module if current_module > 0 else module_order[0],
            "rejoin_note": (
                f"After success on the support branch, Sabi rebuilds and rejoins "
                f"{labels.get(current_module, f'Module {current_module}') if current_module > 0 else 'the main path'}."
            ),
        }

    future_preview: list[dict[str, Any]] = []
    if lesson and lesson.get("next_title"):
        future_preview.append({"kind": "next_lesson", "title": lesson.get("next_title")})
    for module in module_order:
        if current_module > 0 and module > current_module:
            future_preview.append(
                {
                    "kind": "module",
                    "module": module,
                    "label": labels.get(module, f"M{module}"),
                }
            )
            if len([row for row in future_preview if row.get("kind") == "module"]) >= 2:
                break

    return {
        "course": course,
        "current_module": current_module,
        "current_week": view_state.get("current_week"),
        "current_lesson": view_state.get("current_lesson"),
        "current_title": (lesson or {}).get("title"),
        "next_title": (lesson or {}).get("next_title"),
        "scaffold_depth": scaffold_depth,
        "wrong_streak": wrong_streak,
        "correct_streak": correct_streak,
        "mode": mode,
        "nodes": nodes,
        "scaffold_branch": scaffold_branch,
        "future_preview": future_preview,
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
