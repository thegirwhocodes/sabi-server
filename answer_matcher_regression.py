#!/usr/bin/env python3
"""Regression checks for spoken answer matching."""

from __future__ import annotations

from answer_matcher import extract_number, match_answer


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    ok &= check(
        "rejects_nearby_digits",
        match_answer("155", ["156", "one hundred and fifty six"])["matched"] is False,
        match_answer("155", ["156", "one hundred and fifty six"]),
    )
    ok &= check(
        "rejects_nearby_number_words",
        match_answer("sixteen", ["15", "fifteen"])["matched"] is False,
        match_answer("sixteen", ["15", "fifteen"]),
    )
    ok &= check(
        "parses_compound_tens_expected_answer",
        extract_number("thirty seven") == 37,
        extract_number("thirty seven"),
    )
    ok &= check(
        "parses_hyphenated_compound_number",
        extract_number("Forty-five.") == 45,
        extract_number("Forty-five."),
    )
    ok &= check(
        "rejects_noisy_thirty_for_thirty_seven",
        match_answer("30 days", ["37", "thirty seven"])["matched"] is False,
        match_answer("30 days", ["37", "thirty seven"]),
    )
    ok &= check(
        "rejects_embedded_ordinal_noise_for_number",
        match_answer("30th egg", ["37", "thirty seven"])["matched"] is False,
        match_answer("30th egg", ["37", "thirty seven"]),
    )
    ok &= check(
        "parses_hundred_compounds",
        extract_number("one hundred and twenty three") == 123,
        extract_number("one hundred and twenty three"),
    )
    ok &= check(
        "rejects_unparsed_numberish_fuzzy_match",
        match_answer("sickteen", ["15", "fifteen"])["matched"] is False,
        match_answer("sickteen", ["15", "fifteen"]),
    )
    ok &= check(
        "rejects_empty_speech",
        match_answer("", ["100", "one hundred"])["matched"] is False,
        match_answer("", ["100", "one hundred"]),
    )
    ok &= check(
        "accepts_correct_digit_phrase",
        match_answer("it is five", ["5", "five"])["matched"] is True,
        match_answer("it is five", ["5", "five"]),
    )
    ok &= check(
        "accepts_known_stt_variant",
        match_answer("fife", ["5", "five"])["matched"] is True,
        match_answer("fife", ["5", "five"]),
    )
    ok &= check(
        "accepts_fine_for_five",
        match_answer("fine", ["5", "five"])["matched"] is True,
        match_answer("fine", ["5", "five"]),
    )
    ok &= check(
        "accepts_sent_one_for_seven_stt_variant",
        match_answer("Sent one.", ["7", "seven"])["matched"] is True,
        match_answer("Sent one.", ["7", "seven"]),
    )
    ok &= check(
        "fine_does_not_match_fifteen",
        match_answer("fine", ["15", "fifteen"])["matched"] is False,
        match_answer("fine", ["15", "fifteen"]),
    )
    ok &= check(
        "single_sound_does_not_match_inside_word",
        match_answer("mango", ["m", "mmm"])["matched"] is False,
        match_answer("mango", ["m", "mmm"]),
    )
    ok &= check(
        "elongated_m_sound_matches_mmm",
        match_answer("MMMM.", ["m", "mmm"])["matched"] is True,
        match_answer("MMMM.", ["m", "mmm"]),
    )
    ok &= check(
        "meh_repetition_matches_m_sound",
        match_answer("Meh, meh, meh.", ["m", "mmm"])["matched"] is True,
        match_answer("Meh, meh, meh.", ["m", "mmm"]),
    )
    ok &= check(
        "single_vowel_does_not_match_cvc_word",
        match_answer("a", ["cat", "kat"])["matched"] is False,
        match_answer("a", ["cat", "kat"]),
    )
    ok &= check(
        "cvc_near_miss_does_not_fuzzy_match",
        match_answer("cat", ["sat"])["matched"] is False,
        match_answer("cat", ["sat"]),
    )
    ok &= check(
        "yes_does_not_match_letter_sound_s",
        match_answer("yes", ["s", "sss"])["matched"] is False,
        match_answer("yes", ["s", "sss"]),
    )
    ok &= check(
        "short_answer_matches_as_whole_phrase",
        match_answer("it is sat", ["sat"])["matched"] is True,
        match_answer("it is sat", ["sat"]),
    )
    ok &= check(
        "sick_vocab_expected_does_not_poison_other_answers",
        match_answer("medicine", ["sick", "medicine", "doctor"])["matched"] is True,
        match_answer("medicine", ["sick", "medicine", "doctor"]),
    )
    ok &= check(
        "doctor_vocab_expected_matches_after_sick_option",
        match_answer("doctor", ["sick", "medicine", "doctor"])["matched"] is True,
        match_answer("doctor", ["sick", "medicine", "doctor"]),
    )
    ok &= check(
        "short_response_does_not_match_inside_long_word",
        match_answer("a", ["umbrella"])["matched"] is False,
        match_answer("a", ["umbrella"]),
    )
    ok &= check(
        "unsegmented_cvc_does_not_match_segmented_sound_answer",
        match_answer("cat", ["c a t", "k a t", "c, a, t"])["matched"] is False,
        match_answer("cat", ["c a t", "k a t", "c, a, t"]),
    )
    ok &= check(
        "segmented_sound_answer_matches_whole_phrase",
        match_answer("c a t", ["c a t", "k a t", "c, a, t"])["matched"] is True,
        match_answer("c a t", ["c a t", "k a t", "c, a, t"]),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
