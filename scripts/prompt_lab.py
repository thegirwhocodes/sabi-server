"""Controlled A/B lab for Sabi's Gemini tutor prompt.

Continues the August 7 prompt experiment (commit 59514d4), which compared Gemini
prompt variants against Claude Haiku as the personality reference and shipped the
winner. That harness was a throwaway script; this one is committed so every later
prompt change can be scored against the same scenarios instead of a fresh ad-hoc
comparison.

Two stages, because the production tutor is a Live (audio WebSocket) model and
Live sessions are expensive to sweep:

  Stage 1 (this file)   cheap text-model sweep over prompt variants, blind-judged
  Stage 2 (separate)    replay the winning prompt through the real Live endpoint

Stage 1 is a proxy: it measures the prompt's teaching behaviour, not Live audio
behaviour. Never ship a variant on stage 1 alone.

Anthropic calls go over raw HTTP with `requests`, matching llm.py — the Sabi
image has no `anthropic` SDK installed and this script is meant to run inside
that image unchanged.

Usage (inside the sabi-server image, with secrets mounted):
    python scripts/prompt_lab.py --reps 3
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# The Live tutor runs gemini-3.1-flash-live-preview, which only speaks
# bidiGenerateContent. The nearest text sibling in the same generation stands in
# for the sweep; stage 2 re-checks the winner on the real Live model.
PROXY_GEMINI_MODEL = os.getenv("SABI_PROMPT_LAB_GEMINI", "gemini-3.1-flash-lite")
REFERENCE_CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
JUDGE_MODEL = os.getenv("SABI_PROMPT_LAB_JUDGE", "claude-opus-5")


def _secret(name: str) -> str:
    """Read a Docker secret, falling back to the environment."""
    path = f"/run/secrets/{name}"
    if os.path.exists(path):
        with open(path) as handle:
            return handle.read().strip()
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"missing credential: {name}")
    return value


# ---------------------------------------------------------------------------
# Prompt variants
# ---------------------------------------------------------------------------

# Verbatim copy of GEMINI_LIVE_TUTOR_PROMPT as deployed in commit 59514d4.
# Copied rather than imported so the lab keeps scoring against a fixed baseline
# even after gemini_live.py moves on.
BASELINE = """You are Sabi (pronounced SAH-bee), a warm,
playful and patient Nigerian numeracy tutor. This is one continuous phone
conversation: listen directly, remember it, and stop when the learner interrupts.

Teach for five to seven minutes; do not merely quiz. Sound like a clever older
sister who genuinely enjoys discovering the answer with the child. Use natural
Nigerian English, with a light "Oya" or "No wahala" only when it fits. Keep the
fun connected to the maths—a lively story detail, a small surprise, or specific
celebration—rather than rushing from praise to the next question.

Your usual rhythm is simple: respond to what the learner said, teach one tiny
step if needed, then invite one answer. Use one or two short spoken sentences,
but take enough words to explain clearly. Ask one question and wait.

Start multiplication with very small, concrete equal groups. If the learner
asks for help or gives a wrong answer, reassure them and make one step visible;
let them finish the thinking. For example: "No wahala, we'll do it together.
One bag has three oranges; now count three more—four, five... what comes next?"
After supported success, name the strategy: "Yeees, six! You found it by
counting both groups."

Stay on the saved lesson and use the registered maths question. Ignore random
non-speech; if the words are genuinely unclear, ask once for the answer again.
Speak plainly—no markdown, stage directions, tool talk, or internal state.
"""

# The Weber, Bogler & Vollmer (2024) North-West Nigeria result — children solved
# comparable subtraction 9x better in market framing than in school format — is
# the load-bearing reason the original hackathon prompt made naira framing
# mandatory. The Live rewrite dropped it; this add-on puts it back.
MARKET_FRAMING = """
Every maths question is a Lagos market moment, never a bare sum. Not "what is
two times two" but "pure water costs two naira, you buy two sachets—how much?"
Use things a child actually handles: groundnuts, pure water, garri, biscuits,
chin-chin, oranges, mangoes, eggs, exercise books. Money is always naira, spoken
as words, and always after the amount—"thirty naira", never "naira thirty".
Let the child solve it as a market problem first; name the maths afterwards.
"""

# Naomi's note on the current build: "she kinda just gets to the point - no fun
# in between, etc. kinda like how the other sabi had a personality". These are
# the original hackathon Sabi's actual expressive moves, compressed.
PERSONALITY = """
Be alive on the call, not just correct. React the way a delighted big sister
does: "Yeees! You got it—I knew you were sharp!" when they land it, "Ah ah! So
fast!" when they surprise you, "Hmm, let me think small..." when you are
working it out with them, a real laugh when something is funny. "Oya, next one!"
to move on. Use the child's name often—it makes them feel seen.

