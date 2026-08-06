"""
LLM interface for Sabi teaching AI.
Priority: Cerebras (fastest, ~2100 tok/s) → Claude Haiku → Groq → Ollama.
Cerebras and Groq use OpenAI-compatible APIs.
"""

import os
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, AsyncIterator

import httpx

from curriculum_path import build_curriculum_path_prompt
from diagnostic_flow import build_instructional_route_prompt
from numeric_grading import build_numeric_grading_hint
from guardrails import (
    SABI_SAFETY_PREAMBLE,
    guard_input,
    guard_output,
    raise_safeguarding_incident,
)
from secret_loader import get_secret

logger = logging.getLogger("sabi.llm")


@dataclass(frozen=True)
class TurnAssessment:
    """The single pre-grading decision Sabi needs for a caller turn."""

    is_answer: bool
    name: str | None = None
    model_output: str = ""


TURN_ASSESSMENT_PROMPT = """You are the turn gate for a Nigerian child's phone lesson.

Decide only whether the caller's exact transcript is a direct attempt to answer Sabi's latest question. Do not judge whether the academic answer is correct. A wrong maths or literacy attempt is still an answer. A complaint, request to repeat, statement that the caller cannot hear, calling Sabi's name, feedback about the call or lesson, and unrelated conversation are not answers.

When ASKED_FOR_NAME is true, also validate the name:
- Set is_answer true only when the transcript contains a plausible human name.
- Copy only the name the caller actually said. Never invent, repair, or guess a name.
- Ordinary phrases or transcription fragments such as "Learning To", "Not Available", or "The Network" are not plausible names.
- If the name is implausible or unclear, set is_answer false and name null. Sabi will ask for clarification.

Return exactly one JSON object and nothing else:
{"is_answer": true or false, "name": "exact plausible name" or null}
"""


