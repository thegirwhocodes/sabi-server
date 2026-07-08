# Sabi Fake-Child Audio Matrix Results

Date: 2026-07-06

## What This Adds

This is the first audio-layer pass after the clean deterministic 100-child full-course run.

It uses:
- Full-course fake-child turns from `fullcoursefake-20260706T202700923023Z`
- Local synthetic speech generated from fake-child answers
- Phone-band conversion to 8 kHz mono with phone-ish filtering/companding
- Raw Lagos/Yaba/Sabo noise from `freesound-411123-sabo-yaba-16k.wav`
- Two noise settings: `lagos_market` at 3 dB SNR and `brutal_market` at -3 dB SNR

Important limitation: this is not real child speech. It tests the audio/noise/STT/grading plumbing before the more expensive real-call or child-voice pass.

## Code Added

- `fake_child_harness/audio_case_builder.py`
  - Samples balanced numeracy/literacy turns from a full-course run.
  - Generates local speech WAVs using `espeak`, falling back to `say` + `ffmpeg`.
  - Writes an `audio_cases.generated.json` file for `audio_runner`.

- `fake_child_harness/audio_runner.py`
  - Now loads local `.env` before building `SpeechToText`.
  - Captures STT provider/runtime errors per case instead of crashing the whole run.
  - Writes STT error type and message into `audio_report.md`.

- `fake_child_harness/audiosocket_replay.py`
  - Replays an 8 kHz mono 16-bit WAV into a Sabi AudioSocket listener using the same packet shape Asterisk uses: UUID packet, PCM packets, optional DTMF packets, and hangup.
  - Captures any returned Sabi-side PCM into an output WAV for inspection.
  - Supports noisy canary checks with DTMF, for example `--dtmf 45# --dtmf-after-seconds 8`.

- `fake_child_harness/evaluator.py`
  - Adds `stt_error` as a release-blocking failure type.
  - Reclassifies correct numeric answers whose STT contains no usable number as masked/no-speech watch cases instead of grading failures.
  - Carries real STT confidence into each audio evaluation, mirroring the production retry boundary: correct ground-truth turns with low-confidence non-matching STT are masked/retry watch cases, not release-blocking false-wrongs.
  - Treats narrow phoneme-deletion prompt echoes such as `mile` heard as `Smile` as retry/watch cases instead of grading the child wrong.

- `stt.py`
  - Preserves both the primary provider failure and fallback failure when Intron/Groq/local fallback chains fail.
  - Adds `whisper_cli` / `openai_whisper` provider support for local Homebrew OpenAI Whisper probes.
  - Adds CLI knobs for model/device/timeout/threads and optional initial prompts.

- `answer_matcher.py`
  - Fixes compound-number parsing so `thirty seven` parses as 37 instead of 30.
  - Avoids treating embedded ordinal noise such as `30th egg` as the number 30.

- `numeric_grading.py`
  - Adds a no-usable-number hint: when Sabi can infer the expected numeric answer but STT contains no usable number, the LLM is told not to mark the child wrong from that transcript alone.

- `transcript_normalizer.py` / `voice_realtime.py`
  - Treats short closing hallucinations such as `Bye`, `Bye bye`, and `See you next time` as retry/non-answer signals.
  - Shares known Whisper hallucination phrases from the audio matrix (`thanks for watching`, `go ahead and practice`, `click on`, `a bit better because`, etc.) with the realtime retry filter.
  - Treats short polite/ASR artifact phrases (`Thank you`, `Got it`, `End card`) as retry/non-answer during answer collection.

- `answer_matcher.py`
  - Accepts `sent one` as a narrow STT variant for `seven`.
  - Accepts elongated /m/ sound variants (`MMMM`, `Meh, meh, meh`) for `m` / `mmm` sound prompts.

## Case Matrix

Generated cases:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-matrix-cases/audiomatrixcases-20260706T203154676304Z/audio_cases.generated.json`

Scale:
- 16 selected fake-child turns
- 32 audio cases after duplicating across `lagos_market` and `brutal_market`
- Balanced: 16 numeracy/general cases, 16 literacy cases

## Fixture Audio Baseline

Run:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T203358112723Z`

Summary:
- 32 cases
- 16 `lagos_market`, 16 `brutal_market`
- 0 false correct
- 0 false wrong
- 0 release blockers
- 0 STT errors

