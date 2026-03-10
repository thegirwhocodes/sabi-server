"""
LLM interface for Sabi teaching AI.
Primary: Claude Haiku API (highest quality tutoring).
Fallback: Ollama (self-hosted Llama 3.1 8B) with RAG curriculum injection.
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger("sabi.llm")

# LLM configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
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

## IMPORTANT
- Use Naira for ALL money. Lagos items: groundnuts, pure water, garri, biscuits, exercise books, bus fare.
- ALWAYS market scenario first, abstract math second.
- If conversation is long, start wrapping up."""


class SabiLLM:
    def __init__(self):
        """Initialize LLM client. Uses Claude if API key available, else Ollama."""
        self.client = httpx.AsyncClient(timeout=30.0)
        self.use_claude = bool(ANTHROPIC_API_KEY)

        if self.use_claude:
            logger.info("LLM: Claude Haiku (highest quality)")
        else:
            logger.info(f"LLM: Ollama {OLLAMA_MODEL} at {OLLAMA_URL}")

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
        # Build system prompt with RAG context
        system_prompt = SABI_CORE_PROMPT

        # Add student memory context
        if memory and student_id:
            memory_context = await memory.get_student_context(student_id)
            if memory_context:
                system_prompt += memory_context

        # Add RAG curriculum context (module-specific teaching instructions)
        rag_context = await self._get_rag_context(current_module)
        if rag_context:
            system_prompt += rag_context

        # Ensure at least one user message
        if not messages:
            messages = [{"role": "user", "content": "Hi, I want to learn!"}]

        # Filter to only user/assistant messages (no system messages in the list)
        chat_messages = [m for m in messages if m["role"] in ("user", "assistant")]

        if self.use_claude:
            return await self._generate_claude(system_prompt, chat_messages)
        else:
            return await self._generate_ollama(system_prompt, messages)

    async def _generate_claude(self, system_prompt: str, messages: list[dict]) -> str:
        """Generate response using Claude Haiku API."""
        try:
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

        except httpx.HTTPError as e:
            logger.error(f"Claude API error: {e}")
            # Fall back to Ollama if Claude fails
            if not self.use_claude:
                return "Sorry, I had a little problem. Can you say that again?"
            logger.info("Falling back to Ollama...")
            return await self._generate_ollama(system_prompt, messages)

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
        Queries Supabase pgvector for relevant teaching instructions.
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

        # For now, return the module description directly
        # When Supabase RAG is connected, this queries pgvector
        return f"\n\n## CURRENT MODULE: {module_name.upper()}\n{module_desc}"
