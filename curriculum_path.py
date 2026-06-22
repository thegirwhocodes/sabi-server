"""Deterministic curriculum path helpers for Sabi phone lessons.

The LLM can adapt the conversation, but the lesson sequence should remain
fixed: diagnostic placement chooses a module/week/lesson, then each call teaches
one small lesson slice and only advances after mastery evidence is saved.
"""

from __future__ import annotations

from typing import Any


MODULE_NAMES = {
    0: "diagnostic",
    1: "Number Sense: counting and comparison",
    2: "Addition",
    3: "Subtraction",
    4: "Multiplication",
    5: "Division",
    6: "Mixed Word Problems",
    7: "Grade 4 bridge",
}

MODULE_SKILLS = {
    1: "counting",
    2: "addition",
    3: "subtraction",
    4: "multiplication",
    5: "division",
    6: "word_problems",
    7: "grade_4_bridge",
}

MODULE_START = {
    1: {"week": 1, "global": 1, "weeks": 3},
    2: {"week": 4, "global": 13, "weeks": 4},
    3: {"week": 8, "global": 29, "weeks": 4},
    4: {"week": 12, "global": 45, "weeks": 5},
}

LESSON_TITLES = {
    1: "Counting 1 to 10",
    2: "Counting 11 to 20",
    3: "Counting Backward: 10 to 1 and 20 to 10",
    4: "What Comes Next and What Comes Before within 1-20",
    5: "Counting by 10s: the tens song",
    6: "Counting 20 to 50: crossing the tens",
    7: "Counting 50 to 100: completing the number line",
    8: "Skip Counting by 2s and 5s: finding patterns",
    9: "How Many: connecting counting to quantity",
    10: "Comparing Numbers: which is bigger and smaller",
    11: "Ordering Numbers: put them in order",
    12: "Module 1 review and number sense check",
    13: "What Is Addition: putting things together",
    14: "Addition facts to 5: plus and order does not matter",
    15: "Addition facts 6-10: counting on",
    16: "Doubles: same number plus same number",
    17: "Adding to Make 10: friends of 10",
    18: "Adding Past 10: bridge through 10",
    19: "Teen Number Addition: add to the ones",
    20: "Mixed Practice to 20 and speed round",
    21: "Place Value Review for Addition: tens and ones",
    22: "Adding Tens",
    23: "Adding two-digit plus one-digit",
    24: "Adding two-digit plus two-digit without carrying",
    25: "Introduction to carrying",
    26: "Carrying practice",
    27: "Addition word problems in Nigerian market context",
    28: "Module 2 review and addition mastery check",
    29: "What Is Subtraction: taking away",
    30: "Subtraction facts to 10: minus and counting back",
    31: "Subtraction as the opposite of addition: fact families",
    32: "Subtraction from 10: friends of 10 in reverse",
    33: "Subtracting from teen numbers: bridging back through 10",
    34: "Think addition for subtraction",
    35: "Mixed addition and subtraction: word clues",
    36: "Week 9 subtraction mini-check",
    37: "Subtracting Tens",
    38: "Two-digit minus one-digit without borrowing",
    39: "Two-digit minus two-digit without borrowing",
    40: "Nigerian context practice: Naira subtraction",
    41: "Introduction to borrowing",
    42: "Borrowing practice",
    43: "Word problems and mixed operations: market math",
    44: "Module 3 review and subtraction assessment",
    45: "What Is Multiplication: groups of",
    46: "The times symbol",
    47: "Times tables for 2 and 10",
    48: "Times table for 5",
    49: "The 3 times table",
    50: "The 4 times table: double the doubles",
    51: "The 6 times table: double the threes",
    52: "Mixed drill: 2s, 3s, 4s, 5s, 6s, and 10s",
    53: "The 9 times table tricks",
    54: "The 7 times table: building from known facts",
    55: "The 8 times table: double the fours",
    56: "The hardest facts: dedicated practice",
    57: "Commutative property: if you know one, you know the other",
    58: "Multiplying by 1 and 0",
    59: "Two-digit times one-digit mental math",
    60: "Naira multiplication problems",
    61: "Full times tables drill",
    62: "Multiplication word problems in Nigerian context",
    63: "Multiplication and division: inverse relationship",
    64: "Module 4 comprehensive assessment",
}

