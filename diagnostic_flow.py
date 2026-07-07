"""TaRL-style diagnostic routing for Sabi phone lessons.

The LLM can make the call feel human, but the baseline ladder should be
explicit. These items are adapted from the February diagnostic scripts:
quick, oral, one-on-one, contextually familiar, and progressive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from numeric_grading import extract_numbers, is_confusable_numeric_answer
from transcript_normalizer import is_non_answer_transcript


@dataclass(frozen=True)
class DiagnosticItem:
    id: str
    domain: str
    prompt: str
    expected: tuple[int, ...]
    fail_module: int
    fail_week: int
    fail_lesson: int
    fail_tarl_level: int
    fail_reason: str
    matchers: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticResult:
    item_id: str
    domain: str
    correct: bool
    expected: tuple[int, ...]
    child_numbers: tuple[int, ...]
    assistant_question: str
    child_answer: str


@dataclass(frozen=True)
class LiteracyDiagnosticItem:
    id: str
    domain: str
    prompt: str
    fail_phase: int
    fail_module: int
    fail_week: int
    fail_lesson: int
    fail_tarl_level: int
    fail_reason: str
    matchers: tuple[str, ...]
    correct_patterns: tuple[str, ...]
    partial_patterns: tuple[str, ...] = ()


NUMERACY_DIAGNOSTIC_ITEMS: tuple[DiagnosticItem, ...] = (
    DiagnosticItem(
        id="count_after_29",
        domain="counting",
        prompt="Let's play a quick number game. What number comes after twenty-nine?",
        expected=(30,),
        fail_module=1,
        fail_week=1,
        fail_lesson=1,
        fail_tarl_level=0,
        fail_reason="Needs counting sequence and tens-transition practice.",
        matchers=(r"after\s+(?:twenty[- ]?nine|29)",),
    ),
    DiagnosticItem(
        id="count_after_99",
        domain="counting",
        prompt="Good. What number comes after ninety-nine?",
        expected=(100,),
        fail_module=1,
        fail_week=2,
        fail_lesson=1,
        fail_tarl_level=1,
        fail_reason="Counts some numbers but needs work crossing into hundreds.",
        matchers=(r"after\s+(?:ninety[- ]?nine|99)",),
    ),
    DiagnosticItem(
        id="compare_7_3",
        domain="number_sense",
        prompt="Which is bigger: seven or three?",
        expected=(7,),
        fail_module=1,
        fail_week=1,
        fail_lesson=1,
        fail_tarl_level=0,
        fail_reason="Needs one-digit comparison and quantity sense.",
        matchers=(r"bigger.*(?:seven|7).*(?:three|3)", r"(?:seven|7).*(?:three|3).*bigger"),
    ),
    DiagnosticItem(
        id="compare_23_32",
        domain="number_sense",
        prompt="Nice. Which is bigger: twenty-three or thirty-two?",
        expected=(32,),
        fail_module=1,
        fail_week=3,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Needs two-digit place-value comparison.",
        matchers=(r"bigger.*(?:twenty[- ]?three|23).*(?:thirty[- ]?two|32)",),
    ),
    DiagnosticItem(
        id="compare_156_148",
        domain="number_sense",
        prompt="Try one more: which is bigger, one hundred and fifty-six or one hundred and forty-eight?",
        expected=(156,),
        fail_module=1,
        fail_week=3,
        fail_lesson=2,
        fail_tarl_level=2,
        fail_reason="Compares smaller numbers but needs three-digit place value.",
        matchers=(r"(?:one hundred and fifty[- ]?six|156).*(?:one hundred and forty[- ]?eight|148)",),
    ),
    DiagnosticItem(
        id="add_within_10",
        domain="addition",
        prompt="You buy pure water for three naira and groundnuts for two naira. How much altogether?",
        expected=(5,),
        fail_module=1,
        fail_week=3,
        fail_lesson=3,
        fail_tarl_level=2,
        fail_reason="Has some number sense but needs addition readiness.",
        matchers=(r"three naira.*two naira.*altogether", r"3.*2.*altogether"),
    ),
    DiagnosticItem(
        id="add_within_20",
        domain="addition",
        prompt="Biscuits cost eight naira and sweets cost seven naira. How much altogether?",
        expected=(15,),
        fail_module=2,
        fail_week=5,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Can add small numbers but needs teen addition and bridging.",
        matchers=(r"eight naira.*seven naira.*altogether", r"8.*7.*altogether"),
    ),
    DiagnosticItem(
        id="add_two_digit_no_carry",
        domain="addition",
        prompt="Tomatoes cost twenty-three naira and peppers cost fourteen naira. How much altogether?",
        expected=(37,),
        fail_module=2,
        fail_week=6,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Needs two-digit addition without carrying.",
        matchers=(r"twenty[- ]?three naira.*fourteen naira", r"23.*14"),
    ),
    DiagnosticItem(
        id="add_two_digit_carry",
        domain="addition",
        prompt="Garri costs forty-seven naira and oil costs thirty-eight naira. How much altogether?",
        expected=(85,),
        fail_module=2,
        fail_week=7,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Needs two-digit addition with carrying.",
        matchers=(r"forty[- ]?seven naira.*thirty[- ]?eight naira", r"47.*38"),
    ),
    DiagnosticItem(
        id="subtract_within_10",
        domain="subtraction",
        prompt="You have nine naira and spend four naira. How much is left?",
        expected=(5,),
        fail_module=3,
        fail_week=9,
        fail_lesson=1,
        fail_tarl_level=3,
        fail_reason="Ready for subtraction from concrete take-away stories.",
        matchers=(r"nine naira.*(?:spend|spent).*four naira.*left", r"9.*4.*left"),
    ),
    DiagnosticItem(
        id="subtract_within_20",
        domain="subtraction",
        prompt="You have fifteen naira and spend eight naira on biscuits. How much is left?",
        expected=(7,),
        fail_module=3,
        fail_week=9,
        fail_lesson=2,
        fail_tarl_level=3,
        fail_reason="Needs subtraction within twenty and bridging through ten.",
        matchers=(r"fifteen naira.*(?:spend|spent).*eight naira.*left", r"15.*8.*left"),
    ),
    DiagnosticItem(
        id="subtract_two_digit_borrow",
        domain="subtraction",
        prompt="You have forty-two naira and spend eighteen naira. How much is left?",
        expected=(24,),
        fail_module=3,
        fail_week=10,
        fail_lesson=1,
        fail_tarl_level=3,
        fail_reason="Needs two-digit subtraction with borrowing.",
        matchers=(r"forty[- ]?two naira.*(?:spend|spent).*eighteen naira", r"42.*18"),
    ),
    DiagnosticItem(
        id="multiply_easy",
        domain="multiplication",
        prompt="A mango costs three naira. You buy four mangoes. How much do you pay?",
        expected=(12,),
        fail_module=4,
        fail_week=12,
        fail_lesson=1,
        fail_tarl_level=4,
        fail_reason="Ready for multiplication as equal groups.",
        matchers=(r"mango.*three naira.*four mango", r"3.*4.*mango"),
    ),
    DiagnosticItem(
        id="multiply_fact",
        domain="multiplication",
        prompt="A notebook costs six naira. You buy seven notebooks. How much do you pay?",
        expected=(42,),
        fail_module=4,
        fail_week=14,
        fail_lesson=1,
        fail_tarl_level=4,
        fail_reason="Knows early equal groups but needs harder multiplication facts.",
        matchers=(r"notebook.*six naira.*seven notebook", r"6.*7.*notebook"),
    ),
    DiagnosticItem(
        id="multiply_money",
        domain="multiplication",
        prompt="One mango costs thirty naira. You buy four mangoes. How much do you pay?",
        expected=(120,),
        fail_module=4,
        fail_week=14,
        fail_lesson=2,
        fail_tarl_level=4,
        fail_reason="Needs applying multiplication to money contexts.",
        matchers=(r"mango.*thirty naira.*four mango", r"30.*4.*mango"),
    ),
    DiagnosticItem(
        id="divide_sharing",
        domain="division",
        prompt="Twelve oranges are shared equally among three children. How many oranges does each child get?",
        expected=(4,),
        fail_module=5,
        fail_week=17,
        fail_lesson=1,
        fail_tarl_level=4,
        fail_reason="Ready for division as fair sharing.",
        matchers=(r"twelve oranges.*shared equally.*three children", r"12.*oranges.*3.*children"),
    ),
    DiagnosticItem(
        id="divide_fact",
        domain="division",
        prompt="Twenty-four mangoes are packed equally into six trays. How many mangoes are on each tray?",
        expected=(4,),
        fail_module=5,
        fail_week=17,
        fail_lesson=1,
        fail_tarl_level=4,
        fail_reason="Needs division facts and equal groups.",
        matchers=(r"twenty[- ]?four mangoes.*six trays", r"24.*mango.*6.*tray"),
    ),
    DiagnosticItem(
        id="mixed_change_problem",
        domain="word_problems",
        prompt="You buy four mangoes at thirty naira each and pay with two hundred naira. How much change do you get?",
        expected=(80,),
        fail_module=6,
        fail_week=21,
        fail_lesson=1,
        fail_tarl_level=4,
        fail_reason="Can calculate but needs mixed two-step word-problem reasoning.",
        matchers=(r"four mangoes.*thirty naira each.*two hundred naira.*change", r"4.*30.*200.*change"),
    ),
)

LITERACY_DIAGNOSTIC_ITEMS: tuple[LiteracyDiagnosticItem, ...] = (
    LiteracyDiagnosticItem(
        id="lit_beginning_sound_ball",
        domain="phonemic_awareness_beginning",
        prompt="Let's play a sound game. What sound do you hear at the very beginning of the word ball? Ball.",
        fail_phase=1,
        fail_module=1,
        fail_week=1,
        fail_lesson=1,
        fail_tarl_level=0,
        fail_reason="Needs beginning-sound awareness before phonics or reading work.",
        matchers=(r"beginning.*word ball", r"first sound.*ball"),
        correct_patterns=(r"\b/b/\b", r"\bb\b", r"\bbuh\b", r"\bbb+\b"),
    ),
    LiteracyDiagnosticItem(
        id="lit_rhyme_cat_hat",
        domain="rhyming",
        prompt="Good. Do cat and hat sound the same at the end? If yes, tell me another word that rhymes with cat.",
        fail_phase=1,
        fail_module=1,
        fail_week=2,
        fail_lesson=1,
        fail_tarl_level=0,
        fail_reason="Can try sounds, but needs rhyming and sound-pattern practice.",
        matchers=(r"cat.*hat.*same.*end", r"rhymes? with cat"),
        correct_patterns=(r"\b(bat|sat|fat|mat|rat|pat|hat|that)\b",),
        partial_patterns=(r"\byes\b", r"\bsame\b"),
    ),
    LiteracyDiagnosticItem(
        id="lit_blend_cat",
        domain="phonemic_blending",
        prompt="Now I will say sounds slowly. What word do these sounds make: k, a, t?",
        fail_phase=1,
        fail_module=1,
        fail_week=3,
        fail_lesson=1,
        fail_tarl_level=1,
        fail_reason="Needs oral blending practice with two- and three-sound words.",
        matchers=(r"sounds make.*k.*a.*t", r"\bk\b.*\ba\b.*\bt\b"),
        correct_patterns=(r"\bcat\b", r"\bkat\b"),
    ),
    LiteracyDiagnosticItem(
        id="lit_blend_ship",
        domain="phonemic_blending",
        prompt="Excellent. What word do these sounds make: sh, i, p?",
        fail_phase=1,
        fail_module=1,
        fail_week=4,
        fail_lesson=1,
        fail_tarl_level=1,
        fail_reason="Can blend simple words but needs more complex sound blending.",
        matchers=(r"sounds make.*sh.*i.*p", r"\bsh\b.*\bi\b.*\bp\b"),
        correct_patterns=(r"\bship\b",),
    ),
    LiteracyDiagnosticItem(
        id="lit_letter_sound_s",
        domain="letter_sound_knowledge",
        prompt="Do you know the sounds letters make? What sound does the letter S make?",
        fail_phase=1,
        fail_module=5,
        fail_week=10,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Has oral sound awareness but needs letter-sound mapping.",
        matchers=(r"letter s", r"\bs make"),
        correct_patterns=(r"\b/s/\b", r"\bs\b", r"\bsss+\b"),
    ),
    LiteracyDiagnosticItem(
        id="lit_spell_sat",
        domain="word_reading",
        prompt="I am going to spell a short word. S, A, T. What word is that?",
        fail_phase=2,
        fail_module=6,
        fail_week=13,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Knows some sounds but needs print-supported blending and decoding.",
        matchers=(r"s.*a.*t.*what word", r"spell.*short word"),
        correct_patterns=(r"\bsat\b",),
    ),
    LiteracyDiagnosticItem(
        id="lit_story_dog_gate",
        domain="listening_comprehension",
        prompt="Listen to this tiny story. The big dog ran to the gate. It barked at the man. The man jumped back. What did the dog do?",
        fail_phase=1,
        fail_module=3,
        fail_week=5,
        fail_lesson=1,
        fail_tarl_level=2,
        fail_reason="Needs listening comprehension, retelling, and story meaning practice.",
        matchers=(r"big dog ran to the gate", r"what did the dog do"),
        correct_patterns=(r"\bran\b", r"\bbarked\b", r"\bgate\b"),
    ),
)


def build_opening_turn(student: dict[str, Any] | None, state: dict[str, Any] | None) -> str:
    """Deterministic first turn so returning callers are not asked their name."""
    student = student or {}
    state = state or {}
    if student.get("needs_identity_confirmation"):
        return "Hello! I'm Sabi, your learning friend. I remember this phone, but more than one learner may use it. What is your name?"

    name = _clean_name(student.get("name") or "")
    course = str(state.get("course") or student.get("course") or "numeracy")
    module = int(state.get("current_module") or student.get("current_module") or 0)
    diagnostic_status = state.get("diagnostic_status") or student.get("baseline_status") or "not_started"
    onboarding_status = state.get("onboarding_status") or "needs_school"

    if not name:
        return "Hello! I'm Sabi, your learning friend. Sabi means to know, and together, we're going to know so much! What is your name?"
    if onboarding_status == "needs_name":
        onboarding_status = "needs_school"

    if course == "literacy":
        return _build_literacy_opening_turn(name, student, state, onboarding_status)

    if module == 0 or diagnostic_status != "done":
        if onboarding_status == "needs_name":
            return "Hello! I'm Sabi, your learning friend. Sabi means to know, and together, we're going to know so much! What is your name?"
        if onboarding_status == "needs_market":
            return f"Welcome back, {name}! I remember you. Do you help your family at the market, or do you sell anything?"
        if onboarding_status == "complete":
            progress = state.get("diagnostic_results") if isinstance(state.get("diagnostic_results"), dict) else None
            next_item = progress.get("next_item") if progress else None
            if isinstance(next_item, dict) and next_item.get("prompt"):
                return f"Welcome back, {name}! Let's continue our number game. {next_item['prompt']}"
            first_item = NUMERACY_DIAGNOSTIC_ITEMS[0]
            return f"Welcome back, {name}! Let's play a quick number game. {first_item.prompt}"
        return f"Welcome back, {name}! Sabi here. Before we start learning, tell me, do you go to school?"

    warmups = {
        1: "What number comes after nine?",
        2: "You buy pure water for five naira and groundnuts for three naira. How much altogether?",
        3: "You have ten naira and spend four naira. How much is left?",
        4: "A mango costs three naira. You buy four mangoes. How much do you pay?",
        5: "Twelve oranges are shared equally among three children. How many does each child get?",
        6: "You buy two eggs at fifty naira each and pay with two hundred naira. How much change do you get?",
    }
    warmup = warmups.get(module, "Tell me one thing you remember from our last lesson.")
    topic = state.get("active_skill") or student.get("current_topic") or "numbers"
    return f"Welcome back, {name}! Last time we worked on {topic}. Quick warm-up: {warmup}"


def _build_literacy_opening_turn(
    name: str,
    student: dict[str, Any],
    state: dict[str, Any],
    onboarding_status: str,
) -> str:
    literacy = state.get("literacy") if isinstance(state.get("literacy"), dict) else {}
    literacy = literacy or {}
    diagnostic_status = literacy.get("diagnostic_status", "not_started")

    if diagnostic_status != "done":
        if onboarding_status == "needs_name":
            return "Hello! I'm Sabi, your learning friend. Sabi means to know, and together, we're going to know so much! What is your name?"
        if onboarding_status == "needs_market":
            return f"Welcome back, {name}! I remember you. Before our sound game, do you help your family at the market, or do you sell anything?"
        if onboarding_status != "complete":
            return f"Welcome back, {name}! Sabi here. Before our sound game, tell me, do you go to school?"

        progress = literacy.get("diagnostic_results") if isinstance(literacy.get("diagnostic_results"), dict) else None
        next_item = progress.get("next_item") if progress else None
        if isinstance(next_item, dict) and next_item.get("prompt"):
            return f"Welcome back, {name}! Let's continue our sound game. {next_item['prompt']}"
        first_item = LITERACY_DIAGNOSTIC_ITEMS[0]
        return f"Welcome back, {name}! {first_item.prompt}"

    module = int(literacy.get("current_module") or 1)
    warmups = {
        1: "What sound do you hear at the beginning of ball?",
        2: "Tell me two words that rhyme with cat.",
        3: "Listen: the goat ran home. Who ran home?",
        4: "Say this sentence again: I bought rice.",
        5: "Say the first sound in sun.",
        6: "I will say three sounds: s, a, t. What word do they make?",
    }
    warmup = warmups.get(module, "Tell me one sound, word, or story part you remember from our last lesson.")
    topic = literacy.get("active_skill") or student.get("current_topic") or "sounds"
    return f"Welcome back, {name}! Last time we worked on {topic}. Quick sound warm-up: {warmup}"


def build_instructional_route_prompt(messages: list[dict[str, str]], current_module: int = 0, course: str = "numeracy") -> str:
    """Give the LLM the next hard instructional route without exposing code IDs."""
    if course == "literacy":
        return build_literacy_route_prompt(messages)

    if current_module != 0:
        latest = latest_diagnostic_result(messages)
        if latest and not latest.correct:
            item = item_by_id(latest.item_id)
            return _bump_down_prompt(item)
        return ""

    progress = analyze_diagnostic_progress(messages)
    if not _has_child_name(messages):
        return """

