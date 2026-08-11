# Making Sabi personable on Gemini — what the research actually says

**Date:** 11 August 2026
**Question:** what kind of prompt makes Gemini behave like the warm, funny Sabi we want?
**Short answer:** the prompt is only one of four levers, and it is not the biggest one.

Background: the blind A/B lab (`scripts/prompt_lab.py`, 6 rounds) measured the live
prompt at **5.0–5.67 out of 10 on personality** — the worst dimension of any Gemini
variant tested. Naomi's description, "she kinda just gets to the point, no fun in
between", is a real and reproducible regression, not a vibe. This document is the
research into why, and what to do about it.

---

## 1. Three of the four biggest levers are not prompt text

### 1.1 The voice is literally named "Firm"

Sabi speaks through Gemini's **Kore** voice ([gemini_live.py:63](../gemini_live.py#L63)).
Google's own characterisation of its 30 prebuilt voices lists:

| Voice | Google's descriptor |
|---|---|
| **Kore** | **Firm** ← currently deployed |
| Leda | Youthful |
| Sulafat | Warm |
| Achird | Friendly |
| Vindemiatrix | Gentle |
| Sadachbia | Lively |
| Laomedeia | Upbeat |
| Callirrhoe | Easy-going |

We are asking a voice selected for firmness to read warm big-sister lines. No prompt
fixes that — the delivery is chosen at config time.

This matters more than it sounds. Moreno and Mayer's work on pedagogical agents found
that **the agent's voice was the significant contributor to learning outcomes, not the
animated persona**. Voice is not decoration; in this literature it is the part that
measurably moved learning.

It is also free to change: `SABI_GEMINI_LIVE_VOICE` is an environment variable, so an
A/B across Kore / Leda / Sulafat / Achird is a restart, not a code change.

### 1.2 The model we run cannot do affective dialog

Google's Live API has a feature called **affective dialog** — "the model adapts its
response style to match the expression and tone of the input", i.e. it hears that a
child is discouraged and softens. Enabled with `enable_affective_dialog: true` on the
`v1beta` API.

