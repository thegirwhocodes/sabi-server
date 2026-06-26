#!/usr/bin/env python3
"""Regression checks for the admin curriculum review map."""

from __future__ import annotations

import sys

from curriculum_review import build_curriculum_review_map, resolve_position_review


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    data = build_curriculum_review_map()
    numeracy_modules = data.get("numeracy", {}).get("modules", [])
    literacy_modules = data.get("literacy", {}).get("modules", [])
    numeracy_lesson_count = sum(len(module.get("lessons", [])) for module in numeracy_modules)
    literacy_lesson_count = sum(len(module.get("lessons", [])) for module in literacy_modules)
    scaffold_ladders = data.get("scaffold_ladders", [])

    ok = True
    ok &= check("map_status_ok", data.get("status") == "ok")
    ok &= check("has_level_schema", "scaffold_depth" in data.get("schema", {}))
    ok &= check("has_bump_down_policy", "depth_3" in data.get("bump_down_policy", {}))
    ok &= check("has_numeracy_modules", len(numeracy_modules) >= 6, len(numeracy_modules))
    ok &= check("has_full_numeracy_lesson_path", numeracy_lesson_count >= 96, numeracy_lesson_count)
    ok &= check("has_literacy_modules", len(literacy_modules) >= 5, len(literacy_modules))
    ok &= check("has_literacy_lesson_path", literacy_lesson_count >= 80, literacy_lesson_count)
    ok &= check("has_scaffold_ladders", len(scaffold_ladders) >= 3, len(scaffold_ladders))

    position = resolve_position_review(
        {
            "course": "numeracy",
            "current_module": 4,
            "current_week": 12,
            "current_lesson": 1,
            "active_skill": "multiplication",
            "scaffold_depth": 2,
            "wrong_streak": 1,
            "literacy": {
                "current_module": 1,
                "current_week": 1,
                "current_lesson": 2,
            },
        }
    )
    ok &= check("resolves_numeracy_position", position.get("numeracy", {}).get("title") == "What Is Multiplication: groups of")
    ok &= check("resolves_literacy_position", "Beginning Sounds" in (position.get("literacy", {}).get("title") or ""))
    ok &= check("preserves_scaffold_state", position.get("scaffold_depth") == 2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
