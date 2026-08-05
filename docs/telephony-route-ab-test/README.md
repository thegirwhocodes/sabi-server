# Sabi Nigerian Telephony Route A/B/C Test — Handoff Plan

**Status:** Ready for engineering setup and tester scheduling

**Decision owner:** Naomi / Education for Equality

**Test owner:** Assign one test coordinator

**Technical owner:** Assign one engineer who can configure Africa's Talking, Asterisk, Twilio, WebRTC, and the audio collector

**Analysis owner:** Assign one analyst who will not see the route key until results are locked

## 1. Decision this test must answer

For the same Nigerian caller using the same handset, SIM, room, and speaking style:

1. Does a call from Nigeria to the US Twilio route produce more accurately transcribed caller audio than the local Africa's Talking route?
2. How much of the failure is caused by the PSTN route, the STT model, turn segmentation, or environmental noise?
3. Does a browser/WebRTC recording provide a materially better reference than either telephone route?
4. Is any measured Twilio improvement large enough to justify international calling burden, cost, and migration risk?

This is a **route-acquisition test**, not a comparison of ElevenLabs against Google or Whisper. Every route must be evaluated with the same locked STT model and settings.

## 2. Routes

| Code | Route | Purpose |
|---|---|---|
| A | Nigerian caller → Africa's Talking Nigerian number → SIP → Asterisk → benchmark collector | Current local-phone baseline |
| B | Same Nigerian caller → US Twilio number → Twilio Media Streams/recording → same benchmark collector | Candidate international PSTN route |
| C | Same handset and SIM data → browser/WebRTC → same benchmark collector | Higher-bandwidth diagnostic reference; not a phone-line replacement |

Route B must capture Twilio's raw caller stream **before ElevenLabs, denoising, gain correction, or STT**. Sending Route B through ElevenLabs while Route A goes through Sabi would invalidate the route comparison.

Route C is optional for testers without a suitable smartphone/data connection. Never substitute another handset: compare A and B on the original handset and mark C unavailable.

## 3. Hypotheses and interpretation

| Result pattern | Most likely interpretation |
|---|---|
| A ≈ B and both are worse than C | Narrowband telephone acquisition is the main limitation; changing AT to Twilio will not solve it |
| Humans understand A/B but STT fails on both | STT/accent/domain mismatch is the main limitation |
| Continuous audio contains the word but the derived clip loses its beginning/end | VAD or endpointing is the main limitation |
| B clearly beats A with the same STT and human protocol | The AT/local carrier path is contributing measurable degradation |
| A clearly beats B | The international Twilio path is adding degradation |
| A/B/C all degrade in the noise block | Handset/environmental noise dominates |
| One route has high loss/jitter and matching recognition failures | Network transport is contributing; repeat before making a provider decision |

## 4. Non-negotiable validity rules

1. Use the same participant, handset, SIM, call mode, room, and approximate phone-to-mouth distance for all available routes.
2. Run all routes within one testing window where practical. Record any unavoidable change.
3. Use identical benchmark prompts, beep timing, endpointing, and capture logic on Routes A and B.
4. Save caller-only continuous audio and derived utterance clips. Do not use a mixed caller/Sabi recording for scoring.
5. Preserve each route's native inbound audio before enhancement or sample-rate conversion.
6. Run the same STT provider, model version, language, vocabulary/prompt, decoding settings, and segmentation policy on every route.
7. Do not place the expected phrase in an STT prompt or filename.
8. Lock STT outputs and blind human transcripts before revealing the route key.
9. Primary analysis uses the quiet-room block. Noise testing is a separate, labeled challenge block.
10. Start with adults. No child participates until the adult dry run is green and the required guardian consent and child assent are recorded.

## 5. Two complementary test layers

The study needs both layers. Repeated live speech is never acoustically identical, even when the person reads the same words.

### Layer 1 — controlled acoustic replay

Use a high-quality 48 kHz recording of a consented Nigerian adult reading the benchmark phrases. Play that exact recording through one fixed loudspeaker into one mounted test phone while the phone is connected through A, B, and C.

- Use one phone, one SIM, one room, and fixed phone/loudspeaker stands.
- Mark and photograph the phone and speaker positions; use approximately 20–30 cm separation.
- Lock playback volume and record it.
- Disable Wi-Fi, Bluetooth, and Wi-Fi Calling. Route C should use mobile data from the same SIM where supported.
- Establish at least three separate calls per route so results do not depend on one unusually good or bad call.
- Do not use an existing 8 kHz telephone recording as the source; that would apply telephone degradation twice.

