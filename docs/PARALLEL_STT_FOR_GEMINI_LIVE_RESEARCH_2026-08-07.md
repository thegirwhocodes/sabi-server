# Parallel STT for Sabi Gemini Live

Date: 7 August 2026  
Scope: Nigerian PSTN numeracy calls; Groq Whisper plus a local recognizer; free and self-hosted alternatives

## Decision

Keep Gemini Live responsible for the continuous conversation, voice activity detection, barge-in, and turn boundaries. For numeric-answer turns only, send the same learner speech segment concurrently to Groq `whisper-large-v3` and a warmed local recognizer. Grade automatically only when both engines extract the same single numeric value. If they disagree, time out, or produce multiple values, ask the learner to repeat just the number; do not mark the answer wrong.

Roll this out first in shadow mode on Naomi's caller ID. Store every engine's literal transcript, extracted number, timing, and audio hash without changing the conversation. Switch the consensus result into grading only after the accepted-answer precision on labeled Nigerian PSTN clips is at least 98%.

This preserves what now works well in Gemini Live—continuous context and interruption—while making consequential correctness decisions independently auditable.

## What Sabi already has

The turn-based route already contains a `parallel_consensus` engine in `stt.py`. Its regression verifies that Groq Whisper and local faster-whisper start concurrently, numeric-value agreement ignores object nouns, both transcripts remain auditable, slow local inference is bounded, and unresolved disagreement fails closed.

The Gemini Live route does not use that engine. It streams 8 kHz PCM directly to Gemini and does not import `SpeechToText`. Therefore today's Twilio/Gemini calls do **not** run Groq and local Whisper side by side.

The existing consensus scaffold needs five changes before it should affect Gemini Live grading:

1. Attach it as a sidecar to Gemini's turn boundary; do not let it control VAD or barge-in.
2. Remove the question and answer operands from numeric STT prompts, because they can bias recognition.
3. Replace fixed `0.82` and `0.95` confidence labels with real metadata and a calibrated acceptance model.
4. Reduce the five-second deadline to approximately 1.2–1.5 seconds.
5. During the first rollout, do not let a separate Gemini transcription break a Groq/local disagreement; disagreement should abstain and request a repeat.

## Proposed audio and concurrency path

```text
Asterisk AudioSocket signed-linear PCM, 8 kHz mono
              |
              +--> Gemini Live continuous stream
              |      owns VAD, turn-taking, context and barge-in
              |
              +--> per-call ring buffer tagged by call UUID and turn ID
                         |
                  numeric grade tool call
                         |
                latest complete speech segment
                 with 160-200 ms edge padding
                         |
                resample once to 16 kHz mono
                    +----+----+
                    |         |
              Groq Whisper  local recognizer
                    |         |
                    +----+----+
                         |
              single-value numeric normalizer
                         |
              exact value agreement or abstain
                         |
               deterministic answer grader
```