MODULE_PRINCIPLES = {
    1: "Use fingers, body parts, counting aloud, number neighbors, comparing, and ordering. Make counting feel powerful, not childish.",
    2: "Teach addition as putting groups together to find the total. Start with fingers or market items, then name plus, altogether, and total.",
    3: "Teach subtraction as taking away and finding what is left. Tie it to change at the market so the child feels in control.",
    4: "Teach multiplication as equal groups and repeated addition. Use packs, trays, children, notebooks, mangoes, and Naira prices.",
}

FALLBACK_MODULE_PROMPTS = {
    5: {
        "title": "Division as fair sharing",
        "focus": "Use sharing oranges, mangoes, notebooks, or snacks equally. Connect division back to known multiplication facts.",
        "next": "division facts and equal groups",
    },
    6: {
        "title": "Mixed market word problems",
        "focus": "Use one realistic Nigerian market story, identify the steps aloud, solve one step at a time, then check the answer.",
        "next": "harder two-step word problems",
    },
    7: {
        "title": "Grade 4 bridge problem",
        "focus": "Use a richer market or school problem, but keep it voice-friendly and scaffolded.",
        "next": "the next Grade 4 bridge problem",
    },
}

LITERACY_MODULE_NAMES = {
    1: "Phonemic Awareness",
    2: "Oral Vocabulary Building",
    3: "Listening Comprehension",
    4: "Oral English and Grammar",
    5: "Advanced Phonemic Awareness",
    6: "Print Bridge",
}

LITERACY_MODULE_START = {
    1: {"phase": 1, "week": 1, "global": 1, "weeks": 4, "suffix": ""},
    2: {"phase": 1, "week": 5, "global": 17, "weeks": 4, "suffix": ""},
    3: {"phase": 1, "week": 5, "global": 17, "weeks": 4, "suffix": "b"},
    4: {"phase": 1, "week": 9, "global": 33, "weeks": 4, "suffix": ""},
    5: {"phase": 1, "week": 9, "global": 33, "weeks": 4, "suffix": "b"},
}

LITERACY_MODULE_SKILLS = {
    1: "phonemic_awareness",
    2: "oral_vocabulary",
    3: "listening_comprehension",
    4: "oral_grammar",
    5: "advanced_phonemic_awareness",
    6: "print_bridge",
}

