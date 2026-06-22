"""Deterministic learning-state updates for Sabi phone lessons.

The LLM teaches, but core placement/progression should not be purely vibes.
This module keeps TaRL-inspired state: current module, skill scores, correct
and wrong streaks, scaffold depth, and a short next-step directive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from diagnostic_flow import (
    NUMERACY_DIAGNOSTIC_ITEMS,
    analyze_diagnostic_progress,
    analyze_literacy_diagnostic_progress,
    onboarding_status_from_messages,
)
from numeric_grading import analyze_latest_numeric_turn


MODULE_NAMES = {
    0: "diagnostic",
    1: "counting",
    2: "addition",
    3: "subtraction",
    4: "multiplication",
    5: "division",
    6: "word_problems",
    7: "completed",
}

MODULE_SKILLS = {
    0: "diagnostic",
    1: "counting",
    2: "addition",
    3: "subtraction",
    4: "multiplication",
    5: "division",
    6: "word_problems",
    7: "completed",
}

SKILL_MODULE = {skill: module for module, skill in MODULE_SKILLS.items()}


@dataclass
class SessionStats:
    summary: str
    correct_count: int
    wrong_count: int
    topics_covered: list[str]
    recommended_module: int
    current_level: str
    should_advance: bool
    skills: dict[str, float]
    learning_state: dict[str, Any]
    child_name: str | None = None


def default_learning_state() -> dict[str, Any]:
    return {
        "course": "numeracy",
        "phase": "onboarding",
        "onboarding_status": "needs_name",
        "diagnostic_status": "not_started",
        "current_module": 0,
        "current_week": 1,
        "current_lesson": 1,
        "tarl_level": 0,
        "active_skill": "diagnostic",
        "correct_streak": 0,
        "wrong_streak": 0,
        "scaffold_depth": 0,
        "last_expected_answer": None,
        "last_child_numbers": [],
        "last_turn_correct": None,
        "next_step": "Run a warm diagnostic disguised as a game, then start the first mini-lesson at the placed level.",
        "literacy": {
            "phase": "onboarding",
            "diagnostic_status": "not_started",
            "current_phase": 1,
            "current_module": 1,
            "current_week": 1,
            "current_lesson": 1,
            "tarl_reading_level": 0,
            "active_skill": "phonemic_awareness_beginning",
            "next_step": "Run a warm sound-and-story diagnostic disguised as a game.",
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_learning_state(student: dict[str, Any] | None) -> dict[str, Any]:
    state = default_learning_state()
    if not student:
        return state
    existing = student.get("learning_state")
    if isinstance(existing, dict):
        state.update(existing)
    current_module = student.get("current_module")
    if isinstance(current_module, int):
        state["current_module"] = current_module
        state["active_skill"] = MODULE_SKILLS.get(current_module, state.get("active_skill", "diagnostic"))
    return state


def infer_skill_from_question(question: str, fallback_module: int = 0) -> str:
    lower = question.lower()
    if re.search(r"\b(after|before|count|bigger|smaller|which number)\b", lower):
        return "counting"
    if re.search(r"\b(altogether|total|plus|add|together|in all)\b", lower):
        return "addition"
    if re.search(r"\b(change|left|remain|minus|subtract)\b", lower):
        return "subtraction"
    if re.search(r"\b(times|multiply|each|every)\b", lower) or (
        re.search(r"\b(cost|costs|costing)\b", lower)
        and re.search(r"\b(buy|buys|bought)\b", lower)
        and re.search(r"\b(pay|pays|paid)\b", lower)
    ):
        return "multiplication"
    if re.search(r"\b(share|shared|divide|divided|equally|groups)\b", lower):
        return "division"
    if re.search(r"\b(enough|both|how much did you make|keep half)\b", lower):
        return "word_problems"
    return MODULE_SKILLS.get(fallback_module, "diagnostic")


def extract_child_name(messages: list[dict[str, str]]) -> str | None:
    non_names = {
        "yes", "no", "okay", "ok", "hello", "hi", "ready", "thank you",
        "thanks", "i don't know", "i dont know", "and some", "numerous",
    }
    for index, message in enumerate(messages[:8]):
        if message.get("role") != "user":
            continue
        text = message.get("content", "").strip()
        match = re.search(r"\b(?:my name is|i am|i'm|its|it's)\s+([A-Za-z][A-Za-z' -]{1,30})", text, re.I)
        if match:
            return _clean_name(match.group(1))
        normalized = re.sub(r"[^a-z' ]", "", text.lower()).strip()
        previous_assistant = ""
        for prev_index in range(index - 1, -1, -1):
            if messages[prev_index].get("role") == "assistant":
                previous_assistant = messages[prev_index].get("content", "").lower()
                break
        asked_name = "your name" in previous_assistant or "tell me your name" in previous_assistant
        if (
            asked_name
            and 1 <= len(text.split()) <= 3
            and normalized not in non_names
            and not re.search(r"\d|\b(yes|no|okay|hello|hi|ready|thank|thanks)\b", text, re.I)
        ):
            return _clean_name(text)
    return None


def _clean_name(text: str) -> str | None:
    cleaned = re.sub(r"[^A-Za-z' -]", "", text).strip(" .,'-")
    if not cleaned:
        return None
    words = cleaned.split()
    if len(words) > 2:
        words = words[:2]
    return " ".join(word.capitalize() for word in words)


def analyze_session(student: dict[str, Any] | None, messages: list[dict[str, str]]) -> SessionStats:
    state = merge_learning_state(student)
    if state.get("course") == "literacy":
        return _analyze_literacy_session(student, messages, state)

    current_module = int(state.get("current_module") or 0)
    diagnostic_progress = analyze_diagnostic_progress(messages) if current_module == 0 else None
    onboarding_status = onboarding_status_from_messages(messages) if current_module == 0 else state.get("onboarding_status", "complete")
    skill_rows: dict[str, list[bool]] = {}
    topics: list[str] = []
    correct_count = 0
    wrong_count = 0
    correct_streak = int(state.get("correct_streak") or 0)
    wrong_streak = int(state.get("wrong_streak") or 0)
    scaffold_depth = int(state.get("scaffold_depth") or 0)
    last_expected = None
    last_child_numbers: list[int] = []
    last_turn_correct = None

    for index, message in enumerate(messages):
        if message.get("role") != "user":
            continue
        check = analyze_latest_numeric_turn(messages[: index + 1])
        if check.expected is None or check.is_correct is None:
            continue
        skill = infer_skill_from_question(check.assistant_question, current_module)
        if skill not in topics:
            topics.append(skill)
        skill_rows.setdefault(skill, []).append(bool(check.is_correct))
        last_expected = check.expected
        last_child_numbers = check.child_numbers
        last_turn_correct = check.is_correct
        if check.is_correct:
            correct_count += 1
            correct_streak += 1
            wrong_streak = 0
            scaffold_depth = max(0, scaffold_depth - 1)
        else:
            wrong_count += 1
            wrong_streak += 1
            correct_streak = 0
            if wrong_streak >= 2:
                scaffold_depth = min(3, scaffold_depth + 1)

    skill_scores = {
        skill: round(sum(1 for ok in rows if ok) / len(rows), 2)
        for skill, rows in skill_rows.items()
        if rows
    }

    active_skill = topics[-1] if topics else state.get("active_skill", MODULE_SKILLS.get(current_module, "diagnostic"))
    placement = diagnostic_progress.get("placement") if diagnostic_progress else None
    if placement:
        recommended_module = int(placement.get("module") or current_module or 0)
    elif (
        current_module == 0
        and diagnostic_progress
        and diagnostic_progress.get("status") in {"not_started", "in_progress"}
        and _is_ordered_diagnostic_prefix(diagnostic_progress)
    ):
        recommended_module = 0
    else:
        recommended_module = _recommended_module(current_module, active_skill, correct_streak, wrong_streak, scaffold_depth)
    should_advance = correct_streak >= 3 and wrong_count == 0 and current_module not in (0, 7)
    current_level = _current_level(skill_scores, scaffold_depth, wrong_streak)
    phase = _phase_for_state(current_module, recommended_module, messages, correct_count, wrong_count, diagnostic_progress, onboarding_status)
    next_step = _next_step(active_skill, scaffold_depth, wrong_streak, correct_streak)
    diagnostic_status = _diagnostic_status(current_module, recommended_module, diagnostic_progress, topics)
    current_week = int((placement or {}).get("week") or state.get("current_week") or 1)
    current_lesson = int((placement or {}).get("lesson") or state.get("current_lesson") or 1)

    updated_state = {
        **state,
        "phase": phase,
        "onboarding_status": onboarding_status,
        "diagnostic_status": diagnostic_status,
        "diagnostic_results": diagnostic_progress,
        "current_module": recommended_module,
        "current_week": current_week,
        "current_lesson": current_lesson,
        "tarl_level": int((placement or {}).get("tarl_level") or _tarl_level_for_module(recommended_module)),
        "active_skill": MODULE_SKILLS.get(recommended_module, active_skill),
        "correct_streak": correct_streak,
        "wrong_streak": wrong_streak,
        "scaffold_depth": scaffold_depth,
        "last_expected_answer": last_expected,
        "last_child_numbers": last_child_numbers,
        "last_turn_correct": last_turn_correct,
        "next_step": next_step,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    summary = _summary(active_skill, correct_count, wrong_count, scaffold_depth, recommended_module, diagnostic_progress)
    return SessionStats(
        summary=summary,
        correct_count=correct_count,
        wrong_count=wrong_count,
        topics_covered=topics or [MODULE_NAMES.get(recommended_module, "diagnostic")],
        recommended_module=recommended_module,
        current_level=current_level,
        should_advance=should_advance,
        skills=skill_scores,
        learning_state=updated_state,
        child_name=extract_child_name(messages),
    )


def build_learning_state_prompt(student: dict[str, Any] | None) -> str:
    state = merge_learning_state(student)
    active_skill = state.get("active_skill", "diagnostic")
    scaffold_depth = int(state.get("scaffold_depth") or 0)
    wrong_streak = int(state.get("wrong_streak") or 0)
    correct_streak = int(state.get("correct_streak") or 0)

    return f"""

