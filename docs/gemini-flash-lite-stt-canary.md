# Gemini 3.5 Flash-Lite STT canary

The isolated Sabi phone lane sends every completed caller turn to Gemini 3.5
Flash-Lite. The production phone lane remains unchanged while the canary is
evaluated.

## Per-turn prompt policy

Every request uses Naomi's broad human-conversation prompt:

> A Nigerian child on a noisy 8kHz phone call is saying their name, introducing themselves and answering a numeracy lesson in sweets. This could also be the child calling the name of the AI, Sabi, a complaint about the quality of the call or lesson, complaining they can't hear the agent, or some other normal human phrase. Reply with their response

The course (`numeracy` or `literacy`) and the final safe topic (`sweets`,
`naira`, `beginning sounds`, and so on) change automatically from the current
curriculum turn. The question's operands, examples, and expected answer are
never sent to Gemini. The exact prompt used is stored on every call-review
turn so prompt behavior remains auditable.

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
SABI_GEMINI_STT_PROMPT_MODE=curriculum
SABI_GEMINI_STT_GLOBAL_PROMPT=A Nigerian child on a noisy 8kHz phone call
SABI_GEMINI_STT_THINKING_LEVEL=minimal
SABI_GEMINI_STT_TIMEOUT=5.5
```

Keep `GEMINI_API_KEY` in the server secret store. Never put it in a request URL
or commit it to Git.