This layer answers: **which route preserves identical acoustic input better?**

### Layer 2 — live-speaker crossover

The participant reads the assigned phrases over every route using their normal voice and normal handset position. This layer captures real speaking behavior, device handling, fatigue, carrier variability, and usability.

This layer answers: **which route works better for Sabi's actual callers?**

## 6. Recommended cohort and workload

### Stage 0 — technical dry run

- 2 Nigerian adults.
- 8 phrases, 2 repetitions, all available routes.
- Purpose: prove route capture, file mapping, timing, raw-audio preservation, and blind export.
- Do not proceed if any route uses different prompts/settings, files cannot be paired, or more than 1% of expected clips are missing.

### Stage 1 — adult route comparison

- Target: 12 Nigerian adult testers; minimum useful pilot: 8.
- Where possible, cover MTN, Airtel, Glo, and 9mobile, ideally at least 2 testers per represented carrier.
- Alternate Phrase Set A and Phrase Set B so each set has equal representation.
- Balance the six route orders: `ABC`, `ACB`, `BAC`, `BCA`, `CAB`, `CBA`. With 12 testers, use each order twice.
- Each tester reads 20 assigned phrases three times **on each route**. Repetitions occur in three shuffled rounds, not three times consecutively.
- Rotate routes between rounds so every route appears early, middle, and late. For an initial `ABC` assignment, use `ABC` in Round 1, `BCA` in Round 2, and `CAB` in Round 3. Apply the same rotation rule to the other five initial orders.
- Expected load: 120 utterances for A+B; 180 with optional C. Allow approximately 30–45 minutes including connection time and breaks. Stop or split the session if fatigue changes speaking behavior.
- Twelve adults form a pilot capable of detecting a large route defect. If the difference is small or uncertainty remains, use the pilot's observed variability to recruit a 24–36-person confirmation; do not call an underpowered result “equivalent.”

### Stage 1B — controlled noise challenge

- Run only after the quiet block succeeds.
- Use the rows marked `noise_subset=yes` in `phrase-bank.csv`.
- Play the same approved Lagos/market reference audio from the same second device, at the same volume and marked distance, for every route.
- Record measured dBA if available. If it cannot be standardized, label the block exploratory and do not use it to choose the route.
- One repetition per phrase per route is enough for this challenge block.

### Stage 2 — child canary

- Only after the adult analysis pipeline is locked and the adult test reveals a decision-relevant difference.
- Start with 2 children, review within 24 hours, then expand to no more than 6 for this confirmation.
- Guardian Consent A, separate Consent B for retaining improvement/test recordings, and child assent are all required before recording.
- Use 12 neutral phrases from the same bank, three repetitions on A and B. Add C only if it does not create fatigue.
  - Child Set A: `A01,A02,A05,A06,A07,A09,A11,A12,A13,A15,A17,A18`
  - Child Set B: `B01,B02,B05,B06,B07,B09,B11,B12,B13,B15,B17,B18`
- Stop immediately if a child is uncomfortable, tired, or asks to stop. No result is worth overriding assent.
- This canary validates ecological fit and catches a large child-specific failure; six children are not enough to prove two routes equivalent.

### Stage 3 — child confirmatory test, if needed

- Run only if a route migration is still being considered after adult testing and the decision needs a child-specific claim.
- Use Stage 2 variability to size the cohort; plan for at least 12 consented children and increase if the expected route difference is small.
- Analyze children separately from adults. Never allow the much larger utterance count to disguise a small number of participating children.

## 7. Phrase and route assignment

The master phrase bank is `phrase-bank.csv`.

- Odd participant IDs receive Set A; even participant IDs receive Set B.
- The participant uses the same set on every route.
- Create three rounds. Each round contains one independently shuffled 20-phrase block on every available route.
- Save the random seed and presented sequence.
- Do not let the participant repeat an item after hearing how STT interpreted it.
- If the participant makes a genuine reading error, retain the audio, mark `speaker_deviation=yes`, and exclude it from reference-text accuracy while keeping it for audibility analysis.

Example route-order allocation:

| Participant | Phrase set | Route order |
|---|---|---|
| T001 | A | ABC |
| T002 | B | ACB |
| T003 | A | BAC |
| T004 | B | BCA |
| T005 | A | CAB |
| T006 | B | CBA |
| T007–T012 | Alternate A/B | Repeat the six orders once |

If C is unavailable, collapse the assignment to balanced `AB` and `BA` orders.

