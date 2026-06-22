#!/usr/bin/env python3
"""Regression checks for Sabi's deterministic numeric answer guard."""

from __future__ import annotations

from numeric_grading import analyze_latest_numeric_turn, build_numeric_grading_hint


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def _turn(question: str, answer: str):
    return analyze_latest_numeric_turn(
        [
            {"role": "assistant", "content": question},
            {"role": "user", "content": answer},
        ]
    )


def main() -> int:
    ok = True

    simple_change = _turn(
        "A customer gives you five hundred naira, and groundnuts cost three hundred and fifty naira. How much change do you give back?",
        "one hundred and fifty naira",
    )
    ok &= check(
        "simple_market_change_accepts_150",
        simple_change.expected == 150 and simple_change.is_correct is True,
        simple_change,
    )

    unit_price_change = _turn(
        "You buy four mangoes at thirty naira each. You pay with two hundred naira. How much change do you get?",
        "eighty naira",
    )
    ok &= check(
        "unit_price_change_accepts_80",
        unit_price_change.expected == 80 and unit_price_change.is_correct is True,
        unit_price_change,
    )

    multi_item_change = _turn(
        "You buy two notebooks at fifty naira each and three pens at twenty naira each. You pay with two hundred naira. How much change is left?",
        "forty naira",
    )
    ok &= check(
        "multi_item_unit_price_change_accepts_40",
        multi_item_change.expected == 40 and multi_item_change.is_correct is True,
        multi_item_change,
    )

    wrong_answer = _turn(
        "You buy four mangoes at thirty naira each. You pay with two hundred naira. How much change do you get?",
        "seventy naira",
    )
    ok &= check(
        "unit_price_change_rejects_70",
        wrong_answer.expected == 80 and wrong_answer.is_correct is False,
        wrong_answer,
    )

    hint = build_numeric_grading_hint(
        [
            {
                "role": "assistant",
                "content": "You buy four mangoes at thirty naira each. You pay with two hundred naira. How much change do you get?",
            },
            {"role": "user", "content": "eighty naira"},
        ]
    )
    ok &= check(
        "grading_hint_for_correct_unit_price_change",
        "Treat that answer as correct" in hint and "80" in hint,
        hint,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
