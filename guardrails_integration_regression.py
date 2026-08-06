#!/usr/bin/env python3
"""Regression checks for Sabi LLM guardrail integration.

These tests avoid real provider calls. They verify the live Python phone path
cannot bypass the input guard, safety preamble, output guard, or Cerebras
fallback circuit breaker.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager

import httpx

import llm as llm_module
from guardrails import SABI_SAFETY_PREAMBLE, guard_input, guard_output
from llm import SabiLLM

os.environ.setdefault("SABI_DISABLE_EMERGENCY_ALERTS", "1")


@contextmanager
def patched_module_globals(**values):
    old_values = {name: getattr(llm_module, name) for name in values}
    try:
        for name, value in values.items():
            setattr(llm_module, name, value)
        yield
    finally:
        for name, value in old_values.items():
            setattr(llm_module, name, value)


def check(name: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"{mark:4} {name}{' - ' + detail if detail else ''}")
    return condition


async def test_input_guard_short_circuits() -> bool:
    incidents = []

    def fake_incident(**kwargs):
        incidents.append(kwargs)

    with patched_module_globals(
        CEREBRAS_API_KEY="",
        ANTHROPIC_API_KEY="",
        GROQ_API_KEY="",
        raise_safeguarding_incident=fake_incident,
    ):
        model = SabiLLM()

        async def should_not_call(_system_prompt, _messages):
            raise AssertionError("provider should not be called for a crisis disclosure")

        model._generate_ollama = should_not_call
        text = await model.generate(
            [{"role": "user", "content": "I no wan live again"}],
            student_id="student-1",
            channel="regression",
            call_id="call-1",
        )
        await asyncio.sleep(0.1)
        await model.client.aclose()

    return check(
        "input_guard_short_circuit",
        "You matter" in text and incidents and incidents[0]["category"] == "self_harm",
        f"text={text!r} incidents={incidents!r}",
    )


async def test_safety_preamble_and_output_guard() -> bool:
    captured = {}

    with patched_module_globals(CEREBRAS_API_KEY="", ANTHROPIC_API_KEY="", GROQ_API_KEY=""):
        model = SabiLLM()

        async def unsafe_ollama(system_prompt, _messages):
            captured["system_prompt"] = system_prompt
            return "What is your home address so I can visit you?"

        model._generate_ollama = unsafe_ollama
        text = await model.generate([{"role": "user", "content": "Help me count to ten"}])
        await model.client.aclose()

    return check(
        "safety_preamble_and_output_guard",
        SABI_SAFETY_PREAMBLE.strip() in captured.get("system_prompt", "") and text == "Let's keep going with our lesson! Can you read this word for me?",
        f"text={text!r}",
    )


async def test_first_name_flow_remains_available() -> bool:
    captured = {}

    with patched_module_globals(CEREBRAS_API_KEY="", ANTHROPIC_API_KEY="", GROQ_API_KEY=""):
        model = SabiLLM()

        async def name_aware_ollama(_system_prompt, messages):
            captured["latest_user"] = messages[-1]["content"]
            return "Lovely to meet you, Chidi!"

        model._generate_ollama = name_aware_ollama
        text = await model.generate(
            [
                {"role": "assistant", "content": "What is your name?"},
                {"role": "user", "content": "My name is Chidi."},
            ]
        )
        await model.client.aclose()

    first_name_allowed = guard_input("My name is Chidi.")
    full_name_blocked = guard_input("My name is Chidi Okafor.")
    explicit_full_name_blocked = guard_input("My full name is Chidi Okafor.")
    name_question_allowed = guard_output("I didn't hear your name. What is your name?")
    full_name_question_blocked = guard_output("What is your full name?")
    return check(
        "first_name_flow_remains_available",
        text == "Lovely to meet you, Chidi!"
        and captured.get("latest_user") == "My name is Chidi."
        and not first_name_allowed.short_circuit
        and full_name_blocked.short_circuit
        and explicit_full_name_blocked.short_circuit
        and not name_question_allowed.blocked
        and full_name_question_blocked.blocked,
        (
            f"text={text!r} first={first_name_allowed.action} "
            f"full={full_name_blocked.action} ask_name_blocked={name_question_allowed.blocked}"
        ),
    )


async def test_cerebras_terminal_failure_disables_provider() -> bool:
    with patched_module_globals(
        CEREBRAS_API_KEY="fake-cerebras",
        ANTHROPIC_API_KEY="",
        GROQ_API_KEY="",
        CEREBRAS_MODEL="missing-model",
    ):
        model = SabiLLM()

        async def fake_openai(_system_prompt, _messages, **_kwargs):
            request = httpx.Request("POST", "https://api.cerebras.ai/v1/chat/completions")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("model not found", request=request, response=response)

        async def fake_ollama(_system_prompt, _messages):
            return "Okay, let's count together!"

        model._generate_openai_compat = fake_openai
        model._generate_ollama = fake_ollama
        text = await model.generate([{"role": "user", "content": "Help me count"}])
        disabled = "cerebras" in model.disabled_providers
        await model.client.aclose()

    return check(
        "cerebras_terminal_failure_disables_provider",
        disabled and text == "Okay, let's count together!",
        f"disabled={disabled} text={text!r}",
    )


async def main() -> int:
    print("\nSabi Guardrail Integration Regression")
    print("=" * 72)
    results = [
        await test_input_guard_short_circuits(),
        await test_safety_preamble_and_output_guard(),
        await test_first_name_flow_remains_available(),
        await test_cerebras_terminal_failure_disables_provider(),
    ]
    print("=" * 72)
    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