## CURRENT CALL ROUTE
First capture the child's name. Ask only for their name, warmly. Do not start the diagnostic until the first-call onboarding is complete."""

    onboarding = _first_call_onboarding_prompt(messages)
    if onboarding:
        return onboarding

    if progress["status"] == "placed":
        placement = progress["placement"]
        failed = progress["failed_item"]
        return f"""

## CURRENT CALL ROUTE — BASELINE PLACEMENT MADE
The child has shown enough for baseline placement. Do not continue harder diagnostic questions.
Placement: Module {placement['module']}, Week {placement['week']}, Lesson {placement['lesson']}, TaRL level {placement['tarl_level']}.
Reason: {placement['reason']}
Say warmly: "Good try — now I know where we should start."
Then begin a tiny first lesson at that exact level using concrete Nigerian market examples.
If the missed skill was {failed['domain']}, bump down to its prerequisite before asking another question."""

    if progress["status"] == "complete":
        return """

## CURRENT CALL ROUTE — BASELINE PASSED
The child passed the full foundational numeracy diagnostic. Do not ask more diagnostic items.
Celebrate briefly, then start a Grade 4 bridge style market word problem and keep monitoring."""

    next_item = progress["next_item"]
    return f"""

## CURRENT CALL ROUTE — NUMERACY DIAGNOSTIC GAME
Run the baseline as a quick game, not a test. Ask exactly ONE diagnostic item now, then wait.
Next item domain: {next_item['domain']}
Ask: "{next_item['prompt']}"
If they answer correctly, celebrate briefly and move to the next diagnostic item.
If they miss it, stop the diagnostic ladder and start teaching at the lower placement level. Do not ask harder diagnostic items after a miss."""


