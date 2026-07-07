#!/usr/bin/env python3
"""Regression harness for Sabi phone STT and transcript normalization.

Use it in two modes:

1. Built-in normalizer checks:
   python stt_regression.py

2. Real audio manifest checks:
   python stt_regression.py --manifest stt_eval_manifest.example.json --transcribe

Manifest shape:
[
  {
    "id": "remi_market_answer",
    "audio_path": "/shared/audio/calls/example_rx.wav",
    "expected_any": ["eighty naira", "80 naira"],
    "expected_numbers": [80],
    "assistant_context": "Your mom gives you two hundred naira..."
  }
]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from numeric_grading import extract_numbers
from transcript_normalizer import (
    is_likely_stt_hallucination_transcript,
    is_non_answer_transcript,
    is_phone_system_transcript,
    normalize_lesson_transcript,
    normalize_number_mishears,
)


BUILT_IN_CASES: list[dict[str, Any]] = [
    {
        "id": "numeric_context_for_to_four",
        "transcript": "for naira",
        "assistant_context": "What is two plus two? How much naira is that?",
        "expected_text": "four naira",
        "expected_numbers": [4],
    },
    {
        "id": "non_numeric_for_stays_for",
        "transcript": "for me",
        "assistant_context": "Tell me what you like to do after school.",
        "expected_text": "for me",
        "expected_numbers": [],
    },
    {
        "id": "eighty_naira_passes",
        "transcript": "I have eighty naira left",
        "assistant_context": "You buy pure water for fifty naira and groundnuts for seventy naira. How much money is left?",
        "expected_text": "I have eighty naira left",
        "expected_numbers": [80],
    },
    {
        "id": "ate_in_math_context",
        "transcript": "ate naira",
        "assistant_context": "What is five plus three?",
        "expected_text": "eight naira",
        "expected_numbers": [8],
    },
    {
        "id": "bag_object_context",
        "transcript": "five bucks",
        "assistant_context": "You asked for five bags of rice. How many bags?",
        "expected_text": "five bags",
        "expected_numbers": [5],
    },
    {
        "id": "single_word_for_after_math_prompt",
        "transcript": "for",
        "assistant_context": "What is two plus two?",
        "expected_text": "four",
        "expected_numbers": [4],
    },
    {
        "id": "single_word_to_after_math_prompt",
        "transcript": "to",
        "assistant_context": "What is one plus one?",
        "expected_text": "two",
        "expected_numbers": [2],
    },
    {
        "id": "fine_after_math_prompt_is_five",
        "transcript": "fine",
        "assistant_context": "You have two mangoes and buy three more. How many mangoes altogether?",
        "expected_text": "five",
        "expected_numbers": [5],
    },
    {
        "id": "fine_outside_numeric_context_stays_fine",
        "transcript": "fine",
        "assistant_context": "How are you feeling today?",
        "expected_text": "fine",
        "expected_numbers": [],
    },
    {
        "id": "long_speech_does_not_turn_to_into_two",
        "transcript": "I think I need to work on the code before you test it",
        "assistant_context": "You buy pure water for fifty naira and groundnuts for seventy naira. How much money is left?",
        "expected_text": "I think I need to work on the code before you test it",
        "expected_numbers": [],
    },
    {
        "id": "long_speech_does_not_turn_oh_into_zero",
        "transcript": "Oh yeah I am using a glo line to call it",
        "assistant_context": "You buy pure water for fifty naira and groundnuts for seventy naira. How much money is left?",
        "expected_text": "Oh yeah I am using a glo line to call it",
        "expected_numbers": [],
    },
    {
        "id": "price_phrase_keeps_for",
        "transcript": "I sell ground nuts for fifteen naira",
        "assistant_context": "Do you help your family at the market, or do you sell anything?",
        "expected_text": "I sell groundnuts for fifteen naira",
        "expected_numbers": [15],
    },
    {
        "id": "market_item_mishears_normalized",
        "transcript": "granotes for fifteen naira and piota for thirty naira",
        "assistant_context": "Groundnuts for fifteen naira and pure water for thirty naira. How much do you spend?",
        "expected_text": "groundnuts for fifteen naira and pure water for thirty naira",
        "expected_numbers": [15, 30],
    },
    {
        "id": "twelve_nero_is_naira_in_money_context",
        "transcript": "Twelve nero.",
        "assistant_context": "A mango costs three naira. You buy four mangoes. How much naira altogether?",
        "expected_text": "Twelve naira.",
        "expected_numbers": [12],
    },
    {
        "id": "for_narrow_is_four_naira_in_money_context",
        "transcript": "For narrow...",
        "assistant_context": "One exercise book is twenty naira. Another exercise book is also twenty naira. How many naira altogether?",
        "expected_text": "four naira",
        "expected_numbers": [4],
    },
    {
        "id": "name_peter_not_pure_water",
        "transcript": "Peter",
        "assistant_context": "What is your name?",
        "expected_text": "Peter",
        "expected_numbers": [],
    },
    {
        "id": "carrier_not_available_detected",
        "transcript": "The number you have dialed is not available. Press one to leave a message.",
        "assistant_context": "What number comes after twenty-nine?",
        "expected_text": "The number you have dialed is not available. Press one to leave a message.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": True,
    },
    {
        "id": "short_not_available_detected",
        "transcript": "Not available.",
        "assistant_context": "What is your name?",
        "expected_text": "Not available.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": True,
    },
    {
        "id": "finished_recording_detected",
        "transcript": "When you have finished recording, you may hang up.",
        "assistant_context": "Tell me, do you go to school?",
        "expected_text": "When you have finished recording, you may hang up.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": True,
    },
    {
        "id": "short_bye_hallucination_is_non_answer",
        "transcript": "Bye.",
        "assistant_context": "You buy pure water for three naira and groundnuts for two naira. How much altogether?",
        "expected_text": "Bye.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": False,
    },
    {
        "id": "short_bye_bye_hallucination_is_non_answer",
        "transcript": "Bye bye.",
        "assistant_context": "Say the first sound in ball.",
        "expected_text": "Bye bye.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": False,
    },
    {
        "id": "short_see_you_next_time_hallucination_is_non_answer",
        "transcript": "See you next time.",
        "assistant_context": "What is two plus three?",
        "expected_text": "See you next time.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": False,
    },
    {
        "id": "short_thank_you_is_non_answer",
        "transcript": "Thank you.",
        "assistant_context": "What word do these sounds make: sh, i, p?",
        "expected_text": "Thank you.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": False,
    },
    {
        "id": "short_got_it_is_non_answer",
        "transcript": "Got it.",
        "assistant_context": "What word do these sounds make: k, a, t?",
        "expected_text": "Got it.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": False,
    },
    {
        "id": "short_end_card_is_non_answer",
        "transcript": "End card.",
        "assistant_context": "What word do these sounds make: k, a, t?",
        "expected_text": "End card.",
        "expected_numbers": [],
        "expected_non_answer": True,
        "expected_phone_system": False,
    },
    {
        "id": "whisper_phrase_hallucination_a_bit_better",
        "transcript": "a bit better because...",
        "assistant_context": "What is the first sound in mango?",
        "expected_text": "a bit better because...",
        "expected_numbers": [],
        "expected_hallucination": True,
    },
    {
        "id": "whisper_phrase_hallucination_click_on",
        "transcript": "And you click on...",
        "assistant_context": "Blend these sounds: c-a-t.",
        "expected_text": "And you click on...",
        "expected_numbers": [],
        "expected_hallucination": True,
    },
]


def _messages(context: str) -> list[dict[str, str]]:
    return [{"role": "assistant", "content": context}] if context else []


def _normalize_case(case: dict[str, Any]) -> dict[str, Any]:
    transcript = str(case.get("transcript", "")).strip()
    context = str(case.get("assistant_context", "")).strip()
    result = normalize_lesson_transcript(transcript, _messages(context))
    numbers = extract_numbers(result.text)

    expected_text = case.get("expected_text")
    expected_numbers = case.get("expected_numbers", [])
    expected_any = [str(item).lower() for item in case.get("expected_any", [])]

    checks: list[bool] = []
    details: list[str] = []
    if expected_text is not None:
        ok = result.text.lower() == str(expected_text).lower()
        checks.append(ok)
        details.append(f"text={'ok' if ok else f'got {result.text!r}, wanted {expected_text!r}'}")
    if expected_numbers:
        ok = all(int(number) in numbers for number in expected_numbers)
        checks.append(ok)
        details.append(f"numbers={'ok' if ok else f'got {numbers}, wanted {expected_numbers}'}")
    if expected_any:
        lower = result.text.lower()
        ok = any(phrase in lower for phrase in expected_any)
        checks.append(ok)
        details.append(f"expected_any={'ok' if ok else f'got {result.text!r}, wanted any {expected_any!r}'}")
    if "expected_non_answer" in case:
        actual = is_non_answer_transcript(result.text)
        expected = bool(case["expected_non_answer"])
        ok = actual is expected
        checks.append(ok)
        details.append(f"non_answer={'ok' if ok else f'got {actual!r}, wanted {expected!r}'}")
    if "expected_phone_system" in case:
        actual = is_phone_system_transcript(result.text)
        expected = bool(case["expected_phone_system"])
        ok = actual is expected
        checks.append(ok)
        details.append(f"phone_system={'ok' if ok else f'got {actual!r}, wanted {expected!r}'}")
    if "expected_hallucination" in case:
        actual = is_likely_stt_hallucination_transcript(result.text)
        expected = bool(case["expected_hallucination"])
        ok = actual is expected
        checks.append(ok)
        details.append(f"hallucination={'ok' if ok else f'got {actual!r}, wanted {expected!r}'}")

    return {
        "id": case.get("id", "unnamed"),
        "ok": all(checks) if checks else True,
        "raw_text": transcript,
        "text": result.text,
        "numbers": numbers,
        "substitutions": result.substitutions,
        "details": details,
    }


def _transcribe_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from stt import SpeechToText

    stt = SpeechToText()
    rows = []
    for case in cases:
        audio_path = Path(str(case.get("audio_path", "")))
        if not audio_path.exists():
            rows.append({
                "id": case.get("id", str(audio_path)),
                "ok": False,
                "details": [f"missing audio_path {audio_path}"],
            })
            continue

        started_at = time.monotonic()
        stt_result = stt.transcribe(str(audio_path), context=str(case.get("assistant_context", "")))
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        case_with_text = dict(case)
        case_with_text["transcript"] = stt_result.get("text", "")
        row = _normalize_case(case_with_text)
        row.update({
            "audio_path": str(audio_path),
            "confidence": stt_result.get("confidence"),
            "latency_ms": elapsed_ms,
            "raw_stt": stt_result,
        })
        rows.append(row)
    return rows


def _load_manifest(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("manifest must be a JSON list")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="JSON manifest of audio/transcript cases")
    parser.add_argument("--transcribe", action="store_true", help="Run STT on audio_path entries before evaluating")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text report")
    args = parser.parse_args()

    cases = _load_manifest(args.manifest) if args.manifest else BUILT_IN_CASES
    rows = _transcribe_cases(cases) if args.transcribe else [_normalize_case(case) for case in cases]
    failed = [row for row in rows if not row["ok"]]

    if args.json:
        print(json.dumps({"ok": not failed, "rows": rows}, indent=2))
    else:
        print("\nSabi STT Regression")
        print("=" * 72)
        for row in rows:
            mark = "PASS" if row["ok"] else "FAIL"
            print(f"{mark:4} {row['id']}")
            print(f"     raw: {row.get('raw_text', '')}")
            print(f"     out: {row.get('text', '')}")
            if row.get("substitutions"):
                print(f"     substitutions: {row['substitutions']}")
            if row.get("latency_ms") is not None:
                print(f"     latency_ms: {row['latency_ms']} confidence={row.get('confidence')}")
            for detail in row.get("details", []):
                print(f"     {detail}")
        print("=" * 72)
        print(f"{len(rows) - len(failed)}/{len(rows)} passed")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
