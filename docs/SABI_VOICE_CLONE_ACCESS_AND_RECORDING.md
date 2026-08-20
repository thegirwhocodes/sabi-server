# Getting Sabi a real Nigerian voice on Google — the two steps

Written 20 Aug 2026. Everything here is from Google's own Chirp 3: Instant Custom Voice
documentation, checked the same day.

---

## Step 1 — Get access

Instant Custom Voice is **allow-list only**. Two routes, cheapest first.

### 1a. Check the console before you ask anyone

Open **https://console.cloud.google.com/vertex-ai/studio/media/generate;tab=audio**

Sign in as `naomi.i@eduforequality.org`, pick the E4E project, and look for Instant Custom
Voice on that page. If it is there, you are already allow-listed and step 1b is unnecessary.
This costs two minutes and may skip the whole wait.

### 1b. If it is not there, request it

Google's own instruction is to contact sales: **https://cloud.google.com/contact**

Use `naomi.i@eduforequality.org`, not a personal address — that form generally rejects free
email domains, and the whole reason Cloud Identity was set up was to have a business address
on the domain.

Have these ready before you open the form:

- **The GCP project ID** the voice will run in
- **The billing account ID** attached to it
- Country: whichever the entity actually is — not where you are sitting
- Expected volume: be honest and small. A pilot is a pilot.

⚠️ **Check the billing account before you send this.** If the project is still on the billing
account created under the Wesleyan identity, then access — and anything built on it — attaches
to an account tied to a university you graduate from. Confirm which billing account the project
uses, and move it to one owned by `eduforequality.org` first if it is not already.

### Message to paste into the form

> I am building a voice tutor that Nigerian children reach by phone call — no smartphone, no
> data — to learn foundational literacy and numeracy. It is a nonprofit programme, currently in
> pre-pilot with adult testers before children are involved.
>
> I would like access to Chirp 3: Instant Custom Voice.
>
> The reason is specific: Cloud Text-to-Speech has no Nigerian English voice, and neither does
> Gemini. My learners are children in Lagos on 8 kHz phone lines, and Nigerian listeners
> immediately hear a non-Nigerian voice as foreign. A cloned voice from a consenting Nigerian
> speaker is the only way I can find on Google's stack to give them a tutor who sounds like
> someone from their own city.
>
> Volume is small: a pre-pilot of a few testers, then roughly ten children. Streaming synthesis
> to a telephony line, MULAW at 8 kHz.
>
> Project ID: [FILL IN]
> Billing account: [FILL IN]

---

## Step 2 — The ten seconds that become Sabi's voice

### First, a constraint that decides who it is

The consent recording says, word for word, **"I am the owner of this voice."** That means the
voice has to belong to a real person who consents on record. The original Sabi voice cannot be
cloned — it was not a person you have consent from.

So Sabi's voice is now a casting decision between:

- **You.** You are Nigerian, it is your project, consent is trivial, and your voice was already
  the clone running on the non-Gemini lane. The cost is that Sabi becomes permanently tied to
  one founder's voice.
- **Sonia**, or another Nigerian woman already close to the work.
- **A hired Nigerian voice actor**, which is the version that scales and de-risks — but needs a
  written release alongside the spoken consent, and money.

This is your call and nobody else's. Everything below works the same whoever it is.

### What to record

Two separate files, **recorded in the same room, in the same session, back to back**. Google is
explicit about this: the clone reproduces the microphone and the room as faithfully as it
reproduces the voice.

**File 1 — consent. Up to 10 seconds. Read exactly, no improvising:**

> I am the owner of this voice, and I consent to Google using this voice to create a synthetic
> voice model.

**File 2 — reference. Up to 10 seconds.** This one is the whole ballgame — it sets the accent,
the warmth and the pace of every lesson Sabi ever teaches. Three options; pick one and rehearse
it a few times before recording:

**A — praise and a question, the two things she does most**
> Yeees! You got it — I knew you were sharp! Oya, if pure water is twenty naira and you buy
> two, how much altogether?

**B — the gentle register, for when a child is wrong**
> Ah ah, good try! No worry, we go do am together. Start from twenty, and count twenty more —
> what do you land on?

**C — a warm open, closest to the original first line**
> Hello! I'm SAH-bee, your learning friend. Sabi means "to know" — and together, we are going
> to know so much. What is your name?

### How to record it

- **Single channel (mono), no background noise**, in a soft room — a bedroom with fabric beats
  a kitchen. Accepted encodings: LINEAR16, PCM, MP3 or M4A.
- **Aim for 9–10 seconds.** Not five. Google says as close to ten as possible.
- **Do not read it like a newsreader.** "Too refined" is the exact complaint about the current
  voice, and the reference recording is where that gets decided — not the prompt.
- **Smile while you say it.** It is audible, and it is most of what "warm" means acoustically.
- Let the Nigerian markers land naturally — the tapped *r* in "naira", the full vowels, the
  pitch jump on "Ah ah!". Do not soften them for an imagined foreign listener.
- **Record five takes and keep the best one.** It is ten seconds; there is no reason to accept
  the first.

### Then

Both files go into a Cloud Storage bucket, and the create-voice call returns a **voice cloning
key**. That key goes into every synthesis request:

```json
{
  "input": { "text": "Yeees! You got it!" },
  "voice": {
    "languageCode": "en-GB",
    "voiceClone": { "voiceCloningKey": "<the key>" }
  },
  "audioConfig": { "audioEncoding": "MULAW", "sampleRateHertz": 8000 }
}
```

`en-GB` is a label, not an accent — Instant Custom Voice has no `en-NG` locale, and the accent
comes from the recording, not the locale. Worth testing `en-GB` against `en-IN` once the key
exists and keeping whichever sounds less foreign; the two base models handle rhythm differently.

Pace control (0.25x–2x), pause tags and IPA pronunciation control are all available on top —
which is the proper fix for "she talks too fast", rather than another prompt edit.

---

## What is blocked on me vs on you

- **On you:** the console check, the sales request, deciding whose voice, and recording the two
  files. None of it is code.
- **On me:** `gcloud` is not installed on this Mac. Once you have access and the recordings, I
  install it, create the bucket, run the create-voice call, wire the key into the pipeline and
  put it on a real call.