def build_literacy_route_prompt(messages: list[dict[str, str]]) -> str:
    progress = analyze_literacy_diagnostic_progress(messages)
    if not _has_child_name(messages):
        return """

## CURRENT CALL ROUTE
First capture the child's name. Ask only for their name, warmly. Do not start the literacy diagnostic until the first-call onboarding is complete."""

    onboarding = _first_call_onboarding_prompt(messages)
    if onboarding:
        return onboarding

    if progress["status"] == "placed":
        placement = progress["placement"]
        failed = progress["failed_item"]
        return f"""

## CURRENT CALL ROUTE — LITERACY BASELINE PLACEMENT MADE
The child has shown enough for literacy placement. Do not continue harder diagnostic questions.
Placement: Phase {placement['phase']}, Module {placement['module']}, Week {placement['week']}, Lesson {placement['lesson']}, TaRL reading level {placement['tarl_level']}.
Reason: {placement['reason']}
Say warmly: "Good try — now I know where we should start."
Then begin a tiny first oral literacy lesson at that exact level. If the missed skill was {failed['domain']}, bump down to its prerequisite and use easier sounds or a shorter story."""

    if progress["status"] == "complete":
        return """

## CURRENT CALL ROUTE — LITERACY BASELINE PASSED
The child passed the voice-only literacy diagnostic. Do not claim full reading mastery unless print evidence exists.
Celebrate briefly, then begin an oral comprehension or print-bridge lesson and say that reading with printed letters will need a card, book, or screen later."""

    next_item = progress["next_item"]
    return f"""

## CURRENT CALL ROUTE — LITERACY DIAGNOSTIC GAME
Run the baseline as a quick sound-and-story game, not a test. Ask exactly ONE diagnostic item now, then wait.
Next item domain: {next_item['domain']}
Ask: "{next_item['prompt']}"
If they answer correctly, celebrate briefly and move to the next literacy diagnostic item.
If they miss it, stop the ladder and start teaching at the lower placement level. Do not ask harder diagnostic items after a miss."""


