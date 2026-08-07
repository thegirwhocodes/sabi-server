# Self-hosted ElevenLabs-style turn taking

## Correct reference agent

The live dashboard was inspected on 2026-08-07. The February hackathon account
is the account whose `E4e test` API key ends in `19d3` and was created on
February 28. Its Education for Equality agent is:

- Agent ID: `agent_7001kjhsraavfz28xcy7t7mb7ey6`
- ASR: `scribe_realtime`, quality `high`, `pcm_16000`
- Turn model: `turn_v2`
- Turn eagerness: `normal`
- Speculative turn: enabled
- Turn timeout: 7 seconds
- Background voice detection: disabled
- First-message interruptions: enabled
- Custom LLM: OpenAI-compatible HTTP endpoint at
  `https://curriculum-app-eta.vercel.app/api/sabi/voice/llm`

`agent_5701kp7djbvreqk9cb3mf4g55n09` belongs to a later account: that account's
keys were created April 12 and the dashboard dates the agent to April 14. It
was recorded as “canonical” in May project notes, but it is not the February
reference for this rebuild.

## Why an RMS threshold was insufficient

The old AudioSocket path stopped playback after two 20 ms frames exceeded an
RMS threshold. That only answers “is this waveform energetic?” It cannot
answer whether the waveform is speech, whether it is Sabi leaking back through
the handset, or whether the caller has completed a thought. The August 7 call
`01eadbaf-883f-417e-b84c-1c438cfedc65` proved the failure: seven short clips of
ordinary sound were promoted into turns and Gemini invented curriculum-shaped
transcripts.

## Replacement architecture

1. **Energy prefilter:** inexpensive RMS opens an interruption candidate but
   can never stop playback.
2. **Learned speech gate:** Silero VAD v5 from `faster-whisper` must find at
   least 320 ms of sustained speech with probability at or above 0.68.
3. **Echo rejection:** the candidate is correlated against the last three
   seconds of Sabi's actual outgoing PCM. A strong delayed match is rejected as
   acoustic echo.
4. **Phase-sensitive sensitivity:** while Sabi speaks, the strict gate favors
   false-rejection over false-interruption. After the prompt, a permissive
   64 ms Silero gate retains one-phoneme literacy answers.
5. **Learned endpointing:** after 360 ms of silence, Pipecat Smart Turn v3.2
   reads up to eight seconds of the current turn's PCM audio. If its prosodic
   and linguistic classifier says the thought is incomplete, Sabi waits for
   more speech instead of cutting the learner off.
6. **STT last:** Gemini receives audio only after the audio-control layer has
   established a real learner turn.

Smart Turn is pinned to Hugging Face revision
`f766f81d3cfdf7737ac64aad813d91bbfd56bf93`, file
`smart-turn-v3.2-cpu.onnx`, SHA-256
`2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f`.
The model and training code use the BSD 2-Clause license.

## Safety and rollout

`SABI_BARGE_IN_ENABLED=0` remains the public default. This lets the learned
post-prompt speech gate and endpointing run while guaranteeing that no
interruption can stop Sabi. Enable barge-in only after the private recorded-call
regressions and a live test pass.

Run in the deployed container:

```bash
python /app/turn_taking_regression.py
python /app/false_barge_call_regression.py
python /app/phone_runtime_config_regression.py
```

The August 7 false-barge replay currently rejects all seven contaminated clips.

## Primary references

- [ElevenLabs conversation flow](https://elevenlabs.io/docs/eleven-agents/customization/voice/conversation-flow)
- [ElevenLabs agent configuration API](https://elevenlabs.io/docs/api-reference/agents/get)
- [Pipecat Smart Turn](https://github.com/pipecat-ai/smart-turn)
- [Smart Turn v3 model and benchmarks](https://huggingface.co/pipecat-ai/smart-turn-v3)
- [Silero VAD](https://github.com/snakers4/silero-vad)