## 8. Engineering handoff

### 8.1 One benchmark application

All routes must terminate in the same benchmark application. The application should:

1. Play an identical instruction and ready tone.
2. Present or announce only a neutral sequence number, not the target phrase.
3. Record caller-only continuous audio from before the tone until after the final utterance.
4. Produce per-utterance clips while preserving offsets back to the continuous recording.
5. Use identical pre-roll, end-of-speech threshold, hangover/post-roll, maximum duration, and silence timeout for A and B.
6. Record monotonic timestamps for tone end, speech start, speech end, segment finalization, STT submission, and STT result.
7. Permit `#` or a coordinator control to mark an utterance complete without changing the saved raw audio.

### 8.2 Native evidence to retain

For every route call, retain:

- caller-only continuous native stream or the closest lossless representation available;
- decoded PCM WAV used for inspection;
- derived utterance WAVs;
- native codec, sample rate, channels, and capture source;
- call/session ID and timestamps;
- segmentation offsets and settings;
- packet loss, jitter, RTT, and disconnect reason where available;
- route/provider cost and caller reimbursement cost.

Suggested route-specific evidence:

- **A:** Asterisk caller RX WAV, RTP/RTCP summary, negotiated codec, and optional short-lived packet capture for the dry run only.
- **B:** original Twilio μ-law media payload or recording plus decoded caller-only WAV and Twilio Voice Insights metrics.
- **C:** server-received Opus/WebRTC audio, decoded WAV, `getStats()` summary, browser/device version, and media constraints such as echo cancellation/noise suppression/automatic gain control.

For Route C, request echo cancellation, noise suppression, and automatic gain control off for the controlled replay where the browser permits it, and save the actual `getSettings()` response. Also create an offline G.711/8 kHz simulation from the native WebRTC recording. Comparing native C against simulated C estimates bandwidth/codec loss; comparing simulated C against A/B estimates additional handset/carrier/telephone-path loss.

Do not normalize volume, remove silence, denoise, dereverberate, or apply EQ to the primary evidence. Enhanced derivatives may be tested later and must have separate filenames.

### 8.3 Locked STT replay

After all audio is captured:

1. Hash and record the STT configuration.
2. Randomize filenames into blind sample IDs.
3. Run every native/decoded sample through the same STT model and settings.
4. If the model requires resampling, use the same deterministic resampler configuration while preserving native files. Do not downsample Route C to 8 kHz merely to imitate PSTN.
5. Save raw transcript, normalized transcript, confidence/metadata, and processing latency.
6. Do not use conversation history, route identity, expected answer, or category-specific prompts in the primary run.
7. Optional phrase-bias or constrained-decoding runs happen only after the unbiased primary outputs are locked, and must apply identically to every route.

### 8.4 Blinding and identifiers

- Public analysis files use only a random `blind_sample_id`.
- `route-key-template.csv` is restricted to the data manager until analysis is locked.
- The analyst and human listeners do not see route, participant name, phone number, target phrase, or expected transcript.
- Store the participant contact list separately from research/test data.
- Never put a phone number in an audio filename.

Recommended recording layout:

```text
route-test-run-YYYYMMDD/
  restricted/
    route-key.csv
    contact-consent-register.csv
  raw/
    continuous/
    native-utterances/
  derived/
    decoded-wav/
    stt-input/
  blind-export/
    audio/
    sample-manifest.csv
  results/
    stt-locked.csv
    human-locked.csv
    route-scorecard.csv
```

## 9. Tester instructions

The coordinator reads these instructions before each participant begins:

> We are comparing ways a phone system receives speech. This is not a test of your reading, intelligence, accent, or English. Use your normal voice. Hold the phone the way you normally would and keep the same phone, SIM, room, and call mode for every call. After each tone, read the phrase shown once. Do not deliberately slow down, exaggerate, or change your accent. If you misread the card, tell me; we will mark it and continue. You can pause or stop at any time.

The participant must not be told which commercial route is active or which one is expected to perform better. Refer to them only as Route 1, Route 2, and Route 3.

## 10. Human listening control

Use at least two independent listeners familiar with Nigerian English. They receive only randomized clips.

For each clip, each listener must:

1. Transcribe only what they actually hear; no guessing from a phrase list.
2. Mark `unintelligible` for any unheard portion.
3. Rate audibility from 0–3:
   - 0: no usable speech;
   - 1: fragments only;
   - 2: understandable with uncertainty;
   - 3: clearly understandable.
4. Mark likely initial clipping, final clipping, dropout, distortion, competing speech, and low level.