Per Google's Live API capabilities documentation, affective dialog and proactive audio
are supported on **Gemini 2.5 Flash Live Preview** and are **not supported on Gemini 3.1
Flash Live** — which is the model Sabi runs
(`gemini-3.1-flash-live-preview`, [gemini_live.py:59](../gemini_live.py#L59)).

So the single feature that most directly produces emotional responsiveness is
unavailable on our current model. That is a genuine architectural trade-off, not an
oversight: 3.1 was chosen on the Aug 7 rebuild and performs well on reasoning,
tool-calling and barge-in. Whether 2.5's affective dialog is worth 3.1's other gains is
a decision to make deliberately, and it should be tested, not assumed.

**Verify before acting on this.** Documentation for preview models moves; confirm the
current support matrix against the live endpoint before any model switch.

### 1.3 Gemini 3 is terse by default — and Google says you must ask

This is the most directly explanatory finding of the whole search. Google's prompting
guidance for Gemini 3 states:

> "By default, Gemini 3 models provide direct and efficient answers. If you need a more
> conversational or detailed response, you must explicitly request it."

Our current prompt describes Sabi as "warm, playful and patient" and tells her to keep
"the fun connected to the maths". It never explicitly requests a conversational
register or sets a verbosity level. Google's recommended system-instruction fields are
explicit: `Tone: [Formal/Casual/Technical]` and `Verbosity: [Low/Medium/High]`.

"Get to the point with no fun in between" **is Gemini 3's documented default
behaviour.** We inherited it by not overriding it.

### 1.4 Our prompt is not structured the way Google says to structure it

Google's Live API best-practices guidance prescribes an order:

> "have a clearly-defined set of system instructions that defines the agent persona,
> conversational rules, and guardrails, in this order"

and adds "provide examples of what the model should and shouldn't do", "limit prompts to
one prompt per persona or role at a time", and — for anything that must not be missed —
use the word **"unmistakably"**.

Our live prompt is five undifferentiated paragraphs of prose with persona, pedagogy,
turn mechanics and guardrails interleaved. Restructuring costs nothing and is what the
vendor explicitly recommends.

---

## 2. Why personality is a learning intervention, not decoration

The strongest evidence found is the **Politeness Effect** (Wang, Johnson, Mayer, Rizzo,
Shaw & Collins, AIED 2005).

Learners were tutored by an agent that either mitigated face threat ("polite") or
disregarded it ("direct"). Everything else was identical.

| Condition | Mean learning outcome | SD |
|---|---|---|
| Polite | **19.45** | 5.61 |
| Direct | 15.65 | 5.15 |

t(35) = 2.135, **p = 0.040**, n = 37. The effect was **amplified in learners who
preferred indirect feedback**, and the authors also observed effects on attitude and
motivation.

Their conclusion is pointed, and it is a direct argument for the work we are doing:

> "pedagogical agent research should perhaps place less emphasis on the Persona Effect
> in animated pedagogical agents, and focus more on the Politeness Effect and related
> means by which pedagogical agents can exhibit social intelligence."

### 2.1 The actual tactic ladder

Politeness theory (Brown & Levinson) distinguishes **positive face** (wanting approval)
from **negative face** (wanting autonomy). A correction threatens both. The paper gives
the same tutorial act at five levels of mitigation:

| Level | Example from the paper |
|---|---|
| Bald on record | "Save the factory now." |
| Off record (no blame assigned) | "The factory parameters need saving." |
| Negative politeness (preserves autonomy) | "Do you want to save the factory now?" |
| Tutor-would-do | "I would save the factory now." |
| **Joint action (positive politeness)** | **"How about if we save our factory now?"** |

Two mechanisms the paper names explicitly, both directly portable to a phone tutor:

- **"phrasing a hint as a question reinforces the learner's sense of control"**
- **"phrasing suggestions as activities to be performed jointly by the tutor and the learner"**

### 2.2 This is already why our best variants win

The winning lab variants scored highest on patience, and their best-scoring lines are
textbook joint-action positive politeness:

> "No wahala, we'll do it together. One bag has three oranges; now count three more..."

That is not charm. It is the highest rung of the mitigation ladder, and it is why the
judge scored patience 7.3–8.3 on those variants against 5.0–5.67 personality on the
baseline. **We have been getting the mechanism right by instinct.** Naming it lets us
apply it deliberately instead of hoping the model improvises it.

---

## 3. Examples: Google says always, but our variant C shows the failure mode

Google's prompting-strategies guidance is unusually strong on this:

> "We recommend to always include few-shot examples in your prompts. Prompts without
> few-shot examples are likely to be less effective."

with the caveat: "If you include too many examples, the model may start to overfit", and
"make sure that the structure and formatting of few-shot examples are the same".

The lab has already seen both sides of this. Variant C (personality language, no market
grounding) drifted to **grapes, piggy banks and kitten whiskers** — the judge noted
"counting kitten whiskers is a nonsense object for real maths". Adjectives without
grounded exemplars let the model invent its own world. Variant D/E, which pinned the
world to Lagos market items, scored 9.0 on concrete framing.

The implication for the next variant: replace loose illustrative phrases with a small,
consistent set of **full exchange exemplars** (learner turn → Sabi turn) covering the
beats that break — help request, wrong answer, correct answer, unclear audio.

---

## 4. What the register should be — Pidgin or not

From existing project research (`research-agents/9. On the Ground/`): Nigerian Pidgin is
a first language for 3–5 million Nigerians and a second language for roughly **75
million**, and mother-tongue instruction is associated with better comprehension and
engagement than English-only.

But that argues for Pidgin as a *medium of instruction*, which is a much larger product
decision than personality. For the personality work the defensible position is the one
the original hackathon prompt took: **warm, natural, Nigerian-accented standard English
with light Pidgin markers** ("Oya", "No wahala", "Well done oh") — enough to sound local
and unstiff, without switching the language of instruction. Full Pidgin delivery should
be its own tested decision with native-speaker review, not a side effect of a
personality prompt.

---

## 5. Honest limits of this research

- **The politeness study is not our population.** n=37 US university students learning
  factory-simulation software, screen-based, with an animated agent. Nigerian children
  aged 8–14 on a shared phone are a different setting. The *mechanism* (face, autonomy,
  joint action) is claimed cross-cultural by Brown & Levinson, but do not transport the
  effect size.
- **Politeness response varies by culture.** The literature already documents South
  Korean participants reacting more strongly to politeness variation than North
  Americans. The Nigerian case is untested. This is a reason to validate with Sonia and
  real callers, not to assume.
- **Pedagogical-agent meta-analyses are mixed overall.** The strong claim here is
  specifically about politeness and voice, not about agents in general.
- **Persona drift is real but probably not our problem.** Models begin diverging from an
  assigned persona after roughly 100 turns; a 5–7 minute Sabi lesson is 15–25 turns. Not
  a live concern within a call.
- **Preview-model feature support moves.** The affective-dialog finding must be
  re-verified against the endpoint before any model change.

---

## 6. Recommended next steps

Ordered by leverage per unit of effort.

1. **Voice A/B — highest leverage, lowest cost.** Kore ("Firm") against Leda
   ("Youthful"), Sulafat ("Warm"), Achird ("Friendly"). Environment variable only.
   Evidence says voice moved learning where persona did not.
2. **Add the two things Google says are mandatory and we omit:** an explicit
   conversational-register request (Gemini 3 is terse by default) and a stated
   verbosity level.
3. **Restructure the prompt into Google's prescribed order** — persona, then
   conversational rules, then guardrails — instead of interleaved prose.
4. **Rewrite the personality block as politeness tactics** rather than adjectives:
   hints phrased as questions, corrections as joint action, approval made overt and
   specific.
5. **Replace loose example phrases with consistent full-exchange exemplars** for the
   four beats that break.
6. **Then re-run the lab** (variant F) against the current champions, and only after
   that validate on the real Live endpoint.
7. **Separately and deliberately: decide whether affective dialog is worth moving to
   2.5 Flash Live.** Test, don't assume — 3.1 was chosen for good reasons.

---

## Sources

- [Live API best practices — Google AI for Developers](https://ai.google.dev/gemini-api/docs/live-api/best-practices)
- [Live API capabilities guide — Google AI for Developers](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Prompt design strategies — Google AI for Developers](https://ai.google.dev/gemini-api/docs/prompting-strategies)
- [Gemini 3 Prompting: Best Practices for General Usage — Philipp Schmid](https://www.philschmid.de/gemini-3-prompt-practices)
- [The Politeness Effect: Pedagogical Agents and Learning Gains (Wang, Johnson, Mayer, Rizzo, Shaw, Collins — AIED 2005)](https://people.ict.usc.edu/~nwang/PDF/AIED-2005.pdf)
- [The politeness effect: Pedagogical agents and learning outcomes — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1071581907001267)
- [The Effects of Pedagogical Agent Voice and Animation on Learning, Motivation and Perceived Persona — LearnTechLib](https://www.learntechlib.org/p/13800/)
- [How effective are pedagogical agents for learning? A meta-analytic review (Schroeder, Adesope, Gilbert)](http://debdavis.pbworks.com/w/file/fetch/96898947/schroeder%20adesope%20gilbert%20--%20how%20effective%20are%20pedagogical%20agents.pdf)
- [Comparison of all 30 Gemini TTS voices](https://note.com/tsukubalab/n/n0f143277b947?hl=en)
- [Examining Identity Drift in Conversations of LLM Agents](https://arxiv.org/pdf/2412.00804)
- [How to Write an AI Voice Agent System Prompt in 2026 — Famulor](https://www.famulor.io/blog/how-to-write-an-ai-voice-agent-system-prompt-in-2026)
- Existing project research: `research-agents/9. On the Ground/` (Nigerian Pidgin comprehension, mother-tongue instruction)