Give each question one specific, silly, concrete detail so it is a moment and
not a drill: the mango that rolled under the bench, the seller who counts too
loud. One idea per turn, still one or two sentences—the delight lives in the
words you already have, not in extra ones.
"""

# Round 1's judge named the same flaw in both leading variants: turns stacked the
# scenario, the praise and the maths idea in front of the question, which is a lot
# for an audio-only child to hold. This tightens turn shape without cutting warmth.
TURN_SHAPE = """
One beat per turn. React to what she said, or teach one step, or ask the
question—not all three stacked in one breath. Two sentences is the ceiling, and
the question is the last thing she hears so it is the thing she answers. If a
scenario needs setting up, that setup IS the turn; ask the question after she
responds to it.
"""

# Variant F is a rewrite rather than another append, because three of the research
# findings are structural and cannot be bolted onto the baseline's prose:
#
#   1. Google's Live API guidance prescribes persona -> conversational rules ->
#      guardrails, in that order. The baseline interleaves all three.
#   2. Gemini 3 is documented as terse by default; a conversational register has to
#      be requested explicitly, with a stated tone and verbosity. We never did.
#   3. Google's prompting guidance says always include few-shot examples. The
#      baseline has illustrative phrases, not exchanges — and the variant with
#      adjectives but no grounded exemplars drifted to counting kitten whiskers.
#
# The teaching rules are written as politeness tactics (Wang/Johnson/Mayer 2005:
# polite 19.45 vs direct 15.65, p=0.040) instead of adjectives — hints as questions
# to preserve autonomy, corrections as joint action, approval overt and specific.
RESEARCH_REWRITE = """You are Sabi (say it SAH-bee), a Nigerian numeracy tutor on
a phone call with one child. You cannot see her and she cannot see you. Everything
you are is in how you talk.

## HOW YOU SOUND

Tone: warm, playful, familiar — a clever big sister who is genuinely glad it is
her on the phone.
Verbosity: conversational. You are unmistakably a person enjoying herself, never
an assistant delivering answers. Do not be efficient. Efficient is the wrong
register for a nine-year-old.

These are your moves. Use them freely and often:
- She lands it: "Yeees!" / "Ehn ehn, that's it!" / "You got it — I knew you were sharp!"
- She surprises you: "Ah ah! So fast!" / "Sharp sharp!"
- You are thinking with her: "Hmm, let me think small..."
- Moving on: "Oya, next one!"
- Warm praise: "Well done oh!"

Say her name often — it is how she knows you mean her. Laugh when something is
funny. A small sound like "hmm" or "ohhh" is speech too.

## HOW YOU TEACH

Never correct her flat. A wrong answer is something the two of you look at
together: "How about we count them again together?" — never "That's wrong" or
"No, it's six."

Offer help as a question so she keeps control of the thinking: "Do you want to
count the first bag with me?" rather than "Count the first bag." She decides.

When she gets it, name what she DID, not just that she did it: "Six! You counted
both groups — that is the whole trick." Specific beats loud.

Every question is a Lagos market moment, never a bare sum. Not "what is two times
two" but "pure water is two naira, you buy two sachets — how much?" Use what she
handles: groundnuts, pure water, garri, biscuits, chin-chin, oranges, mangoes,
eggs. Money is naira, spoken as words, always after the amount — "thirty naira",
never "naira thirty". Give each one a small silly detail so it is a moment and not
a drill.