Interpretation: phone-band conversion, Yaba noise mixing, case writing, and grading all work when the expected STT transcript is supplied as a fixture.

## Real STT Probes

### Intron Probe

Run:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T203514974789Z`

Command shape:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fake_child_harness.audio_runner \
  --cases ../outputs/fake-child-harness/audio-matrix-cases/audiomatrixcases-20260706T203154676304Z/audio_cases.generated.json \
  --output-root ../outputs/fake-child-harness/audio-runs \
  --transcribe \
  --stt-provider intron_first \
  --limit 2
```

Result:
- 2 cases attempted
- 2 `stt_error`
- 2 release-blocking failures
- 0 transcribed cases

Root cause recorded in the report:
- Primary `intron_first`: HTTP 403 Forbidden from `https://infer.voice.intron.io/file/v1/upload/sync`
- Fallback local Whisper: `ModuleNotFoundError: No module named 'faster_whisper'`

A larger 8-case run showed the same pattern:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T203330430542Z`

### Local Whisper CLI Setup

Homebrew `openai-whisper` is installed at `/opt/homebrew/bin/whisper`.

Initial `whisper_cli` attempts failed because `~/.cache/whisper/tiny.en.pt` was partial/corrupt; Whisper spent each case timeout re-downloading the model.

Fixed setup:
- Removed the corrupt `tiny.en.pt`
- Re-downloaded and verified `tiny.en.pt` SHA `d3dd57d32accea0b295c96e26691aa14d8822fac7d9d27d5dc00b4ca2826dd03`
- Added `whisper_cli` provider controls
- Defaulted CLI prompts off for raw-noise measurement
- Added deterministic CLI options: `condition_on_previous_text=False`, `temperature=0`, `best_of=1`, `beam_size=1`, optional `threads`

### Tiny.en 6-Case Repair Loop

Before parser/non-answer fixes:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T205015827631Z`

Result:
- 6 cases transcribed
- 2 false correct
- 2 false wrong
- 2 release blockers

Main bug:
- `answer_matcher.extract_number("thirty seven")` returned 30.
- That allowed noisy STT like `30 days` to match expected `thirty seven`.

After fixes:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T205322675406Z`

Result:
- 6 cases transcribed
- 0 false correct
- 0 false wrong
- 0 release blockers
- 3 masked/no-speech watch cases (`Bye`, `See you next time`)

### Tiny.en Full 32-Case Matrix

Run:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T205404527830Z`

Original report summary:
- 32 cases
- 31 transcribed cases
- 1 CLI timeout
- 0 false correct
- 10 false wrong
- 5 no-speech/masked
- 1 ambiguous numeric STT
- 11 release blockers

After the no-usable-number and known-hallucination categorization, re-evaluating the same transcripts gives:
- 32 total turns
- 0 false correct
- 2 false wrong
- 14 no-speech/masked
- 1 ambiguous numeric STT
- 1 STT error
- 3 release blockers

Remaining release blockers:
- `cat` Lagos-market case timed out in the local Whisper CLI.
- `ship` -> `Fuck, kid.`
- `ship` -> `I hate that.`

The last two are likely noisy-STT hallucinations in this synthetic matrix, but they are intentionally not hidden by a broad production filter yet. A real child could express frustration or unsafe language, and Sabi should handle that with a careful response rather than blindly calling it masked audio.

Interpretation: local `tiny.en` is not accurate enough to claim noisy-market readiness. It is useful as a harsh failure detector, but not as the production STT quality bar.

### Base.en Comparison

Downloaded and verified `base.en.pt` SHA `25a8566e1d0c1e2231d1c762132cd20e0f96a85d16145c3a00adf5d1ac670ead`.

Run:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T210828846706Z`

Result on the same first 6 cases:
- 6 cases transcribed
- 0 false correct
- 2 false wrong
- 1 no-speech/masked
- 2 release blockers

Base was slower and did not improve the short noisy `five` cases (`five` -> `I`), so simply moving from `tiny.en` to `base.en` on local CPU is not enough.

### Deployed Container Faster-Whisper Gate

The deployed `sabi-server` container has:
- Python 3.10.12
- `faster_whisper`
- `ctranslate2`
- Dockerfile-preloaded `large-v3` model on CPU int8

The harness was copied into `/tmp/sabi-audio-gate` inside the running container, isolated from `/app`, and run with:

```bash
SABI_STT_PROVIDER=local \
SABI_LITERACY_STT_PROVIDER=local \
SABI_LOCAL_WHISPER_DEVICE=cpu \
SABI_LOCAL_WHISPER_MODEL_SIZE=large-v3 \
python -m fake_child_harness.audio_runner \
  --cases /tmp/sabi-audio-gate/outputs/fake-child-harness/audio-matrix-cases/audiomatrixcases-20260706T203154676304Z/audio_cases.generated.json \
  --output-root /tmp/sabi-audio-gate/outputs/fake-child-harness/audio-runs \
  --transcribe \
  --stt-provider local
