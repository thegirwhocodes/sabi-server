"""Educator branching learning-path tree for Sabi (Prezi-style expand-on-click).

Builds a nested concept tree straight from the curriculum scripts. Each lesson
node splits into two educator-visible branches at the current position:
  • On-level route → next scripted lessons
  • Support ladder → repair moves from SCAFFOLD_LADDERS → rejoin → continue

Past modules collapse until clicked; the live path auto-expands to the child.
"""

from __future__ import annotations

from typing import Any

from curriculum_path import (
    LESSON_TITLES,
    LITERACY_LESSON_TITLES,
    LITERACY_MODULE_NAMES,
    LITERACY_MODULE_START,
    MODULE_NAMES,
    MODULE_START,
    resolve_literacy_lesson,
    resolve_numeracy_lesson,
)
from learning_state import SCAFFOLD_LADDERS

SUPPORT_LABELS = ("First repair", "Bump down", "Foundation rebuild")


def _literacy_module_record(module: int) -> dict[str, Any]:
    from curriculum_review import _literacy_module_record as load

    return load(module)


def _numeracy_module_record(module: int) -> dict[str, Any]:
    from curriculum_review import _numeracy_module_record as load

    return load(module)


def _concept_from_title(title: str) -> str:
    text = str(title or "").strip()
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text


def _lesson_code(*, global_lesson: int | None = None, week: int | None = None, lesson: int | None = None, script_lesson: int | None = None, suffix: str = "") -> str:
    if script_lesson is not None:
        base = f"Script {script_lesson}{suffix}"
        return f"{base} · W{week} L{lesson}" if week and lesson else base
    if global_lesson is not None:
        return f"Lesson {global_lesson} · W{week} L{lesson}" if week and lesson else f"Lesson {global_lesson}"
    return "Lesson"


def _resolve_ladder_steps(active_skill: str) -> tuple[str, list[dict[str, Any]]]:
    canonical = active_skill
    ladder_defs = SCAFFOLD_LADDERS.get(canonical) or []
    if not ladder_defs:
        for skill_key in SCAFFOLD_LADDERS:
            if skill_key in active_skill or active_skill in skill_key:
                ladder_defs = SCAFFOLD_LADDERS[skill_key]
                canonical = skill_key
                break
    steps = []
    for index, step in enumerate(ladder_defs[:3], start=1):
        steps.append(
            {
                "level": index,
                "label": SUPPORT_LABELS[index - 1],
                "teacher_move": step.get("teacher_move"),
                "example_prompt": step.get("example_prompt"),
                "rebuild_move": step.get("rebuild_move"),
            }
        )
    return canonical, steps


def _base_node(**fields: Any) -> dict[str, Any]:
    return {
        "id": fields.get("id"),
        "kind": fields.get("kind", "concept"),
        "status": fields.get("status", "future"),
        "code": fields.get("code", ""),
        "title": fields.get("title", ""),
        "concept": fields.get("concept", ""),
        "branch_label": fields.get("branch_label"),
        "example": fields.get("example"),
        "rebuild": fields.get("rebuild"),
        "expanded": bool(fields.get("expanded", False)),
        "auto_expand": bool(fields.get("auto_expand", False)),
        "children": list(fields.get("children") or []),
    }


def _lesson_node(course: str, row: dict[str, Any], module: int, status: str, *, suffix: str = "") -> dict[str, Any]:
    if course == "literacy":
        script = int(row.get("script_lesson") or 0)
        title = (LITERACY_LESSON_TITLES.get(module) or {}).get(script, "Literacy lesson")
        return _base_node(
            id=f"lit-l{script}{suffix}",
            kind="lesson",
            status=status,
            module=module,
            code=_lesson_code(script_lesson=script, week=int(row.get("week") or 0), lesson=int(row.get("lesson") or 0), suffix=suffix),
            title=title,
            concept=_concept_from_title(title),
        )
    global_lesson = int(row.get("global_lesson") or 0)
    title = LESSON_TITLES.get(global_lesson, "Numeracy lesson")
    return _base_node(
        id=f"num-l{global_lesson}",
        kind="lesson",
        status=status,
        module=module,
        code=_lesson_code(global_lesson=global_lesson, week=int(row.get("week") or 0), lesson=int(row.get("lesson") or 0)),
        title=title,
        concept=_concept_from_title(title),
    )


def _chain_lessons(course: str, rows: list[dict[str, Any]], module: int, start: int, end: int, current_idx: int, *, suffix: str = "") -> dict[str, Any] | None:
    head: dict[str, Any] | None = None
    prev: dict[str, Any] | None = None
    for index in range(start, end):
        if index < current_idx:
            status = "completed"
        elif index == current_idx:
            status = "current"
        else:
            status = "future"
        node = _lesson_node(course, rows[index], module, status, suffix=suffix)
        if prev is None:
            head = node
        else:
            prev["children"] = [node]
        prev = node
    return head