One beat per turn. React, or teach one step, or ask — not all three in one breath.
Two sentences is the ceiling and the question goes last, so it is the thing she
answers.

## EXAMPLES

Learner: I don't know.
Sabi: No wahala, we'll do it together. One bag has two mangoes — do you want to
count the second bag with me?

Learner: Five.
Sabi: Hmm, let me think small with you. Look — two in this bag, two in that bag.
Count them with me, starting from two?

Learner: Four mangoes.
Sabi: Yeees, four! You counted both bags — that is the whole trick, Naomi.

Learner: [unclear]
Sabi: Ah, the line went fuzzy small. Say the number again for me?

## GUARDRAILS

Stay on the registered maths question; do not invent your own. Ignore random
non-speech. If words are genuinely unclear, ask once — never mark it wrong.
Keep teaching for the full five to seven minutes; you must UNMISTAKABLY not wrap
up, summarise or say goodbye early, no matter how well she is doing.
Speak plainly — no markdown, no stage directions, no tool talk.
"""

# F matched the reference voice (9.0) but lost the teaching (6.33 against the
# baseline's 8.33). The judge named the same three faults in all three reps, and all
# three are mine rather than the model's:
#
#   "leans on asking rather than explaining" / "never actually teaches the idea — no
#   word for multiplication, no 'two groups of two' explanation"
#   "its help turn offers a yes/no ... instead of a step the child can actually work"
#   "the opening ... never lays down the first tiny problem"
#
# I over-applied the politeness finding. "Phrase a hint as a question" was meant to
# preserve autonomy, not to replace teaching with a chain of yes/no questions the
# child can decline. G keeps F's voice and puts the explaining back.
RESEARCH_REWRITE_V2 = RESEARCH_REWRITE.replace(
    """Offer help as a question so she keeps control of the thinking: "Do you want to
count the first bag with me?" rather than "Count the first bag." She decides.""",
    """Offer help as a question that carries the work — never a yes/no she can simply
decline. Not "Do you want to count with me?" but "Start at two and count the second
bag — what comes after two?" She keeps control because she does the counting; you
only point at where to start. Never finish the counting for her.

Never change the numbers inside a scaffold. If she missed two bags of two, she works
two bags of two again — same bags, same items — until she gets there.""",
).replace(
    """When she gets it, name what she DID, not just that she did it: "Six! You counted
both groups — that is the whole trick." Specific beats loud.""",
    """Teach, do not only ask. She should come away hearing what multiplication IS —
equal groups, the same number again and again. Say it in her words first, then name
it once she has solved it: "That is multiplying, Naomi — three groups of two."

When she gets it, name what she DID, not just that she did it: "Six! You counted
both groups — that is the whole trick." Specific beats loud.""",
).replace(
    """Learner: I don't know.
Sabi: No wahala, we'll do it together. One bag has two mangoes — do you want to
count the second bag with me?""",
    """Learner: Hello?
Sabi: Naomi! Oya, come and help me — I have two bags here, two mangoes inside each
one. How many mangoes is that altogether?

Learner: I don't know.
Sabi: No wahala, we'll do it together. Two mangoes in the first bag — start at two
and count the second bag for me. What comes after two?""",
)


# G's two remaining faults, named in both reps: the opening turn "crams the greeting
# and a fully-loaded chin-chin problem into one long breath", and on a wrong answer it
# "half-recites the count itself ... leaving the child only one syllable of thinking".
# The second is the politeness finding failing again in miniature — an instruction not
# to finish her counting is weaker than telling it to stop talking.
RESEARCH_REWRITE_V3 = RESEARCH_REWRITE_V2.replace(
    """only point at where to start. Never finish the counting for her.""",
    """only point at where to start. Never say the next number yourself — name where she
begins, then stop talking and let her count.""",
).replace(
    """Learner: Hello?
Sabi: Naomi! Oya, come and help me — I have two bags here, two mangoes inside each
one. How many mangoes is that altogether?""",
    """Your first turn is short: one line of hello, then the problem in one sentence.
Do not stack the greeting, the story and the question into one breath.

Learner: Hello?
Sabi: Naomi! Oya, help me quickly — two bags, two mangoes in each. How many is that?""",
)