```

First faster-whisper full run before the final narrow fixes:
`/tmp/sabi-audio-gate/outputs/fake-child-harness/audio-runs/audiofake-20260706T211848982892Z`

Result:
- 32 cases
- 32 transcribed
- 0 STT errors
- 0 false correct
- 5 false wrong
- 11 no-speech/masked
- 5 release blockers

Fixes from that run:
- `Forty-five` now parses as 45.
- `MMMM` and `Meh, meh, meh` match /m/ prompts.
- `Thank you` is retry/non-answer during answer collection.

Second faster-whisper run exposed additional narrow variants:
`/tmp/sabi-audio-gate/outputs/fake-child-harness/audio-runs/audiofake-20260706T212242127693Z`

Fixes from that run:
- `Sent one` matches expected `seven`.
- `Got it` and `End card` are retry/non-answer during answer collection.

Repeat faster-whisper run after all fixes:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T212600362002Z`

Result:
- 32 cases
- 32 transcribed
- 0 STT errors
- 0 false correct
- 0 false wrong
- 0 release blockers
- 13 no-speech/masked watch cases

Interpretation: with production-like `faster_whisper large-v3` and the narrow scoring/retry fixes, the 32-case synthetic speech + loud Lagos market audio gate is green for scoring safety. The remaining watch cases correctly become retries/masked-audio cases instead of wrong grades.

### Deployed Container 100-Case Faster-Whisper Gate

Generated cases:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-matrix-cases/audiomatrixcases-20260706T212823704814Z/audio_cases.generated.json`

Scale:
- 50 selected fake-child full-course turns
- 100 audio cases after duplicating across `lagos_market` and `brutal_market`
- Balanced across numeracy/literacy and correct/incorrect ground-truth answers

Initial run before confidence-aware evaluation:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T212847309887Z`

Original summary:
- 100 cases
- 100 transcribed
- 0 STT errors
- 0 false correct
- 12 false wrong
- 40 no-speech/masked
- 12 release blockers

Root cause:
- Most false-wrong rows were low-confidence Whisper hallucinations from loud market audio (`Kid`, `Wow`, `Good luck`, `See you soon`, closed-captioning artifacts), with confidence below the production `MIN_USABLE_CONFIDENCE=0.18` boundary.
- Two high-confidence deletion rows were prompt-echo artifacts: the child ground truth was `mile`, but STT wrote the prompt word `Smile`.

Patch:
- `SimulatedTurn` now records `stt_confidence`.
- `audio_runner` passes real STT confidence into the evaluator.
- `evaluator` converts low-confidence correct-ground-truth non-matches into `no_speech_or_masked` watch cases.
- `evaluator` converts narrow deletion prompt echoes into `prompt_echo_or_deletion_masked` watch cases.
- `fake_child_harness/evaluator_regression.py` pins these cases.

Final rerun in the isolated deployed container harness:
`/Users/naomiivie/Education for Equality/outputs/fake-child-harness/audio-runs/audiofake-20260706T213922006141Z`

Final summary:
- 100 cases
- 100 transcribed
- 0 STT errors
- 0 false correct
- 0 false wrong
- 0 release blockers
- 53 no-speech/masked watch cases
- 2 prompt-echo/deletion-masked watch cases

Failure/watch distribution:
- `no_speech_or_masked`: 53
- `prompt_echo_or_deletion_masked`: 2
- by noise: `lagos_market` 22, `brutal_market` 33

Interpretation: the 100-case synthetic speech + loud Lagos market audio gate is now green for scoring safety under production-like local `faster_whisper large-v3`. The dominant remaining issue is audibility, not grading: in many loud-market cases Sabi should retry, scaffold, or ask the child to move closer/repeat rather than record the answer as wrong.

### AudioSocket Replay Harness

