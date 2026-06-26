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
    ok &= check("renders_admin_console_title", "Sabi Admin Console" in html)
    ok &= check("renders_table_first_navigation", "nav-learners" in html and "Learner Database" in html)
    ok &= check("fetches_learner_roster", "/admin/learners?limit=100" in html)
    ok &= check("fetches_call_queue", "/admin/calls?limit=100" in html)
    ok &= check("fetches_curriculum_map", "/admin/curriculum-map" in html)
    ok &= check("opens_learner_detail", "/admin/learners/${encodeURIComponent(id)}" in html)
    ok &= check("opens_call_detail", "/admin/calls/${encodeURIComponent(id)}" in html)
    ok &= check("accepts_simple_key_param", 'params.get("key")' in html and '"X-Admin-Pin"' in html)
    ok &= check("renders_learners_as_rows", "<table>" in html and "User</th>" in html and "Progress Map</th>" in html)
    ok &= check("renders_curriculum_graph", "progressSparkline" in html and "bigCurriculumMap" in html)
    ok &= check("explains_missing_phone", "No phone linked yet" in html and "Web/demo profile" in html and '"no phone"' not in html)
    ok &= check("formats_session_dates", "fmtTimestamp(session.created_at)" in html and "No date saved" in html)
    ok &= check("avoids_overlapping_map_label", "Current: M" not in html and "curriculumStatusText" in html)
    ok &= check("renders_curriculum_positions", "Current numeracy lesson" in html and "Current literacy lesson" in html)
    ok &= check("renders_learning_amount", "Learning evidence" in html and "Recent calls" in html)
    ok &= check("renders_exact_tts_text", "Sent to TTS" in html and "assistant.tts_text" in html)
    ok &= check(
        "renders_curriculum_and_scaffolds",
        "Curriculum Map" in html
        and "Full Curriculum Line" in html
        and "Bump-Down Rules" in html,
    )
    ok &= check(
        "renders_full_call_audio",
        "Conversation Recording" in html
        and "Child side" in html
        and "Sabi side" in html
        and "recordings.mixed" in html,
    )
    ok &= check("renders_turn_audio", "turn.audio" not in html and "audio_endpoint" in html)
    ok &= check("propagates_key_to_audio_tags", "${authParamName}=${encodeURIComponent(accessKey)}" in html)
    ok &= check("shows_bump_down_language", "bump-down" in html and "scaffold" in html)
    ok &= check("supports_board_workflows", "Download CSV" in html and "Recent Conversations" in html and "Turn Evidence" in html)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