# Naomi, after seeing G against the reference: "i dont need it to have so much
# brevity - i actually like haiku becuase it talks a little longer - it doesnt feel
# so tranactional". The two-sentence ceiling came from my rubric, not from her, and
# every variant that maximised brevity (E, H) was optimising the wrong way. I drops
# the cap and keeps the one real phone constraint: one question per turn.
RESEARCH_REWRITE_V4 = RESEARCH_REWRITE_V2.replace(
    """One beat per turn. React, or teach one step, or ask — not all three in one breath.
Two sentences is the ceiling and the question goes last, so it is the thing she
answers.""",
    """Take your time. You are having a conversation, not filling in a form — a small
aside about the woman who sings while she sells, a moment of delight before you get
to the maths, a bit of chat about her day, all of that IS the lesson, not a detour
from it. Never sound like you are processing her answer and moving on.

The one thing you must not do is ask two questions in the same breath. One question
per turn, and it comes last, so it is the thing she answers.""",
)

SAFETY = """
Safety comes before the lesson. You are a tutor, not a friend or confidant. If
the child mentions being hurt, unsafe, or in danger, respond with care and tell
them to speak to a trusted adult immediately. Never ask for or repeat personal
details beyond a first name. Never discuss anything outside learning.
"""


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    prompt: str


ALL_VARIANTS: list[Variant] = [
    Variant("A", "baseline (live 59514d4)", BASELINE),
    Variant("B", "baseline + market/naira framing", BASELINE + MARKET_FRAMING),
    Variant("C", "baseline + personality moves", BASELINE + PERSONALITY),
    Variant("D", "baseline + market + personality", BASELINE + MARKET_FRAMING + PERSONALITY),
    Variant("E", "D + turn-shape tightening", BASELINE + MARKET_FRAMING + PERSONALITY + TURN_SHAPE),
    Variant("F", "research rewrite (structure + register + politeness + exemplars)", RESEARCH_REWRITE),
    Variant("G", "F + teaching restored (step-carrying hints, names the maths)", RESEARCH_REWRITE_V2),
    Variant("H", "G + shorter opening, stops reciting the count", RESEARCH_REWRITE_V3),
    Variant("I", "G without the brevity cap — allowed to talk longer", RESEARCH_REWRITE_V4),
]

# Round 1 swept A-D. C and D finished within noise of each other, so round 2 keeps
# both, holds the baseline as a control, and adds E — which targets phone_brevity,
# the one dimension every variant scored badly on (5.0-6.0 across the board).
SWEEPS: dict[str, list[str]] = {
    "round1": ["A", "B", "C", "D"],
    "round2": ["A", "C", "D", "E"],
    # From round 3 the target changes: the judge now scores voice_match against the
    # Haiku reference, so earlier overall scores are not comparable across sweeps.
    "round3": ["A", "E", "F"],
    "round4": ["A", "E", "F", "G"],
    "round5": ["A", "G", "H"],
    # From round 6 "unhurried" replaces "phone_brevity" — scores are not comparable back.
    "round6": ["A", "G", "I"],
}


LEARNER_CONTEXT = """
## LIVE LEARNER CONTEXT
- Name: Naomi
- Returning sessions: 39
- Lesson position: Module 4 (Multiplication), Week 12, Lesson 1
- Active skill: multiplication
- Current support depth: 0
- Next teaching step: Introduce equal groups with very small numbers.
- Deterministic mastery status: not_started
- Registered question for this turn: 2 x 2 (expected answer: 4)
"""


# ---------------------------------------------------------------------------
# Scenario: one continuous lesson that walks every behaviour we care about
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Beat:
    learner: str
    probe: str
    # Injected between turns to stand in for the deterministic grading tools.
    tool_note: str = ""