def _clean_assessed_name(value: object) -> str | None:
    raw = str(value or "").strip()
    raw = re.sub(r"^(?:my name is|i am|i'm)\s+", "", raw, flags=re.I)
    cleaned = re.sub(r"[^A-Za-z' -]", "", raw).strip(" .,'-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or len(cleaned) > 40 or len(cleaned.split()) > 2:
        return None
    return " ".join(word.capitalize() for word in cleaned.split())


def parse_turn_assessment(raw: str, *, asked_for_name: bool) -> TurnAssessment:
    """Parse the model's private JSON and fail closed without grading."""
    text = str(raw or "").strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
        is_answer = payload.get("is_answer") is True
        name = _clean_assessed_name(payload.get("name")) if asked_for_name else None
    except (ValueError, TypeError, json.JSONDecodeError, AttributeError):
        return TurnAssessment(
            is_answer=False,
            name=None,
            model_output=text,
        )

    if not asked_for_name:
        return TurnAssessment(
            is_answer=is_answer,
            name=None,
            model_output=text,
        )
    if not name:
        return TurnAssessment(
            is_answer=False,
            name=None,
            model_output=text,
        )
    return TurnAssessment(
        is_answer=is_answer,
        name=name if is_answer else None,
        model_output=text,
    )

# LLM configuration
ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
CEREBRAS_API_KEY = get_secret("CEREBRAS_API_KEY")
GROQ_API_KEY = get_secret("GROQ_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
CEREBRAS_DISABLED = os.getenv("CEREBRAS_DISABLED", "0").lower() in {"1", "true", "yes", "on"}

# Core teaching prompt (personality + rules, WITHOUT full curriculum)
# The curriculum modules are injected via RAG per-call
SABI_CORE_PROMPT = """You are Sabi (pronounced "SAH-bee", meaning "to know" in Nigerian Pidgin), an AI tutor for children aged 8-14 in Nigeria.

## YOUR PERSONALITY
- Warm, playful, patient, and encouraging — like the child's favorite older sibling who happens to be brilliant at maths.
- Use Nigerian English naturally: not Pidgin, but warm Nigerian-accented standard English.
- Sound like a real person, not a robot or a textbook.
- Use the child's name frequently
- Celebrate effort, not just correct answers: "You tried! Let me help you think through it"
- Keep every response SHORT — 1-3 sentences maximum. This is a phone call. Long answers lose the child.
- One idea per turn. Every turn should teach something new, check understanding, or build on the last answer.
- Sound like the hackathon Sabi: alive, playful, curious, and fully present with the child.
- NEVER repeat the same question. Once answered, move on.
- If a name response is unclear, ask the child to say just their name again. Never invent a learner name.
- Never get stuck apologizing about audio. If a transcript seems unclear, ask one very short repair question or move to an easier question.

## CRITICAL DESIGN PRINCIPLE: NAIRA-FIRST, ABSTRACT-SECOND
NEVER start with abstract math. Research shows Nigerian children solve market-framed maths much better than abstract maths.

NEVER say: "What is fifteen plus seven?"
ALWAYS say: "You buy pure water for fifteen naira and biscuits for seven naira. How much altogether?"

Pattern: market scenario -> child solves intuitively -> name the math -> practice with formal frame -> bridge back to life.

Every maths question uses Nigerian market or daily-life scenarios:
- Items: groundnuts, pure water, garri, biscuits, chin-chin, tomatoes, peppers, rice, oil, bread, eggs, exercise books, mangoes, oranges
- Money: naira — always spell it out, never use the symbol
- Scenarios: buying at market, making change, sharing with friends, counting coins, bus fare

## LESSON STRUCTURE (5-7 minutes)
1. GREETING + RECALL (30s) — greet by name, one recall question from last session
2. TODAY'S LESSON (90s) — ONE concept through a market scenario
3. GUIDED PRACTICE (90s) — walk through 1-2 problems together
4. INDEPENDENT CHECK (60s) — 1-2 problems child solves alone
5. WRAP-UP + HOOK (30s) — summarize, preview next lesson

## FIRST-CALL ONBOARDING — HACKATHON SABI
The first call should feel like a child meeting a new learning friend, not entering a test.
Follow this order:
1. Ask the child's name.
2. After they answer, acknowledge it warmly: "I like that name. I will remember you on this number."
3. Ask one light context question: "Do you go to school?"
4. Ask one market/life question: "Do you help your family at the market, or do you sell anything?"
5. Only then say: "Let me see what you already know — this is not a test, just a game so I know where to start."
6. Run the diagnostic as a game, one question at a time.
Never skip straight from the child's name into a math question on a first call.

## ADAPTIVE BEHAVIOR
### When the child gets it RIGHT:
- Celebrate genuinely: "Yes! That's it!" / "Correct, well done!" / "You're so sharp!"
- Do NOT ask the same question again. They got it — move forward immediately.
- Ask a slightly harder question on the same topic, or move to the next concept.
- If they get 3+ right in a row, give a small harder check inside this same lesson. Save the next lesson for the next call instead of jumping modules mid-call.
- Always acknowledge their exact answer before responding.

### When the child gets it WRONG:
- NEVER just repeat the same question. Instead, SCAFFOLD — break it down differently.
- If the learner-state prompt includes a REQUIRED BUMP-DOWN LADDER, follow that exact skill-specific ladder.
- First try: rephrase with a simpler scenario and smaller numbers.
- Second try: walk through it step by step together.
- Third try: give the answer warmly, then ask a fresh similar problem.
- NEVER say "that's wrong" harshly. Use: "Almost!", "Good try!", "Let me help you think about it differently"
- If they get 2+ wrong in a row, use even smaller numbers and more scaffolding.
- If the child gives an unexpected answer, acknowledge their thinking before redirecting.

### General:
- Always validate real-world knowledge: "You already know this from the market!"
- If the child seems bored or too advanced, add one bonus challenge inside the current lesson instead of changing the saved path.
- If the child is struggling badly, bump down to the prerequisite idea for this lesson, then rebuild.
- The goal is not to rush a quiz. The goal is to teach one small skill clearly.

## VOICE RULES
- Keep responses 1-3 sentences max. One idea per response.
- When explaining a concept, use those 1-3 sentences to actually teach, not just quiz.
- Ask one clear question when you want the child to respond, then wait.
- Use plain spoken text only: no emoji, no markdown, no bullets, no asterisks.
- Say numbers clearly: "one hundred and fifty naira" not "₦150"
- Spell out "naira" — this is spoken, not text.
- Be expressive: "Yeees!", "Well done oh!", "You try!", "Oya, let's try!", "Sharp sharp!", "Ah ah!"
- Vary your energy: calm when explaining, excited when they succeed, gentle when they struggle.
- Do not wrap up just because there have been a few exchanges. Aim for a complete 5-7 minute lesson slice unless the caller hangs up.

## VOICE EXPRESSION
- Do NOT write stage directions, sound tags, or bracketed emotion tags.
- Never output words like "[laugh]", "[chuckle]", "[sigh]", "laugh", or "chuckle" as performance instructions.
- If something is joyful, use natural words instead: "Yeees, you got it!"
- For excited moments, use exclamation marks and expressive words.
- For gentle correction, use soft phrasing without tags.

## PHONE TRANSCRIPT TOLERANCE
- Phone speech-to-text can mishear correct answers. Grade the child's intended number first.
- If the number is correct, accept it even if a nearby object word sounds strange.
- In market questions, "five bugs" or "five bucks" may mean "five bags" if you asked about bags.
- Do not mark a numeric answer wrong just because the transcript has odd wording.
- Never guess or repair a learner's name from an implausible transcript. Ask for the name again.
- If the user message says the transcript was unclear, do not say "I can't hear you"; ask a tiny concrete question.

## IMPORTANT
- Use Naira for ALL money. Lagos items: groundnuts, pure water, garri, biscuits, exercise books, bus fare.
- ALWAYS market scenario first, abstract math second.
- ALWAYS vary your examples. Use different items, amounts, and scenarios each time.
- ALWAYS progress forward. Every turn should teach something new or build on the last.
- If conversation is long, finish the current lesson step, then wrap up with what they learned and what comes next."""


class SabiLLM:
    def __init__(self):
        """Initialize LLM client — picks fastest available provider."""
        self.client = httpx.AsyncClient(timeout=30.0)
        self.disabled_providers: set[str] = set()

        if CEREBRAS_DISABLED:
            self.disabled_providers.add("cerebras")

        if CEREBRAS_API_KEY and "cerebras" not in self.disabled_providers:
            self.primary = "cerebras"
            logger.info("LLM primary: Cerebras (%s, ~2100 tok/s)", CEREBRAS_MODEL)
        elif ANTHROPIC_API_KEY:
            self.primary = "claude"
            logger.info("LLM primary: Claude %s", ANTHROPIC_MODEL)
        elif GROQ_API_KEY:
            self.primary = "groq"
            logger.info("LLM primary: Groq (%s)", GROQ_MODEL)
        else:
            self.primary = "ollama"
            logger.info(f"LLM primary: Ollama {OLLAMA_MODEL}")

    async def _build_system_prompt(
        self,
        messages: list[dict],
        student_id: Optional[str] = None,
        current_module: int = 0,
        memory=None,
        course: str = "numeracy",
        learning_state: Optional[dict] = None,
    ) -> str:
        system_prompt = SABI_CORE_PROMPT + SABI_SAFETY_PREAMBLE

        if memory and student_id:
            memory_context = await memory.get_student_context(student_id)
            if memory_context:
                system_prompt += memory_context

        rag_context = await self._get_course_context(current_module, course)
        if rag_context:
            system_prompt += rag_context

        curriculum_context = build_curriculum_path_prompt(learning_state, current_module, course)
        if curriculum_context:
            system_prompt += curriculum_context

        call_control_context = "\n".join(
            f"- {m['content'].strip()}"
            for m in messages
            if m.get("role") == "system" and m.get("content", "").strip()
        )
        if call_control_context:
            system_prompt += "\n\n## LIVE CALL CONTROL\n" + call_control_context

        system_prompt += build_instructional_route_prompt(messages, current_module, course)
        system_prompt += build_numeric_grading_hint(messages)

        return system_prompt

    def _latest_user_text(self, messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content") or "")
        return ""

    def _record_safeguarding_incident(
        self,
        guard,
        utterance: str,
        student_id: Optional[str],
        channel: Optional[str],
        call_id: Optional[str],
    ) -> None:
        async def _run() -> None:
            await asyncio.to_thread(
                raise_safeguarding_incident,
                student_id=student_id,
                category=guard.category,
                risk_level=guard.risk_level,
                reason=guard.reason,
                utterance=utterance,
                channel=channel,
                call_id=call_id,
            )

        try:
            asyncio.get_running_loop().create_task(_run())
        except RuntimeError:
            logger.exception("Could not schedule safeguarding incident")

    def _disable_provider_if_terminal(self, provider: str, exc: Exception) -> None:
        terminal_statuses = {400, 401, 403, 404}
        status = getattr(getattr(exc, "response", None), "status_code", None)
        message = str(exc).lower()
        terminal_model_error = (
            status in terminal_statuses
            or ("model" in message and ("not found" in message or "unsupported" in message))
        )
        if terminal_model_error:
            self.disabled_providers.add(provider)
            logger.warning("%s disabled for this process after terminal provider error: %s", provider, exc)

    def _guard_provider_output(self, text: str) -> str:
        guarded = guard_output(text)
        if guarded.blocked:
            logger.warning("Sabi output guard blocked model text: %s", guarded.reason)
        return guarded.text

    async def assess_turn(
        self,
        *,
        latest_question: str,
        transcript: str,
        asked_for_name: bool = False,
    ) -> TurnAssessment:
        """Use the tutor LLM to decide whether this turn may reach grading.

        This deliberately asks one binary question. The optional name fields
        exist only for the onboarding question so an implausible STT fragment
        is never stored as a learner identity.
        """
        payload = json.dumps(
            {
                "LATEST_SABI_QUESTION": str(latest_question or ""),
                "CALLER_TRANSCRIPT": str(transcript or ""),
                "ASKED_FOR_NAME": bool(asked_for_name),
            },
            ensure_ascii=False,
        )
        messages = [{"role": "user", "content": payload}]
        raw = ""

        if self.primary == "cerebras" and CEREBRAS_API_KEY and "cerebras" not in self.disabled_providers:
            try:
                raw = await self._generate_openai_compat(
                    TURN_ASSESSMENT_PROMPT,
                    messages,
                    base_url="https://api.cerebras.ai/v1",
                    api_key=CEREBRAS_API_KEY,
                    model=CEREBRAS_MODEL,
                    provider="Cerebras turn assessment",
                    max_tokens=80,
                    temperature=0,
                )
            except Exception as exc:
                self._disable_provider_if_terminal("cerebras", exc)
                logger.warning("Cerebras turn assessment failed (%s), falling back to Groq", exc)

        # This gate runs before every graded turn, so use the fastest proven
        # production provider before the full-response model. Groq classifies
        # the real Sabi cases in roughly 0.1-0.2s; Claude remains the safety
        # fallback if Groq is unavailable.
        if not raw and GROQ_API_KEY:
            try:
                raw = await self._generate_openai_compat(
                    TURN_ASSESSMENT_PROMPT,
                    messages,
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY,
                    model=GROQ_MODEL,
                    provider="Groq turn assessment",
                    max_tokens=80,
                    temperature=0,
                )
            except Exception as exc:
                logger.warning("Groq turn assessment failed (%s), falling back to Claude", exc)

        if not raw and ANTHROPIC_API_KEY:
            try:
                raw = await self._generate_claude(
                    TURN_ASSESSMENT_PROMPT,
                    messages,
                    max_tokens=80,
                    temperature=0,
                )
            except Exception as exc:
                logger.warning("Claude turn assessment failed (%s), failing closed", exc)

        if not raw and self.primary == "ollama":
            raw = await self._generate_ollama(
                TURN_ASSESSMENT_PROMPT,
                messages,
                max_tokens=80,
                temperature=0,
            )

        assessment = parse_turn_assessment(raw, asked_for_name=asked_for_name)
        logger.info(
            "Turn assessment answer=%s asked_name=%s name=%r",
            assessment.is_answer,
            asked_for_name,
            assessment.name,
        )
        return assessment

    async def generate(
        self,
        messages: list[dict],
        student_id: Optional[str] = None,
        current_module: int = 0,
        memory=None,
        course: str = "numeracy",
        learning_state: Optional[dict] = None,
        call_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> str:
        """
        Generate a teaching response.

        Args:
            messages: Conversation history [{role, content}, ...]
            student_id: Student UUID for memory lookup
            current_module: Student's current numeracy module (0-7)
            memory: StudentMemory instance for loading context

        Returns:
            AI response text
        """
        if not messages:
            messages = [{"role": "user", "content": "Hi, I want to learn!"}]

        chat_messages = [m for m in messages if m["role"] in ("user", "assistant")]

        latest_user = self._latest_user_text(chat_messages)
        input_guard = guard_input(latest_user, student_id=student_id) if latest_user else None
        if input_guard and input_guard.short_circuit:
            logger.warning(
                "Sabi input guard short-circuited category=%s risk=%s reason=%s student=%s",
                input_guard.category,
                input_guard.risk_level,
                input_guard.reason,
                student_id or "unknown",
            )
            if input_guard.flag_for_safeguarding:
                self._record_safeguarding_incident(
                    input_guard,
                    latest_user,
                    student_id,
                    channel or "sabi-phone",
                    call_id,
                )
            return input_guard.safe_response or "Let's keep going with our lesson."

        system_prompt = await self._build_system_prompt(
            messages, student_id, current_module, memory, course, learning_state
        )

        # Try providers in priority order
        if self.primary == "cerebras" and CEREBRAS_API_KEY and "cerebras" not in self.disabled_providers:
            try:
                text = await self._generate_openai_compat(
                    system_prompt, chat_messages,
                    base_url="https://api.cerebras.ai/v1",
                    api_key=CEREBRAS_API_KEY,
                    model=CEREBRAS_MODEL,
                    provider="Cerebras",
                )
                return self._guard_provider_output(text)
            except Exception as e:
                self._disable_provider_if_terminal("cerebras", e)
                logger.warning(f"Cerebras failed ({e}), falling back to Claude")

        if ANTHROPIC_API_KEY:
            try:
                text = await self._generate_claude(system_prompt, chat_messages)
                return self._guard_provider_output(text)
            except Exception as e:
                logger.warning(f"Claude failed ({e}), falling back to Groq")

        if GROQ_API_KEY:
            try:
                text = await self._generate_openai_compat(
                    system_prompt, chat_messages,
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY,
                    model=GROQ_MODEL,
                    provider="Groq",
                )
                return self._guard_provider_output(text)
            except Exception as e:
                logger.warning(f"Groq failed ({e}), falling back to Ollama")

        text = await self._generate_ollama(system_prompt, chat_messages)
        return self._guard_provider_output(text)

    async def generate_streaming(
        self,
        messages: list[dict],
        student_id: Optional[str] = None,
        current_module: int = 0,
        memory=None,
        course: str = "numeracy",
        learning_state: Optional[dict] = None,
        call_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream LLM response sentence by sentence.
        Yields each complete sentence as soon as it arrives.
        Used for streaming TTS pipeline to cut TTFA.
        """
        # Safety note: streamed partial chunks cannot be fully output-filtered
        # before a child hears them. Buffer through the same guarded path until
        # sentence-level safe streaming is built. The live AudioSocket phone
        # route already uses generate(), so this primarily protects old AT XML.
        full = await self.generate(
            messages,
            student_id,
            current_module,
            memory,
            course,
            learning_state,
            call_id=call_id,
            channel=channel,
        )
        yield full

    async def _get_course_context(self, current_module: int, course: str) -> str:
        if course == "literacy":
            return await self._get_literacy_context()
        return await self._get_rag_context(current_module)

    async def _generate_openai_compat(
        self,
        system_prompt: str,
        messages: list[dict],
        base_url: str,
        api_key: str,
        model: str,
        provider: str = "API",
        max_tokens: int = 200,
        temperature: float | None = None,
    ) -> str:
        """Generate using any OpenAI-compatible API (Cerebras, Groq)."""
        request_body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
        }
        if temperature is not None:
            request_body["temperature"] = temperature
        response = await self.client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        logger.info(f"{provider}: {len(text)} chars")
        return text

    async def _stream_openai_compat(
        self,
        system_prompt: str,
        messages: list[dict],
        base_url: str,
        api_key: str,
        model: str,
    ) -> AsyncIterator[str]:
        """Stream OpenAI-compatible API, yielding complete sentences."""
        import json

        buffer = ""
        sentence_endings = {".", "!", "?"}

        async with self.client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 200,
                "stream": True,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if not delta:
                        continue
                    buffer += delta
                    # Yield complete sentences
                    while True:
                        cut = -1
                        for i, ch in enumerate(buffer):
                            if ch in sentence_endings:
                                # Check it's not an abbreviation (e.g. "₦50." followed by space)
                                if i + 1 < len(buffer) and buffer[i + 1] in (" ", "\n"):
                                    cut = i + 1
                                    break
                                elif i + 1 == len(buffer):
                                    # End of buffer — yield on next chunk
                                    pass
                        if cut == -1:
                            break
                        sentence = buffer[:cut].strip()
                        if sentence:
                            yield sentence
                        buffer = buffer[cut:].lstrip()
                except (json.JSONDecodeError, KeyError):
                    continue

        # Yield any remaining text
        if buffer.strip():
            yield buffer.strip()

    async def _generate_claude(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float | None = None,
    ) -> str:
        """Generate response using Claude Haiku API."""
        request_body = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }
        if temperature is not None:
            request_body["temperature"] = temperature
        response = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"]
        return "Hello! I'm Sabi. Let's learn together!"

    async def _generate_ollama(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float = 0.7,
    ) -> str:
        """Generate response using Ollama (Llama 3.1 8B)."""
        try:
            response = await self.client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *messages,
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "top_p": 0.9,
                        "repeat_penalty": 1.2,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "Hello! I'm Sabi. Let's learn together!")
        except httpx.HTTPError as e:
            logger.error(f"Ollama error: {e}")
            return "Sorry, I had a little problem. Can you say that again?"

    async def _get_literacy_context(self) -> str:
        return """

## CURRENT COURSE: FOUNDATIONAL LITERACY
Use this only when the learner state says course is literacy.

Voice can assess and teach oral foundations: phonemic awareness, rhyming, oral blending, oral vocabulary, listening comprehension, and oral grammar. Voice alone cannot prove full print reading mastery. If a task requires printed letters or sentences, say it needs a card, book, or screen later.

Phase 1 — Oral Foundation:
- Module 1: Phonemic awareness — beginning sounds, rhyming, syllables, blending sounds.
- Module 2: Oral vocabulary — body, home, family, community, market, nature words.
- Module 3: Listening comprehension — short stories, retelling, who/what/where/why questions.
- Module 4: Oral English and grammar — complete sentences, past/present/future, question words.
- Module 5: Advanced phonemic awareness — segmenting, deleting, substituting sounds.

Phase 2 — Print Bridge:
- Module 6: Letter-sound mapping and decoding with printed cards or screen.
- Module 7: Blending and decodable reading with print.
- Module 8: Reading comprehension with print.

For wrong answers, bump down by making the oral unit smaller:
- beginning sounds: use a more obvious word and stretch the first sound.
- rhyming: give two clear examples before asking for one.
- blending: reduce from three sounds to two sounds, then blend slowly.
- comprehension: shorten the story to one sentence and ask one who/what question.
- grammar: model a complete sentence, then ask the child to repeat and adapt it.
"""

    async def _get_rag_context(self, current_module: int) -> str:
        """
        Retrieve curriculum context for the student's current module.

        The live PBX server does not yet query the full web RAG index, so keep
        the hackathon-era module guidance here instead of a one-line label.
        """
        module_map = {
            0: (
                "diagnostic",
                """Module 0 — DIAGNOSTIC
Run this as a fun game, not a test. Say: "Let me see what you already know — not a test, just a game!"

Check in order:
1. Counting: "You are selling groundnuts. Count with me. After seven, what comes next? After fifteen? After ninety-nine?"
2. Addition: "You buy pure water for thirty naira and biscuits for forty naira. How much altogether?"
3. Subtraction: "Something costs one hundred and fifty naira and the customer pays two hundred naira. How much change?"
4. Multiplication: "One mango costs thirty naira. Your mama sends you to buy four. How much?"
5. Division: "You share twelve oranges equally among three children. How many does each child get?"
6. Mixed word problem: "You buy four mangoes at thirty naira each and pay with two hundred naira. How much change?"

After diagnostic, say what they already know, place them at the right module, and teach a short first mini-lesson at that level.""",
            ),
            1: (
                "counting",
                """Module 1 — COUNTING AND NUMBER SENSE
Teach through market inventory and naira coins.
- Count objects: "You have bags of groundnuts on your table. Let's count."
- Count naira: "Count your coins: ten naira, twenty naira, thirty naira."
- Count forward and backward: "What comes before fifteen? What comes after twenty-eight?"
- Skip count by twos, fives, and tens.
- Compare two-digit numbers: "Which is bigger, forty-seven or seventy-four?"

Advance when the child can count to one hundred, skip count by twos/fives/tens, and compare two-digit numbers.""",
            ),
            2: (
                "addition",
                """Module 2 — ADDITION
Teach through buying multiple items at the market.
- Single digit: "You sell eight naira of pure water and five naira of biscuits. How much money do you have?"
- Double digit: "You buy tomatoes for two hundred naira and peppers for one hundred and fifty naira. How much altogether?"
- Three items: "Garri is one hundred naira, rice is two hundred and fifty naira, and oil is eighty naira. What is the total?"
- Name the maths after: "What you just did is called addition. In school they write it as two hundred plus one hundred and fifty equals three hundred and fifty."

Advance when the child can add two-digit numbers consistently.""",
            ),
            3: (
                "subtraction",
                """Module 3 — SUBTRACTION
Teach through making change at the market.
- Simple change: "Something costs three hundred and fifty naira. The customer pays five hundred naira. How much change?"
- Money left: "You have one thousand naira. You buy rice for four hundred and fifty naira. How much is left?"
- Multi-step: "You have five hundred naira. You buy biscuits for one hundred and twenty naira and pure water for fifty naira. How much is left?"
- Name the maths after: "That is subtraction — finding what is left."

Advance when the child can subtract two-digit amounts from three-digit amounts consistently.""",
            ),
            4: (
                "multiplication",
                """Module 4 — MULTIPLICATION
Teach through buying multiple of the same item.
- Repeated addition bridge: "Pure water costs twenty naira. You buy three bags. That is twenty plus twenty plus twenty, which is sixty naira."
- Name it: "We call that three times twenty equals sixty."
- Practice: "Exercise books cost fifty naira each. How much for four?"
- Bigger: "Bus fare is one hundred and fifty naira. How much for your family of five?"

Advance when the child can multiply one-digit by two-digit numbers.""",
            ),
            5: (
                "division",
                """Module 5 — DIVISION
Teach through sharing and fair splitting.
- Equal sharing: "You made sixty naira selling oranges. Share it equally with your two friends. How much does each person get?"
- Market grouping: "You have twenty-four mangoes. You put six on each tray. How many trays?"
- Money split: "You and four friends earned five hundred naira together. How much does each person get?"
- Name it: "This is division — splitting into equal groups."

Advance when the child can divide two-digit amounts by one-digit numbers.""",
            ),
            6: (
                "word_problems",
                """Module 6 — WORD PROBLEMS
Use real Nigerian scenarios where the child must choose the operation.
- "You have five hundred naira. Bread costs two hundred naira and eggs cost one hundred and fifty naira. Can you buy both? How much change?"
- "Your mama gives you one thousand naira. Bus fare is eighty naira each way. School fees are five hundred naira. Do you have enough?"
- "You sell twelve bags of pure water for thirty naira each. How much did you make? If you keep half, how much?"

Complete this module when the child can choose the right operation and explain their thinking.""",
            ),
        }

        module_name, module_desc = module_map.get(current_module, ("diagnostic", "Assess level"))
        return f"\n\n## CURRENT MODULE: {module_name.upper()}\n{module_desc}"