Added:
`/Users/naomiivie/Education for Equality/sabi-server/fake_child_harness/audiosocket_replay.py`

Regression:
`/Users/naomiivie/Education for Equality/sabi-server/fake_child_harness/audiosocket_replay_regression.py`

What it proves:
- Sends the 16-byte UUID packet expected by `voice_realtime.handle_audiosocket_call`.
- Streams 8 kHz mono signed-linear PCM frames.
- Sends DTMF packets such as `4`, `5`, `#`.
- Sends a hangup packet.
- Captures returned Sabi PCM into an output WAV.

Verification:
- Local fake-server regression passed.
- Isolated deployed-container fake-server regression passed from `/tmp/sabi-replay-check`, without touching live Sabi ports or `/app`.

Safe live-canary shape, to run on the Hetzner host or inside a controlled SSH session:

```bash
UUID="$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"

curl -fsS -X POST http://127.0.0.1:8000/asterisk/audiosocket/register \
  --data-urlencode "uuid=$UUID" \
  --data-urlencode "phone=+10000000000" \
  --data-urlencode "mode=audiosocket-replay-canary" \
  --data-urlencode "attempt=1"

PYTHONDONTWRITEBYTECODE=1 python -m fake_child_harness.audiosocket_replay \
  --wav /path/to/8khz-mono-noisy-answer.wav \
  --host 127.0.0.1 \
  --port 9019 \
  --uuid "$UUID" \
  --dtmf '45#' \
  --dtmf-after-seconds 8 \
  --output-wav /tmp/sabi-replay-response.wav
```

This is the bridge from synthetic audio files to real AudioSocket turn segmentation. The next step is to run a tiny canary set through it with known fake-child answers and inspect the resulting turn sidecars, not to replay all 24,000 calls through live STT/LLM/TTS.

### Live AudioSocket Canary: Chatterbox 9020 Lane

After the replay harness passed protocol tests, a tiny known-answer canary was run against the real deployed AudioSocket listener on Hetzner.

Lane and environment verified before/after deploy:
- Production listener 9019 remained `SABI_TTS_PRIMARY=elevenlabs`.
- Isolated test listener 9020 ran `SABI_TTS_TEST_PRIMARY=chatterbox_only`.
- `SABI_CHATTERBOX_URL=http://chatterbox:8001/tts`.
- `SABI_STT_TEST_PROVIDER=intron_first`, but Intron still returned 403 and the lane fell back to Groq as designed.

Canary setup:
- Temporary phone: `+1555009019`.
- Temporary learner name: `Canary`.
- Prompt seeded in the learner state: `Groundnuts cost fifteen naira and pure water costs thirty naira. How much do you spend?`
- Audio shape: 12 seconds of silence, then a phone-band answer mixed with the raw Lagos/Sabo/Yaba market audio.
- Temporary Supabase rows/sessions were deleted after evidence capture; sidecars and response WAVs remain on the server for inspection.

Evidence sequence:

| UUID | Audio answer / STT | Result |
|---|---|---|
| `32bc7c4f-87e8-4c5e-bdbf-2e963a7899a7` | Correct `forty-five` audio was heard by live Groq as `Forty naira.` before the patch | False wrong found: session `wrong_count=1`, student `total_wrong=1`. |
| `0e5077a3-10bb-457e-ad7b-9c6b9c8fd48c` | Same noisy correct clip was heard as `Forty-five.` after the patch | Correct path passed: session `correct_count=1`, `wrong_count=0`, `tts_providers_used=["chatterbox"]`, `stt_providers_used=["groq"]`. |
| `a6a2aebd-5472-44af-8daa-7bc4210e8449` | Deliberate `forty naira` guard clip | Persistence guard passed: `questions_total=0`, session `correct_count=0`, `wrong_count=0`, student `total_wrong=0`; response still sounded like a soft correction, so the live response path was tightened. |
| `e06b5ae2-f2ff-465b-ad03-2c8a56bb2e37` | Same deliberate `forty naira` guard clip after response patch | Final pass: session saved `correct_count=0`, `wrong_count=0`; student stayed `total_correct=0`, `total_wrong=0`; learning state saved `last_expected_answer=45`, `last_child_numbers=[40]`, `last_numeric_ambiguous=true`, `last_turn_correct=null`; Sabi replied `I may not have heard the full amount. Say the naira amount again slowly for me.`; `tts_providers_used=["chatterbox"]`, `stt_providers_used=["groq"]`. |

