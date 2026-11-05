#!/usr/bin/env python3
"""Regression checks for Sabi name capture.

Every artifact in the ARTIFACT_CASES list was written to production
sabi_students.name before this module existed, so these are real failures, not
hypotheticals. The GOOD_CASES are real learners from the same database.
"""

from __future__ import annotations

import sys

from identity_capture import (
    STATUS_CONFIRMED_REPEAT,
    STATUS_REJECTED,
    STATUS_UNKNOWN,
    STATUS_UNVERIFIED,
    assess_answer,
    capture,
    clean_name,
    confirmation_line,
    identity_event_payloads,
    is_confirmation_question,
    parse_yes_no,
)

ASK = "Hello! I'm Sabi, your learning friend. What is your name?"

#: (utterance, stored name in production) - all must now be refused.
ARTIFACT_CASES = [
    ("What the heck?", "What The"),
    ("A speech", "A Speech"),
    ("Uhhh", "Uhhh"),
    ("Already", "Already"),
    ("And how", "And How"),
    ("Qu significa", "Qu Significa"),
    ("Ja mann", "Ja Mann"),
    ("Chama a emergência, corre!", None),
    ("Salam alaikum.", None),
    ("I don't know", None),
    ("The number you have dialled is not available", None),
]

#: Real children, must still be captured.
GOOD_CASES = [
    ("My name is Richard", "Richard"),
    ("I am Sonia", "Sonia"),
    ("Gideon", "Gideon"),
    ("it's Hilda", "Hilda"),
    ("Ukamaka", "Ukamaka"),
]


def _check(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        failures.append(label)


def main() -> int:
    failures: list[str] = []

    print("artifact utterances are refused:")
    for utterance, stored in ARTIFACT_CASES:
        candidate = assess_answer(utterance, asked_for_name=True)
        _check(
            not candidate.accepted,
            f"{utterance!r} refused (would have stored {stored!r}) -> {candidate.verdict}",
            failures,
        )

    print("real names are still captured:")
    for utterance, expected in GOOD_CASES:
        candidate = assess_answer(utterance, asked_for_name=True)
        _check(
            candidate.accepted and candidate.name == expected,
            f"{utterance!r} -> {candidate.name!r}",
            failures,
        )

    print("a name is not stored when sabi was not asking:")
    _check(
        not assess_answer("The answer is twelve", asked_for_name=False).accepted,
        "lesson answer cannot become a name",
        failures,
    )

    print("legacy transcript without confirmation is unverified, not trusted:")
    legacy = [
        {"role": "assistant", "content": ASK},
        {"role": "user", "content": "My name is Sonia"},
        {"role": "assistant", "content": "Welcome Sonia!"},
    ]
    result = capture(legacy)
    _check(result.name == "Sonia", f"legacy name {result.name!r}", failures)
    _check(result.status == STATUS_UNVERIFIED, f"legacy status {result.status}", failures)
    _check(not result.confirmed, "legacy capture is not confirmed", failures)
    _check(result.name_for_storage == "Sonia", "legacy name still usable for continuity", failures)

    print("confirmed by repeat is trusted:")
    confirmed = [
        {"role": "assistant", "content": ASK},
        {"role": "user", "content": "Uhhh"},
        {"role": "assistant", "content": ASK},
        {"role": "user", "content": "Richard"},
        {"role": "assistant", "content": confirmation_line("Richard")},
        {"role": "user", "content": "Yes that's right"},
    ]
    result = capture(confirmed)
    _check(result.name == "Richard", f"confirmed name {result.name!r}", failures)
    _check(result.status == STATUS_CONFIRMED_REPEAT, f"confirmed status {result.status}", failures)
    _check(
        any("Uhhh" in text for text, _ in result.rejections),
        "the 'Uhhh' attempt is recorded as rejected evidence",
        failures,
    )

    print("a rejected repeat falls back to unverified:")
    rejected = [
        {"role": "assistant", "content": ASK},
        {"role": "user", "content": "Ade"},
        {"role": "assistant", "content": confirmation_line("Ade")},
        {"role": "user", "content": "No"},
    ]
    result = capture(rejected)
    _check(result.name is None, f"rejected name {result.name!r}", failures)
    _check(result.status == STATUS_REJECTED, f"rejected status {result.status}", failures)

    print("a corrected name during confirmation is kept as unverified:")
    corrected = [
        {"role": "assistant", "content": ASK},
        {"role": "user", "content": "Ade"},
        {"role": "assistant", "content": confirmation_line("Ade")},
        {"role": "user", "content": "No, my name is Amina"},
    ]
    result = capture(corrected)
    _check(result.name == "Amina", f"corrected name {result.name!r}", failures)
    _check(result.status == STATUS_UNVERIFIED, f"corrected status {result.status}", failures)

    print("pure artifact transcript never yields a name:")
    junk = [
        {"role": "assistant", "content": ASK},
        {"role": "user", "content": "What the heck?"},
        {"role": "assistant", "content": "Ah, that is a great name!"},
    ]
    result = capture(junk)
    _check(result.name is None, f"junk name {result.name!r}", failures)
    _check(result.status == STATUS_REJECTED, f"junk status {result.status}", failures)
    _check(result.name_for_storage is None, "nothing storable from junk", failures)

    print("empty transcript is unknown:")
    _check(capture([]).status == STATUS_UNKNOWN, "empty -> unknown", failures)

    print("idempotent: repeated capture gives the same answer:")
    first = capture(confirmed)
    second = capture(confirmed)
    _check((first.name, first.status) == (second.name, second.status), "replay is stable", failures)

    print("helpers:")
    _check(is_confirmation_question("Did I hear you right, is your name Ade?"), "detects confirmation question", failures)
    _check(not is_confirmation_question(ASK), "does not mistake the ask for a confirmation", failures)
    _check(parse_yes_no("yes") is True and parse_yes_no("no") is False, "yes/no parsing", failures)
    _check(parse_yes_no("maybe later") is None, "ambiguous reply is not a yes", failures)
    _check(clean_name("  richard  ") == "Richard", "clean_name title-cases", failures)

    print("event payloads describe every rejection and the outcome:")
    events = identity_event_payloads(capture(confirmed), student_id="stu-1", call_sid="CA123")
    _check(len(events) == 2, f"two events emitted, got {len(events)}", failures)
    _check(events[0]["event_type"] == "name_rejected", "first event is the rejection", failures)
    _check(events[-1]["event_type"] == "name_confirmed", "last event is the confirmation", failures)
    _check(all(e.get("call_sid") == "CA123" for e in events), "events carry the call_sid", failures)

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all identity capture checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