def _support_chain(course: str, active_skill: str, view_state: dict[str, Any], scaffold_depth: int, future_head: dict[str, Any] | None) -> list[dict[str, Any]]:
    canonical, steps = _resolve_ladder_steps(active_skill)
    ladder = view_state.get("scaffold_ladder") if isinstance(view_state.get("scaffold_ladder"), dict) else None
    active_level = int((ladder or {}).get("level") or scaffold_depth or 0)
    if not steps:
        return []

    nodes: list[dict[str, Any]] = []
    for step in steps:
        step_status = "support_future"
        if active_level and step["level"] < active_level:
            step_status = "support_completed"
        elif active_level and step["level"] == active_level:
            step_status = "support_current"
        nodes.append(
            _base_node(
                id=f"{course}-support-{step['level']}",
                kind="scaffold",
                status=step_status,
                code=f"Support {step['level']} · {canonical.replace('_', ' ')}",
                title=step["label"],
                concept=step.get("teacher_move"),
                example=step.get("example_prompt"),
                rebuild=step.get("rebuild_move"),
                auto_expand=step_status == "support_current",
            )
        )

    for index in range(len(nodes) - 1):
        nodes[index]["children"] = [nodes[index + 1]]

    rejoin = _base_node(
        id=f"{course}-rejoin",
        kind="rejoin",
        status="planned",
        code="Rebuild & rejoin",
        title="Return to the planned lesson check",
        concept=(ladder or {}).get("rebuild_move")
        or steps[min(max(active_level, 1), len(steps)) - 1].get("rebuild_move")
        or "Rebuild with one success, then re-ask the planned lesson independently.",
        auto_expand=active_level > 0,
    )
    nodes[-1]["children"] = [rejoin]
    if future_head:
        rejoin["children"] = [future_head]
    return [nodes[0]] if nodes else []


def _branch_node(label: str, children: list[dict[str, Any]], *, status: str = "future", auto_expand: bool = False) -> dict[str, Any]:
    return _base_node(
        id=f"branch-{abs(hash(label)) % 10**8}",
        kind="branch",
        status=status,
        branch_label=label,
        title=label,
        concept="Click to expand this route through the curriculum.",
        children=children,
        auto_expand=auto_expand,
    )


def _attach_current_branches(
    current: dict[str, Any],
    *,
    course: str,
    active_skill: str,
    view_state: dict[str, Any],
    scaffold_depth: int,
    on_support: bool,
    future_chain: dict[str, Any] | None,
) -> None:
    support_children = _support_chain(course, active_skill, view_state, scaffold_depth, future_chain)
    on_level = _branch_node(
        "On-level route · child answers confidently",
        [future_chain] if future_chain else [],
        status="current" if not on_support else "future",
        auto_expand=not on_support,
    )
    support = _branch_node(
        "Support ladder · child needs repair (curriculum bump-down)",
        support_children,
        status="support_current" if on_support else "future",
        auto_expand=on_support,
    )
    current["children"] = [on_level, support]
    current["auto_expand"] = True


def _module_node(course: str, module: int, *, status: str, lesson_rows: list[dict[str, Any]], suffix: str = "") -> dict[str, Any]:
    if course == "literacy":
        record = _literacy_module_record(module)
    else:
        record = _numeracy_module_record(module)
    lesson_count = len(record.get("lessons") or [])
    return _base_node(
        id=f"{course}-mod{module}",
        kind="module_gate",
        status=status,
        module=module,
        code=f"{'Literacy' if course == 'literacy' else 'Numeracy'} Module {module}",
        title=str(record.get("module_name") or f"Module {module}"),
        concept=f"{lesson_count} scripted lessons · {str(record.get('principle') or '')[:140]}",
        children=[],
        auto_expand=status == "current",
    )


