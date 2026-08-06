# Gemini 3.5 Flash-Lite STT canary

The live Sabi phone lane sends every completed caller turn to Gemini 3.5
Flash-Lite. The previous listener remains available as a rollback lane while
the Gemini route is evaluated.

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
is 5.5 seconds.

## Failure and control behavior

`gemini` and `gemini_first` are strict providers. A Gemini timeout or error
becomes an unclear-audio retry; Sabi does not silently substitute Whisper or
Groq. `gemini_fallback` is the only setting that authorizes that substitution.

After transcription, the tutor LLM makes one pre-grading decision: is this a
direct attempt to answer the current question or not? Complaints, repeat
requests, calling Sabi, and unrelated conversation do not reach the
deterministic grader and cannot lower the learner's level. The old repeat
regex and short-barge grading shortcuts are not used.

This binary gate is not a second STT model and does not rewrite Gemini's
transcript. It uses the fast Groq text model first (about 0.1-0.2 seconds in
the production-shaped check), then Claude only as a fallback. If neither can
return valid JSON, the turn fails closed as not graded.

When Sabi asks for a learner's name, that same LLM gate accepts only a
plausible human name. An implausible STT fragment is not stored; Sabi asks the
learner to say the name again.

Only when the current tutor question has a computable numeric answer may the
caller speak or type digits. Keypad input and the keypad announcement remain
off for literacy, names, complaints, and ordinary conversation. Digits submit
with `#`, after the short inter-digit pause, or at the configured maximum
length.

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
