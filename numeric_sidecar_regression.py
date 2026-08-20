#!/usr/bin/env python3
"""Regressions for the Gemini Live numeric STT sidecar (shadow mode).

Runs entirely offline: no Groq call, no Whisper model, no Gemini session. The
engines are replaced with stubs so the checks are about the *policy* — one
canonical clip, independent votes, numeric-value agreement, deadline handling,
stale rejection, and the guarantee that none of it can touch a live lesson.
"""

from __future__ import annotations

import inspect
import json
import os
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

import numeric_sidecar
import stt as stt_module
from numeric_sidecar import NumericSidecar, expected_number_from_problem
from stt import SpeechToText, _canonical_numeric_clip


FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    if condition:
        print(f"PASS {name}")
        return True
    FAILURES.append(f"{name}: {detail}" if detail else name)
    print(f"FAIL {name} {detail}")
    return False


def write_wav(path: Path, seconds: float = 0.4, rate: int = 8000) -> Path:
    frames = int(rate * seconds)
    pcm = b"".join(
        struct.pack("<h", int(6000 * ((index % 40) - 20) / 20)) for index in range(frames)
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return path


def build_stt(groq_text: str, local_text: str, *, groq_delay: float = 0.0,
              local_delay: float = 0.0, groq_error: Exception | None = None):
    """A SpeechToText whose two votes are stubs, with no model or network."""
    from concurrent.futures import ThreadPoolExecutor

    item = object.__new__(SpeechToText)
    item._ensemble_executor = ThreadPoolExecutor(max_workers=3)
    item._groq_key = "test-key"
    item._azure_speech_key = ""
    item._azure_speech_region = ""
    seen_paths: list[str] = []

    def groq_vote(audio_path: str) -> dict:
        seen_paths.append(audio_path)
        if groq_delay:
            time.sleep(groq_delay)
        if groq_error is not None:
            raise groq_error
        return {
            "text": groq_text,
            "provider": "groq",
            "model": "whisper-large-v3",
            "duration_seconds": 0.4,
            "diagnostics": {"avg_logprob": -0.31, "max_no_speech_prob": 0.02},
        }

    def local_vote(audio_path: str) -> dict:
        seen_paths.append(audio_path)
        if local_delay:
            time.sleep(local_delay)
        return {
            "text": local_text,
            "provider": "local_whisper",
            "model": "faster-whisper:large-v3:cpu",
            "duration_seconds": 0.4,
            "diagnostics": {"avg_logprob": -0.44, "mean_word_probability": 0.71},
        }

    item._transcribe_groq_numeric_vote = groq_vote
    item._transcribe_local_numeric_vote = local_vote
    return item, seen_paths


def run_sidecar(groq_text: str, local_text: str, wav: Path, **kwargs) -> tuple[dict, list[str]]:
    engine, seen = build_stt(groq_text, local_text, **kwargs)
    result = engine.transcribe_numeric_sidecar(
        str(wav),
        decision_deadline_seconds=kwargs.pop("deadline", 1.5),
        collection_timeout_seconds=10.0,
    )
    return result, seen


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sabi-sidecar-regression-"))
    wav = write_wav(tmp / "user_turn_00.wav")

    # 1. One canonical 16 kHz clip, and BOTH engines read that same file.
    clip_path, clip_meta = _canonical_numeric_clip(str(wav))
    try:
        with wave.open(clip_path, "rb") as handle:
            clip_rate = handle.getframerate()
            clip_channels = handle.getnchannels()
        check("canonical_clip_is_16k_mono", clip_rate == 16000 and clip_channels == 1,
              f"rate={clip_rate} channels={clip_channels}")
        check("canonical_clip_records_hash", len(clip_meta.get("sha256", "")) == 64,
              str(clip_meta))
        check("canonical_clip_keeps_source_rate", clip_meta.get("source_sample_rate") == 8000,
              str(clip_meta))
    finally:
        os.unlink(clip_path)

    result, seen = run_sidecar("thirty", "thirty naira", wav)
    check("both_engines_get_identical_bytes", len(set(seen)) == 1 and len(seen) == 2, str(seen))
    check("temp_clip_is_cleaned_up", not Path(seen[0]).exists(), seen[0])
    check("agreement_within_deadline_is_eligible",
          result["status"] == "agreed" and result["decision_eligible"] is True, str(result))
    check("agreement_returns_the_number", result["consensus_numeric_value"] == 30, str(result))
    check("audit_keeps_both_transcripts",
          result["ensemble_results"]["groq"]["text"] == "thirty"
          and result["ensemble_results"]["local_whisper"]["text"] == "thirty naira",
          str(result["ensemble_results"]))

    # 2. Object nouns never decide the answer.
    result, _ = run_sidecar("two mangoes", "two fries", wav)
    check("object_nouns_ignored", result["consensus_numeric_value"] == 2, str(result))

    # 3. Teen/tens conflict must NOT be resolved by guessing.
    result, _ = run_sidecar("thirteen", "thirty", wav)
    check("teen_tens_conflict_abstains",
          result["status"] == "disagreed" and result["consensus_numeric_value"] is None,
          str(result))
    check("disagreement_asks_for_repeat",
          result["hypothetical_action"] == "neutral_repeat_disagreement", str(result))

    # 4. Ambiguous multi-value speech is not scorable.
    result, _ = run_sidecar("is it twenty or thirty", "thirty", wav)
    check("multiple_values_abstain", result["status"] == "abstained", str(result))

    # 5. Nothing heard: silence must never become a number.
    result, _ = run_sidecar("", "", wav)
    check("silence_never_becomes_a_number",
          result["status"] == "abstained" and result["consensus_numeric_value"] is None,
          str(result))

    # 6. A slow local vote is evidence, not a live decision.
    engine, _ = build_stt("thirty", "thirty", local_delay=0.6)
    result = engine.transcribe_numeric_sidecar(
        str(wav), decision_deadline_seconds=0.2, collection_timeout_seconds=10.0
    )
    check("late_agreement_is_not_decision_eligible",
          result["status"] == "agreed_late" and result["decision_eligible"] is False, str(result))

    # 7. A provider failure abstains instead of letting one engine decide alone.
    engine, _ = build_stt("thirty", "thirty", groq_error=RuntimeError("HTTP 429"))
    result = engine.transcribe_numeric_sidecar(str(wav), collection_timeout_seconds=5.0)
    check("single_engine_never_decides", result["status"] == "abstained", str(result))
    check("provider_error_is_recorded",
          "429" in json.dumps(result["ensemble_results"]["groq"]), str(result["ensemble_results"]))

    # 8. No question, operands, or expected answer may reach a recogniser.
    groq_source = inspect.getsource(SpeechToText._transcribe_groq_numeric_vote)
    local_source = inspect.getsource(SpeechToText._transcribe_local_numeric_vote)
    check("groq_vote_takes_no_context",
          "context" not in inspect.signature(SpeechToText._transcribe_groq_numeric_vote).parameters,
          "vote must not accept lesson context")
    check("local_vote_takes_no_context",
          "context" not in inspect.signature(SpeechToText._transcribe_local_numeric_vote).parameters,
          "vote must not accept lesson context")
    check("votes_use_no_lesson_prompt",
          "_prompt_for_mode" not in groq_source and "_prompt_for_mode" not in local_source
          and "initial_prompt=None" in local_source,
          "the biased turn-based prompt must stay out of the votes")
    check("generic_prompt_is_off_by_default",
          os.getenv("SABI_SIDECAR_GENERIC_PROMPT", "") == "",
          "a generic prompt needs bake-off evidence first")
    check("groq_vote_has_no_local_fallback",
          "_transcribe_local" not in groq_source,
          "salvage would make the two votes one engine")

    # 9. Shadow mode is the only implemented mode, even if misconfigured.
    os.environ["SABI_NUMERIC_SIDECAR_MODE"] = "live"
    check("unimplemented_mode_falls_back_to_shadow", numeric_sidecar.sidecar_mode() == "shadow")
    os.environ.pop("SABI_NUMERIC_SIDECAR_MODE")

    # 10. End-to-end shadow record.
    engine, _ = build_stt("thirty", "thirty naira")
    sidecar = NumericSidecar("call-regression", engine, audio_dir=tmp)
    queued = sidecar.submit(
        turn_index=0, audio_path=wav, gemini_text="Tati", expected_answer=30,
        problem_id="mult_2x2", attempt=1, prompt_level="none",
    )
    check("numeric_turn_is_measured", queued is True)
    sidecar.drain(10)
    records = [json.loads(line) for line in sidecar.record_path.read_text().splitlines()]
    check("record_is_persisted", len(records) == 1, str(records))
    row = records[0]
    check("record_keeps_gemini_and_engine_text",
          row["gemini_text"] == "Tati" and row["groq_text"] == "thirty"
          and row["local_whisper_text"] == "thirty naira", str(row))
    check("record_has_audio_hash", len(row["audio"].get("sha256", "")) == 64, str(row["audio"]))
    check("record_is_never_applied_to_grading",
          row["applied_to_grading"] is False and row["mode"] == "shadow", str(row))
    check("record_scores_against_expected",
          row["agreement_matches_expected"] is True and row["expected_answer"] == 30, str(row))
    summary = sidecar.summary()
    check("summary_counts_the_turn",
          summary["turns_measured"] == 1 and summary["numeric_agreement"] == 1, str(summary))

    # 11. A result for an old turn is audit-only.
    engine, _ = build_stt("thirty", "thirty")
    sidecar = NumericSidecar("call-stale", engine, audio_dir=tmp)
    sidecar.submit(turn_index=0, audio_path=wav, gemini_text="", expected_answer=30)
    sidecar.note_current_turn(3)
    sidecar.drain(10)
    check("late_turn_is_marked_stale", sidecar.summary()["stale_results"] == 1,
          str(sidecar.summary()))

    # 12. Missing audio is skipped silently. A turn with no expected answer is
    # NOT skipped any more: checking whether Sabi heard the child correctly is
    # Gemini's transcript against the two re-hearers, and needs no answer key.
    engine, _ = build_stt("thirty", "thirty")
    sidecar = NumericSidecar("call-skip", engine, audio_dir=tmp)
    check("turn_without_answer_key_still_runs",
          sidecar.submit(turn_index=0, audio_path=wav, expected_answer=None) is True)
    sidecar.drain(10)
    skip_rows = [json.loads(line) for line in sidecar.record_path.read_text().splitlines()]
    check("hearing_check_runs_without_expected_answer",
          len(skip_rows) == 1 and skip_rows[0]["expected_answer"] is None
          and skip_rows[0]["consensus_numeric_value"] == 30,
          str(skip_rows))
    # Naomi's 16:15 call in miniature: she said thirty, Gemini rendered it "13 €".
    # Both re-hearers agreeing on 30 is what tells us Sabi mis-heard her.
    engine, _ = build_stt("thirty", "thirty")
    sidecar = NumericSidecar("call-mishear", engine, audio_dir=tmp)
    sidecar.submit(turn_index=0, audio_path=wav, gemini_text="13 \u20ac", expected_answer=None)
    sidecar.drain(10)
    mishear = [json.loads(line) for line in sidecar.record_path.read_text().splitlines()]
    check("mishear_is_flagged",
          len(mishear) == 1 and mishear[0]["sabi_heard_it_right"] is False,
          str(mishear))

    engine, _ = build_stt("thirty", "thirty")
    sidecar = NumericSidecar("call-heard-ok", engine, audio_dir=tmp)
    sidecar.submit(turn_index=0, audio_path=wav, gemini_text="thirty naira", expected_answer=None)
    sidecar.drain(10)
    ok = [json.loads(line) for line in sidecar.record_path.read_text().splitlines()]
    check("correct_hearing_is_not_flagged",
          len(ok) == 1 and ok[0]["sabi_heard_it_right"] is True, str(ok))

    check("missing_audio_skipped",
          sidecar.submit(turn_index=0, audio_path=tmp / "nope.wav", expected_answer=4) is False)
    check("no_stt_disables_sidecar", NumericSidecar("call-none", None).enabled is False)

    # 13. An engine crash cannot break the lesson; it becomes a record.
    class ExplodingStt:
        def transcribe_numeric_sidecar(self, *args, **kwargs):
            raise RuntimeError("boom")

    sidecar = NumericSidecar("call-error", ExplodingStt(), audio_dir=tmp)
    check("engine_crash_does_not_raise",
          sidecar.submit(turn_index=0, audio_path=wav, expected_answer=8) is True)
    sidecar.drain(10)
    error_rows = [json.loads(line) for line in sidecar.record_path.read_text().splitlines()]
    check("engine_crash_is_recorded",
          len(error_rows) == 1 and error_rows[0]["status"] == "error", str(error_rows))

    # 14. Queue pressure drops work instead of queueing behind the learner.
    os.environ["SABI_NUMERIC_SIDECAR_MAX_PENDING"] = "1"
    engine, _ = build_stt("thirty", "thirty", local_delay=0.5)
    sidecar = NumericSidecar("call-capacity", engine, audio_dir=tmp)
    first = sidecar.submit(turn_index=0, audio_path=wav, expected_answer=30)
    second = sidecar.submit(turn_index=1, audio_path=wav, expected_answer=30)
    check("capacity_limit_drops_extra_work", first is True and second is False)
    sidecar.drain(10)
    check("dropped_work_is_reported", sidecar.summary()["dropped_for_capacity"] == 1,
          str(sidecar.summary()))
    os.environ.pop("SABI_NUMERIC_SIDECAR_MAX_PENDING")

    # 15. The graded item wins over the reserved next problem.
    import gemini_live

    runner = object.__new__(gemini_live.GeminiLiveCallRunner)
    engine, _ = build_stt("thirty", "thirty")
    runner.sidecar = NumericSidecar("call-graded-item", engine, audio_dir=tmp)
    runner.turn_index = 4
    runner.call = type("Call", (), {"call_uuid": "call-graded-item"})()
    runner.tools = gemini_live.GeminiLiveNumeracyTools("call-graded-item")
    runner.tools.next_problem()
    runner.turn_tool_events = [
        {
            "name": "grade_numeric_answer",
            "result": {
                "status": "correct",
                "problem_id": "graded_item",
                "expected_answer": 6,
                "prompt_level": "none",
                # a correct grade reserves the NEXT item, whose answer differs
                "next_problem": {"problem_id": "reserved_item", "expected_answer": 9},
            },
        }
    ]
    runner._submit_numeric_sidecar(wav, "six")
    runner.sidecar.drain(10)
    graded_rows = [
        json.loads(line) for line in runner.sidecar.record_path.read_text().splitlines()
    ]
    check("sidecar_scores_the_item_the_child_answered",
          len(graded_rows) == 1 and graded_rows[0]["expected_answer"] == 6
          and graded_rows[0]["problem_id"] == "graded_item", str(graded_rows))

    # 16. Ungraded turn still measured while a registered problem is open.
    runner.turn_tool_events = []
    runner.sidecar = NumericSidecar("call-open-problem", engine, audio_dir=tmp)
    runner.tools.current_problem_resolved = False
    submitted = runner._submit_numeric_sidecar(wav, "I don't know")
    check("open_registered_problem_is_measured", submitted is True)
    runner.sidecar.drain(10)

    # 17. Resolved problem with no grade event is not invented into a turn.
    runner.sidecar = NumericSidecar("call-resolved", engine, audio_dir=tmp)
    runner.tools.current_problem_resolved = True
    check("resolved_problem_without_grade_is_skipped",
          runner._submit_numeric_sidecar(wav, "okay") is False)

    # 18. The live path stays in shadow: gemini_live may not read a consensus.
    gemini_source = Path("gemini_live.py").read_text()
    check("gemini_live_never_reads_a_consensus_value",
          "consensus_numeric_value" not in gemini_source,
          "shadow mode must not feed grading")
    check("sidecar_submit_is_guarded_from_exceptions",
          "Numeric sidecar submit failed" in gemini_source,
          "a measurement failure must not break a call")

    # 19. Azure as the second vote — different family, same policy.
    engine, seen_azure = build_stt("thirty", "unused")
    engine._azure_speech_key = "azure-test-key"
    engine._azure_speech_region = "eastus"

    def azure_vote(audio_path: str) -> dict:
        seen_azure.append(audio_path)
        return {
            "text": "30",
            "provider": "azure",
            "model": "azure-speech:en-NG",
            "diagnostics": {"azure_confidence": 0.07, "recognition_status": "Success"},
        }

    engine._transcribe_azure_numeric_vote = azure_vote
    names = [name for name, _call, _ok in engine.numeric_sidecar_engines()]
    check("azure_is_the_default_second_vote_when_configured",
          names == ["groq", "azure"], str(names))
    result = engine.transcribe_numeric_sidecar(str(wav), collection_timeout_seconds=10.0)
    check("azure_vote_agrees_on_the_number",
          result["status"] == "agreed" and result["consensus_numeric_value"] == 30, str(result))
    check("record_names_both_engines", result["engines"] == ["groq", "azure"], str(result["engines"]))
    check("azure_diagnostics_are_preserved",
          result["ensemble_results"]["azure"]["diagnostics"].get("azure_confidence") == 0.07,
          str(result["ensemble_results"]["azure"]))
    check("azure_and_groq_share_one_clip",
          len({path for path in seen_azure}) == 1, str(seen_azure))

    azure_source = inspect.getsource(SpeechToText._transcribe_azure_numeric_vote)
    # Scan the executable code, not the docstring that explains why we avoid these.
    azure_parts = azure_source.split('"""')
    azure_code = azure_parts[0] + "".join(azure_parts[2:])
    check("azure_vote_takes_no_context",
          "context" not in inspect.signature(SpeechToText._transcribe_azure_numeric_vote).parameters,
          "vote must not accept lesson context")
    check("azure_vote_sends_no_phrase_list",
          "phrase" not in azure_code.lower() and "expected" not in azure_code.lower(),
          "biasing Azure toward the answer destroys the point of the vote")
    check("azure_confidence_is_not_a_gate",
          "azure_confidence" in azure_source and "azure_confidence" not in inspect.getsource(
              SpeechToText._collect_numeric_votes),
          "Azure confidence is recorded, never used to accept an answer")

    # 20. Forcing the offline engine back must still work (no Azure dependency).
    os.environ["SABI_NUMERIC_SIDECAR_SECOND_ENGINE"] = "local_whisper"
    engine, _ = build_stt("thirty", "thirty")
    engine._azure_speech_key = "azure-test-key"
    engine._azure_speech_region = "eastus"
    names = [name for name, _call, _ok in engine.numeric_sidecar_engines()]
    check("second_engine_is_overridable", names == ["groq", "local_whisper"], str(names))
    os.environ.pop("SABI_NUMERIC_SIDECAR_SECOND_ENGINE")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} numeric sidecar check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("All numeric sidecar checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
