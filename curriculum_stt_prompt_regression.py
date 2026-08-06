#!/usr/bin/env python3
"""Prove curriculum turns receive Naomi's exact-question Gemini prompt."""

from __future__ import annotations

from curriculum_path import LESSON_TITLES, LITERACY_LESSON_TITLES
from diagnostic_flow import LITERACY_DIAGNOSTIC_ITEMS, NUMERACY_DIAGNOSTIC_ITEMS
from learning_state import SCAFFOLD_LADDERS
from stt import _current_tutor_question, build_gemini_curriculum_prompt


REQUIRED = (
    "A Nigerian child on a noisy 8kHz phone call",
    "with Sabi their AI tutor",
    "answering the question:",
    "complaining about the quality of the call or lesson",
    "some other human phrase",
    "Reply with their response.",
)

LITERACY_SCAFFOLDS = {
    "phonemic_awareness_beginning",
    "rhyming",
    "blending",
    "listening_comprehension",
    "oral_grammar",
}


def check_prompt(name: str, source: str, course: str) -> None:
    context = (
        f"Lesson metadata: course={course}; lesson_title={source}. "
        f"Exact recent tutor prompt: {source}"
    )
    prompt, actual_course, _label = build_gemini_curriculum_prompt(
        context,
        mode="literacy" if course == "literacy" else "general",
    )
    assert actual_course == course, f"{name}: expected {course}, got {actual_course}"
    assert f"walking through a {course} lesson" in prompt, f"{name}: missing course"
    assert all(required in prompt for required in REQUIRED), f"{name}: incomplete universal prompt"
    expected = _current_tutor_question(context)
    assert expected in prompt, f"{name}: missing exact final tutor question or instruction"


def main() -> int:
    checked = 0
    for lesson_number, title in sorted(LESSON_TITLES.items()):
        check_prompt(f"numeracy lesson {lesson_number}", title, "numeracy")
        checked += 1

    for module, lessons in sorted(LITERACY_LESSON_TITLES.items()):
        for lesson_number, title in sorted(lessons.items()):
            check_prompt(f"literacy module {module} lesson {lesson_number}", title, "literacy")
            checked += 1

    for item in NUMERACY_DIAGNOSTIC_ITEMS:
        check_prompt(f"numeracy diagnostic {item.id}", item.prompt, "numeracy")
        checked += 1

    for item in LITERACY_DIAGNOSTIC_ITEMS:
        check_prompt(f"literacy diagnostic {item.id}", item.prompt, "literacy")
        checked += 1

    for skill, steps in sorted(SCAFFOLD_LADDERS.items()):
        course = "literacy" if skill in LITERACY_SCAFFOLDS else "numeracy"
        for level, step in enumerate(steps, start=1):
            check_prompt(
                f"{course} scaffold {skill} level {level}",
                str(step["example_prompt"]),
                course,
            )
            checked += 1

    print(f"PASS: {checked} curriculum lesson, diagnostic, and scaffold rows use the universal prompt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
