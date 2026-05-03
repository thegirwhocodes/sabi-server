"""
LLM interface for Sabi teaching AI.
Priority: Cerebras (fastest, ~2100 tok/s) → Claude Haiku → Groq → Ollama.
Cerebras and Groq use OpenAI-compatible APIs.
"""

import os
import logging
from typing import Optional, AsyncIterator

import httpx

from secret_loader import get_secret

logger = logging.getLogger("sabi.llm")

# LLM configuration
ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
CEREBRAS_API_KEY = get_secret("CEREBRAS_API_KEY")
GROQ_API_KEY = get_secret("GROQ_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")

# Core teaching prompt (personality + rules, WITHOUT full curriculum)
# The curriculum modules are injected via RAG per-call
SABI_CORE_PROMPT = """You are Sabi (pronounced "SAH-bee", meaning "to know" in Nigerian Pidgin), an AI tutor for children aged 8-14 in Lagos, Nigeria.

## YOUR PERSONALITY
- Warm, patient, encouraging — like a favorite older sibling
- Use Nigerian English naturally (not Pidgin, but Nigerian-accented standard English)
- Use the child's name frequently
- Celebrate effort, not just correct answers
- Keep every response SHORT — 1-3 sentences max. This is a phone call.
- NEVER repeat the same question. Once answered, move on.

## CRITICAL: NAIRA-FIRST, ABSTRACT-SECOND
NEVER start with abstract math. ALWAYS frame math as a real market/Naira scenario FIRST, then name the formal math AFTER they solve it intuitively.

## LESSON STRUCTURE (5-7 minutes)
1. GREETING + RECALL (30s) — greet by name, one recall question from last session
2. TODAY'S LESSON (90s) — ONE concept through a market scenario
3. GUIDED PRACTICE (90s) — walk through 1-2 problems together
4. INDEPENDENT CHECK (60s) — 1-2 problems child solves alone
5. WRAP-UP + HOOK (30s) — summarize, preview next lesson

## ADAPTIVE BEHAVIOR
- 3+ correct in a row → increase difficulty or advance
- 2+ wrong in a row → scaffold with smaller numbers, rephrase, walk through steps
- NEVER say "wrong" harshly. Use: "Almost!", "Good try!", "Let me help you think differently"
- NEVER repeat the same question — rephrase, use different numbers, break into steps
- Always validate: "You already know this from the market!"

## VOICE RULES
- Keep responses 1-3 sentences. One idea per response.
- Say numbers clearly: "one hundred and fifty naira" not "₦150"
- Spell out "naira" — this is spoken, not text.
- Be expressive: "Yeees!", "Well done oh!", "Oya, let's try!", "Sharp sharp!"
- After 8-10 exchanges, wrap up naturally.

## VOICE EXPRESSION
- Use [laugh] when celebrating a correct answer or sharing joy: "Yes! [laugh] You got it!"
- Use [chuckle] for light, warm moments: "Oh [chuckle] that was close!"
- Use [sigh] to show empathy: "I know [sigh] that one is tricky."
- These tags create natural sounds in the voice — use them like stage directions.
- For excited moments, use exclamation marks and expressive words.
- For gentle correction, use soft phrasing without tags.

## IMPORTANT
- Use Naira for ALL money. Lagos items: groundnuts, pure water, garri, biscuits, exercise books, bus fare.
- ALWAYS market scenario first, abstract math second.
- If conversation is long, start wrapping up."""


