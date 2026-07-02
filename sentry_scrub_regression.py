"""
Regression: Sentry PII scrubbing + fail-open init.

Proves:
  1. Phone numbers (E.164, local 080..., learner_key form) are masked in every
     event surface Sentry sends: message, logentry, exception values,
     breadcrumbs, request data/url, extra, tags.
  2. Sensitive headers (Authorization, X-API-Key, Cookie) are filtered.
  3. User identity is always reduced to a filtered placeholder.
  4. init_sentry() is a no-op (returns False, no crash) when SENTRY_DSN is unset.
  5. A broken event never leaks: if scrubbing throws, the event is dropped.

Run: python3 sentry_scrub_regression.py
"""

import os
import sys

import sentry_setup
from sentry_setup import init_sentry, scrub_event

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name}")


def flat(obj):
    import json

    return json.dumps(obj)


# --- 1+2+3: full event scrub ---
event = {
    "message": "call from +2348012345678 failed",
    "transaction": "/admin/calls/+18604367048",
    "logentry": {
        "message": "learner %s not found",
        "formatted": "learner +234 801 234 5678 not found",
        "params": ["+2348012345678::amara"],
    },
    "exception": {
        "values": [{"type": "ValueError", "value": "bad phone 08012345678"}]
    },
    "breadcrumbs": {
        "values": [
            {"message": "dialing +2342017001459", "data": {"phone": "+2348012345678"}}
        ]
    },
    "request": {
        "url": "https://api.eduforequality.org/admin/feedback?phone=%2B2348012345678",
        "query_string": "phone=+2348012345678",
        "headers": {"Authorization": "Bearer abc", "X-API-Key": "k", "Accept": "*/*"},
        "cookies": {"session": "x"},
        "data": {"phone": "+2348012345678", "note": "ok"},
    },
    "extra": {"caller": "+2348012345678", "turns": 5},
    "tags": {"phone": "+2348012345678"},
    "user": {"id": "+2348012345678", "ip_address": "1.2.3.4"},
}

scrubbed = scrub_event(event)
s = flat(scrubbed)
check("no raw phone digits survive anywhere", "2348012345678" not in s and "8604367048" not in s and "2342017001459" not in s and "234 801 234 5678" not in s)
check("message masked", scrubbed["message"] == "call from [phone] failed")
check("exception value masked", "[phone]" in scrubbed["exception"]["values"][0]["value"])
check("logentry formatted masked", "[phone]" in scrubbed["logentry"]["formatted"])
check("learner_key param masked", "[phone]" in flat(scrubbed["logentry"]["params"]))
check("breadcrumb masked", "[phone]" in scrubbed["breadcrumbs"]["values"][0]["message"])
check("auth header filtered", scrubbed["request"]["headers"]["Authorization"] == "[filtered]")
check("api key header filtered", scrubbed["request"]["headers"]["X-API-Key"] == "[filtered]")
check("benign header kept", scrubbed["request"]["headers"]["Accept"] == "*/*")
check("cookies dropped", "cookies" not in scrubbed["request"])
check("user reduced to placeholder", scrubbed["user"] == {"id": "[filtered]"})
check("non-string extra untouched", scrubbed["extra"]["turns"] == 5)

# Ordinary small numbers (scores, counts) must survive — only phone-shaped runs masked.
ev2 = scrub_event({"message": "child answered 45 after 3 tries in lesson 12"})
check("ordinary numbers survive", ev2["message"] == "child answered 45 after 3 tries in lesson 12")

# --- 4: fail-open init without DSN ---
old = os.environ.pop("SENTRY_DSN", None)
try:
    check("init without DSN returns False (no crash)", init_sentry() is False)
finally:
    if old is not None:
        os.environ["SENTRY_DSN"] = old

# --- 5: scrubber failure drops the event instead of leaking ---
class Evil(dict):
    def get(self, *a, **kw):  # force an exception inside scrub_event
        raise RuntimeError("boom")


check("broken event dropped, not leaked", scrub_event(Evil()) is None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
