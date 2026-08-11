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
]

# Round 1 swept A-D. C and D finished within noise of each other, so round 2 keeps
# both, holds the baseline as a control, and adds E — which targets phone_brevity,
# the one dimension every variant scored badly on (5.0-6.0 across the board).
SWEEPS: dict[str, list[str]] = {
    "round1": ["A", "B", "C", "D"],
    "round2": ["A", "C", "D", "E"],
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
    "patience": "Stays with a struggling child. Teaches one step and lets the child finish the thinking instead of supplying the answer or switching questions.",
    "teaches_not_quizzes": "Explains and builds understanding rather than firing questions. A quizmaster who only grades and moves on scores low.",
    "personality": "Alive and specific — real delight, a concrete story detail, a big-sister voice. Generic praise ('Great job!', 'Well done!') scores low.",
    "phone_brevity": "One or two short spoken sentences per turn, one question at a time. Written-text habits (markdown, lists, long paragraphs) score low.",
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


def build_judge_prompt(labelled: list[tuple[str, list[dict[str, str]]]]) -> str:
    rubric = "\n".join(f"- {name}: {desc}" for name, desc in DIMENSIONS.items())
    blocks = []
    for tid, transcript in labelled:
        turns = []
        for turn in transcript:
            turns.append(
                f"  [{turn['probe']}]\n  LEARNER: {turn['learner']}\n  SABI: {turn['sabi']}"
            )
        blocks.append(f"### TRANSCRIPT {tid}\n" + "\n\n".join(turns))

    return (
        "You are evaluating candidate phone tutors for Sabi, a voice AI that teaches "
        "foundational numeracy to Nigerian children aged 8-14 over an ordinary phone call. "
        "The child cannot see anything — audio only, often on a shared handset, often noisy. "
        "Each transcript below is the same scripted lesson run against a different tutor.\n\n"
        "Score every transcript on each dimension, 1-10:\n"
        f"{rubric}\n\n"
        "Then give an overall 1-10, name the single worst thing about that tutor, and quote "
        "its best line. Finally rank all transcripts best first and give a one-paragraph verdict "
        "on what separates the top from the bottom.\n\n"
        "Judge only what is in the transcript. The transcripts are unlabelled and in random "
        "order; do not speculate about which system produced which.\n\n"
        + "\n\n".join(blocks)
    )


def judge(labelled: list[tuple[str, list[dict[str, str]]]], key: str, attempts: int = 3) -> dict[str, Any]:
    """Score one round, retrying if the judge invents transcript ids.

    The schema constrains shape but not the id *values* — a judge occasionally
    emits a stub like "placeholder". Scoring that against the wrong variant is
    worse than paying for another call, so the ids are checked before use.
    """
    expected = {blind for blind, _ in labelled}
    last = ""
    for attempt in range(attempts):
        result = _judge_once(labelled, key)
        got = [entry["transcript_id"] for entry in result["transcripts"]]
        # Compare as a list, not a set: a duplicated entry has the right ids but
        # double-counts one variant, which silently skews its average.
        if len(got) == len(expected) and set(got) == expected:
            return result
        last = f"expected {sorted(expected)}, got {sorted(got)}"
        print(f"    judge returned unusable ids ({last}); retrying", flush=True)
    raise RuntimeError(f"judge produced unusable transcript ids after {attempts} attempts: {last}")


def _judge_once(labelled: list[tuple[str, list[dict[str, str]]]], key: str) -> dict[str, Any]:
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
            "messages": [{"role": "user", "content": build_judge_prompt(labelled)}],
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
    args = parser.parse_args()

    wanted = SWEEPS[args.sweep]
    variants = [v for v in ALL_VARIANTS if v.key in wanted]

    keys = {"gemini": _secret("GEMINI_API_KEY"), "anthropic": _secret("ANTHROPIC_API_KEY")}

    # Running as scripts/prompt_lab.py puts scripts/ on sys.path, not the repo root.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from original_sabi_prompt import original_sabi_prompt_for_phone

    reference_prompt = original_sabi_prompt_for_phone("+18604367048")

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

        print("  running REF (Claude Haiku, original hackathon prompt)", flush=True)
        runs.append(("REF", run_lesson("claude", reference_prompt, keys)))

        # Blind the judge: shuffle, and hand out opaque ids.
        random.shuffle(runs)
        blind_ids = [f"T{i + 1}" for i in range(len(runs))]
        mapping = {blind: key for blind, (key, _) in zip(blind_ids, runs)}
        labelled = [(blind, transcript) for blind, (_, transcript) in zip(blind_ids, runs)]

        print("  judging...", flush=True)
        result = judge(labelled, keys["anthropic"])

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
            }
        )
        # Persist after every round: a later failure must not discard the
        # conversations and judging already paid for.
        with open(args.out, "w") as handle:
            json.dump({"rounds": rounds}, handle, indent=2)

    def mean(values: list[int]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

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