Resolve listener disagreement only after both independent transcripts are locked. Human accuracy separates an acoustically damaged sample from a model-specific STT failure.

## 11. Metrics

### Primary

- normalized exact-match accuracy, paired by participant + phrase + repeat;
- semantic correctness for names, numbers, Naira amounts, and short literacy words;
- critical-field error rate for names/numbers;
- human exact-match and audibility;
- initial/final clipping rate.

Freeze normalization before unblinding:

- Unicode-normalize, lowercase, trim, and collapse whitespace.
- Remove punctuation that does not change meaning.
- Expand only a fixed contraction list, such as `don't` → `do not`.
- Canonicalize number words and digits to the same representation for the semantic-number metric.
- Score names and literacy words exactly after case/punctuation normalization; never silently “correct” a name or homophone.
- Report both lexical exact match and semantic critical-field accuracy. A transcript can be semantically correct for `30` while not being a verbatim sentence match.

### Secondary

- word error rate and character error rate;
- no-speech, hallucination, substitution, deletion, and insertion rates;
- segment-finalization latency: true speech end → utterance finalized;
- STT latency: submission → result;
- total end-of-speech → transcript latency;
- packet loss, jitter, RTT, disconnects, and missing-audio rate;
- RMS/peak level, clipping percentage, duration, voiced fraction, and estimated noise floor;
- platform cost, caller cost/reimbursement, cost per valid utterance, and projected cost per 10-minute lesson.

Do not treat every utterance as an independent participant. Use either mixed-effects models with participant and phrase as random effects, or a two-way cluster bootstrap over participants and phrases. Report paired route differences and 95% intervals.

## 12. Decision rules

Keep Africa's Talking unless Route B produces a practically meaningful, reproducible advantage. A Twilio route winner must satisfy all of the following:

1. At least **10 percentage points higher normalized exact-match accuracy** in the confirmatory result.
2. The lower bound of the paired 95% interval is at least **5 percentage points above zero**.
3. No critical name/number category declines by more than 2 percentage points.
4. Initial/final clipping does not worsen by more than 1 percentage point.
5. P95 end-of-speech-to-transcript latency is no more than 300 ms worse.
6. No new call-completion, evidence-loss, privacy, or safety failure.
7. The benefit remains large enough after accounting for international caller cost, reimbursement, access friction, and operating cost.

For eventual production promotion, bounded number/Naira semantic accuracy should also meet the existing Sabi controlled-gold standard of at least 98%.

Treat A and B as practically equivalent only if the entire 95% interval for their difference lies inside ±5 percentage points. If the interval includes both meaningful benefit and meaningful harm, the result is inconclusive—not evidence of equivalence.

If results are statistically or operationally inconclusive, the decision is **no migration** and the next experiment should focus on STT, endpointing, or WebRTC—not a provider swap.

## 13. Invalidation and pause conditions

Pause and repair the test if:

- a route uses a different STT model, expected-answer prompt, VAD, or target phrase presentation;
- more than 1% of expected raw recordings or route mappings are missing;
- caller and system audio are mixed and caller-only audio cannot be recovered;
- route identity or ground truth is exposed before transcription locks;
- the tester changes handset/SIM/call mode without the change being recorded;
- packet loss/jitter indicates a temporary carrier incident affecting only one test window;
- a child lacks all required consent/assent or asks to stop;
- raw child audio would be stored outside the consented, encrypted test corpus.

## 14. Required deliverables before the decision meeting

- completed `tester-session-log-template.csv`;
- completed `participant-assignment-template.csv`;
- completed blind `sample-manifest-template.csv`;
- locked STT output file and configuration hash;
- two locked human-listener files;
- restricted route key;
- completed `route-scorecard-template.csv`;
- per-category confusion/error table;
- latency, network-quality, and cost table;
- list of exclusions with reasons;
- 10–20 representative blind clips, including disagreements and clipping examples;
- one-page recommendation: keep AT, move to Twilio, or neither route solves the problem.

## 15. Existing Sabi gates this test must respect

- `docs/intron-test-route.md` describes the isolated STT route and replay expectations.
- `docs/FAKE_CHILD_AUDIO_MATRIX_RESULTS_2026-07-06.md` documents the synthetic/noise preflight and why real caller evidence is still needed.
- The canonical pilot privacy policy requires separate guardian consent before retaining child recordings for product improvement.
- This experiment does not change production routing. Any later migration still requires isolated-route, adult-canary, child-canary, promotion, and rollback gates.