def build_learning_path_tree(
    state: dict[str, Any] | None,
    *,
    course: str = "numeracy",
    past_lessons: int = 3,
    future_lessons: int = 4,
) -> dict[str, Any]:
    state = state or {}
    if course == "literacy":
        literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
        view_state = {**state, **literacy, "course": "literacy"}
        lesson = resolve_literacy_lesson(view_state)
        module_order = sorted(LITERACY_MODULE_START.keys())
        suffix = str(LITERACY_MODULE_START.get(int(view_state.get("current_module") or 0), {}).get("suffix") or "")
        lessons_for = _literacy_module_record
        lesson_key = lambda row: int(row.get("script_lesson") or 0)
        current_key = int((lesson or {}).get("script_lesson") or 0)
    else:
        view_state = {**state, "course": "numeracy"}
        lesson = resolve_numeracy_lesson(view_state)
        module_order = sorted(MODULE_START.keys())
        suffix = ""
        lessons_for = _numeracy_module_record
        lesson_key = lambda row: int(row.get("global_lesson") or 0)
        current_key = int((lesson or {}).get("global_lesson") or 0)

    current_module = int(view_state.get("current_module") or 0)
    scaffold_depth = int(view_state.get("scaffold_depth") or 0)
    wrong_streak = int(view_state.get("wrong_streak") or 0)
    correct_streak = int(view_state.get("correct_streak") or 0)
    active_skill = str(view_state.get("active_skill") or (lesson or {}).get("module_name") or "")

    if correct_streak >= 2 and scaffold_depth == 0:
        mode = "advancing"
    elif scaffold_depth > 0 or wrong_streak >= 2:
        mode = "support"
    else:
        mode = "on_level"
    on_support = mode == "support"

    if current_module <= 0:
        root = _base_node(
            id=f"{course}-placement",
            kind="placement",
            status="current",
            code="Diagnostic",
            title="Foundational placement call",
            concept="Oral probes until the first fail sets the starting module and TaRL level.",
            auto_expand=True,
            children=[
                _base_node(
                    id=f"{course}-after-placement",
                    kind="future_route",
                    status="future",
                    code="After placement",
                    title=(lesson or {}).get("title") or "First teaching lesson",
                    concept=(lesson or {}).get("focus") or "Begin at the lesson the diagnostic selects.",
                )
            ]
            if lesson
            else [],
        )
        return _finalize(course, view_state, lesson, mode, root)

    tarl = view_state.get("tarl_reading_level") if course == "literacy" else view_state.get("tarl_level")
    root = _base_node(
        id=f"{course}-origin",
        kind="origin",
        status="completed",
        code="Program entry",
        title=f"TaRL level {tarl if tarl is not None else '?'}",
        concept="Every branch below is anchored to this placement level and the fixed script sequence.",
        auto_expand=True,
    )

    completed_modules: list[dict[str, Any]] = []
    for module in module_order:
        if module >= current_module:
            break
        rows = lessons_for(module).get("lessons") or []
        mod = _module_node(course, module, status="completed", lesson_rows=rows, suffix=suffix if course == "literacy" else "")
        lesson_chain = _chain_lessons(course, rows, module, 0, len(rows), len(rows), suffix=suffix if course == "literacy" else "")
        if lesson_chain:
            mod["children"] = [lesson_chain]
        completed_modules.append(mod)

    rows = lessons_for(current_module).get("lessons") or []
    current_idx = next((i for i, row in enumerate(rows) if lesson_key(row) == current_key), max(0, len(rows) - 1))
    current_mod = _module_node(course, current_module, status="current", lesson_rows=rows, suffix=suffix if course == "literacy" else "")

    start = max(0, current_idx - past_lessons)
    past_chain = _chain_lessons(
        course,
        rows,
        current_module,
        start,
        current_idx,
        current_idx,
        suffix=suffix if course == "literacy" else "",
    )
    current_node = _lesson_node(course, rows[current_idx], current_module, "current", suffix=suffix if course == "literacy" else "")
    future_chain = _chain_lessons(
        course,
        rows,
        current_module,
        current_idx + 1,
        min(len(rows), current_idx + 1 + future_lessons),
        current_idx,
        suffix=suffix if course == "literacy" else "",
    )

    if past_chain:
        tail = past_chain
        while tail.get("children"):
            tail = tail["children"][0]
        tail["children"] = [current_node]
        module_head = past_chain
    else:
        module_head = current_node

    _attach_current_branches(
        current_node,
        course=course,
        active_skill=active_skill,
        view_state=view_state,
        scaffold_depth=scaffold_depth,
        on_support=on_support,
        future_chain=future_chain,
    )
    current_mod["children"] = [module_head]
    current_mod["auto_expand"] = True
    root["auto_expand"] = True
    root["children"] = [*completed_modules, current_mod]
    _mark_expand_path(current_mod)
    return _finalize(course, view_state, lesson, mode, root)


def _mark_expand_path(node: dict[str, Any]) -> None:
    node["auto_expand"] = True
    node["expanded"] = True
    children = node.get("children") or []
    if not children:
        return
    active_child = None
    for child in children:
        status = str(child.get("status") or "")
        if status in {"current", "support_current"} or child.get("auto_expand"):
            active_child = child
            break
    if active_child is None:
        active_child = children[-1]
    if active_child.get("kind") == "module_gate" and active_child.get("status") == "completed":
        return
    active_child["auto_expand"] = True
    active_child["expanded"] = True
    _mark_expand_path(active_child)


def _finalize(
    course: str,
    view_state: dict[str, Any],
    lesson: dict[str, Any] | None,
    mode: str,
    root: dict[str, Any],
) -> dict[str, Any]:
    return {
        "course": course,
        "mode": mode,
        "module": view_state.get("current_module"),
        "module_name": (lesson or {}).get("module_name"),
        "current_title": (lesson or {}).get("title"),
        "current_concept": _concept_from_title((lesson or {}).get("title") or ""),
        "next_step": view_state.get("next_step"),
        "legend": {
            "main": "Completed and on-level route",
            "support": "Live support ladder from the curriculum repair scripts",
            "rejoin": "Rebuild, then return to the planned lesson",
            "future": "Planned next — click any node to expand its branch",
        },
        "root": root,
        "interaction": "Choose a path button to see what that curriculum future means, or click any node to inspect that lesson or move.",
    }


def render_learning_path_tree_svg(tree: dict[str, Any]) -> str:
    return ""
