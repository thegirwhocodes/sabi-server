"""End-of-call teacher's note for Sabi.

After each lesson call, Sabi writes a short, human-sounding note about what she
noticed about the child during the call: strengths, struggles, engagement, any
misconceptions, and the single most useful thing to focus on next. This is the
qualitative half of the learning record that sits beside the hard numbers.

Design:
- One small LLM call (Claude Haiku preferred; Cerebras/Groq OpenAI-compatible
  fallback). This runs AFTER the call has ended (post-hangup, in the session
  save path), so its latency never touches a child mid-lesson.
- A cost guard skips generation for calls with no real learning content
  (carrier/voicemail, no child turns, or very short calls).
- If no provider is configured or the call fails, a deterministic heuristic note
  is built from the already-computed session stats, so a call is never blocked
  and the board console always has something to show.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from secret_loader import get_secret

logger = logging.getLogger("sabi.teacher_notes")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Cost guard: do not spend an LLM call on a session with no real lesson content.
MIN_TEACHER_NOTE_TURNS = int(os.getenv("SABI_TEACHER_NOTE_MIN_TURNS", "1"))
MIN_TEACHER_NOTE_SECONDS = int(os.getenv("SABI_TEACHER_NOTE_MIN_SECONDS", "45"))
TEACHER_NOTE_TIMEOUT_SECONDS = float(os.getenv("SABI_TEACHER_NOTE_TIMEOUT_SECONDS", "12"))

ENGAGEMENT_VALUES = {"eager", "focused", "shy", "distracted", "frustrated", "mixed"}

_SYSTEM_PROMPT = (
    "You are an experienced foundational literacy and numeracy teacher, trained in "
    "Teaching at the Right Level (TaRL), writing a short private note for the education "
    "coordinator right after a phone tutoring call with a child in Nigeria. "
    "Base your note ONLY on the transcript and lesson data provided. Be specific, warm, "
    "and honest; never invent facts the transcript does not support. If evidence is thin, "
    "say so briefly.\n\n"
    "Return STRICT JSON only, no prose before or after, with exactly these keys:\n"
    '- "strengths": array of 0-3 short strings (what the child did well)\n'
    '- "struggles": array of 0-3 short strings (what was hard for them)\n'
    '- "engagement": one of "eager", "focused", "shy", "distracted", "frustrated", "mixed"\n'
    '- "misconceptions": array of 0-3 short strings (specific wrong ideas heard), can be empty\n'
    '- "recommended_focus": one short sentence naming the single most useful next teaching move\n'
    '- "narrative": 2-3 plain sentences a parent could understand, in a warm teacher voice'
)


def should_generate_teacher_note(user_turns: int, duration_seconds: int) -> bool:
    """Cost guard: only write a note when the call held real lesson content."""
    return int(user_turns or 0) >= MIN_TEACHER_NOTE_TURNS and int(duration_seconds or 0) >= MIN_TEACHER_NOTE_SECONDS


def heuristic_teacher_note(
    *,
    correct_count: int,
    wrong_count: int,
    skills: dict[str, float] | None,
    summary: str,
    current_level: str,
    lesson: dict[str, Any] | None,
    learning_state: dict[str, Any] | None,
    user_turns: int = 0,
) -> dict[str, Any]:
    """Deterministic note built from computed stats. Always safe, never blocks."""
    skills = skills or {}
    learning_state = learning_state or {}
    lesson = lesson or {}
    active_skill = str(learning_state.get("active_skill") or (lesson.get("module_name") or "this skill"))
    active_skill_label = active_skill.replace("_", " ")

    strengths: list[str] = []
    struggles: list[str] = []
    if correct_count > 0:
        strengths.append(
            f"Answered {correct_count} question{'s' if correct_count != 1 else ''} correctly on {active_skill_label}."
        )
    strong_skills = [name.replace("_", " ") for name, score in skills.items() if float(score or 0) >= 0.8]
    if strong_skills:
        strengths.append("Strong on " + ", ".join(sorted(set(strong_skills))[:3]) + ".")
    if wrong_count > 0:
        struggles.append(
            f"Needed support on {wrong_count} question{'s' if wrong_count != 1 else ''} in {active_skill_label}."
        )
    weak_skills = [name.replace("_", " ") for name, score in skills.items() if float(score or 0) < 0.5]
    if weak_skills:
        struggles.append("Still building " + ", ".join(sorted(set(weak_skills))[:3]) + ".")

    total = correct_count + wrong_count
    if total == 0:
        engagement = "focused" if int(user_turns or 0) >= 2 else "shy"
    elif wrong_count > correct_count and int(learning_state.get("scaffold_depth") or 0) >= 2:
        engagement = "frustrated"
    elif correct_count > 0 and wrong_count == 0:
        engagement = "eager"
    else:
        engagement = "mixed"

    recommended_focus = str(learning_state.get("next_step") or "Continue the current lesson with one guided example and one independent check.")
    narrative = summary or (
        f"Practiced {active_skill_label} this call with {correct_count} correct and {wrong_count} needing support."
    )
    return {
        "strengths": strengths,
        "struggles": struggles,
        "engagement": engagement,
        "misconceptions": [],
        "recommended_focus": recommended_focus,
        "narrative": narrative,
        "source": "heuristic",
    }


async def generate_teacher_note(
    *,
    messages: list[dict[str, str]],
    correct_count: int,
    wrong_count: int,
    skills: dict[str, float] | None,
    summary: str,
    current_level: str,
    lesson: dict[str, Any] | None,
    learning_state: dict[str, Any] | None,
    user_turns: int,
    duration_seconds: int,
    timeout: float = TEACHER_NOTE_TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    """Return a teacher note dict, or None if the cost guard skips this call.

    Falls back to the heuristic note if no LLM provider is configured or the LLM
    call fails or returns unparseable output.
    """
    if not should_generate_teacher_note(user_turns, duration_seconds):
        return None

    fallback = heuristic_teacher_note(
        correct_count=correct_count,
        wrong_count=wrong_count,
        skills=skills,
        summary=summary,
        current_level=current_level,
        lesson=lesson,
        learning_state=learning_state,
        user_turns=user_turns,
    )

    user_prompt = _build_user_prompt(
        messages=messages,
        correct_count=correct_count,
        wrong_count=wrong_count,
        skills=skills or {},
        current_level=current_level,
        lesson=lesson or {},
        learning_state=learning_state or {},
    )

    anthropic_key = get_secret("ANTHROPIC_API_KEY")
    cerebras_key = get_secret("CEREBRAS_API_KEY")
    groq_key = get_secret("GROQ_API_KEY")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            raw = None
            if anthropic_key:
                raw = await _call_anthropic(client, anthropic_key, user_prompt)
            elif cerebras_key:
                raw = await _call_openai_compat(
                    client, "https://api.cerebras.ai/v1", cerebras_key, CEREBRAS_MODEL, user_prompt
                )
            elif groq_key:
                raw = await _call_openai_compat(
                    client, "https://api.groq.com/openai/v1", groq_key, GROQ_MODEL, user_prompt
                )
            else:
                logger.info("No LLM provider configured for teacher note; using heuristic note.")
                return fallback
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("Teacher-note LLM call failed (%s); using heuristic note.", exc)
        return fallback

    parsed = _parse_note(raw)
    if not parsed:
        logger.warning("Teacher-note LLM returned unparseable output; using heuristic note.")
        return fallback
    parsed["source"] = "llm"
    return parsed


def _build_user_prompt(
    *,
    messages: list[dict[str, str]],
    correct_count: int,
    wrong_count: int,
    skills: dict[str, float],
    current_level: str,
    lesson: dict[str, Any],
    learning_state: dict[str, Any],
) -> str:
    transcript_lines = []
    for message in messages[-30:]:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        speaker = "Child" if role == "user" else "Sabi"
        text = " ".join(str(message.get("content") or "").split())
        if text:
            transcript_lines.append(f"{speaker}: {text}")
    transcript = "\n".join(transcript_lines) or "(no usable transcript)"

    course = str(learning_state.get("course") or lesson.get("course") or "numeracy")
    lesson_line = ""
    if lesson:
        lesson_line = (
            f"Lesson attempted: {course} Module {lesson.get('module')} "
            f"({lesson.get('module_name')}), {lesson.get('title')}.\n"
        )
    skill_line = ""
    if skills:
        skill_line = "Per-skill accuracy this call: " + ", ".join(
            f"{name.replace('_', ' ')} {round(float(score or 0) * 100)}%" for name, score in skills.items()
        ) + ".\n"

    return (
        f"{lesson_line}"
        f"Active skill: {learning_state.get('active_skill')}. Current level read: {current_level}.\n"
        f"Numbers this call: {correct_count} correct, {wrong_count} needed support.\n"
        f"{skill_line}"
        f"Scaffold depth (0-3, higher = more support given): {learning_state.get('scaffold_depth', 0)}. "
        f"Correct streak: {learning_state.get('correct_streak', 0)}. Wrong streak: {learning_state.get('wrong_streak', 0)}.\n\n"
        f"Transcript (Child = the learner, Sabi = the tutor):\n{transcript}\n\n"
        "Write the note as strict JSON now."
    )


async def _call_anthropic(client: httpx.AsyncClient, api_key: str, user_prompt: str) -> str:
    response = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 400,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        },
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]
    return ""


async def _call_openai_compat(
    client: httpx.AsyncClient, base_url: str, api_key: str, model: str, user_prompt: str
) -> str:
    response = await client.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _parse_note(raw: str | None) -> dict[str, Any] | None:
    """Pull the JSON object out of the model output and coerce it into shape."""
    if not raw:
        return None
    text = str(raw).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    def _str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()][:3]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    engagement = str(data.get("engagement") or "").strip().lower()
    if engagement not in ENGAGEMENT_VALUES:
        engagement = "mixed"

    narrative = str(data.get("narrative") or "").strip()
    recommended_focus = str(data.get("recommended_focus") or "").strip()
    if not narrative and not recommended_focus:
        return None

    return {
        "strengths": _str_list(data.get("strengths")),
        "struggles": _str_list(data.get("struggles")),
        "engagement": engagement,
        "misconceptions": _str_list(data.get("misconceptions")),
        "recommended_focus": recommended_focus,
        "narrative": narrative,
    }