def analyze_diagnostic_progress(messages: list[dict[str, str]]) -> dict[str, Any]:
    results = diagnostic_results_from_messages(messages)
    by_id = {result.item_id: result for result in results}

    first_failed: DiagnosticItem | None = None
    for item in NUMERACY_DIAGNOSTIC_ITEMS:
        result = by_id.get(item.id)
        if result and not result.correct:
            first_failed = item
            break

    if first_failed:
        return {
            "status": "placed",
            "results": [_result_payload(result) for result in results],
            "failed_item": _item_payload(first_failed),
            "placement": placement_for_failed_item(first_failed),
            "next_item": None,
        }

    for item in NUMERACY_DIAGNOSTIC_ITEMS:
        result = by_id.get(item.id)
        if not result:
            return {
                "status": "in_progress" if results else "not_started",
                "results": [_result_payload(result) for result in results],
                "failed_item": None,
                "placement": None,
                "next_item": _item_payload(item),
            }

    return {
        "status": "complete",
        "results": [_result_payload(result) for result in results],
        "failed_item": None,
        "placement": {
            "module": 7,
            "week": 1,
            "lesson": 1,
            "tarl_level": 4,
            "reason": "Passed the foundational numeracy diagnostic.",
        },
        "next_item": None,
    }


def analyze_literacy_diagnostic_progress(messages: list[dict[str, str]]) -> dict[str, Any]:
    results = literacy_diagnostic_results_from_messages(messages)
    by_id = {result["item_id"]: result for result in results}

    first_failed: LiteracyDiagnosticItem | None = None
    for item in LITERACY_DIAGNOSTIC_ITEMS:
        result = by_id.get(item.id)
        if result and not result["correct"]:
            first_failed = item
            break

    if first_failed:
        return {
            "status": "placed",
            "results": results,
            "failed_item": _literacy_item_payload(first_failed),
            "placement": literacy_placement_for_failed_item(first_failed),
            "next_item": None,
        }

    for item in LITERACY_DIAGNOSTIC_ITEMS:
        result = by_id.get(item.id)
        if not result:
            return {
                "status": "in_progress" if results else "not_started",
                "results": results,
                "failed_item": None,
                "placement": None,
                "next_item": _literacy_item_payload(item),
            }

    return {
        "status": "complete",
        "results": results,
        "failed_item": None,
        "placement": {
            "phase": 2,
            "module": 8,
            "week": 21,
            "lesson": 1,
            "tarl_level": 4,
            "reason": "Passed the voice-only literacy diagnostic; ready for comprehension and print-bridge work.",
        },
        "next_item": None,
    }


