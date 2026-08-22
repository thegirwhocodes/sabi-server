# Gemini Live phone routing and rollback

Sabi routes every caller into a persistent native-audio Gemini Live conversation
by default. This applies equally to Africa's Talking, Twilio, arbitrary caller
IDs, and calls whose caller ID is unknown: carrier routing ends at the same
AudioSocket handler, and the handler makes the Gemini/old-pipeline decision.

## Route

With `SABI_GEMINI_LIVE_ALL=1`:

```text
AT or Twilio SIP -> Asterisk AudioSocket 9020 (8 kHz PCM)
           <-> one Gemini Live WebSocket for the whole call
           <-> deterministic Sabi numeracy tools and Supabase memory
```

The established turn-based route remains in the same deployed application:

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

## Activation, exclusions, and rollback

```dotenv
# Production default: every caller, including unknown caller IDs.
SABI_GEMINI_LIVE_ALL=1
# Per-number escape hatch while all-mode remains enabled.
SABI_GEMINI_LIVE_EXCLUDE_PHONES=
# Used only when SABI_GEMINI_LIVE_ALL=0.
SABI_GEMINI_LIVE_PHONES=+18605551234
SABI_GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
SABI_GEMINI_LIVE_VOICE=Kore

# The 9020 turn-based fallback must not depend on paid/dead providers.
SABI_TTS_TEST_PRIMARY=chatterbox_only
SABI_CHATTERBOX_URL=http://chatterbox:8001/tts
SABI_CHATTERBOX_SPEAKER=naomi
```

`SABI_GEMINI_LIVE_EXCLUDE_PHONES` is a comma/semicolon/newline-separated list.
Excluded callers immediately use the established STT → LLM → TTS pipeline.

For the fast global rollback, set `SABI_GEMINI_LIVE_ALL=0` and recreate the
`sabi-server` container so it re-reads `.env`. In rollback mode only
`SABI_GEMINI_LIVE_PHONES` uses Gemini; an empty allowlist sends every caller to
the established pipeline. Do not remove the old pipeline or the allowlist.

If the Live WebSocket or prompt cannot be configured before media reading
begins, that call automatically falls back to the established AudioSocket
pipeline. Because public inbound and callback dialplans use port 9020,
`SABI_TTS_TEST_PRIMARY=chatterbox_only` makes that fallback use the healthy
self-hosted Naomi voice without first waiting for dead ElevenLabs or YarnGPT.

A failure after Gemini has connected and consumed caller media cannot hand the
call seamlessly to the turn-based pipeline mid-call. It ends that call and is
recorded as `gemini_live_error:*`.

## Verification

```bash
python phone_routing_promotion_regression.py
python gemini_live_regression.py
python phone_runtime_config_regression.py
python numeric_grading_regression.py
```

The regression covers all-mode routing (Nigerian, US, and unknown callers),
exclusions, global rollback/allowlist mode, setup-time fallback to the old
pipeline, raw protocol configuration, VAD, downsampling, transcript merging,
and deterministic grading.
