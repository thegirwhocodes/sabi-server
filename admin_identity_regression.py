#!/usr/bin/env python3
"""Regression checks for learner display identities in admin surfaces."""

from __future__ import annotations

import sys
import types

if "supabase" not in sys.modules:
    supabase_stub = types.ModuleType("supabase")
    supabase_stub.create_client = lambda *args, **kwargs: None
    sys.modules["supabase"] = supabase_stub

from memory import _student_review_record


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    ok = True

    phone_record = _student_review_record(
        {
            "id": "student-phone",
            "name": None,
            "phone_number": "+2348033374126",
            "total_sessions": 4,
        },
        {},
        [],
    )
    ok &= check("phone_pending_gets_display_name", phone_record["display_name"] == "Learner 4126", phone_record)
    ok &= check("phone_pending_needs_name_capture", phone_record["needs_name_capture"] is True, phone_record)
    ok &= check("phone_pending_has_identity_label", phone_record["identity_label"] == "Name pending", phone_record)

    named_record = _student_review_record(
        {
            "id": "student-naomi",
            "name": "Naomi",
            "phone_number": "+18604367048",
            "total_sessions": 15,
        },
        {},
        [],
    )
    ok &= check("real_name_wins", named_record["display_name"] == "Naomi", named_record)
    ok &= check("real_name_not_marked_pending", named_record["needs_name_capture"] is False, named_record)

    demo_record = _student_review_record(
        {
            "id": "student-demo",
            "name": None,
            "browser_id": "93f13077-f98f-433c-b971-ab2b5ff34f3e",
            "total_sessions": 0,
        },
        {},
        [],
    )
    ok &= check("demo_record_gets_display_name", demo_record["display_name"] == "Demo profile 93f13077", demo_record)
    ok &= check("no_unnamed_display", "Unnamed" not in str([phone_record, named_record, demo_record]))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