def literacy_diagnostic_results_from_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if message.get("role") != "user":
            continue
        assistant_question = ""
        for prev_index in range(index - 1, -1, -1):
            if messages[prev_index].get("role") == "assistant":
                assistant_question = messages[prev_index].get("content", "")
                break
        if not assistant_question:
            continue
        item = match_literacy_diagnostic_item(assistant_question)
        if not item:
            continue
        child_answer = message.get("content", "")
        if is_non_answer_transcript(child_answer):
            continue
        normalized = _normalize_text(child_answer)
        correct = any(re.search(pattern, normalized) for pattern in item.correct_patterns)
        partial = (not correct) and any(re.search(pattern, normalized) for pattern in item.partial_patterns)
        results.append(
            {
                "item_id": item.id,
                "domain": item.domain,
                "correct": correct,
                "partial": partial,
                "child_answer": child_answer,
            }
        )
    return results


def match_literacy_diagnostic_item(question: str) -> LiteracyDiagnosticItem | None:
    normalized = _normalize_text(question)
    for item in LITERACY_DIAGNOSTIC_ITEMS:
        if any(re.search(pattern, normalized) for pattern in item.matchers):
            return item
    return None


def literacy_placement_for_failed_item(item: LiteracyDiagnosticItem) -> dict[str, Any]:
    return {
        "phase": item.fail_phase,
        "module": item.fail_module,
        "week": item.fail_week,
        "lesson": item.fail_lesson,
        "tarl_level": item.fail_tarl_level,
        "reason": item.fail_reason,
    }