## LEARNER STATE AND ADAPTIVE ROUTING
- Course: {state.get('course', 'numeracy')}
- Phase: {state.get('phase', 'onboarding')}
- Diagnostic status: {state.get('diagnostic_status', 'not_started')}
- Current module: {state.get('current_module', 0)} ({MODULE_NAMES.get(int(state.get('current_module') or 0), 'diagnostic')})
- TaRL-style level: {state.get('tarl_level', 0)}
- Active skill: {active_skill}
- Correct streak: {correct_streak}
- Wrong streak: {wrong_streak}
- Scaffold depth: {scaffold_depth}
- Next step: {state.get('next_step', 'Continue the planned lesson.')}

## LITERACY STATE
- Literacy diagnostic status: {(state.get('literacy') or {}).get('diagnostic_status', 'not_started')}
- Literacy phase/module/week/lesson: {(state.get('literacy') or {}).get('current_phase', 1)} / {(state.get('literacy') or {}).get('current_module', 1)} / {(state.get('literacy') or {}).get('current_week', 1)} / {(state.get('literacy') or {}).get('current_lesson', 1)}
- Literacy TaRL reading level: {(state.get('literacy') or {}).get('tarl_reading_level', 0)}
- Active literacy skill: {(state.get('literacy') or {}).get('active_skill', 'phonemic_awareness_beginning')}
- Literacy next step: {(state.get('literacy') or {}).get('next_step', 'Run the oral literacy diagnostic when literacy mode is selected.')}