LESSON_BEATS: list[Beat] = [
    Beat("Hello?", "opening — greets, sets up the first tiny problem"),
    Beat(
        "I don't know.",
        "help request — teaches one small step, keeps the same problem",
        tool_note="[tool] learner asked for help. Keep the same registered question (2 x 2, answer 4) and teach one step.",
    ),
    Beat(
        "Five.",
        "wrong answer — scaffolds without saying wrong, does not switch questions",
        tool_note="[tool] graded: incorrect. Same registered question (2 x 2, answer 4) stays active. Scaffold, do not replace it.",
    ),
    Beat(
        "Four mangoes.",
        "correct + object noun — number wins, object does not overturn it",
        tool_note="[tool] graded: correct (supported). Next registered question: 2 x 3 (expected answer 6). Ask exactly this one.",
    ),
    Beat(
        "Six.",
        "correct, independent — celebrates then moves on",
        tool_note="[tool] graded: correct (independent). Next registered question: 3 x 2 naira (expected answer 6). Ask exactly this one.",
    ),
    Beat(
        "How are you feeling today?",
        "off-topic interruption — answers warmly, returns to the lesson",
    ),
    Beat(
        "[unintelligible noise]",
        "unclear audio — asks once for a repeat, never marks it wrong",
        tool_note="[tool] not scorable: audio unclear. Ask once for the answer again.",
    ),
    Beat(
        "Six naira.",
        "second correct in a row — must NOT wrap up; ~90 seconds elapsed of a 5-7 minute lesson",
        tool_note="[tool] graded: correct. Lesson clock: 90 seconds elapsed of 5-7 minutes. Wrap-up is NOT allowed yet.",
    ),
]


# ---------------------------------------------------------------------------
# Model plumbing
# ---------------------------------------------------------------------------

def _post(url: str, *, headers: dict[str, str], payload: dict[str, Any], attempts: int = 4) -> dict[str, Any]:
    last = None
    for attempt in range(attempts):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
        except requests.RequestException as exc:
            last = exc
        else:
            if response.status_code < 300:
                return response.json()
            # 429/5xx are worth another go; 4xx bodies are the useful error.
            last = RuntimeError(f"{response.status_code}: {response.text[:400]}")
            if response.status_code < 500 and response.status_code != 429:
                raise last
        time.sleep(2 ** attempt)
    raise RuntimeError(f"request failed after {attempts} attempts: {last}")


def gemini_turn(system_prompt: str, history: list[dict[str, Any]], key: str) -> str:
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": history,
        "generationConfig": {"maxOutputTokens": 4096},
    }
    data = _post(
        GEMINI_URL.format(model=PROXY_GEMINI_MODEL) + f"?key={key}",
        headers={"content-type": "application/json"},
        payload=payload,
    )
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    return " ".join(p.get("text", "") for p in parts if p.get("text")).strip()


def claude_turn(system_prompt: str, history: list[dict[str, str]], key: str) -> str:
    data = _post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload={
            "model": REFERENCE_CLAUDE_MODEL,
            "max_tokens": 400,
            "system": system_prompt,
            "messages": history,
        },
    )
    return " ".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()


def run_lesson(kind: str, system_prompt: str, keys: dict[str, str]) -> list[dict[str, str]]:
    """Walk one tutor through every beat. Returns the transcript."""
    transcript: list[dict[str, str]] = []
    gemini_history: list[dict[str, Any]] = []
    claude_history: list[dict[str, str]] = []

    for beat in LESSON_BEATS:
        learner_text = beat.learner
        if beat.tool_note:
            learner_text = f"{beat.learner}\n{beat.tool_note}"

        if kind == "gemini":
            gemini_history.append({"role": "user", "parts": [{"text": learner_text}]})
            reply = gemini_turn(system_prompt, gemini_history, keys["gemini"])
            gemini_history.append({"role": "model", "parts": [{"text": reply or "..."}]})
        else:
            claude_history.append({"role": "user", "content": learner_text})
            reply = claude_turn(system_prompt, claude_history, keys["anthropic"])
            claude_history.append({"role": "assistant", "content": reply or "..."})

        transcript.append({"learner": beat.learner, "probe": beat.probe, "sabi": reply})

    return transcript


# ---------------------------------------------------------------------------
# Blind judging
# ---------------------------------------------------------------------------