def diagnostic_results_from_messages(messages: list[dict[str, str]]) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    for index, message in enumerate(messages):
        if message.get("role") != "user":
            continue
        assistant_question = ""
        for prev_index in range(index - 1, -1, -1):
            if messages[prev_index].get("role") == "assistant":
                assistant_question = messages[prev_index].get("content", "")
                break
        if not assistant_question:
            continue
        item = match_diagnostic_item(assistant_question)
        if not item:
            continue
        child_answer = message.get("content", "")
        if is_non_answer_transcript(child_answer):
            continue
        child_numbers = tuple(extract_numbers(child_answer))
        if child_numbers and is_confusable_numeric_answer(item.expected, child_numbers):
            continue
        correct = any(expected in child_numbers for expected in item.expected)
        results.append(
            DiagnosticResult(
                item_id=item.id,
                domain=item.domain,
                correct=correct,
                expected=item.expected,
                child_numbers=child_numbers,
                assistant_question=assistant_question,
                child_answer=child_answer,
            )
        )
    return results


def latest_diagnostic_result(messages: list[dict[str, str]]) -> DiagnosticResult | None:
    results = diagnostic_results_from_messages(messages)
    return results[-1] if results else None


def match_diagnostic_item(question: str) -> DiagnosticItem | None:
    normalized = " ".join(question.lower().split())
    for item in NUMERACY_DIAGNOSTIC_ITEMS:
        if any(re.search(pattern, normalized) for pattern in item.matchers):
            return item
    return None