Asterisk AudioSocket normally supplies signed-linear 16-bit 8 kHz mono PCM. Upsampling to 16 kHz satisfies Whisper input expectations, but it cannot recreate acoustic frequencies already removed by the telephone path. The two recognizers must receive the exact same padded and resampled bytes. [Asterisk AudioSocket application](https://docs.asterisk.org/Latest_API/API_Documentation/Dialplan_Applications/AudioSocket/), [AudioSocket protocol](https://docs.asterisk.org/Configuration/Channel-Drivers/AudioSocket/)

For shadow mode, copy the learner PCM at Gemini Live turn finalization and transcribe it asynchronously. For live grading, snapshot the current completed speech segment when `grade_numeric_answer` is called. Attach `call_uuid`, monotonically increasing `turn_id`, and an audio hash to every job, and discard results that arrive for a turn that is no longer current.

Use a persistent Groq client so TLS connections are reused. Warm the local model once during service startup. Put local inference behind a bounded worker queue and semaphore. Late results may still be logged, but they must never be applied to the next turn.

The current global executor has only three threads and a local-inference lock. That lock makes model access safe but serializes local STT across learners. At production concurrency, run local STT as a dedicated service or worker with an explicit queue timeout and GPU/latency monitoring.

## Turn and latency policy

- Gemini Live remains the endpoint detector.
- Soft target: consensus available within 800 ms after Gemini's speech endpoint.
- Hard deadline: 1.2–1.5 seconds.
- Groq 429/provider failure: abstain or use a separately validated one-engine fallback; do not sleep and retry while the child waits.
- Local queue timeout: fail quickly and log capacity pressure.
- Any late job whose `turn_id` is stale is audit-only.
- Do not start a separate Gemini transcription request; the persistent Gemini session already heard the turn.

The child-facing abstention should be neutral: “I didn't catch the number clearly. Say just the number again.” Recognition disagreement is not academic incorrectness.

## Numeric agreement

Apply consensus only to curriculum items whose answer contract explicitly expects a number.

1. Normalize complete values such as “twenty four” and “one hundred and two.”
2. Accept a candidate only when an engine returns one distinct numeric value.
3. `two`, `two mangoes`, `two fries`, and `two apples` are the same answer unless the item is explicitly testing units.
4. Multiple values—“is it twenty or thirty?”—are ambiguous and not scorable.
5. Teen/tens conflicts such as 13/30, 14/40, 15/50, and 16/60 require repetition.
6. Do not infer a number from silence, coughs, clicks, or object nouns.
7. Keep the expected answer and problem operands outside both recognizer prompts.
8. Use a fixed generic optional prompt only if bake-off data shows that it helps: “A Nigerian learner is saying a short answer. Transcribe literally.”
9. For self-corrections such as “I thought three, but it is two,” abstain until a final-answer rule has been validated on real calls.

Exact text agreement is unnecessary: `two mangoes` and `two fries` agree numerically. For nonnumeric conversation, semantic agreement is too subjective for grading. Literacy phonemes and isolated letter sounds need a separate protocol.

## Confidence and calibration

Current Sabi values—`0.82` for a nonempty Groq transcript and at least `0.95` for agreement—are labels, not probabilities.

Groq `verbose_json` now exposes segment `avg_logprob`, `no_speech_prob`, `compression_ratio`, and timestamps. Local faster-whisper exposes segment log probability, no-speech probability, compression ratio, word timestamps/probabilities, and Silero VAD information. [Groq STT documentation](https://console.groq.com/docs/speech-to-text), [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

Calibrate the probability that the **numeric value** is correct—not generic WER—on held-out speakers and phones. Candidate features:

- whether both engines found the same single value;
- minimum and mean log probability;
- maximum no-speech probability;
- number-token word probability;
- speech duration and VAD score;
- clipping and approximate SNR;
- transcript length and number count;
- teen/tens risk;
- timeout/provider failure;
- carrier and codec, when available.

Use logistic or isotonic calibration and select a threshold for at least 98% precision among automatically accepted values. High abstention is acceptable during the canary. Report calibration by speaker, handset, noise condition, and carrier.

Groq and local Whisper large-v3 share the same architecture and weights, so their errors are correlated. Different runtimes, decoding, quantization, and preprocessing provide some diversity, but agreement is evidence rather than certainty. A later second vote from a Parakeet/SBPN-family model would be more independent.

## Groq Whisper: current economics and limits

Groq documents file/URL transcription endpoints rather than a supported streaming STT WebSocket. Use per-turn batch transcription after Gemini closes the learner utterance. [Groq STT](https://console.groq.com/docs/speech-to-text)

| Model | Price per audio hour | Vendor speed factor | Vendor WER | Sabi use |
|---|---:|---:|---:|---|
| `whisper-large-v3` | $0.111 | 189x | 10.3% | Accuracy-first grading vote |
| `whisper-large-v3-turbo` | $0.04 | 216x | 12% | Later cost/latency bake-off |

These are general vendor figures, not Nigerian children over PSTN. Groq recommends large-v3 for error-sensitive multilingual use.

Other current details:

- minimum accepted clip: 0.01 seconds;
- minimum billed clip: 10 seconds;
- free-tier upload maximum: 25 MB; developer tier: 100 MB;
- Groq internally downsamples to 16 kHz mono;
- WAV is preferred for lower latency and FLAC for smaller lossless transfer;
- prompt limit: 224 tokens;
- word and segment timestamps are supported.

At the ten-second billing minimum, large-v3 costs about $0.000308 per learner turn and turbo about $0.000111. Twenty numeric turns cost about $0.00617 on large-v3 or $0.00222 on turbo; thirty cost about $0.00925 or $0.00333.

The published organization-wide free limits are 20 requests/minute, 2,000 requests/day, 7,200 audio seconds/hour, and 28,800 audio seconds/day. Request count limits roughly 20-turn lessons to 100/day on the base free plan. Confirm the actual account limits in the Groq console and response headers. [Groq rate limits](https://console.groq.com/docs/rate-limits), [Groq pricing](https://groq.com/pricing)

Groq says inputs/outputs are not retained by default, although temporary reliability/abuse logging can last up to 30 days. Zero Data Retention is available; usage metadata excluding content remains. Groq says it does not train on inputs or outputs without permission. For children, enable ZDR, use pseudonymous IDs, minimize raw audio, encrypt stored clips, document consent, and set a deletion period. [Groq data controls](https://console.groq.com/docs/your-data)

## Local faster-whisper and hardware

`faster-whisper` is the easiest local companion because it is already in Sabi. It supports FP16/INT8, word timestamps, and Silero VAD. Maintainer reference benchmarks report up to four times OpenAI Whisper's speed at comparable accuracy, but these are not two-second PSTN latency measurements. [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

Reference results for 13 minutes of audio include:

| Hardware / mode | Time | Memory |
|---|---:|---:|
| RTX 3070 Ti, large-v2 FP16 | 63 s | 4,525 MB VRAM |
| RTX 3070 Ti, batch 8 | 17 s | 6,090 MB VRAM |
| RTX 3070 Ti, INT8 | 59 s | 2,926 MB VRAM |
| Intel i7-12700K, small FP32 | 157 s | 2,257 MB RAM |
| Intel i7-12700K, small INT8 | 102 s | 1,477 MB RAM |
| Intel i7-12700K, batched INT8 | 51 s | 3,608 MB RAM |

Sabi's current compose configuration forces local Whisper onto CPU; the live container logs confirm that no NVIDIA driver is exposed. This is the largest infrastructure obstacle to a 1.5-second hard deadline. Prefer a dedicated local-STT container with GPU access.

The planned Hetzner GEX44—RTX 4000 SFF Ada with 20 GB GDDR6 ECC, i5-13500, 64 GB RAM, and dual 1.92 TB NVMe—should be sufficient for a warmed Whisper-class recognizer, subject to actual GPU sharing. [Hetzner GEX44](https://www.hetzner.com/dedicated-rootserver/gex44/)

Start with local large-v3 FP16 for quality, then benchmark turbo, medium, and INT8 on the Sabi gold set. Do not put CPU large-v3 synchronously behind a 1.5-second deadline until its p95 is measured.

## Free and self-hosted alternatives

| Candidate | Why it matters | Constraint / decision |
|---|---|---|
| Azure Speech `en-NG` | Explicit Nigerian English locale; realtime and fast transcription; Custom Speech adaptation | Best independent cloud comparator. F0: 5 audio hours/month shared across standard/custom realtime, one hosted custom model; no free batch. [Languages](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support), [pricing](https://azure.microsoft.com/en-us/pricing/details/speech/) |
| SBPN Base/Large | Nigerian English, Pidgin, Yoruba, Hausa, Igbo; 120M/600M Parakeet/NeMo family; model diversity | Reported 29% average relative WER reduction; no trusted PSTN-child result. CC BY-NC-SA research/noncommercial license requires clearance. [Model](https://huggingface.co/ogunlao/SBPN_multilingual_base), [paper](https://arxiv.org/abs/2605.17710) |
| NaijaVox 2.0 | Whisper large-v3 LoRA for Nigerian English and major Nigerian languages | Card reports 19.6% Nigerian-English WER and 14.7% Pidgin on only 50 samples/language. Whisper-family and custom restrictions require review. [Model](https://huggingface.co/Axiveri/NaijaVox-2.0) |
| NVIDIA Parakeet Unified | 600M FastConformer RNN-T, offline/streaming, 160–2,080 ms latency; independent family | Mostly US-English training; valuable diversity experiment, not validated for Nigerian calls. [Model](https://huggingface.co/nvidia/parakeet-unified-en-0.6b) |
| NVIDIA Nemotron 3.5 streaming | 600M cache-aware FastConformer, 80–1,120 ms chunks, commercial terms | Forty locales exclude Nigerian English and major Nigerian languages. [Model](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) |
| Meta Omnilingual ASR | Apache 2.0, 1,600+ languages, 300M–7B models | Attractive for future multilingual lessons; no Nigerian narrowband-numeracy validation. [Repository](https://github.com/facebookresearch/omnilingual-asr) |
| Meta MMS | 1,100+ languages with adapters; wav2vec2/CTC diversity | CC BY-NC; more relevant to Hausa/Igbo/Yoruba than Nigerian English. [Model](https://huggingface.co/facebook/mms-1b-all) |
| Moonshine v2 | True streaming ONNX, 34M–245M English models, cached state, MIT English models | No Nigerian/PSTN result; strong low-latency experiment, not initial grading authority. [Repository](https://github.com/moonshine-ai/moonshine) |
| Vosk | Apache 2.0, offline streaming, ~50 MB models, dynamic grammar, Asterisk-friendly server | No Nigerian model; official English example degrades to 29.78% WER on call-center audio. A number grammar may be useful as a tertiary signal. [API](https://github.com/alphacep/vosk-api), [models](https://alphacephei.com/vosk/models) |
| whisper.cpp | C/C++, quantization, CPU/GPU, Silero VAD | Easier deployment alternative, not an independent vote. Its sample streaming method is explicitly naive. [Repository](https://github.com/ggml-org/whisper.cpp) |
| sherpa-onnx | Apache 2.0 runtime for Whisper, Moonshine, Parakeet, Zipformer, VAD and WebSockets | Useful service boundary, not itself a Nigerian-trained recognizer. [Repository](https://github.com/k2-fsa/sherpa-onnx) |
| XLS-R / SpeechBrain | Fine-tuning building blocks for a consented Sabi corpus | Public XLSR-53 checkpoint is pretraining-only; prior Pidgin results around 30% WER are not grading quality. [XLSR-53](https://huggingface.co/facebook/wav2vec2-large-xlsr-53) |

Other cloud allowances: Google V1 offers 60 minutes/month free; V2 begins at $0.016/minute and does not list `en-NG`, although Chirp covers Hausa, Igbo, and Yoruba. AWS offers 60 minutes/month for the first 12 months and lacks Nigerian English; Hausa is batch-only. Azure `en-NG` is the most relevant current cloud alternative. [Google pricing](https://cloud.google.com/speech-to-text/pricing), [Google languages](https://cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages), [AWS pricing](https://aws.amazon.com/transcribe/pricing/), [AWS languages](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html)

## Evaluation and rollout

### Phase 1: Naomi-only shadow mode

For each numeric answer, store call UUID, turn ID, audio hash, speech boundaries, Gemini transcript, both sidecar transcripts and metadata, extracted candidates, agreement outcome, per-engine latency, model/config/prompt versions, and the hypothetical accept/abstain result. Do not alter Gemini's reply.

### Phase 2: labeled Nigerian PSTN bake-off

Build the gold set from audio after it passes through Twilio/Asterisk. Include numbers 0–100; teen/tens pairs; number-plus-random-object answers; Nigerian English, Pidgin and code-switching; soft child voices; inexpensive handsets; fans, market noise, television and background adults; silence/coughs/clicks; clipped first phonemes; barge-in and echo; and self-corrections such as “I thought X, but the answer is Y.” Double-label clips where possible.

Primary measures:

- numeric-value accuracy;
- agreement coverage and wrong-agreement rate;
- precision among accepted values;
- abstention/repeat and false non-speech acceptance rates;
- endpoint-to-consensus p50/p95/p99;
- 429/provider/capacity failures;
- performance by age, accent, handset, noise, carrier and codec.

Generic WER is secondary: a poor-looking transcript can still recover the correct number, while one wrong digit can make a low-WER transcript academically wrong.

### Phase 3: gated grading

```text
same single external numeric value
AND calibrated probability above threshold
AND current turn ID/audio hash still valid
    -> deterministic grade
otherwise
    -> neutral number-only repeat
```

### Phase 4: genuine model diversity

Benchmark Azure `en-NG`, SBPN, NaijaVox 2.0, and Parakeet on the same gold clips. If licensing is acceptable and one outperforms generic local Whisper, replace the local large-v3 vote. Groq Whisper plus a Parakeet/SBPN-family local vote is more independent than two large-v3 deployments.

## Immediate engineering sequence

1. Add a Naomi-only Gemini Live shadow sidecar at turn finalization.
2. Resample one canonical segment and reuse it for both engines.
3. Remove question-dependent prompts and fabricated confidence.
4. Record real Groq/faster-whisper metadata.
5. Add strict turn IDs, audio hashes, 1.5-second deadline, and late-result rejection.
6. Run the labeled PSTN bake-off.
7. Enable exact numeric consensus for grading only after the precision gate passes.
8. Separately benchmark Azure `en-NG` and an independent local family.

