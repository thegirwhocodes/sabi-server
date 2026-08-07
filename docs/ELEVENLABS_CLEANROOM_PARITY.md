# ElevenLabs conversational-agent clean-room parity

## Boundary

The original February agent is the behavioral oracle:
`agent_7001kjhsraavfz28xcy7t7mb7ey6`. ElevenLabs' hosted Scribe inference,
`turn_v2`, speculative execution service, telephone DSP, and orchestration
backend are proprietary and are not downloadable from the dashboard or public
web application.

ElevenLabs does publish its Agents client SDK under the MIT License. This audit
used the official `elevenlabs/packages` repository at commit
`da7b5326fefdac8c6a086e4f6aa4f1bfb58eefc2` (2026-08-06), the official API
schema, the original agent's authenticated configuration API, and controlled
audio sent to the original agent. Sabi reimplements observed behavior; it does
not copy private backend code.

## What the public client actually does

- Captures and sends continuous audio in 25 ms chunks. It does not wait for a
  local energy threshold to declare a user turn.
- Requests browser `voiceIsolation`, echo cancellation, noise suppression,
  automatic gain control, and mono audio.
- Receives server-side VAD scores, tentative and final transcripts, turn
  probabilities, interruptions, tentative agent responses, streaming response
  parts, and timestamped audio chunks.
- Associates user, agent, and audio events with event IDs. An interruption
  advances the event ID, clears queued playback, and prevents stale audio from
  playing.
- Starts output playback as audio chunks arrive instead of waiting for a full
  response file.

The public schemas expose the orchestration shape, including
`internal_turn_probability` and `internal_tentative_agent_response`, but not the
models or decision code that produce them.

## Original-agent oracle measurement

A controlled WebSocket session fed the exact 1.52-second
`user_turn_02.wav` clip from Sabi call
`2458d516-0334-4648-9662-993b9492743d` to the original agent. Gemini had
transcribed the clip as `bi`; the original Scribe agent returned `Vee.` This is
evidence that narrowband phonemes remain ambiguous even in the managed stack.

The original conversation record reported:

- turn silence before initiation: 320 ms
- Scribe trailing latency: 41 ms
- LLM first byte: 567 ms
- LLM first sentence: 605 ms
- TTS first byte: 105 ms
- first audible response after silence: 1.082 seconds
- configured speculative turn: enabled
- configured TTS streaming optimization: level 3

The 16-second probe cost 113 credits / about USD 0.0246. The platform portion
was about USD 0.0231; this is why Sabi should reproduce the orchestration on
its own server rather than route production calls through the managed agent.

## Sabi parity status

| Managed behavior | Sabi implementation | Status |
| --- | --- | --- |
| learned speech gate | Silero VAD v5 | live |
| background/echo rejection | strict interruption duration plus outgoing-audio correlation | live |
| semantic/prosodic endpoint | Pipecat Smart Turn v3.2 | live |
| separate interruption/listening sensitivity | 320 ms strict / 192 ms post-prompt | live |
| event-scoped interruption | per-listener barge control and immediate playback cancellation | live on Twilio canary |
| high-quality phoneme ASR | Gemini for names/numeracy; fast Groq Whisper for literacy | live on Twilio canary |
| speculative partial transcript | batch transcription after endpoint | not yet |
| speculative LLM generation | full turn closes before LLM starts | not yet |
| streaming TTS playback | full audio file generated before playback | not yet |
| browser acoustic DSP | not available on a PSTN AudioSocket; server echo guard substitutes | partial |

## Next parity work

1. Add continuous partial ASR during caller speech, preserving the final
   post-gate transcript as authoritative.
2. Start a cancelable tentative LLM generation when Smart Turn probability
   rises, then discard it if the caller continues.
3. Stream sentence-safe TTS chunks and tag them with event IDs so accepted
   interruptions cancel queued and in-flight audio.
4. Record turn probability, ASR tail, LLM first byte, TTS first byte, and first
   audible response for every call, matching the managed service's latency
   observability.
5. Benchmark a self-hosted streaming TTS replacement before removing the
   current ElevenLabs voice; Chatterbox is currently free but takes roughly
   1.8-2.3 seconds per tested response on this server.

## Primary sources

- <https://github.com/elevenlabs/packages>
- <https://elevenlabs.io/docs/eleven-agents/api-reference/eleven-agents/websocket>
- <https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow>
- <https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies>
- <https://github.com/pipecat-ai/smart-turn>
- <https://github.com/snakers4/silero-vad>