def item_by_id(item_id: str) -> DiagnosticItem | None:
    for item in NUMERACY_DIAGNOSTIC_ITEMS:
        if item.id == item_id:
            return item
    return None


def placement_for_failed_item(item: DiagnosticItem) -> dict[str, Any]:
    return {
        "module": item.fail_module,
        "week": item.fail_week,
        "lesson": item.fail_lesson,
        "tarl_level": item.fail_tarl_level,
        "reason": item.fail_reason,
    }


def _has_child_name(messages: list[dict[str, str]]) -> bool:
    for message in messages[:6]:
        if message.get("role") != "user":
            continue
        text = message.get("content", "").strip()
        if _looks_like_phone_system_response(text):
            continue
        if re.search(r"\b(?:my name is|i am|i'm|its|it's)\s+[A-Za-z]", text, re.I):
            return True
        if extract_numbers(text):
            continue
        if 1 <= len(text.split()) <= 3 and not re.search(r"\d|\b(yes|no|okay|hello|hi|ready)\b", text, re.I):
            return True
    return False


def _looks_like_phone_system_response(text: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"not available|currently unavailable|unavailable|not reachable|"
            r"switched off|line busy|mailbox|voice ?mail|"
            r"leave (?:a )?message|record (?:your )?message|"
            r"finished recording|after the tone|try again later|hang up"
            r")\b",
            str(text or "").lower(),
        )
    )