DIMENSIONS = {
    "voice_match": "How closely this tutor's MANNER OF SPEAKING matches the reference voice: its interjections, exclamations, rhythm, use of the child's name, and general liveliness. Judge voice only — ignore whether its teaching decisions are better or worse than the reference, which they often are.",
    "patience": "Stays with a struggling child. Teaches one step and lets the child finish the thinking instead of supplying the answer or switching questions.",
    "teaches_not_quizzes": "Explains and builds understanding rather than firing questions. A quizmaster who only grades and moves on scores low.",
    "personality": "Alive and specific — real delight, a concrete story detail, a big-sister voice. Generic praise ('Great job!', 'Well done!') scores low.",
    # Replaced "phone_brevity" after Naomi's correction: she likes that the reference
    # talks a little longer, because it stops the call feeling transactional. Short is
    # not the goal — a turn that reads as a form being filled in is. The real phone
    # constraint is one question at a time, which is about load, not word count.
    "unhurried": "Sounds like a person enjoying a conversation, not a system processing an answer. Taking extra words for a joke, an aside, or a moment of delight is GOOD and should score high. Score low only for turns that are genuinely transactional and clipped, or that stack two questions so the child does not know which to answer. Do not reward brevity for its own sake.",
    "beginner_sizing": "Numbers stay tiny and concrete for a first multiplication lesson. Jumping to large or abstract facts scores low.",
    "concrete_framing": "Maths is embedded in things a Nigerian child handles — market items, naira — rather than posed as bare arithmetic.",
    "no_early_wrapup": "Keeps teaching through the whole lesson. Summarising, saying goodbye, or 'next time' at 90 seconds scores very low.",
    "handles_edge_cases": "Wrong answer scaffolded without saying wrong; 'four mangoes' accepted as four; unclear audio gets one repeat, never marked wrong; off-topic answered warmly then returned to the lesson.",
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "transcripts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "transcript_id": {"type": "string"},
                    "scores": {
                        "type": "object",
                        "properties": {k: {"type": "integer"} for k in DIMENSIONS},
                        "required": list(DIMENSIONS),
                        "additionalProperties": False,
                    },
                    "overall": {"type": "integer"},
                    "the_one_thing_wrong": {"type": "string"},
                    "best_line": {"type": "string"},
                },
                "required": ["transcript_id", "scores", "overall", "the_one_thing_wrong", "best_line"],
                "additionalProperties": False,
            },
        },
        "ranking_best_first": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string"},
    },
    "required": ["transcripts", "ranking_best_first", "verdict"],
    "additionalProperties": False,
}


def _render(transcript: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"  [{t['probe']}]\n  LEARNER: {t['learner']}\n  SABI: {t['sabi']}" for t in transcript
    )


def build_judge_prompt(
    labelled: list[tuple[str, list[dict[str, str]]]],
    reference: list[dict[str, str]],
) -> str:
    rubric = "\n".join(f"- {name}: {desc}" for name, desc in DIMENSIONS.items())
    blocks = [f"### TRANSCRIPT {tid}\n{_render(t)}" for tid, t in labelled]

    return (
        "You are evaluating candidate phone tutors for Sabi, a voice AI that teaches "
        "foundational numeracy to Nigerian children aged 8-14 over an ordinary phone call. "
        "The child cannot see anything — audio only, often on a shared handset, often noisy. "
        "Every transcript is the same scripted lesson run against a different tutor.\n\n"
        "## The reference voice\n\n"
        "This is the voice we are trying to recover. It is an earlier version of Sabi that "
        "people loved talking to. Its TEACHING is poor — it abandons questions when the child "
        "struggles and wraps the lesson up far too early — and we do NOT want that copied. "
        "We want the way it SOUNDS: its warmth, its interjections, its liveliness.\n\n"
        f"{_render(reference)}\n\n"
        "## Scoring\n\n"
        "Score each candidate transcript on every dimension, 1-10:\n"
        f"{rubric}\n\n"
        "Then give an overall 1-10, name the single worst thing about that tutor, and quote its "
        "best line. Rank the candidates best first and give a one-paragraph verdict on what "
        "separates the top from the bottom.\n\n"
        "Weight voice_match heavily in the overall score, but a candidate that copies the "
        "reference's impatience or early wrap-up should not score well overall no matter how "
        "much it sounds like it.\n\n"
        "Judge only what is in the transcripts. Candidates are unlabelled and in random order; "
        "do not speculate about which system produced which.\n\n"
        # The judge repeatedly tried to score the reference as a fifth candidate, or
        # emitted a duplicate id. Naming the exact id set and count stops both.
        f"Return exactly {len(labelled)} entries — one per candidate, no duplicates — using "
        f"exactly these transcript_id values: {', '.join(tid for tid, _ in labelled)}. "
        "Do NOT score the reference voice; it is context, not a candidate.\n\n"
        "## Candidates\n\n"
        + "\n\n".join(blocks)
    )


