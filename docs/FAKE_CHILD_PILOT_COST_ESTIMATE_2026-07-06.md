# Sabi 100 Fake-Child Full-Pilot Cost Estimate

Date: 2026-07-06

Purpose: first direct-spend estimate for Naomi's requested fake-child performance pilot: 100 simulated children, noisy Lagos/market audio, full 5-7 minute lesson-call shape, TaRL progression, failure analysis, then iterative Sabi fixes.

## Bottom Line

Do not spend real telephony or paid ElevenLabs money for the main fake-child harness. Run the full battery as a phone-call simulator with phone codec, noisy Lagos audio, real STT where needed, real learning-state/assessment logic, and self-hosted or YarnGPT TTS fixtures.

Recommended budget for the first full 100-child, 240-call fake pilot:

| Mode | Direct spend |
|---|---:|
| Deterministic text/progression rehearsal | $0 marginal |
| Full-course provider-backed QA, no real telephony, Groq Whisper Large + buffered Claude + self-hosted/YarnGPT TTS | $462-$551 |
| Same, reserving one Hetzner month for sustained runs | $665-$754 |
| Production-like phone minutes added with AT flash callback assumption | $719-$911 |
| Paid ElevenLabs Flash TTS across all fake calls, no phone minutes | $2,262-$6,551 |

My recommendation: budget about **$750** for the real provider-backed fake pilot, and keep a **$1,000 cap**. Only spend more if a specific failure category requires paid ElevenLabs or real carrier behavior. A full paid-ElevenLabs fake pilot is the wrong shape for this test.

## Scale Assumption

Existing Sabi planning docs define the full course as 240 calls per child. For 100 fake children:

| Quantity | Low | Expected | High |
|---|---:|---:|---:|
| Calls | 24,000 | 24,000 | 24,000 |
| Minutes per call | 5 | 6 | 7 |
| Total call minutes | 120,000 | 144,000 | 168,000 |
| Total audio hours | 2,000 | 2,400 | 2,800 |
| AI turns, at about 7 turns/call | 168,000 | 168,000 | 168,000 |
| TTS characters, if paid TTS is used | 36M | 60M | 120M |

The 100-call lesson rehearsal currently averages only about 519 assistant characters per call because it is a compact deterministic rehearsal, not full LLM output. For paid TTS budgeting I padded that to 1,500/2,500/5,000 chars per call.

## Cost Components

### STT

Official Groq pricing on 2026-07-06 lists Whisper Large v3 Turbo at $0.04 per hour transcribed and Whisper V3 Large at $0.111 per hour. ElevenLabs API pricing lists Scribe at $0.22/hr and Scribe realtime at $0.39/hr.

| STT option | Low | Expected | High |
|---|---:|---:|---:|
| Groq Whisper Turbo | $80 | $96 | $112 |
| Groq Whisper Large | $222 | $266 | $311 |
| ElevenLabs Scribe | $440 | $528 | $616 |
| ElevenLabs realtime STT | $780 | $936 | $1,092 |

Use Groq Large for the serious STT pass, because the point is to catch Sabi failures, not save $170 and miss audio problems.

### LLM

The old Sabi docs used about $0.0045/call for Claude Haiku style calls. I use a buffered $0.01/call for this estimate because provider pricing changes and full lesson-call transcripts are longer than the compact rehearsal.

| LLM option | Cost |
|---|---:|
| Lean Claude estimate, $0.0045/call | $108 |
| Buffered Claude estimate, $0.01/call | $240 |

### TTS

This is the dangerous line item. Official ElevenLabs API pricing lists Text to Speech at $0.05 per 1,000 chars for Flash/Turbo and $0.10 per 1,000 chars for Multilingual v2/v3. Africa's Talking voice docs list Google Standard TTS at $0.000008 per character.

| TTS option | Low | Expected | High |
|---|---:|---:|---:|
| Self-hosted/YarnGPT/pre-generated fixtures | $0 | $0 | $0 |
| Africa's Talking Google Standard TTS | $288 | $480 | $960 |
| ElevenLabs Flash/Turbo | $1,800 | $3,000 | $6,000 |
| ElevenLabs Multilingual | $3,600 | $6,000 | $12,000 |

Use self-hosted/YarnGPT/pre-generated fixtures for the full fake pilot. Use paid ElevenLabs only on a small sampled subset if voice quality itself is being tested.

### Telephony

