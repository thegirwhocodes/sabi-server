#!/usr/bin/env python3
"""Replay the August 7 false-barge incident through the learned speech gate.

The audio remains in the private production call-review volume; no caller
recording is committed to git.  Run this script in the deployed container.  A
regression fails if any clip that Gemini previously hallucinated into a learner
turn would now be allowed to interrupt Sabi.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

from turn_taking import (
    INTERRUPTION_MIN_SPEECH_MS,
    INTERRUPTION_VAD_ONSET,
    get_managed_turn_detector,
)


DEFAULT_CALL_ID = "01eadbaf-883f-417e-b84c-1c438cfedc65"
DEFAULT_POST_PROMPT_CALL_ID = "2458d516-0334-4648-9662-993b9492743d"
DEFAULT_AUDIO_ROOT = Path("/shared/audio/call_turns")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-id", default=DEFAULT_CALL_ID)
    parser.add_argument("--post-prompt-call-id", default=DEFAULT_POST_PROMPT_CALL_ID)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    args = parser.parse_args()

    call_dir = args.audio_root / args.call_id
    clips = sorted(call_dir.glob("user_turn_*.wav"))
    if not clips:
        print(f"FAIL missing private call fixtures - {call_dir}")
        return 1

    detector = get_managed_turn_detector()
    accepted: list[str] = []
    for clip in clips:
        with wave.open(str(clip), "rb") as wav:
            pcm = wav.readframes(wav.getnframes())
        evidence = detector.speech_evidence(
            pcm,
            onset=INTERRUPTION_VAD_ONSET,
            min_speech_ms=INTERRUPTION_MIN_SPEECH_MS,
        )
        print(
            json.dumps(
                {
                    "clip": clip.name,
                    "would_interrupt": evidence.accepted,
                    **evidence.log_fields(),
                },
                sort_keys=True,
            )
        )
        if evidence.accepted:
            accepted.append(clip.name)

    if accepted:
        print(f"FAIL false_barge_incident_blocked - accepted={accepted}")
        return 1
    print(f"PASS false_barge_incident_blocked - rejected={len(clips)} clips")

    # The first candidate in the Aug 7 post-deploy call contained only 160 ms
    # of learned speech evidence. Gemini correctly returned an empty string,
    # but a literal Whisper model can invent text for the same weak audio. The
    # post-prompt gate must therefore reject it before any recognizer runs.
    listening_clip = (
        args.audio_root / args.post_prompt_call_id / "user_turn_00.wav"
    )
    if not listening_clip.is_file():
        print(f"FAIL missing post-prompt noise fixture - {listening_clip}")
        return 1
    with wave.open(str(listening_clip), "rb") as wav:
        listening_pcm = wav.readframes(wav.getnframes())
    listening = detector.listening_speech(listening_pcm)
    print(
        json.dumps(
            {
                "clip": listening_clip.name,
                "call_id": args.post_prompt_call_id,
                "would_reach_stt": listening.accepted,
                **listening.log_fields(),
            },
            sort_keys=True,
        )
    )
    if listening.accepted:
        print("FAIL post_prompt_noise_blocked")
        return 1
    print("PASS post_prompt_noise_blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
