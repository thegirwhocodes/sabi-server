# Gemini Live phone canary

Sabi has a caller-scoped Gemini Live route for testing a persistent native-audio
conversation without changing other learners' calls.

## Route

For a phone number listed in `SABI_GEMINI_LIVE_PHONES`:

```text
Twilio SIP -> Asterisk AudioSocket (8 kHz PCM)
           <-> one Gemini Live WebSocket for the whole call
           <-> deterministic Sabi numeracy tools and Supabase memory
```

Every other caller remains on the established route:

```text
AudioSocket -> completed utterance -> STT -> text LLM -> TTS
```

The canary streams 20 ms caller frames continuously to Gemini Live. Gemini's
automatic activity detection closes turns and sends an `interrupted` event when
the caller speaks over Sabi. The bridge immediately clears all unsent playback
frames. Native 24 kHz Gemini audio is filtered, downsampled to 8 kHz, and paced
back to Asterisk in 20 ms frames.

## Context and learning controls

The canonical Sabi prompt, learner memory, curriculum route, and current
learning state are sent once when the WebSocket opens. Gemini then retains the
in-call conversation instead of receiving a rebuilt context after every WAV
transcription.

Two local tools remain authoritative:

- `get_next_numeracy_problem` selects a varied problem deck with unique
  products and factor pairs.
- `grade_numeric_answer` compares the number Gemini heard with the stored
  expected answer. Object nouns do not affect correctness, so `two apples`,
  `two fries`, and `two mangoes` all grade as the number two.

Transcriptions, actually played assistant audio, tool decisions, state changes,
and call completion continue to appear in Sabi Call Review. The provider is
recorded as `gemini_live`; no fake STT confidence is assigned.

## Activation and fallback

```dotenv
SABI_GEMINI_LIVE_PHONES=+18605551234
SABI_GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
SABI_GEMINI_LIVE_VOICE=Kore
```

An empty phone allowlist disables the route. If the Live WebSocket cannot be
configured before media reading begins, that call falls back to the established
AudioSocket pipeline. A mid-call provider failure ends only the canary call and
is recorded as `gemini_live_error:*`.

## Verification

```bash
python gemini_live_regression.py
python phone_runtime_config_regression.py
python numeric_grading_regression.py
```

The regression covers phone isolation, raw protocol configuration, conservative
VAD settings, downsampling, streaming transcript merging, varied multiplication
products, and noun-independent deterministic grading.