LITERACY_LESSON_TITLES = {
    1: {
        1: "Environmental Sounds vs. Speech Sounds: Hearing Differences",
        2: "Beginning Sounds: Identifying the First Sound in a Word",
        3: "Beginning Sounds Practice: Sorting Words by First Sound",
        4: "Ending Sounds: Identifying the Last Sound in a Word",
        5: "What Is Rhyming? Recognizing Rhyming Pairs",
        6: "Rhyming Practice: Identifying Which Words Rhyme",
        7: "Producing Rhymes: Making Up Rhyming Words",
        8: "Odd One Out: Which Word Does Not Rhyme?",
        9: "What Are Syllables? Clapping Word Parts",
        10: "Counting Syllables in 1-4 Syllable Words",
        11: "Blending Syllables: Putting Word Parts Together",
        12: "Segmenting Syllables: Breaking Words Into Parts",
        13: "Blending 2 Sounds Into Words",
        14: "Blending 3 Sounds: CVC Words",
        15: "Blending 3-4 Sounds: Harder Words",
        16: "Week 4 Review and Module Assessment",
    },
    2: {
        17: "Body Parts We Can See: The Touch Your Body Game",
        18: "Body Parts Inside: What They Do",
        19: "Health Words: Visiting the Clinic",
        20: "Action Verbs With the Body: Move and Learn",
        21: "Family Roles: Adaeze's Family Tree",
        22: "Household Items: Describing a Nigerian Home",
        23: "Describing Words for Home: Opposites",
        24: "Daily Routines: Sequencing Funke's Day",
        25: "Places in the Community: Where Do You Go?",
        26: "People and Jobs: What Do They Do?",
        27: "Market Words: Buying and Selling",
        28: "Transport and Direction Words: Giving Directions",
        29: "Common Animals: Animals Around Us",
        30: "Wild Animals of Africa: Our Amazing Continent",
        31: "Weather and Nature: Sun, Rain, and Harmattan",
        32: "Plants, Food, and Module Review: Vocabulary Assessment",
    },
    3: {
        17: "Amina Goes to the Market",
        18: "Emeka's Morning",
        19: "The Lost Goat",
        20: "Kemi's Birthday",
        21: "The Broken Bucket",
        22: "Tunde and the Homework",
        23: "The Market Fire",
        24: "Ngozi's Garden",
        25: "Bola's Bad Day",
        26: "The New Student",
        27: "Adaeze's Secret",
        28: "Two Brothers",
        29: "Lagos: The Big City",
        30: "How Cocoa Becomes Chocolate",
        31: "Nigerian Animals in Danger",
        32: "Module 3 Assessment: The School Garden",
    },
    4: {
        33: "What Is a Sentence?",
        34: "Expanding Sentences",
        35: "Statements vs. Questions",
        36: "Commands and Exclamations",
        37: "Present Tense",
        38: "Past Tense: Regular",
        39: "Past Tense: Irregular",
        40: "Future Tense",
        41: "Question Words: Who, What, Where",
        42: "Question Words: When, Why, How",
        43: "Answering in Full Sentences",
        44: "Asking Questions About a Story",
        45: "Adjectives: Words That Describe",
        46: "Comparatives: Comparing Two Things",
        47: "Superlatives: The Best of All",
        48: "Module 4 Review and Assessment",
    },
    5: {
        33: "Segmenting 3-Sound Words",
        34: "Segmenting 4-Sound Words",
        35: "Segmenting Words with Digraphs",
        36: "Segmentation Speed Drill",
        37: "Deleting the First Sound",
        38: "Deleting the Last Sound",
        39: "Deleting Middle Sounds in Blends",
        40: "Mixed Deletion Practice",
        41: "Changing the First Sound",
        42: "Changing the Last Sound",
        43: "Changing the Middle Sound",
        44: "Mixed Substitution Practice",
        45: "First Letter-Sound Pairs: S, A, T, I, P, N",
        46: "More Letter-Sound Pairs: C/K, E, H, R, M, D",
        47: "Building Words from Letter Sounds: Oral",
        48: "Module 5 Assessment and Phase 1 Exit Assessment",
    },
}

LITERACY_MODULE_PRINCIPLES = {
    1: "Teach oral sound awareness only: environmental sounds, beginning/ending sounds, rhyme, syllables, and oral blending. Say pure sounds, not letter names.",
    2: "Use the vocabulary cycle: say the word twice, give a child-friendly definition, use a Nigerian-context sentence, ask the child to repeat and use it.",
    3: "Tell one short Nigerian story, then ask who/what/where/when first before why/how. Support retelling, sequence, problem-solution, inference, and main idea.",
    4: "Teach oral grammar through complete spoken sentences: model, repeat, adapt. Keep grammar alive inside stories and daily-life speech.",
    5: "Teach advanced sound play: segmenting, deleting, substituting, and oral letter-sound links. Use pure sounds and do not claim print mastery from voice-only evidence.",
}