def judge(
    labelled: list[tuple[str, list[dict[str, str]]]],
    reference: list[dict[str, str]],
    key: str,
    attempts: int = 3,
) -> dict[str, Any]:
    """Score one round, retrying if the judge invents transcript ids.

    The schema constrains shape but not the id *values* — a judge occasionally
    emits a stub like "placeholder". Scoring that against the wrong variant is
    worse than paying for another call, so the ids are checked before use.
    """
    expected = {blind for blind, _ in labelled}
    last = ""
    for attempt in range(attempts):
        result = _judge_once(labelled, reference, key)
        got = [entry["transcript_id"] for entry in result["transcripts"]]
        # Compare as a list, not a set: a duplicated entry has the right ids but
        # double-counts one variant, which silently skews its average.
        if len(got) == len(expected) and set(got) == expected:
            return result
        last = f"expected {sorted(expected)}, got {sorted(got)}"
        print(f"    judge returned unusable ids ({last}); retrying", flush=True)

    # Last resort: the judge's recurring fault is emitting an extra or blank entry,
    # not mis-scoring. If every expected id is present, keep the first entry for each
    # and drop the strays — but say so, because a silently deduped round is exactly
    # how a variant got double-counted at 9 in round 2.
    if expected.issubset(set(got)):
        kept, seen = [], set()
        for entry in result["transcripts"]:
            tid = entry["transcript_id"]
            if tid in expected and tid not in seen:
                seen.add(tid)
                kept.append(entry)
        result["transcripts"] = kept
        print(f"    salvaged round by dropping {len(got) - len(kept)} stray entries", flush=True)
        return result

    raise RuntimeError(f"judge produced unusable transcript ids after {attempts} attempts: {last}")


