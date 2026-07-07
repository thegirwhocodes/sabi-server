#!/usr/bin/env python3
"""Regression checks for the protected Sabi board/admin review console.

These pin Naomi's board-backend requirements so the console cannot silently
drift: human-language labels, learner name + phone together, no "Unnamed
learner" / "no phone" text, a real labelled sort control, STT provider
visibility, per-turn evidence (audio, raw vs cleaned STT, confidence,
timings, exact TTS text), feedback notes as first-class items, and a green,
non-overlapping curriculum node map.
"""

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

    # Shell + navigation
    ok &= check("renders_admin_console_title", "Sabi Admin Console" in html)
    ok &= check("renders_overview_first_navigation", "nav-overview" in html and "Launch Control" in html and 'view: "overview"' in html)
    ok &= check("renders_launch_gates_navigation", "nav-gates" in html and "Launch Gate Report" in html and "/admin/launch-gates" in html)
    ok &= check("renders_table_navigation", "nav-learners" in html and "Learner Database" in html)
    ok &= check("renders_indicator_backend_tab", "nav-kids" in html and "Indicator Backend" in html and "isChildProfile" in html)
    ok &= check("renders_feedback_tab", "nav-feedback" in html and "Voice Notes" in html and "/admin/feedback" in html)
    ok &= check("renders_premium_brand", "Cormorant" in html and "Lexend" in html and "brand-spark" in html and "#cba868" in html)
    ok &= check("shows_live_health_indicator", "health-dot" in html and "/health" in html)

    # Data wiring
    ok &= check("fetches_learner_roster", "/admin/learners?limit=100" in html)
    ok &= check("fetches_call_queue", "/admin/calls?limit=100" in html)
    ok &= check("fetches_feedback_notes", "/admin/feedback?limit=100" in html)
    ok &= check("fetches_curriculum_map", "/admin/curriculum-map" in html)
    ok &= check("opens_learner_detail", "/admin/learners/${encodeURIComponent(id)}" in html)
    ok &= check("opens_call_detail", "/admin/calls/${encodeURIComponent(id)}" in html)
    ok &= check("opens_feedback_for_call", "/admin/feedback/${encodeURIComponent(id)}" in html)
    ok &= check("accepts_simple_key_param", 'params.get("key")' in html and '"X-Admin-Pin"' in html)
    ok &= check("propagates_key_to_audio_tags", "${authParamName}=${encodeURIComponent(accessKey)}" in html)

    # Identity rules — no unnamed learners, no raw "no phone"
    ok &= check("explains_missing_phone", "Phone not captured yet" in html and "identity_label" in html and '"no phone"' not in html)
    ok &= check("never_renders_unnamed_learner", "Unnamed learner" not in html and "learnerName" in html and "display_name" in html)
    ok &= check("calls_show_learner_and_number", "Learner / Number" in html and "callLearnerName" in html and "callerCell" in html)

    # Sorting + filtering — real labelled controls, not filter-looking pills
    ok &= check(
        "renders_real_sort_control",
        "sort-select" in html
        and "Newest first" in html
        and "Oldest first" in html
        and "Recently active" in html,
    )
    ok &= check(
        "renders_stt_provider_filter",
        "provider-select" in html and "All providers" in html and "providerLabel" in html,
    )
    ok &= check("renders_status_filter", "status-select" in html and "Needs review" in html)
    ok &= check("renders_course_filter", "course-select" in html and "All courses" in html)

    # Human-language flags — never raw snake_case to the board
    ok &= check(
        "translates_flags_to_human_language",
        "callFlagLabel" in html
        and "Ended too soon" in html
        and "No child speech" in html
        and "Voicemail or carrier message" in html
        and "Lesson completed" in html,
    )
    ok &= check(
        "translates_turn_flags_to_human_language",
        "turnFlagLabel" in html and "Child jumped in" in html and "Asked to repeat" in html,
    )
    ok &= check(
        "calls_table_prevents_status_overlap",
        "call-status-cell" in html and "call-review-cell" in html and "review-title" in html and "flag-wrap" in html,
    )

    # STT provider visibility
    ok &= check(
        "shows_stt_provider_per_call_and_turn",
        "stt_providers_used" in html
        and "providerPills" in html
        and "user.stt_provider" in html
        and "Groq Whisper" in html
        and "Intron" in html,
    )

    # Learner rows + progress map
    ok &= check("renders_learners_as_rows", "<table>" in html and "User</th>" in html and "Progress Map</th>" in html)
    ok &= check("renders_curriculum_graph", "progressSparkline" in html and "learningPathTreePanel" in html)
    ok &= check("renders_dual_course_positions", "Numeracy learning path" in html and "Literacy learning path" in html and "learningPathTreePanel" in html)
    ok &= check("renders_curriculum_positions", "Current numeracy lesson" in html and "Current literacy lesson" in html)
    ok &= check("renders_learning_amount", "Learning evidence" in html and "Recent practice" in html)
    ok &= check("formats_session_dates", "fmtTimestamp(session.created_at)" in html and "No date saved" in html)
    ok &= check("renders_clean_conversation_rows", "conversation-action" in html and "Child turns" in html and "Length" in html)
    ok &= check("labels_recent_conversations_sort", "Newest first" in html and "Recent Conversations" in html)

    # Curriculum map style rules — green, subtle, no overlap, no brown, no giant ball
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

    # Call review evidence
    ok &= check(
        "renders_full_call_audio",
        "Conversation Recording" in html
        and "Child side" in html
        and "Sabi side" in html
        and "recordings.mixed" in html,
    )
    ok &= check(
        "renders_call_conversation_timeline",
        "Conversation Transcript" in html
        and "Child said" in html
        and "Sabi replied" in html
        and "Lesson text after cleanup" in html,
    )
    ok &= check("renders_exact_tts_text", "Sent to TTS" in html and "assistant.tts_text" in html)
    ok &= check("renders_turn_audio", "turn.audio" not in html and "audio_endpoint" in html)
    ok &= check(
        "renders_turn_timings",
        "timingsLine" in html and "Heard in" in html and "Thought in" in html and "Spoke in" in html,
    )
    ok &= check("shows_bump_down_language", "bump-down" in html and "scaffold" in html)
    ok &= check(
        "renders_feedback_note_on_call",
        "Feedback Note" in html and "feedbackBlock" in html and "redacted_transcript" in html,
    )

    # Curriculum + scaffolds view
    ok &= check(
        "renders_curriculum_and_scaffolds",
        "Curriculum Map" in html
        and "Full Curriculum Line" in html
        and "Bump-Down Rules" in html,
    )

    # Board workflows
    ok &= check("supports_board_workflows", "Download CSV" in html and "Recent Conversations" in html and "Conversation Transcript" in html)
    ok &= check(
        "renders_rct_advancement_board_view",
        "RCT Advancement" in html
        and "protocol, instruments, consent, data quality, outcomes, and publication pack" in html
        and "item-response rows" in html,
    )
    ok &= check(
        "renders_learning_indicator_map",
        "Learning Indicator Map" in html
        and "indicator-node" in html
        and "activeIndicatorKey" in html
        and "click a node to see the learner evidence underneath" in html,
    )
    ok &= check(
        "renders_preview_indicator_mode",
        "preview_learning_indicators" in html
        and "preview_cohort" in html
        and "Pilot evidence preview" in html
        and "Preview only" in html
        and "ready to capture" in html,
    )
    ok &= check(
        "replaces_per_child_evidence_table_with_indicators",
        "Per-child evidence" not in html
        and "Child-Safe Evidence Export" in html
        and "learning_indicators" in html,
    )
    ok &= check(
        "renders_board_training",
        "World-Class Measurement Standard" in html
        and "Sabi Board Training" in html
        and "deliver the measurement" in html
        and "Do not:" in html,
    )
    ok &= check(
        "renders_partner_evidence_service",
        "Partner Evidence Service" in html
        and "/admin/evidence-protocol-kit" in html
        and "ship the same protocol to outside teams" in html,
    )
    ok &= check(
        "renders_learning_ops_overview",
        "Review Queue" in html
        and "Learners Needing Attention" in html
        and "Backend Model We Are Copying" in html
        and "Khan style" in html
        and "Lexia style" in html
        and "OpenAI style" in html,
    )
    ok &= check("celebrates_progress", "Worth Celebrating" in html and "learnersToCelebrate" in html)
    ok &= check(
        "supports_deep_link_urls",
        "applyHashFrom" in html
        and "writeHash" in html
        and "hashchange" in html
        and "history.replaceState" in html
        and "loadData().then(() => applyHashFrom(bootHash))" in html,
    )
    ok &= check("remembers_sort_and_filter_prefs", "savePrefs" in html and "sabi_admin_sort" in html and "sabi_admin_filters" in html)
    ok &= check("debounces_search", "searchTimer" in html and "clearTimeout" in html)
    ok &= check(
        "renders_launch_gate_cards",
        "renderLaunchGatesView" in html
        and "Overall launch posture" in html
        and "Provider canary" in html
        and "Next action:" in html
        and "gate-card" in html,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
