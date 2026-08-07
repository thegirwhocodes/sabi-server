# OpenAI Realtime barge-in clean-room blueprint for Sabi

## Boundary

ChatGPT's private application and model-serving code is not public. This
blueprint uses OpenAI's public API protocol and MIT-licensed Agents SDK, at
`openai/openai-agents-python` commit
`237716cfb3047356dcdce8a8557a6750006e98c7`, as a clean-room behavioral
reference. It does not claim access to or copy proprietary ChatGPT code.

## What OpenAI's public phone implementation actually does

The official Twilio example is a useful reference because it addresses the
delay between generated audio, carrier buffering, and audio actually heard:

1. It forwards 8 kHz G.711 mu-law in 50 ms chunks without waiting for a final
   transcript.
2. It enables `semantic_vad` with `interrupt_response=true`.
3. Every outbound audio item has an item ID and content index.
4. Twilio `mark` acknowledgements update a `RealtimePlaybackTracker`, recording
   how many bytes the caller has actually heard rather than how many bytes the
   model has generated.
5. On `audio_interrupted`, the bridge sends Twilio `clear` immediately.
6. The SDK stops accepting audio deltas for the interrupted response ID.
7. It sends `conversation.item.truncate` at the caller's actual playback
   position, so unplayed assistant audio is removed from conversation history.
8. It sends `response.cancel` when automatic response cancellation is not
   already enabled.

OpenAI's SIP transport can manage output buffering and truncation server-side.
With WebSockets or a custom phone bridge, the application owns playback state
and must do these steps itself.

## Why this matters more than the recognizer

Barge-in is a synchronization problem before it is an STT problem. The system
must decide whether foreground speech exists, stop audible output, stop future
output for the same response, and make model history match what the caller
actually heard. Groq, Whisper, Gemini, or another recognizer can run after that
decision and may return later; none of them should be allowed to decide whether
an untrusted sound immediately cancels playback.

## Sabi translation for Nigerian PSTN audio

Sabi should keep its provider-independent pipeline and add OpenAI-style event
discipline around the learned Nigerian-phone gate:

| OpenAI public mechanism | Sabi equivalent |
| --- | --- |
| continuous G.711 chunks | continuous 20 ms AudioSocket PCM frames |
| server/semantic VAD | Silero foreground gate plus Smart Turn endpointing |
| response/item/content IDs | monotonically increasing response and audio item IDs |
| Twilio playback marks | byte/frame acknowledgements from the local Asterisk sender |
| `audio_interrupted` | accepted learned-interruption event |
| Twilio `clear` | stop sending the active AudioSocket item and discard its queue |
| ignore interrupted deltas | reject all later chunks with the cancelled response ID |
| `conversation.item.truncate` | retain only the assistant prefix actually heard |
| `response.cancel` | cancel tentative LLM/TTS tasks for that response ID |

The interruption gate should remain stricter than the normal listening gate.
For a child on Nigerian PSTN audio, an interruption candidate should require:

- sustained learned human-speech evidence;
- low similarity to the assistant audio currently playing;
- a short grace window for carrier transients;
- a stable response ID so late audio cannot leak into the next turn;
- a post-interruption utterance collector that allows a natural pause;
- telemetry retaining raw decision probabilities and actual playback position.

## Current implementation status

Already live on the phone-scoped Twilio test lane:

- continuous full-duplex AudioSocket input during playback;
- separate strict interruption and permissive post-prompt gates;
- Silero VAD v5, outgoing-audio echo correlation, and Smart Turn v3.2;
- immediate local playback stop after an accepted foreground interruption;
- no recognition call until learned speech evidence passes.

Still required for OpenAI-style parity:

1. Add response/item IDs to every generated assistant audio stream.
2. Track frames actually written to Asterisk, not merely synthesized.
3. Make LLM and TTS generation cancelable and discard late chunks by response
   ID.
4. Replace the full assistant history item with only the heard prefix after an
   interruption.
5. Stream TTS in sentence-safe chunks instead of waiting for a complete WAV.
6. Evaluate thresholds on labelled Nigerian PSTN calls by speech, cough,
   laughter, handset movement, echo, overlapping household voices, and carrier
   noise. Do not use recognizer text as the interruption ground truth.

## Primary sources

- <https://github.com/openai/openai-agents-python>
- <https://github.com/openai/openai-agents-python/tree/main/examples/realtime/twilio>
- <https://developers.openai.com/api/docs/guides/realtime-conversations>
- <https://developers.openai.com/api/docs/guides/realtime-vad>
- <https://developers.openai.com/api/docs/guides/realtime-sip>