def resolve_numeracy_lesson(state: dict[str, Any] | None, current_module: int | None = None) -> dict[str, Any] | None:
    """Resolve module/week/local lesson into a concrete lesson record."""
    state = state or {}
    module = int(state.get("current_module") or current_module or 0)
    if module <= 0:
        return None

    if module not in MODULE_START:
        fallback = FALLBACK_MODULE_PROMPTS.get(module)
        if not fallback:
            return None
        week = int(state.get("current_week") or 1)
        lesson = int(state.get("current_lesson") or 1)
        return {
            "module": module,
            "module_name": MODULE_NAMES.get(module, "advanced numeracy"),
            "week": week,
            "lesson": lesson,
            "global_lesson": None,
            "title": fallback["title"],
            "focus": fallback["focus"],
            "next_title": fallback["next"],
        }

    meta = MODULE_START[module]
    start_week = int(meta["week"])
    week_count = int(meta["weeks"])
    week = int(state.get("current_week") or start_week)
    lesson = int(state.get("current_lesson") or 1)

    if week < start_week or week >= start_week + week_count:
        week = start_week
    if lesson < 1 or lesson > 4:
        lesson = 1

    global_lesson = int(meta["global"]) + (week - start_week) * 4 + (lesson - 1)
    title = LESSON_TITLES.get(global_lesson, MODULE_NAMES.get(module, "numeracy"))
    next_record = _next_lesson_record(module, week, lesson)
    return {
        "module": module,
        "module_name": MODULE_NAMES.get(module, "numeracy"),
        "week": week,
        "lesson": lesson,
        "global_lesson": global_lesson,
        "title": title,
        "focus": MODULE_PRINCIPLES.get(module, "Use concrete Nigerian examples before abstract notation."),
        "next_title": next_record.get("title") if next_record else "the next lesson",
    }