def onboarding_status_from_messages(messages: list[dict[str, str]]) -> str:
    """Return the next first-call onboarding step implied by this transcript."""
    if not _has_child_name(messages):
        return "needs_name"
    if not _has_answer_after_assistant(messages, r"\bdo you go to school\b"):
        return "needs_school"
    if not _has_answer_after_assistant(messages, r"\b(help.*family.*market|sell anything|help.*market)\b"):
        return "needs_market"
    return "complete"


def _first_call_onboarding_prompt(messages: list[dict[str, str]]) -> str:
    """Restore the original hackathon first-call rhythm before placement."""
    if not _has_answer_after_assistant(messages, r"\bdo you go to school\b"):
        return """

## CURRENT CALL ROUTE — FIRST-CALL ONBOARDING
The child has given their name. Do not begin the diagnostic yet.
Acknowledge the name warmly, say you will remember them on this number, then ask exactly:
"Tell me, do you go to school?"
Ask only that one question, then wait."""

    if not _has_answer_after_assistant(messages, r"\b(help.*family.*market|sell anything|help.*market)\b"):
        return """

## CURRENT CALL ROUTE — FIRST-CALL ONBOARDING
The child has answered the school question. Do not begin the diagnostic yet.
Ask one gentle life-context question, exactly:
"Do you help your family at the market, or do you sell anything?"
Ask only that one question, then wait."""

    return ""


def _has_answer_after_assistant(messages: list[dict[str, str]], assistant_pattern: str) -> bool:
    pattern = re.compile(assistant_pattern, re.I)
    for index, message in enumerate(messages[:-1]):
        if message.get("role") != "assistant":
            continue
        if not pattern.search(message.get("content", "")):
            continue
        for later in messages[index + 1:]:
            if later.get("role") == "user" and later.get("content", "").strip():
                return True
            if later.get("role") == "assistant":
                break
    return False


def _clean_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z' -]", "", str(text)).strip(" .,'-")
    if not cleaned:
        return ""
    return " ".join(part.capitalize() for part in cleaned.split()[:2])


def _item_payload(item: DiagnosticItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "domain": item.domain,
        "prompt": item.prompt,
        "expected": list(item.expected),
        "fail_placement": placement_for_failed_item(item),
    }


def _literacy_item_payload(item: LiteracyDiagnosticItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "domain": item.domain,
        "prompt": item.prompt,
        "fail_placement": literacy_placement_for_failed_item(item),
    }


def _result_payload(result: DiagnosticResult) -> dict[str, Any]:
    return {
        "item_id": result.item_id,
        "domain": result.domain,
        "correct": result.correct,
        "expected": list(result.expected),
        "child_numbers": list(result.child_numbers),
        "child_answer": result.child_answer,
    }


def _bump_down_prompt(item: DiagnosticItem | None) -> str:
    domain = item.domain if item else "the current skill"
    return f"""

## CURRENT CALL ROUTE — REPAIR AND BUMP DOWN
The latest diagnostic-style answer shows difficulty with {domain}.
Do not continue with harder questions. Stop, reassure the child, and teach the prerequisite with smaller concrete examples.
Use tiny numbers, count objects aloud, then ask one fresh easier market question."""


def _normalize_text(text: str) -> str:
    normalized = text.lower().replace("/", " ")
    normalized = re.sub(r"[^a-z0-9' ]", " ", normalized)
    return " ".join(normalized.split())
