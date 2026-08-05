# Gemini 3.5 Flash-Lite STT canary

The isolated Sabi phone lane sends every completed caller turn to Gemini 3.5
Flash-Lite. The production phone lane remains unchanged while the canary is
evaluated.

## Per-turn prompt policy

Every request contains the shared context:

> A Nigerian child on a noisy 8kHz phone call

Sabi then appends one compact tag selected from the current lesson state and
the response type. Examples include:

- `is saying their name. Reply with their response.`
- `is responding to a numeracy question. Reply with their response.`
- `is responding to a numeracy question in naira. Reply with their response.`
- `is responding with one spoken beginning letter sound to a literacy phonemics question. Reply with the sound they say.`
- `is responding to a literacy word question. Reply with their response.`

The selector may inspect the tutor's latest question locally, but the tagged
prompt does not send that question, its operands, examples, or the expected
answer to Gemini. This gives the model the response category without turning
the prompt into an answer hint.

Gemini `generateContent` calls are stateless, so the shared context and turn
tag are attached to every audio request. A single persistent HTTP client reuses
connections across turns. Thinking is set to `minimal`, and the canary timeout
is 3.5 seconds.

## Failure and control behavior

`gemini` and `gemini_first` are strict providers. A Gemini timeout or error
becomes an unclear-audio retry; Sabi does not silently substitute Whisper or
Groq. `gemini_fallback` is the only setting that authorizes that substitution.

Repeat requests such as "I didn't hear the question" are treated as control
turns: Sabi repeats the latest question, does not grade the child, and does not
lower the learning level.

During every numeric answer window, callers may speak or type digits. Keypad
digits submit with `#`, after the short inter-digit pause, or at the configured
maximum length.

## Configuration

```env
SABI_STT_TEST_PROVIDER=gemini
SABI_LITERACY_STT_TEST_PROVIDER=gemini
SABI_GEMINI_STT_MODEL=gemini-3.5-flash-lite
SABI_GEMINI_STT_PROMPT_MODE=tagged
SABI_GEMINI_STT_GLOBAL_PROMPT=A Nigerian child on a noisy 8kHz phone call
SABI_GEMINI_STT_THINKING_LEVEL=minimal
SABI_GEMINI_STT_TIMEOUT=3.5
```

Keep `GEMINI_API_KEY` in the server secret store. Never put it in a request URL
or commit it to Git.