If wrong streak is 2 or more, do the proposed bump-down behavior immediately:
1. Stop increasing difficulty.
2. Move to a simpler prerequisite version of {active_skill}.
3. Use tiny numbers or concrete counting objects.
4. If the child still misses, go down to a foundational example like one plus one, then rebuild back upward.
5. After a successful answer, return one small step upward, not all the way to the hard problem."""


def _analyze_literacy_session(
    student: dict[str, Any] | None,
    messages: list[dict[str, str]],
    state: dict[str, Any],
) -> SessionStats:
    progress = analyze_literacy_diagnostic_progress(messages)
    literacy = dict(state.get("literacy") or {})
    placement = progress.get("placement") or {}
    results = progress.get("results") or []
    correct_count = sum(1 for result in results if result.get("correct"))
    wrong_count = sum(1 for result in results if result.get("correct") is False)
    latest_domain = (results[-1].get("domain") if results else literacy.get("active_skill")) or "phonemic_awareness_beginning"

    if placement:
        literacy.update(
            {
                "phase": "first_mini_lesson",
                "diagnostic_status": "done",
                "diagnostic_results": progress,
                "current_phase": int(placement.get("phase") or literacy.get("current_phase") or 1),
                "current_module": int(placement.get("module") or literacy.get("current_module") or 1),
                "current_week": int(placement.get("week") or literacy.get("current_week") or 1),
                "current_lesson": int(placement.get("lesson") or literacy.get("current_lesson") or 1),
                "tarl_reading_level": int(placement.get("tarl_level") or literacy.get("tarl_reading_level") or 0),
                "active_skill": latest_domain,
                "next_step": f"Begin a tiny oral literacy lesson for {latest_domain} at the placed level.",
            }
        )
    elif progress.get("status") == "complete":
        literacy.update(
            {
                "phase": "print_bridge",
                "diagnostic_status": "done",
                "diagnostic_results": progress,
                "current_phase": 2,
                "current_module": 8,
                "current_week": 21,
                "current_lesson": 1,
                "tarl_reading_level": 4,
                "active_skill": "listening_comprehension",
                "next_step": "Start oral comprehension and print-bridge work; do not claim full reading mastery without print evidence.",
            }
        )
    elif results:
        literacy.update(
            {
                "phase": "diagnostic",
                "diagnostic_status": "in_progress",
                "diagnostic_results": progress,
                "active_skill": latest_domain,
                "next_step": "Continue the next oral literacy diagnostic item as a low-pressure game.",
            }
        )
    else:
        literacy.update(
            {
                "phase": "diagnostic",
                "diagnostic_status": "not_started",
                "diagnostic_results": progress,
                "next_step": "Ask the first beginning-sound item as a sound game.",
            }
        )

    updated_state = {
        **state,
        "course": "literacy",
        "phase": literacy.get("phase", "diagnostic"),
        "literacy": literacy,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    summary = _literacy_summary(progress, literacy)
    skills = {}
    for result in results:
        skills[f"literacy_{result.get('domain')}"] = 1.0 if result.get("correct") else 0.0
    return SessionStats(
        summary=summary,
        correct_count=correct_count,
        wrong_count=wrong_count,
        topics_covered=[f"literacy:{latest_domain}"],
        recommended_module=int(state.get("current_module") or 0),
        current_level="beginner" if wrong_count else "intermediate" if correct_count else "beginner",
        should_advance=False,
        skills=skills,
        learning_state=updated_state,
        child_name=extract_child_name(messages),
    )


def _literacy_summary(progress: dict[str, Any], literacy: dict[str, Any]) -> str:
    status = progress.get("status")
    if status == "placed":
        placement = progress.get("placement") or {}
        return (
            "Literacy baseline placed child at "
            f"Phase {placement.get('phase', 1)}, Module {placement.get('module', 1)}, "
            f"Week {placement.get('week', 1)}, Lesson {placement.get('lesson', 1)}: "
            f"{placement.get('reason', 'start at current oral literacy level')}"
        )
    if status == "complete":
        return "Literacy baseline passed for voice-only skills; child is ready for oral comprehension and print-bridge work."
    if status == "in_progress":
        return f"Literacy baseline in progress on {literacy.get('active_skill', 'oral literacy')}; continue the sound-and-story game."
    return "Literacy baseline not started; begin with a warm beginning-sound game."


def _recommended_module(current_module: int, active_skill: str, correct_streak: int, wrong_streak: int, scaffold_depth: int) -> int:
    if current_module == 0 and active_skill in SKILL_MODULE and active_skill != "diagnostic":
        return SKILL_MODULE[active_skill]
    if wrong_streak >= 3 and current_module > 1:
        return max(1, current_module - 1)
    if scaffold_depth >= 2 and active_skill in SKILL_MODULE:
        return max(1, min(current_module or SKILL_MODULE[active_skill], SKILL_MODULE[active_skill]))
    if correct_streak >= 3 and current_module not in (0, 7):
        return min(7, current_module + 1)
    return current_module


def _is_ordered_diagnostic_prefix(diagnostic_progress: dict[str, Any]) -> bool:
    results = diagnostic_progress.get("results") or []
    answered_ids = [result.get("item_id") for result in results]
    expected_prefix = [item.id for item in NUMERACY_DIAGNOSTIC_ITEMS[: len(answered_ids)]]
    return answered_ids == expected_prefix


def _current_level(skill_scores: dict[str, float], scaffold_depth: int, wrong_streak: int) -> str:
    if wrong_streak >= 2 or scaffold_depth >= 2:
        return "beginner"
    if skill_scores and min(skill_scores.values()) >= 0.8:
        return "advanced"
    if skill_scores and max(skill_scores.values()) >= 0.5:
        return "intermediate"
    return "beginner"


def _phase_for_state(
    current_module: int,
    recommended_module: int,
    messages: list[dict[str, str]],
    correct_count: int,
    wrong_count: int,
    diagnostic_progress: dict[str, Any] | None = None,
    onboarding_status: str = "complete",
) -> str:
    if recommended_module != 0 and current_module == 0:
        return "first_mini_lesson" if correct_count + wrong_count <= 1 else "guided_practice"
    if current_module == 0 and onboarding_status != "complete":
        return "onboarding"
    if diagnostic_progress:
        if diagnostic_progress.get("status") in {"not_started", "in_progress"}:
            return "diagnostic"
        if diagnostic_progress.get("status") in {"placed", "complete"}:
            return "first_mini_lesson"
    if current_module == 0 and correct_count + wrong_count == 0:
        return "diagnostic"
    if correct_count + wrong_count <= 1:
        return "guided_practice"
    if correct_count >= 2:
        return "independent_check"
    return "teaching"


def _diagnostic_status(
    current_module: int,
    recommended_module: int,
    diagnostic_progress: dict[str, Any] | None,
    topics: list[str],
) -> str:
    if current_module != 0 or recommended_module != 0:
        return "done"
    if not diagnostic_progress:
        return "done" if topics else "not_started"
    status = diagnostic_progress.get("status")
    if status in {"placed", "complete"}:
        return "done"
    if status == "in_progress":
        return "in_progress"
    return "not_started"


def _tarl_level_for_module(module: int) -> int:
    if module <= 1:
        return 0
    if module == 2:
        return 2
    if module == 3:
        return 3
    return 4


def _next_step(active_skill: str, scaffold_depth: int, wrong_streak: int, correct_streak: int) -> str:
    if wrong_streak >= 3 or scaffold_depth >= 3:
        return f"Use the most concrete prerequisite for {active_skill}: count objects aloud, then ask one plus one or two plus one before returning upward."
    if wrong_streak >= 2 or scaffold_depth >= 2:
        return f"Bump down for {active_skill}: use smaller numbers, model the first step, and ask a fresh easier question."
    if wrong_streak == 1:
        return f"Repair {active_skill}: acknowledge the attempt and rephrase with a simpler market example."
    if correct_streak >= 3:
        return f"Increase difficulty slightly in {active_skill} or move to the next module concept."
    return f"Continue the current {active_skill} lesson with one guided example and one independent check."


def _summary(
    active_skill: str,
    correct_count: int,
    wrong_count: int,
    scaffold_depth: int,
    module: int,
    diagnostic_progress: dict[str, Any] | None = None,
) -> str:
    if diagnostic_progress and diagnostic_progress.get("status") == "placed":
        placement = diagnostic_progress.get("placement") or {}
        return (
            "Baseline diagnostic placed child at "
            f"Module {placement.get('module', module)}, Week {placement.get('week', 1)}, "
            f"Lesson {placement.get('lesson', 1)}: {placement.get('reason', 'start at current level')}"
        )
    if diagnostic_progress and diagnostic_progress.get("status") == "in_progress":
        results = diagnostic_progress.get("results") or []
        return f"Baseline diagnostic in progress with {len(results)} item(s) answered; continue the oral placement game."
    if diagnostic_progress and diagnostic_progress.get("status") == "complete":
        return "Baseline diagnostic passed; child is ready for a Grade 4 bridge while monitoring mastery."
    if correct_count == 0 and wrong_count == 0:
        return f"Phone lesson started on {active_skill}; more evidence is needed before updating mastery."
    if scaffold_depth >= 2:
        return f"Child needs scaffolded review of {active_skill}; Sabi should continue from Module {module} with smaller prerequisite steps."
    return f"Child practiced {active_skill} with {correct_count} correct and {wrong_count} needing support."
