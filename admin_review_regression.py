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
    ok &= check("renders_kids_backend_tab", "nav-kids" in html and "Kids Backend" in html and "isChildProfile" in html)
    ok &= check("fetches_learner_roster", "/admin/learners?limit=100" in html)
    ok &= check("fetches_call_queue", "/admin/calls?limit=100" in html)
    ok &= check("fetches_curriculum_map", "/admin/curriculum-map" in html)
    ok &= check("opens_learner_detail", "/admin/learners/${encodeURIComponent(id)}" in html)
    ok &= check("opens_call_detail", "/admin/calls/${encodeURIComponent(id)}" in html)
    ok &= check("accepts_simple_key_param", 'params.get("key")' in html and '"X-Admin-Pin"' in html)
    ok &= check("renders_learners_as_rows", "<table>" in html and "User</th>" in html and "Progress Map</th>" in html)
    ok &= check("renders_curriculum_graph", "progressSparkline" in html and "bigCurriculumMap" in html)
    ok &= check("explains_missing_phone", "No phone linked" in html and "identity_label" in html and '"no phone"' not in html)
    ok &= check("never_renders_unnamed_learner", "Unnamed learner" not in html and "learnerName" in html and "display_name" in html)
    ok &= check("formats_session_dates", "fmtTimestamp(session.created_at)" in html and "No date saved" in html)
    ok &= check("renders_clean_conversation_rows", "conversation-action" in html and "Child turns" in html and "Length" in html)
    ok &= check("calls_show_learner_and_number", "Learner / Number" in html and "callLearnerName" in html and "callerCell" in html)
    ok &= check(
        "calls_table_prevents_status_overlap",
        "call-status-cell" in html
        and "call-review-cell" in html
        and "review-title" in html
        and "callFlagLabel" in html
        and "Ended too soon" in html
        and "No child speech" in html,
    )
    ok &= check("curriculum_range_is_map_label", "Map view" in html and "renderCurriculumView" in html)
    ok &= check("avoids_overlapping_map_label", "Current: M" not in html and "curriculumStatusText" in html)
    ok &= check("uses_subtle_curriculum_marker", 'r="12"' not in html and 'stroke-width="3"' in html)
    ok &= check(
        "uses_green_branch_curriculum_map",
        "learner curriculum node map" in html
        and "map-branch-label" in html
        and "#9b5b00" not in html.split("function bigCurriculumMap", 1)[-1],
    )
    ok &= check("centers_curriculum_map_labels", 'text-anchor="middle"' in html)
    ok &= check("renders_curriculum_positions", "Current numeracy lesson" in html and "Current literacy lesson" in html)
    ok &= check("renders_learning_amount", "Learning evidence" in html and "Recent practice" in html)
    ok &= check("renders_exact_tts_text", "Sent to TTS" in html and "assistant.tts_text" in html)
    ok &= check(
        "renders_call_conversation_timeline",
        "Conversation Transcript" in html
        and "Child said" in html
        and "Sabi replied" in html
        and "Lesson text after cleanup" in html,
    )
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
    ok &= check("supports_board_workflows", "Download CSV" in html and "Recent Conversations" in html and "Conversation Transcript" in html)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