The fake pilot should not use real telephony for all 24,000 calls. A phone-call harness can simulate codec, 8 kHz bandpass, noise, turn timing, carrier audio, hangups, and AudioSocket-like flow without paying carriers.

If we intentionally replay through real phone minutes:

| Phone option | Low | Expected | High |
|---|---:|---:|---:|
| No real telephony | $0 | $0 | $0 |
| AT flash callback at NGN 3/min, USD/NGN 1400 | $257 | $309 | $360 |
| Toll-free minutes at NGN 14/min, USD/NGN 1400 | $1,200 | $1,440 | $1,680 |

Important caveat: earlier Sabi docs repeatedly flag Africa's Talking Nigeria voice rate ambiguity. Treat the NGN 3/min line as an internal planning assumption until AT confirms it in writing.

## Scenario Totals

| Scenario | Low | Expected | High | Use? |
|---|---:|---:|---:|---|
| Offline deterministic full-course fixture | $0 | $0 | $0 | Yes, first pass |
| Provider-backed fake pilot: Groq Large + Claude buffer + self-hosted/YarnGPT TTS, no phone minutes | $462 | $506 | $551 | Yes, main paid QA |
| Same plus one reserved Hetzner month | $665 | $709 | $754 | Yes, if running sustained jobs on server |
| Same plus AT callback minutes | $719 | $815 | $911 | Only for carrier-specific canary |
| Groq Large + Claude buffer + ElevenLabs Flash, no phone minutes | $2,262 | $3,506 | $6,551 | No, except sampled subset |
| Groq Large + Claude buffer + ElevenLabs Multilingual, no phone minutes | $4,062 | $6,506 | $12,551 | No |

## Raw Lagos/Market Audio

Already usable locally:

- `outputs/fake-child-harness/assets/audio/freesound-411123-sabo-yaba-16k.wav`
- `outputs/fake-child-harness/assets/audio/freesound-411123-sabo-yaba-hq.mp3`
- `outputs/fake-child-harness/audio-runs/audiofake-20260706T073333Z/mixed_audio/*.wav`

Candidate sources:

| Source | Fit | License/use note |
|---|---|---|
| Pixabay: Ambient SaboYaba BusStop Lagos Nigeria | Real Lagos bus stop/crowd/traffic field audio | Free under Pixabay Content License |
| Freesound 411123 via Pixabay artist `jehoshaphatia` | Same Sabo/Yaba field recording lineage | Local harness already has a converted 16 kHz WAV |
| ZapSplat: African village market, busy, many people | Market crowd bed, not Lagos-specific | Page shows CC0 1.0 |
| Epidemic Sound Nigeria market/crowd tracks | Useful professional paid reference | Paid license, not needed for first harness |
| YouTube Yaba/Computer Village ambient videos | Good for discovery/listening | Do not use in harness unless separately licensed |

## Current Harness Status

Verified on 2026-07-06:

| Harness | Command | Result |
|---|---|---|
| Text diagnostic fixture | `python -m fake_child_harness.runner --children 100 --calls-per-child 1 --max-turns 7` | Passed, 675 turns, 0 release blockers |
| Numeracy progression probe | `python -m fake_child_harness.progression_runner --children 100 --calls-per-child 10` | Passed, 5,282 turns, 91 children advanced, 1 possible under-advance |
| Lesson rehearsal | `python -m fake_child_harness.lesson_rehearsal_runner --children 100 --calls-per-child 1` | Passed after fixing profile/state bug and run-ID collision, 100 calls, 94% in 5-7 minute window, 0 release blockers |

The current harness is not yet the complete objective. It still needs the full 240-call course runner, literacy coverage, real AudioSocket/turn-timing simulation, larger audio-STT cases, and automated repair loops that convert failures into regressions and code fixes.

## Reproducible Cost Command

```bash
cd "/Users/naomiivie/Education for Equality/sabi-server"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fake_child_harness.cost_model \
  --children 100 \
  --calls-per-child 240 \
  --ngn-per-usd 1400
```

## Sources

- Groq pricing: https://groq.com/pricing
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- ElevenLabs API pricing: https://elevenlabs.io/pricing/api
- Africa's Talking pricing: https://africastalking.com/pricing
- Africa's Talking voice docs: https://africastalking.com/voice
- Pixabay Sabo/Yaba Lagos audio: https://pixabay.com/sound-effects/city-ambient-saboyaba-busstop-lagos-nigeria-23497/
- ZapSplat African market audio: https://www.zapsplat.com/music/african-village-market-busy-many-people/
