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

    total_spend = _turn(
        "Groundnuts for fifteen naira and pure water for thirty naira. How much do you spend?",
        "forty five naira",
    )
    ok &= check(
        "total_spend_accepts_45",
        total_spend.expected == 45 and total_spend.is_correct is True,
        total_spend,
    )

    total_spend_costs_phrasing = _turn(
        "Groundnuts cost fifteen naira and pure water costs thirty naira. How much do you spend?",
        "forty-five",
    )
    ok &= check(
        "total_spend_costs_phrasing_accepts_45",
        total_spend_costs_phrasing.expected == 45 and total_spend_costs_phrasing.is_correct is True,
        total_spend_costs_phrasing,
    )

    total_spend_dropped_five = _turn(
        "Groundnuts cost fifteen naira and pure water costs thirty naira. How much do you spend?",
        "forty naira",
    )
    ok &= check(
        "total_spend_dropped_five_is_ambiguous_not_wrong",
        total_spend_dropped_five.expected == 45
        and total_spend_dropped_five.child_numbers == [40]
        and total_spend_dropped_five.is_correct is None,
        total_spend_dropped_five,
    )

    fine_for_five = _turn(
        "You have two mangoes and buy three more. How many mangoes altogether?",
        "fine",
    )
    ok &= check(
        "fine_stt_mishear_accepts_five_in_numeric_context",
        fine_for_five.expected == 5 and fine_for_five.child_numbers == [5] and fine_for_five.is_correct is True,
        fine_for_five,
    )

    total_spend_with_budget = _turn(
        "You have five hundred naira. You buy groundnuts for one hundred and fifty naira and pure water for thirty naira. How much did you spend?",
        "one hundred and eighty naira",
    )
    ok &= check(
        "total_spend_ignores_budget_cash",
        total_spend_with_budget.expected == 180 and total_spend_with_budget.is_correct is True,
        total_spend_with_budget,
    )

    unit_price_total = _turn(
        "You buy two notebooks at fifty naira each and three pens at twenty naira each. How much do you pay?",
        "one hundred and sixty naira",
    )
    ok &= check(
        "unit_price_total_accepts_160",
        unit_price_total.expected == 160 and unit_price_total.is_correct is True,
        unit_price_total,
    )

    implied_unit_price_total = _turn(
        "A mango costs three naira. You buy four mangoes. How much do you pay?",
        "twelve naira",
    )
    ok &= check(
        "implied_unit_price_total_accepts_12",
        implied_unit_price_total.expected == 12 and implied_unit_price_total.is_correct is True,
        implied_unit_price_total,
    )

    left_after_spending = _turn(
        "You have five hundred naira. You buy groundnuts for one hundred and fifty naira and pure water for thirty naira. How much is left?",
        "three hundred and twenty naira",
    )
    ok &= check(
        "left_after_spending_still_subtracts",
        left_after_spending.expected == 320 and left_after_spending.is_correct is True,
        left_after_spending,
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

    guided_prompt_wrong_answer = _turn(
        "Let's do one together. You have one hundred naira and spend forty naira. How much is left?",
        "fifty nine naira",
    )
    ok &= check(
        "guided_one_together_is_not_counted_as_math_number",
        guided_prompt_wrong_answer.expected == 60 and guided_prompt_wrong_answer.is_correct is False,
        guided_prompt_wrong_answer,
    )

    carrier_phrase = _turn(
        "No hints for this one: what is two plus three?",
        "The number you have dialed is not available. Press one to leave a message.",
    )
    ok &= check(
        "carrier_phrase_is_non_answer_not_wrong",
        carrier_phrase.expected == 5 and carrier_phrase.child_numbers == [] and carrier_phrase.is_correct is None,
        carrier_phrase,
    )

    teen_tens_ambiguous = _turn(
        "Biscuits cost eight naira and sweets cost seven naira. How much altogether?",
        "fifty naira",
    )
    ok &= check(
        "teen_tens_stt_confusion_is_ambiguous_not_wrong",
        teen_tens_ambiguous.expected == 15
        and teen_tens_ambiguous.child_numbers == [50]
        and teen_tens_ambiguous.is_correct is None,
        teen_tens_ambiguous,
    )

    tens_teen_ambiguous = _turn(
        "Let's play a quick number game. What number comes after twenty-nine?",
        "thirteen",
    )
    ok &= check(
        "tens_teen_stt_confusion_is_ambiguous_not_wrong",
        tens_teen_ambiguous.expected == 30
        and tens_teen_ambiguous.child_numbers == [13]
        and tens_teen_ambiguous.is_correct is None,
        tens_teen_ambiguous,
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

    no_number_hint = build_numeric_grading_hint(
        [
            {
                "role": "assistant",
                "content": "You buy pure water for three naira and groundnuts for two naira. How much altogether?",
            },
            {"role": "user", "content": "I"},
        ]
    )
    ok &= check(
        "grading_hint_for_no_usable_number_retries_instead_of_wrong",
        "no usable number" in no_number_hint and "do not mark the child wrong" in no_number_hint,
        no_number_hint,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