def resolve_literacy_lesson(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Resolve saved literacy phase/module/week/lesson into a script lesson."""
    state = state or {}
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else state
    literacy = literacy or {}
    module = int(literacy.get("current_module") or 1)
    if module not in LITERACY_MODULE_START:
        return {
            "phase": int(literacy.get("current_phase") or 2),
            "module": module,
            "module_name": LITERACY_MODULE_NAMES.get(module, "Literacy Bridge"),
            "week": int(literacy.get("current_week") or 13),
            "lesson": int(literacy.get("current_lesson") or 1),
            "script_lesson": None,
            "lesson_code": None,
            "title": "Print bridge readiness check",
            "focus": "Use oral review first; only ask print tasks when the child has a card, book, or screen.",
            "next_title": "the next print bridge lesson",
        }

    meta = LITERACY_MODULE_START[module]
    start_week = int(meta["week"])
    week_count = int(meta["weeks"])
    week = int(literacy.get("current_week") or start_week)
    lesson = int(literacy.get("current_lesson") or 1)

    if week < start_week or week >= start_week + week_count:
        week = start_week
    if lesson < 1 or lesson > 4:
        lesson = 1

    script_lesson = int(meta["global"]) + (week - start_week) * 4 + (lesson - 1)
    suffix = str(meta.get("suffix") or "")
    next_record = _next_literacy_lesson_record(module, week, lesson)
    return {
        "phase": int(meta["phase"]),
        "module": module,
        "module_name": LITERACY_MODULE_NAMES.get(module, "Foundational Literacy"),
        "week": week,
        "lesson": lesson,
        "script_lesson": script_lesson,
        "lesson_code": f"{script_lesson}{suffix}",
        "title": LITERACY_LESSON_TITLES.get(module, {}).get(script_lesson, "Foundational literacy practice"),
        "focus": LITERACY_MODULE_PRINCIPLES.get(module, "Teach one voice-friendly literacy skill at a time."),
        "next_title": next_record.get("title") if next_record else "the next literacy lesson",
    }


def build_curriculum_path_prompt(
    state: dict[str, Any] | None,
    current_module: int | None = None,
    course: str = "numeracy",
) -> str:
    """Prompt block that pins Sabi to the current lesson sequence."""
    state = state or {}
    if course == "literacy" or state.get("course") == "literacy":
        lesson = resolve_literacy_lesson(state)
        if not lesson:
            return ""
        return f"""

## CURRENT LITERACY CURRICULUM PATH - HACKATHON LESSON DISCIPLINE
Sabi is following the fixed Phase 1 literacy sequence, not choosing random sound games.
Today: Phase {lesson['phase']}, Module {lesson['module']} ({lesson['module_name']}), Week {lesson['week']}, Script Lesson {lesson['lesson_code'] or lesson['script_lesson']}, Local Lesson {lesson['lesson']}: {lesson['title']}.
Teaching focus: {lesson['focus']}

Follow the original hackathon lesson rhythm for this exact literacy lesson:
1. Warm greeting plus one recall question from the previous lesson.
2. Today's skill: model one sound, word, story, or sentence skill.
3. Guided practice: do one example together.
4. Independent check: ask one fresh example and wait.
5. Planned wrap-up only near the end: summarize the skill and preview "{lesson['next_title']}".

Rules:
- Stay on this literacy lesson for the whole call unless the caller explicitly ends.
- If the child is right, acknowledge the exact answer and move to the next step in THIS lesson.
- If the child is wrong twice, bump down to a smaller oral unit in THIS lesson, then rebuild.
- For phonemic work, pronounce pure sounds, not letter names, unless the lesson is specifically a letter-sound bridge.
- Do not claim print reading mastery from voice-only evidence.
- Do not output bracketed performance tags like [laugh] or [chuckle]."""

    lesson = resolve_numeracy_lesson(state, current_module)
    if not lesson:
        return ""

    global_label = f"Global Lesson {lesson['global_lesson']}, " if lesson.get("global_lesson") else ""
    phase = state.get("phase") or "teaching"
    next_step = state.get("next_step") or "Continue the planned lesson."
    return f"""

## CURRENT NUMERACY CURRICULUM PATH - HACKATHON LESSON DISCIPLINE
Sabi is following the fixed foundational numeracy sequence, not choosing random questions.
Today: Module {lesson['module']} ({lesson['module_name']}), Week {lesson['week']}, {global_label}Lesson {lesson['lesson']}: {lesson['title']}.
Teaching focus: {lesson['focus']}
Current call phase: {phase}.
Adaptive next step: {next_step}

Follow the original hackathon lesson rhythm for this exact lesson:
1. Warm greeting plus one recall question from the previous lesson.
2. Today's lesson: introduce one concept using a Nigerian life or market situation.
3. Guided practice: solve one example with the child.
4. Independent check: ask one fresh example and wait.
5. Planned wrap-up only near the end: summarize the skill and preview "{lesson['next_title']}".

Rules:
- Stay on this lesson for the whole call unless the caller explicitly ends.
- If the child is right, acknowledge the exact answer and move to the next step in THIS lesson.
- If the child is wrong twice, bump down to a prerequisite within THIS lesson, then rebuild.
- Do not jump to the next module during the call.
- Do not output bracketed performance tags like [laugh] or [chuckle]."""


def advance_numeracy_state_after_mastery(state: dict[str, Any]) -> dict[str, Any]:
    """Move persisted state to the next lesson after a successful call."""
    state = dict(state or {})
    if state.get("course") == "literacy":
        return state

    lesson = resolve_numeracy_lesson(state)
    if not lesson:
        return state

    next_record = _next_lesson_record(
        int(lesson["module"]),
        int(lesson["week"]),
        int(lesson["lesson"]),
    )
    if not next_record:
        return state

    state.update(
        {
            "phase": "recall",
            "diagnostic_status": "done",
            "current_module": next_record["module"],
            "current_week": next_record["week"],
            "current_lesson": next_record["lesson"],
            "active_skill": MODULE_SKILLS.get(next_record["module"], state.get("active_skill", "numeracy")),
            "correct_streak": 0,
            "wrong_streak": 0,
            "scaffold_depth": 0,
            "next_step": (
                f"Start Module {next_record['module']}, Week {next_record['week']}, "
                f"Lesson {next_record['lesson']}: {next_record['title']}. Begin with one recall question."
            ),
        }
    )
    return state


def advance_literacy_state_after_mastery(state: dict[str, Any]) -> dict[str, Any]:
    """Move persisted literacy state to the next lesson after mastery evidence."""
    state = dict(state or {})
    literacy = dict(state.get("literacy") or {})
    lesson = resolve_literacy_lesson({"literacy": literacy})
    if not lesson:
        return state

    next_record = _next_literacy_lesson_record(
        int(lesson["module"]),
        int(lesson["week"]),
        int(lesson["lesson"]),
    )
    if not next_record:
        return state

    literacy.update(
        {
            "phase": "recall",
            "diagnostic_status": "done",
            "current_phase": next_record["phase"],
            "current_module": next_record["module"],
            "current_week": next_record["week"],
            "current_lesson": next_record["lesson"],
            "active_skill": LITERACY_MODULE_SKILLS.get(next_record["module"], literacy.get("active_skill", "literacy")),
            "next_step": (
                f"Start Phase {next_record['phase']}, Module {next_record['module']}, Week {next_record['week']}, "
                f"Lesson {next_record['lesson']}: {next_record['title']}. Begin with one recall question."
            ),
        }
    )
    state.update(
        {
            "course": "literacy",
            "phase": "recall",
            "literacy": literacy,
        }
    )
    return state


def advance_learning_state_after_mastery(state: dict[str, Any]) -> dict[str, Any]:
    """Advance the active course without letting numeracy and literacy collide."""
    state = dict(state or {})
    if state.get("course") == "literacy":
        return advance_literacy_state_after_mastery(state)
    return advance_numeracy_state_after_mastery(state)


def _next_lesson_record(module: int, week: int, lesson: int) -> dict[str, Any] | None:
    if module not in MODULE_START:
        if module in (5, 6):
            return {
                "module": module,
                "week": week,
                "lesson": min(lesson + 1, 4),
                "title": FALLBACK_MODULE_PROMPTS[module]["next"],
            }
        return None

    meta = MODULE_START[module]
    start_week = int(meta["week"])
    week_count = int(meta["weeks"])
    global_lesson = int(meta["global"]) + (week - start_week) * 4 + (lesson - 1)
    module_last = int(meta["global"]) + week_count * 4 - 1

    if global_lesson < module_last:
        next_global = global_lesson + 1
        offset = next_global - int(meta["global"])
        next_week = start_week + offset // 4
        next_lesson = offset % 4 + 1
        return {
            "module": module,
            "week": next_week,
            "lesson": next_lesson,
            "title": LESSON_TITLES.get(next_global, "the next lesson"),
        }

    next_module = module + 1
    if next_module in MODULE_START:
        next_meta = MODULE_START[next_module]
        return {
            "module": next_module,
            "week": int(next_meta["week"]),
            "lesson": 1,
            "title": LESSON_TITLES.get(int(next_meta["global"]), MODULE_NAMES.get(next_module, "next module")),
        }
    if next_module in FALLBACK_MODULE_PROMPTS:
        return {
            "module": next_module,
            "week": week + 1,
            "lesson": 1,
            "title": FALLBACK_MODULE_PROMPTS[next_module]["title"],
        }
    return None


def _next_literacy_lesson_record(module: int, week: int, lesson: int) -> dict[str, Any] | None:
    if module not in LITERACY_MODULE_START:
        return None

    meta = LITERACY_MODULE_START[module]
    start_week = int(meta["week"])
    week_count = int(meta["weeks"])
    script_lesson = int(meta["global"]) + (week - start_week) * 4 + (lesson - 1)
    module_last = int(meta["global"]) + week_count * 4 - 1

    if script_lesson < module_last:
        next_script = script_lesson + 1
        offset = next_script - int(meta["global"])
        next_week = start_week + offset // 4
        next_lesson = offset % 4 + 1
        return {
            "phase": int(meta["phase"]),
            "module": module,
            "week": next_week,
            "lesson": next_lesson,
            "script_lesson": next_script,
            "title": LITERACY_LESSON_TITLES.get(module, {}).get(next_script, "the next literacy lesson"),
        }

    next_module = module + 1
    if next_module in LITERACY_MODULE_START:
        next_meta = LITERACY_MODULE_START[next_module]
        next_script = int(next_meta["global"])
        return {
            "phase": int(next_meta["phase"]),
            "module": next_module,
            "week": int(next_meta["week"]),
            "lesson": 1,
            "script_lesson": next_script,
            "title": LITERACY_LESSON_TITLES.get(next_module, {}).get(next_script, LITERACY_MODULE_NAMES.get(next_module, "the next literacy module")),
        }

    return {
        "phase": 2,
        "module": 6,
        "week": 13,
        "lesson": 1,
        "script_lesson": None,
        "title": "Print bridge readiness check",
    }