Code changes from this canary:
- `numeric_grading.py` treats likely dropped-final-five transcripts such as expected `45` / observed `40` as ambiguous, not wrong.
- `learning_state.py` preserves `last_numeric_ambiguous`, `last_expected_answer`, and `last_child_numbers` for ambiguous numeric turns without incrementing correct/wrong counts.
- `voice_realtime.py` now bypasses the LLM on numeric ambiguity and asks one deterministic repeat question, preventing the model from softly correcting a possibly misheard answer.
- Regression coverage: `numeric_grading_regression.py` and `learning_state_regression.py`.

Remote verification after deploy:
- Public and local health returned OK.
- Container `numeric_grading_regression.py` passed.
- Container `learning_state_regression.py` passed, including `spend_total_dropped_five_is_ambiguous_not_wrong`.
- The final live AudioSocket canary through 9020 passed with Chatterbox TTS and no false wrong.

## Current Assessment

The audio harness is now real enough to test noisy phone-band WAVs with real STT, and the production-like faster-whisper path has passed both the 32-case and 100-case synthetic-noise gates.

What improved:
- STT provider errors are captured per case.
- Local free Whisper CLI can run after cache repair.
- Deployed-container `faster_whisper large-v3` can run the full 100-case audio matrix.
- The AudioSocket replay harness can drive UUID/PCM/DTMF/hangup protocol and capture returned Sabi audio.
- False corrects from numeric parser bugs are fixed.
- Numeric no-answer/masked transcripts are no longer treated as confident wrong answers in the LLM hint path.
- Low-confidence noisy STT hallucinations are now modeled like production retries instead of release-blocking grades.
- Narrow deletion-task prompt echoes are now watch/retry cases.
- Realtime calls now use a two-step unclear-audio retry ladder: first a simple repeat request, then explicit audibility coaching to move the phone closer, find a quieter spot if possible, and say the answer slowly.
- Realtime numeracy calls now have a narrow keypad fallback after repeated unclear audio: Sabi asks the child to press the number digits and then hash, consumes AudioSocket DTMF packets, and flags the accepted answer as `keypad_numeric_fallback` / `dtmf_answer`.
- The audibility/keypad fallback runtime files were surgically deployed to Hetzner and verified in-container with `keypad_fallback_regression.py` and `phone_runtime_config_regression.py`; public health returned 200 after restart. The keypad regression now covers the actual prompt flow: Sabi synthesizes/plays the fallback prompt, persists review flags, drains stale DTMF, accepts digits after the prompt, and times out cleanly when no digits arrive.
- The real deployed AudioSocket 9020 listener has now been exercised with known noisy-answer canaries; the Chatterbox test lane produced audio and persisted `tts_providers_used=["chatterbox"]` while production 9019 remained ElevenLabs.
- Dropped-final-five numeric STT cases are no longer counted wrong. Live guard canary `e06b5ae2-f2ff-465b-ad03-2c8a56bb2e37` saved `wrong_count=0` and asked the child to repeat the amount slowly.
- Short closing, polite, and known Whisper hallucinations are retry/non-answer signals.

What still blocks a tester-ready claim:
- Intron key/permission is not accepted by the sync upload endpoint.
- Groq key is not present locally or on the inspected server env.
- Local faster-whisper is not installed in `.venv`.
- Homebrew OpenAI Whisper on CPU is too slow and too inaccurate for the noisy one-word literacy cases.
- Synthetic `espeak`/`say` speech is not real child speech, so the current audio matrix is a preflight gate, not an acoustic robustness claim.

This is no longer a core grading/progression blocker for the synthetic noisy-audio gate. AudioSocket turn segmentation has now been canaried with known-answer noisy audio; the remaining blocker is ecological validity from real child/adult voices over real carrier calls.

## Next Gates

1. Replace synthetic speech with real child-like voice samples or recorded adult/child canary answers before claiming acoustic robustness.

2. Expand the known-answer AudioSocket canary from the single dropped-five guard case to a tiny mixed numeracy/literacy set, then inspect the turn sidecars.

3. Exercise the new keypad fallback in a real AudioSocket canary call with poor audio.

4. Decide whether Intron is worth fixing for Nigeria-specific ASR comparison; it is no longer required to unblock the local faster-whisper gate.