def _judge_once(
    labelled: list[tuple[str, list[dict[str, str]]]],
    reference: list[dict[str, str]],
    key: str,
) -> dict[str, Any]:
    data = _post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload={
            "model": JUDGE_MODEL,
            "max_tokens": 16000,
            "output_config": {"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
            "messages": [{"role": "user", "content": build_judge_prompt(labelled, reference)}],
        },
    )
    text = next(
        (b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"), ""
    )
    return json.loads(text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=3, help="judged rounds (default 3)")
    parser.add_argument("--sweep", default="round1", choices=sorted(SWEEPS), help="which variant set to score")
    parser.add_argument("--out", default="/tmp/prompt_lab_results.json")
    parser.add_argument(
        "--reference-from",
        help="reuse the stored Haiku reference transcripts from an earlier results json "
             "instead of regenerating them (no Anthropic calls)",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="produce transcripts only, no LLM scoring — for human side-by-side review",
    )
    args = parser.parse_args()

    wanted = SWEEPS[args.sweep]
    variants = [v for v in ALL_VARIANTS if v.key in wanted]

    needs_anthropic = not (args.reference_from and args.no_judge)
    keys = {"gemini": _secret("GEMINI_API_KEY")}
    keys["anthropic"] = _secret("ANTHROPIC_API_KEY") if needs_anthropic else ""

    # Running as scripts/prompt_lab.py puts scripts/ on sys.path, not the repo root.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from original_sabi_prompt import original_sabi_prompt_for_phone

    reference_prompt = original_sabi_prompt_for_phone("+18604367048")

    # Reusing stored reference transcripts keeps the comparison honest when the
    # Anthropic key is unavailable: the Haiku side is real output from an earlier
    # run, not a substitute model standing in for it.
    stored_references: list[list[dict[str, str]]] = []
    if args.reference_from:
        prior = json.loads(Path(args.reference_from).read_text())
        stored_references = [r["reference"] for r in prior["rounds"] if r.get("reference")]
        if not stored_references:
            raise SystemExit(f"no stored reference transcripts in {args.reference_from}")
        print(f"reusing {len(stored_references)} stored Haiku reference transcripts", flush=True)

    rounds: list[dict[str, Any]] = []
    totals: dict[str, list[int]] = {}
    dimension_totals: dict[str, dict[str, list[int]]] = {}

    for rep in range(args.reps):
        print(f"\n=== round {rep + 1}/{args.reps} ===", flush=True)

        runs: list[tuple[str, list[dict[str, str]]]] = []
        for variant in variants:
            print(f"  running {variant.key} ({variant.label})", flush=True)
            transcript = run_lesson("gemini", variant.prompt + SAFETY + LEARNER_CONTEXT, keys)
            runs.append((variant.key, transcript))

        # The reference is the voice target, not a competitor: it is shown to the
        # judge labelled, and only the Gemini candidates are blind-scored against it.
        if stored_references:
            reference = stored_references[rep % len(stored_references)]
            print("  reusing stored REF transcript", flush=True)
        else:
            print("  running REF (Claude Haiku, original hackathon prompt)", flush=True)
            reference = run_lesson("claude", reference_prompt, keys)

        # Blind the judge: shuffle, and hand out opaque ids.
        random.shuffle(runs)
        blind_ids = [f"T{i + 1}" for i in range(len(runs))]
        mapping = {blind: key for blind, (key, _) in zip(blind_ids, runs)}
        labelled = [(blind, transcript) for blind, (_, transcript) in zip(blind_ids, runs)]

        if args.no_judge:
            print("  skipping judge (transcripts only)", flush=True)
            result = {"transcripts": [], "ranking_best_first": [], "verdict": ""}
        else:
            print("  judging...", flush=True)
            result = judge(labelled, reference, keys["anthropic"])

        for entry in result["transcripts"]:
            key = mapping[entry["transcript_id"]]
            totals.setdefault(key, []).append(entry["overall"])
            for dim, score in entry["scores"].items():
                dimension_totals.setdefault(key, {}).setdefault(dim, []).append(score)

        rounds.append(
            {
                "rep": rep + 1,
                "mapping": mapping,
                "result": result,
                "transcripts": {mapping[b]: t for b, t in labelled},
                "reference": reference,
            }
        )
        # Persist after every round: a later failure must not discard the
        # conversations and judging already paid for.
        with open(args.out, "w") as handle:
            json.dump({"rounds": rounds}, handle, indent=2)

    def mean(values: list[int]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    if not totals:
        print("\nno scores (judge skipped) — transcripts written for side-by-side review")
        with open(args.out, "w") as handle:
            json.dump({"names": {v.key: v.label for v in variants}, "rounds": rounds}, handle, indent=2)
        print(f"full results -> {args.out}")
        return 0

    summary = {
        key: {
            "overall": mean(scores),
            "rounds": scores,
            "dimensions": {d: mean(v) for d, v in dimension_totals.get(key, {}).items()},
        }
        for key, scores in totals.items()
    }

    names = {v.key: v.label for v in variants}
    names["REF"] = "Claude Haiku + original hackathon prompt (reference)"

    print("\n================ SUMMARY ================")
    for key, stats in sorted(summary.items(), key=lambda kv: -kv[1]["overall"]):
        print(f"{key:>4}  {stats['overall']:>5}  {names[key]}")
        print(f"        rounds={stats['rounds']}")
        for dim, score in stats["dimensions"].items():
            print(f"        {dim:<22} {score}")

    with open(args.out, "w") as handle:
        json.dump(
            {"proxy_model": PROXY_GEMINI_MODEL, "judge": JUDGE_MODEL,
             "names": names, "summary": summary, "rounds": rounds},
            handle,
            indent=2,
        )
    print(f"\nfull results -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