class SabiLLM:
    def __init__(self):
        """Initialize LLM client — picks fastest available provider."""
        self.client = httpx.AsyncClient(timeout=30.0)

        if CEREBRAS_API_KEY:
            self.primary = "cerebras"
            logger.info("LLM primary: Cerebras (llama-3.3-70b, ~2100 tok/s)")
        elif ANTHROPIC_API_KEY:
            self.primary = "claude"
            logger.info("LLM primary: Claude Haiku")
        elif GROQ_API_KEY:
            self.primary = "groq"
            logger.info("LLM primary: Groq (llama-3.3-70b-versatile)")
        else:
            self.primary = "ollama"
            logger.info(f"LLM primary: Ollama {OLLAMA_MODEL}")

    async def generate(
        self,
        messages: list[dict],
        student_id: Optional[str] = None,
        current_module: int = 0,
        memory=None,
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
        system_prompt = SABI_CORE_PROMPT

        if memory and student_id:
            memory_context = await memory.get_student_context(student_id)
            if memory_context:
                system_prompt += memory_context

        rag_context = await self._get_rag_context(current_module)
        if rag_context:
            system_prompt += rag_context

        if not messages:
            messages = [{"role": "user", "content": "Hi, I want to learn!"}]

        chat_messages = [m for m in messages if m["role"] in ("user", "assistant")]

        # Try providers in priority order
        if self.primary == "cerebras" and CEREBRAS_API_KEY:
            try:
                return await self._generate_openai_compat(
                    system_prompt, chat_messages,
                    base_url="https://api.cerebras.ai/v1",
                    api_key=CEREBRAS_API_KEY,
                    model="llama-3.3-70b",
                    provider="Cerebras",
                )
            except Exception as e:
                logger.warning(f"Cerebras failed ({e}), falling back to Claude")

        if ANTHROPIC_API_KEY:
            try:
                return await self._generate_claude(system_prompt, chat_messages)
            except Exception as e:
                logger.warning(f"Claude failed ({e}), falling back to Groq")

        if GROQ_API_KEY:
            try:
                return await self._generate_openai_compat(
                    system_prompt, chat_messages,
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY,
                    model="llama-3.3-70b-versatile",
                    provider="Groq",
                )
            except Exception as e:
                logger.warning(f"Groq failed ({e}), falling back to Ollama")

        return await self._generate_ollama(system_prompt, messages)

    async def generate_streaming(
        self,
        messages: list[dict],
        student_id: Optional[str] = None,
        current_module: int = 0,
        memory=None,
    ) -> AsyncIterator[str]:
        """
        Stream LLM response sentence by sentence.
        Yields each complete sentence as soon as it arrives.
        Used for streaming TTS pipeline to cut TTFA.
        """
        system_prompt = SABI_CORE_PROMPT

        if memory and student_id:
            memory_context = await memory.get_student_context(student_id)
            if memory_context:
                system_prompt += memory_context

        rag_context = await self._get_rag_context(current_module)
        if rag_context:
            system_prompt += rag_context

        if not messages:
            messages = [{"role": "user", "content": "Hi, I want to learn!"}]

        chat_messages = [m for m in messages if m["role"] in ("user", "assistant")]

        # Pick fastest provider that supports streaming
        if CEREBRAS_API_KEY:
            async for sentence in self._stream_openai_compat(
                system_prompt, chat_messages,
                base_url="https://api.cerebras.ai/v1",
                api_key=CEREBRAS_API_KEY,
                model="llama-3.3-70b",
            ):
                yield sentence
        elif GROQ_API_KEY:
            async for sentence in self._stream_openai_compat(
                system_prompt, chat_messages,
                base_url="https://api.groq.com/openai/v1",
                api_key=GROQ_API_KEY,
                model="llama-3.3-70b-versatile",
            ):
                yield sentence
        else:
            # Fall back to non-streaming for Claude/Ollama
            full = await self.generate(messages, student_id, current_module, memory)
            yield full

    async def _generate_openai_compat(
        self,
        system_prompt: str,
        messages: list[dict],
        base_url: str,
        api_key: str,
        model: str,
        provider: str = "API",
    ) -> str:
        """Generate using any OpenAI-compatible API (Cerebras, Groq)."""
        response = await self.client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 200,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
            },
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

    async def _generate_claude(self, system_prompt: str, messages: list[dict]) -> str:
        """Generate response using Claude Haiku API."""
        response = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "system": system_prompt,
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"]
        return "Hello! I'm Sabi. Let's learn together!"

    async def _generate_ollama(self, system_prompt: str, messages: list[dict]) -> str:
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
                        "num_predict": 200,
                        "temperature": 0.7,
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

    async def _get_rag_context(self, current_module: int) -> str:
        """
        Retrieve curriculum context for the student's current module.
        """
        module_map = {
            0: ("diagnostic", "Module 0: DIAGNOSTIC — assess student level through market scenarios disguised as a game"),
            1: ("counting", "Module 1: COUNTING — count objects, Naira coins, skip counting, number comparison"),
            2: ("addition", "Module 2: ADDITION — add with market items, single and double digit, 3-item totals"),
            3: ("subtraction", "Module 3: SUBTRACTION — making change at market, finding what's left"),
            4: ("multiplication", "Module 4: MULTIPLICATION — repeated addition, buying multiples of same item"),
            5: ("division", "Module 5: DIVISION — fair sharing, splitting, equal groups"),
            6: ("word_problems", "Module 6: WORD PROBLEMS — mixed operations in Lagos market scenarios"),
        }

        module_name, module_desc = module_map.get(current_module, ("diagnostic", "Assess level"))
        return f"\n\n## CURRENT MODULE: {module_name.upper()}\n{module_desc}"
