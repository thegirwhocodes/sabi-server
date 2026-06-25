#!/usr/bin/env python3
"""Regression checks for the protected Sabi review console shell."""

from __future__ import annotations

import sys

from admin_review import render_admin_review_page


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    html = render_admin_review_page()
    ok = True
    ok &= check("renders_review_console_title", "Sabi Review Console" in html)
    ok &= check("fetches_learner_roster", "/admin/learners?limit=40" in html)
    ok &= check("fetches_call_queue", "/admin/calls?limit=40" in html)
    ok &= check("opens_learner_detail", "/admin/learners/${encodeURIComponent(id)}" in html)
    ok &= check("opens_call_detail", "/admin/calls/${encodeURIComponent(id)}" in html)
    ok &= check(
        "renders_full_call_audio",
        "Full Call Recordings" in html
        and "Caller side" in html
        and "Sabi side" in html
        and "recordings.mixed" in html,
    )
    ok &= check("renders_turn_audio", "turn.audio" not in html and "audio_endpoint" in html)
    ok &= check("propagates_api_key_to_audio_tags", "api_key=${encodeURIComponent(apiKey)}" in html)
    ok &= check("shows_bump_down_language", "bump-down" in html and "scaffold" in html)
    ok &= check("uses_quiet_ops_layout", "Review Queue" in html and "Turn Evidence" in html)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
