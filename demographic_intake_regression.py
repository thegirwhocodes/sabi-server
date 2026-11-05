"""Regression tests for the first-call demographic intake.

Run: python3 demographic_intake_regression.py
No network: the Supabase client is faked, so this asserts the payload shape
that would be written to sabi_students and sabi_identity_events.
"""

from __future__ import annotations

import demographic_intake as d


class FakeQuery:
    def __init__(self, log, table):
        self.log = log
        self.table_name = table
        self.payload = None
        self.filters = {}

    def update(self, payload):
        self.payload = payload
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        self.log.append((self.table_name, self.filters, self.payload))
        return type("Result", (), {"data": [self.payload] if self.payload else []})()


class FakeClient:
    def __init__(self):
        self.log = []

    def table(self, name):
        return FakeQuery(self.log, name)


class FakeStore:
    def __init__(self):
        self.client = FakeClient()


def test_normalisers():
    assert d.normalize_age("nine years") == 9
    assert d.normalize_age("12") == 12
    assert d.normalize_age("twenty") is None
    assert d.normalize_age("3") is None
    assert d.normalize_sex("I am a girl") == "female"
    assert d.normalize_schooling("no school")[0] == "out_of_school"
    assert d.normalize_schooling("government school") == ("in_school", "public")
    assert d.normalize_state("I live in Lagos state") == "Lagos"
    assert d.normalize_state("nowhere") is None
    assert d.normalize_language("we speak Yoruba") == "yo"


def test_question_order_and_completion():
    answers = d.DemographicAnswers()
    asked = []
    question = d.next_question(answers)
    while question:
        asked.append(question)
        field_name = next(f for f, q in d.QUESTIONS if q == question)
        d.apply_answer(answers, field_name, {
            "age_years": "eleven",
            "sex": "boy",
            "schooling_status": "I go to school",
            "school_type": "private",
            "location_state": "Enugu",
            "home_language": "igbo",
        }[field_name])
        question = d.next_question(answers)
    assert asked == [q for _, q in d.QUESTIONS]
    assert answers.answered() == 6


def test_write_payload_is_scoped_and_complete():
    store = FakeStore()
    answers = d.answers_from_mapping({
        "age": "ten",
        "sex": "girl",
        "schooling_status": "public school",
        "state": "Oyo",
        "language": "yoruba",
    })
    result = d.write_demographics(store, "student-1", answers)
    assert result["ok"] is True
    students = [entry for entry in store.client.log if entry[0] == "sabi_students"]
    events = [entry for entry in store.client.log if entry[0] == "sabi_identity_events"]
    assert students and events
    table, filters, payload = students[0]
    assert filters == {"id": "student-1"}
    assert payload["age_years"] == 10
    assert payload["sex"] == "female"
    assert payload["schooling_status"] == "in_school"
    assert payload["school_type"] == "public"
    assert payload["location_state"] == "Oyo"
    assert payload["home_language"] == "yo"
    assert payload["demographics_completed_at"]
    assert events[0][2]["event_type"] == "demographics_recorded"


def test_partial_intake_does_not_mark_complete():
    store = FakeStore()
    answers = d.answers_from_mapping({"age": "eight"})
    result = d.write_demographics(store, "student-2", answers)
    payload = [entry for entry in store.client.log if entry[0] == "sabi_students"][0][2]
    assert result["ok"] is True
    assert "demographics_completed_at" not in payload
    assert payload["age_years"] == 8


def test_junk_answers_are_dropped_not_guessed():
    store = FakeStore()
    answers = d.answers_from_mapping({"age": "uhhh", "sex": "what", "state": "hello", "language": "mmm"})
    assert answers.answered() == 0
    assert d.write_demographics(store, "student-3", answers)["reason"] == "no_answers"


def test_no_store_is_not_fatal():
    assert d.write_demographics(type("S", (), {"client": None})(), "x", d.DemographicAnswers(age_years=9))["ok"] is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all demographic intake tests passed")
