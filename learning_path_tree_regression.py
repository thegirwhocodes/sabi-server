#!/usr/bin/env python3
"""Regression checks for educator branching learning-path trees."""

from __future__ import annotations

import sys

from learning_path_tree import build_learning_path_tree


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return bool(condition)


def _walk(node: dict) -> list[dict]:
    out = [node]
    for child in node.get("children") or []:
        out.extend(_walk(child))
    return out


def main() -> int:
    ok = True
    state = {
        "course": "numeracy",
        "tarl_level": 1,
        "current_module": 2,
        "current_week": 5,
        "current_lesson": 2,
        "active_skill": "addition",
        "scaffold_depth": 2,
        "wrong_streak": 2,
        "correct_streak": 0,
        "next_step": "Bump down for addition: finger counting with sums to five.",
    }
    tree = build_learning_path_tree(state, course="numeracy")
    root = tree.get("root") or {}
    nodes = _walk(root)

    ok &= check("has_root", bool(root.get("id")))
    ok &= check("nested_tree_nodes", len(nodes) >= 10, len(nodes))
    ok &= check("support_mode", tree.get("mode") == "support", tree.get("mode"))
    ok &= check("current_lesson_title", "Adding Past 10" in str(tree.get("current_title")), tree.get("current_title"))

    current = next((n for n in nodes if n.get("kind") == "lesson" and n.get("status") == "current"), None)
    ok &= check("current_has_two_branches", current and len(current.get("children") or []) == 2, current)
    ok &= check("current_has_progress_marker", current and current.get("progress_label"), current)
    ok &= check("current_has_progress_detail", current and "Module 2" in str(current.get("progress_detail")), current)
    branches = current.get("children") if current else []
    ok &= check("branch_labels_present", all(b.get("branch_label") for b in branches if b.get("kind") == "branch"), branches)

    support_branch = next((b for b in branches if "Support ladder" in str(b.get("branch_label"))), None)
    support_nodes = _walk(support_branch) if support_branch else []
    ok &= check("support_branch_has_scaffold_steps", any(n.get("kind") == "scaffold" for n in support_nodes), support_nodes)
    ok &= check("support_steps_are_numbered", any(n.get("progress_label") == "S2" for n in support_nodes), support_nodes)
    ok &= check("support_branch_has_rejoin", any(n.get("kind") == "rejoin" for n in support_nodes), support_nodes)

    on_level = next((b for b in branches if "On-level" in str(b.get("branch_label"))), None)
    ok &= check("on_level_has_future_lessons", any(n.get("status") == "future" for n in _walk(on_level or {})), on_level)

    lit = build_learning_path_tree(
        {"literacy": {"current_module": 1, "current_week": 2, "current_lesson": 1, "tarl_reading_level": 0, "active_skill": "phonemic_awareness"}},
        course="literacy",
    )
    ok &= check("literacy_tree_builds", bool((lit.get("root") or {}).get("children")))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
