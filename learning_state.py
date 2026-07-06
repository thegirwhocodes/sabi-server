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
from pilot_research_design import build_research_state, research_prompt_block


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


SCAFFOLD_LADDERS = {
    "counting": [
        {
            "teacher_move": "Rephrase with a smaller number-neighbor question under 20 and count aloud with the child.",
            "example_prompt": "Let's count together: one, two, three, four. What number comes after four?",
            "rebuild_move": "After one success, move back to the original number range one small step at a time.",
            "avoid": "Do not jump to addition before the child can say the next or previous number.",
        },
        {
            "teacher_move": "Return to one-to-one counting with fingers or real objects, no larger than ten.",
            "example_prompt": "Hold up three fingers and count them with me: one, two, three. How many fingers?",
            "rebuild_move": "Then ask one after/before question within ten before returning to the lesson.",
            "avoid": "Do not use market money yet; rebuild the number sequence first.",
        },
        {
            "teacher_move": "Use the most concrete counting base: count one object, then two objects, then three.",
            "example_prompt": "Put one finger up. Now put one more. Count them: one, two. How many fingers?",
            "rebuild_move": "When the child answers, rebuild to counting to five, then to ten.",
            "avoid": "Do not ask abstract number facts until the child succeeds with concrete counting.",
        },
    ],
    "addition": [
        {
            "teacher_move": "Use a smaller putting-together story and let the child count all items.",
            "example_prompt": "You have two mangoes and I give you one more. How many mangoes altogether?",
            "rebuild_move": "After success, return to sums under ten before trying the original problem size.",
            "avoid": "Do not repeat the same hard Naira amount.",
        },
        {
            "teacher_move": "Return to pure finger counting: count each group, then count all together. Use only sums to five.",
            "example_prompt": "Hold up one finger, then two more fingers. Count them all. How many altogether?",
            "rebuild_move": "Then ask one fresh sum to five, then one sum under ten.",
            "avoid": "Do not introduce carrying, teen numbers, or zero-plus problems yet.",
        },
        {
            "teacher_move": "Use the foundation of addition: one more and one plus one.",
            "example_prompt": "One finger plus one finger makes how many fingers?",
            "rebuild_move": "Move from one plus one to two plus one, then back to a tiny market story.",
            "avoid": "Do not say the child is wrong; model and ask a fresh tiny problem.",
        },
    ],
    "subtraction": [
        {
            "teacher_move": "Use a smaller take-away story and ask what is left.",
            "example_prompt": "You have five groundnuts and eat one. How many groundnuts are left?",
            "rebuild_move": "After success, return to subtraction within ten before trying the original problem size.",
            "avoid": "Do not turn the repair into addition unless the lesson is specifically think-addition.",
        },
        {
            "teacher_move": "Return to pure finger subtraction with very small numbers: show, take away, count what is left.",
            "example_prompt": "Hold up four fingers. Put one down. Count what is left. How many?",
            "rebuild_move": "Then ask four take away one, then five take away two.",
            "avoid": "Do not ask change-making or borrowing yet.",
        },
        {
            "teacher_move": "Use the foundation of subtraction: one less and two take away one.",
            "example_prompt": "If you have two sweets and give away one, how many sweets are left?",
            "rebuild_move": "Move from two take away one to three take away one, then back to a tiny market story.",
            "avoid": "Do not ask one plus one; the child needs take-away language here.",
        },
    ],
    "multiplication": [
        {
            "teacher_move": "Translate multiplication back to equal groups and repeated addition.",
            "example_prompt": "Two bags have three oranges each. That is three plus three. How many oranges?",
            "rebuild_move": "After success, name it as two groups of three before returning to the lesson.",
            "avoid": "Do not drill times-table facts before the child hears the groups.",
        },
        {
            "teacher_move": "Return to very small equal groups: two groups of two or two groups of three, counted on fingers.",
            "example_prompt": "Hold up two fingers, then two more. Count them all. Two groups of two is how many?",
            "rebuild_move": "Then ask two groups of three, then a fresh tiny market group story.",
            "avoid": "Do not use hard facts like six times seven.",
        },
        {
            "teacher_move": "Remove the times vocabulary and build the equal-groups idea from one group, then two groups.",
            "example_prompt": "One bag has two mangoes. Another bag has two mangoes. Count: two, four. How many mangoes?",
            "rebuild_move": "When the child succeeds, say: that is two groups of two.",
            "avoid": "Do not use the word multiply until the group idea is secure again.",
        },
    ],
    "division": [
        {
            "teacher_move": "Translate division into fair sharing with a very small number of items.",
            "example_prompt": "Share six oranges equally between two children. One for you, one for me. How many each?",
            "rebuild_move": "After success, return to a small division fact with the same sharing story.",
            "avoid": "Do not use the division symbol or large money amounts yet.",
        },
        {
            "teacher_move": "Return to four items shared between two people, one at a time.",
            "example_prompt": "Share four sweets between two friends. Give one to each, then one to each again. How many each friend gets?",
            "rebuild_move": "Then ask six shared between two.",
            "avoid": "Do not ask grouping and fair-sharing variants in the same repair turn.",
        },
        {
            "teacher_move": "Use the foundation of fair sharing: two things shared by two people.",
            "example_prompt": "Two biscuits, two children. Give one biscuit to each child. How many does each child get?",
            "rebuild_move": "Move to four shared by two, then six shared by two.",
            "avoid": "Do not connect back to multiplication until the child succeeds with sharing.",
        },
    ],
    "word_problems": [
        {
            "teacher_move": "Separate the story from the calculation: identify the numbers and choose the operation first.",
            "example_prompt": "In this story, are we putting money together or taking money away?",
            "rebuild_move": "After the child chooses the operation, solve one tiny one-step version.",
            "avoid": "Do not ask a two-step problem yet.",
        },
        {
            "teacher_move": "Reduce to one-step comprehension: what do we know, what are we finding?",
            "example_prompt": "You have five naira and spend two naira. Are we finding total money or money left?",
            "rebuild_move": "Then solve that one-step problem before returning to the original story.",
            "avoid": "Do not combine addition, subtraction, and multiplication in one repair turn.",
        },
        {
            "teacher_move": "Ask only the operation choice with tiny numbers; no calculation yet.",
            "example_prompt": "If you buy two things, do you add the prices or take them away?",
            "rebuild_move": "After the child identifies add or take away, ask a tiny calculation.",
            "avoid": "Do not make the child hold the whole story in memory.",
        },
    ],
    "phonemic_awareness_beginning": [
        {
            "teacher_move": "Use a more obvious word and stretch the first sound.",
            "example_prompt": "Listen: mmmango. What sound starts mmmango?",
            "rebuild_move": "Then try another word with the same first sound.",
            "avoid": "Do not ask for letter names when the skill is sound awareness.",
        },
        {
            "teacher_move": "Give two examples before asking: both words start with the same sound.",
            "example_prompt": "Mango and moon both start with mmm. Say mmm. What sound starts mango?",
            "rebuild_move": "Then ask the child to choose whether two words start the same.",
            "avoid": "Do not move to blending yet.",
        },
        {
            "teacher_move": "Use pure sound imitation only.",
            "example_prompt": "Say mmm with me. Good. Now say mmmango.",
            "rebuild_move": "After imitation, ask for the first sound in one familiar word.",
            "avoid": "Do not grade harshly; this is auditory awareness.",
        },
    ],
    "rhyming": [
        {
            "teacher_move": "Give two clear rhyming examples before asking the child to identify one.",
            "example_prompt": "Cat and hat sound the same at the end. Do cat and mat rhyme?",
            "rebuild_move": "Then ask the child to choose between one rhyming and one non-rhyming pair.",
            "avoid": "Do not ask the child to produce a rhyme until recognition is secure.",
        },
        {
            "teacher_move": "Make the ending sound louder and slower.",
            "example_prompt": "C-at, h-at. They both end with at. Do they sound the same at the end?",
            "rebuild_move": "Then try bat and cat.",
            "avoid": "Do not introduce beginning sounds in the same repair.",
        },
        {
            "teacher_move": "Use call-and-response with one rhyme family.",
            "example_prompt": "Say cat. Say hat. Hear the at at the end?",
            "rebuild_move": "After repeating, ask if cat and hat rhyme.",
            "avoid": "Do not ask for invented nonsense words.",
        },
    ],
    "blending": [
        {
            "teacher_move": "Reduce from three sounds to two sounds and blend slowly.",
            "example_prompt": "Listen: g ... o. Put it together. What word?",
            "rebuild_move": "Then try one easy three-sound word like c ... a ... t.",
            "avoid": "Do not use digraphs like sh until two-sound blending works.",
        },
        {
            "teacher_move": "Model the blending, then ask the child to repeat.",
            "example_prompt": "I say g ... o, then I slide it together: go. Your turn: g ... o.",
            "rebuild_move": "After repetition, ask the child to blend without your answer.",
            "avoid": "Do not ask for spelling or letter names.",
        },
        {
            "teacher_move": "Use pure oral imitation only.",
            "example_prompt": "Say go. Now say g ... o. Now say go again.",
            "rebuild_move": "Then ask what word g ... o makes.",
            "avoid": "Do not move to printed words.",
        },
    ],
    "listening_comprehension": [
        {
            "teacher_move": "Shorten the story to one sentence and ask a who or what question.",
            "example_prompt": "Amina carried an umbrella because the sky was dark. What did Amina carry?",
            "rebuild_move": "Then ask one why question using the same sentence.",
            "avoid": "Do not ask inference before literal recall succeeds.",
        },
        {
            "teacher_move": "Repeat the one sentence and give two answer choices.",
            "example_prompt": "Did Amina carry an umbrella or a football?",
            "rebuild_move": "After success, ask the same question without choices.",
            "avoid": "Do not tell a longer story yet.",
        },
        {
            "teacher_move": "Use echo-retell: child repeats the sentence before answering.",
            "example_prompt": "Say this with me: Amina carried an umbrella. Good. What did Amina carry?",
            "rebuild_move": "Then return to one short story with one question.",
            "avoid": "Do not stack multiple questions.",
        },
    ],
    "oral_grammar": [
        {
            "teacher_move": "Model one complete sentence, then ask the child to adapt one word.",
            "example_prompt": "Say: I am going to school. Now change school to market.",
            "rebuild_move": "After success, ask for one fresh complete sentence.",
            "avoid": "Do not explain grammar labels before the spoken pattern is secure.",
        },
        {
            "teacher_move": "Use repeat-after-me first.",
            "example_prompt": "Repeat: I bought mangoes. Good. Now say: I bought rice.",
            "rebuild_move": "Then ask the child to make one sentence with I bought.",
            "avoid": "Do not correct every accent feature; focus on the target pattern.",
        },
        {
            "teacher_move": "Use one sentence frame only.",
            "example_prompt": "Say: I have __. Put mangoes in the blank.",
            "rebuild_move": "Then put books in the same blank.",
            "avoid": "Do not switch tense or sentence type yet.",
        },
    ],
}


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
        "repair_skill": None,
        "scaffold_ladder": None,
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
        "research": build_research_state({}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_learning_state(student: dict[str, Any] | None) -> dict[str, Any]:
    state = default_learning_state()
    if not student:
        return state
    existing = student.get("learning_state")
    if isinstance(existing, dict):
        state.update(existing)
    research_state = student.get("research_state")
    if isinstance(research_state, dict):
        state["research"] = research_state
    elif not isinstance(state.get("research"), dict):
        state["research"] = build_research_state(student)
    current_module = student.get("current_module")
    if isinstance(current_module, int):
        state["current_module"] = current_module
        state["active_skill"] = MODULE_SKILLS.get(current_module, state.get("active_skill", "diagnostic"))
    return state


def route_next_course_after_session(
    state: dict[str, Any],
    user_turns: int = 0,
    has_learning_evidence: bool | None = None,
) -> dict[str, Any]:
    """Select the course for the next call while preserving each course's state.

    Pilot docs call for alternating literacy/numeracy. This only changes the
    saved next-call route after the child has actually spoken; it never switches
    the active lesson mid-call.
    """
    routed = dict(state or {})
    if has_learning_evidence is None:
        has_learning_evidence = user_turns > 0
    if user_turns <= 0 or not has_learning_evidence:
        return routed

    now = datetime.now(timezone.utc).isoformat()
    course = str(routed.get("course") or "numeracy")
    literacy = dict(routed.get("literacy") or {})
    numeracy_done = routed.get("diagnostic_status") == "done" and int(routed.get("current_module") or 0) > 0
    literacy_done = literacy.get("diagnostic_status") == "done"

    if course == "numeracy" and numeracy_done:
        literacy_phase = "recall" if literacy_done else "diagnostic"
        literacy.setdefault("phase", literacy_phase)
        if not literacy_done:
            literacy["phase"] = "diagnostic"
            literacy.setdefault("next_step", "Run the warm sound-and-story diagnostic disguised as a game.")
        routed.update(
            {
                "course": "literacy",
                "phase": literacy.get("phase") or literacy_phase,
                "literacy": literacy,
                "next_step": "Next call should switch to foundational literacy while preserving numeracy progress.",
                "course_rotation": {
                    "last_completed_course": "numeracy",
                    "next_course": "literacy",
                    "updated_at": now,
                },
                "updated_at": now,
            }
        )
        return routed

    if course == "literacy" and literacy_done:
        routed.update(
            {
                "course": "numeracy",
                "phase": "recall" if numeracy_done else "diagnostic",
                "next_step": (
                    "Next call should return to the saved numeracy lesson."
                    if numeracy_done
                    else "Next call should run the numeracy diagnostic game."
                ),
                "course_rotation": {
                    "last_completed_course": "literacy",
                    "next_course": "numeracy",
                    "updated_at": now,
                },
                "updated_at": now,
            }
        )
        return routed

    routed["updated_at"] = now
    return routed


def scaffold_ladder_for(active_skill: str, scaffold_depth: int, wrong_streak: int) -> dict[str, Any] | None:
    level = _scaffold_level(scaffold_depth, wrong_streak)
    if level <= 0:
        return None
    canonical_skill = _canonical_scaffold_skill(active_skill)
    ladder_steps = SCAFFOLD_LADDERS.get(canonical_skill)
    if not ladder_steps:
        return None
    step = dict(ladder_steps[min(level, len(ladder_steps)) - 1])
    step.update(
        {
            "skill": canonical_skill,
            "level": level,
            "trigger": "deep_bump_down" if level >= 3 else "bump_down" if level == 2 else "repair",
        }
    )
    return step


def _scaffold_level(scaffold_depth: int, wrong_streak: int) -> int:
    if wrong_streak >= 3 or scaffold_depth >= 3:
        return 3
    if wrong_streak >= 2 or scaffold_depth >= 2:
        return 2
    if wrong_streak == 1 or scaffold_depth == 1:
        return 1
    return 0


def _canonical_scaffold_skill(active_skill: str) -> str:
    skill = (active_skill or "").lower()
    if skill in SCAFFOLD_LADDERS:
        return skill
    if "phonemic" in skill or "beginning" in skill or "sound" in skill:
        return "phonemic_awareness_beginning"
    if "rhyme" in skill:
        return "rhyming"
    if "blend" in skill:
        return "blending"
    if "comprehension" in skill or "story" in skill or "listening" in skill:
        return "listening_comprehension"
    if "grammar" in skill or "sentence" in skill:
        return "oral_grammar"
    if "word" in skill and "problem" in skill:
        return "word_problems"
    return skill


def infer_skill_from_question(question: str, fallback_module: int = 0) -> str:
    lower = question.lower()
    if re.search(r"\b(times|multiply|each|every)\b", lower) or (
        re.search(r"\b(cost|costs|costing)\b", lower)
        and re.search(r"\b(buy|buys|bought)\b", lower)
        and re.search(r"\b(pay|pays|paid)\b", lower)
    ):
        return "multiplication"
    if re.search(r"\b(groups?\s+of)\b", lower):
        return "multiplication"
    if re.search(r"\b(share|shared|divide|divided|equally|groups)\b", lower):
        return "division"
    if _looks_like_total_spend_question(lower):
        return "addition"
    if re.search(r"\b(change|left|remain|minus|subtract|take away|took away|spent|spend)\b", lower):
        return "subtraction"
    if re.search(r"\b(enough|both|how much did you make|keep half)\b", lower):
        return "word_problems"
    if re.search(r"\b(altogether|total|plus|add|together|in all)\b", lower):
        return "addition"
    if re.search(r"\b(after|before|count|bigger|which number)\b", lower) or re.search(
        r"\b(which is smaller|which number is smaller|smaller number)\b",
        lower,
    ):
        return "counting"
    return MODULE_SKILLS.get(fallback_module, "diagnostic")


def _looks_like_total_spend_question(question_lower: str) -> bool:
    if re.search(r"\b(change|left|remain|remaining|minus|subtract|take away)\b", question_lower):
        return False
    return bool(
        re.search(r"\b(how much (?:do|did|will|would)?\s*(?:you|they|we|she|he)?\s*(?:spend|pay)|total cost|cost in all|spend in all|paid in all|altogether|in total|in all)\b", question_lower)
        and re.search(r"\b(spend|spent|pay|paid|costs?|costing|for|at)\b", question_lower)
    )


def extract_child_name(messages: list[dict[str, str]]) -> str | None:
    non_names = {
        "yes", "no", "okay", "ok", "hello", "hi", "ready", "thank you",
        "thanks", "sorry", "i'm sorry", "im sorry", "i am sorry",
        "i don't know", "i dont know", "and some", "numerous",
    }
    for index, message in enumerate(messages[:8]):
        if message.get("role") != "user":
            continue
        text = message.get("content", "").strip()
        normalized = re.sub(r"[^a-z' ]", "", text.lower()).strip()
        previous_assistant = ""
        for prev_index in range(index - 1, -1, -1):
            if messages[prev_index].get("role") == "assistant":
                previous_assistant = messages[prev_index].get("content", "").lower()
                break
        asked_name = "your name" in previous_assistant or "tell me your name" in previous_assistant
        match = re.search(r"\b(my name is|i am|i'm|its|it's)\s+([A-Za-z][A-Za-z' -]{1,30})", text, re.I)
        if match:
            phrase = match.group(1).lower()
            candidate = _clean_name(match.group(2))
            if candidate and candidate.lower() not in non_names:
                if phrase == "my name is" or asked_name:
                    return candidate
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
    scaffold_ladder = scaffold_ladder_for(active_skill, scaffold_depth, wrong_streak)
    next_step = _next_step(active_skill, scaffold_depth, wrong_streak, correct_streak, scaffold_ladder)
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
        "repair_skill": active_skill if scaffold_ladder else None,
        "scaffold_ladder": scaffold_ladder,
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
    if state.get("course") == "literacy":
        active_skill = (state.get("literacy") or {}).get("active_skill", active_skill)
    scaffold_depth = int(state.get("scaffold_depth") or 0)
    wrong_streak = int(state.get("wrong_streak") or 0)
    correct_streak = int(state.get("correct_streak") or 0)
    scaffold_ladder = state.get("scaffold_ladder")
    if not isinstance(scaffold_ladder, dict):
        scaffold_ladder = scaffold_ladder_for(state.get("repair_skill") or active_skill, scaffold_depth, wrong_streak)
    ladder_block = _scaffold_ladder_prompt(scaffold_ladder, wrong_streak, scaffold_depth)
    research_block = research_prompt_block(state.get("research"))

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
{research_block}
{ladder_block}
If wrong streak is 2 or more, do the proposed bump-down behavior immediately:
1. Stop increasing difficulty.
2. Follow the REQUIRED BUMP-DOWN LADDER above when it is present.
3. Ask one fresh easier question; do not repeat the same hard question.
4. After a successful answer, return one small step upward, not all the way to the hard problem."""


def _scaffold_ladder_prompt(
    scaffold_ladder: dict[str, Any] | None,
    wrong_streak: int,
    scaffold_depth: int,
) -> str:
    if not scaffold_ladder:
        return ""
    title = "REQUIRED BUMP-DOWN LADDER" if scaffold_ladder.get("level", 0) >= 2 else "FIRST REPAIR LADDER"
    return f"""

## {title}
- Repair skill: {scaffold_ladder.get('skill')}
- Trigger: wrong streak {wrong_streak}, scaffold depth {scaffold_depth}
- Teacher move: {scaffold_ladder.get('teacher_move')}
- Ask this style of easier question next: {scaffold_ladder.get('example_prompt')}
- Rebuild move after success: {scaffold_ladder.get('rebuild_move')}
- Avoid: {scaffold_ladder.get('avoid')}"""


def _analyze_literacy_session(
    student: dict[str, Any] | None,
    messages: list[dict[str, str]],
    state: dict[str, Any],
) -> SessionStats:
    literacy = dict(state.get("literacy") or {})
    if literacy.get("diagnostic_status") == "done":
        return _analyze_literacy_lesson_session(student, messages, state, literacy)

    progress = analyze_literacy_diagnostic_progress(messages)
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


def _analyze_literacy_lesson_session(
    student: dict[str, Any] | None,
    messages: list[dict[str, str]],
    state: dict[str, Any],
    literacy: dict[str, Any],
) -> SessionStats:
    user_turns = sum(1 for message in messages if message.get("role") == "user")
    assistant_text = " ".join(
        str(message.get("content") or "").lower()
        for message in messages
        if message.get("role") == "assistant"
    )
    completed = user_turns >= 2 and bool(
        re.search(
            r"\b(today you learned|next time|call me back|you did great|well done.*today|we will continue)\b",
            assistant_text,
        )
    )
    active_skill = literacy.get("active_skill") or "oral_literacy"
    literacy.update(
        {
            "phase": "recall" if completed else "teaching",
            "diagnostic_status": "done",
            "next_step": (
                "Save the next literacy lesson for the next call."
                if completed
                else "Continue the exact current literacy lesson with one guided example and one independent check."
            ),
        }
    )
    updated_state = {
        **state,
        "course": "literacy",
        "phase": literacy.get("phase", "teaching"),
        "literacy": literacy,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    module = int(literacy.get("current_module") or 1)
    week = int(literacy.get("current_week") or 1)
    lesson = int(literacy.get("current_lesson") or 1)
    summary = (
        f"Child completed Literacy Module {module}, Week {week}, Lesson {lesson}."
        if completed
        else f"Child practiced Literacy Module {module}, Week {week}, Lesson {lesson}; continue this exact lesson."
    )
    return SessionStats(
        summary=summary,
        correct_count=0,
        wrong_count=0,
        topics_covered=[f"literacy:{active_skill}"],
        recommended_module=int(state.get("current_module") or 0),
        current_level="intermediate" if user_turns >= 3 else "beginner",
        should_advance=completed,
        skills={},
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


def _next_step(
    active_skill: str,
    scaffold_depth: int,
    wrong_streak: int,
    correct_streak: int,
    scaffold_ladder: dict[str, Any] | None = None,
) -> str:
    if scaffold_ladder and (wrong_streak >= 3 or scaffold_depth >= 3):
        return (
            f"Deep bump-down for {active_skill}: {scaffold_ladder['teacher_move']} "
            f"Ask: {scaffold_ladder['example_prompt']} Then rebuild: {scaffold_ladder['rebuild_move']}"
        )
    if scaffold_ladder and (wrong_streak >= 2 or scaffold_depth >= 2):
        return (
            f"Bump down for {active_skill}: {scaffold_ladder['teacher_move']} "
            f"Ask a fresh easier question like: {scaffold_ladder['example_prompt']}"
        )
    if scaffold_ladder and wrong_streak == 1:
        return (
            f"Repair {active_skill}: {scaffold_ladder['teacher_move']} "
            f"Then ask: {scaffold_ladder['example_prompt']}"
        )
    if wrong_streak >= 3 or scaffold_depth >= 3:
        return f"Use the most concrete prerequisite for {active_skill}: count objects aloud, then ask one plus one or two plus one before returning upward."
    if wrong_streak >= 2 or scaffold_depth >= 2:
        return f"Bump down for {active_skill}: use smaller numbers, model the first step, and ask a fresh easier question."
    if wrong_streak == 1:
        return f"Repair {active_skill}: acknowledge the attempt and rephrase with a simpler market example."
    if correct_streak >= 3:
        return f"Move to the independent check or a small bonus challenge in the same {active_skill} lesson. Save the next lesson for the next call."
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
