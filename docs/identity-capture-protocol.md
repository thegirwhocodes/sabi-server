# Sabi name capture and learner binding

The rule: the name written to `sabi_students.name` must be one a second call can reuse with confidence.
Speech-to-text output is evidence, never a value. Nothing prompts the child writes directly to the name column.

## Turn sequence on a first call

1. **Ask** — "What is your name?" (existing prompt, no change)
2. **Judge the answer**, do not store it. Reject when the text is:
   - one of the artifact strings already in the DB: A Speech, What The, Uhhh, Already, And How, Qu Significa, Ja Mann, Alem Saci
   - a question or greeting: what, why, how, hello, hi, my name, who are you, I don't know
   - under 2 characters, or over 24, or containing digits
   - a language the learner did not answer in (Portuguese/Spanish strings seen on +2348125188233)
   - STT confidence below 0.6, in children's audio that is the common case
3. **Confirm by repeat** — "Did I hear you? Is it <name>?" A yes writes `name_status='confirmed_repeat'`.
4. **Ask again if rejected**, maximum 2 attempts per call, then move on with `name_status='unknown'` and a placeholder display name. Never block the lesson on the name.
5. **Caregiver confirmation** — the only path to a fully trusted name. `name_status='confirmed_caregiver'`, recording which adult, at what number, when.

`name_attempts` counts across calls, so a child who is unintelligible on Monday is asked again next session instead of being stuck as "Uhhh".

## Learner binding

`learner_key = phone_e164::slot`, where slot is `child-1`, `child-2` for a second child on the same handset, never a name.
Names change, spellings change, STT invents them; keys must not. Existing keys keep working via `identity_version = 1`
until a merge is reviewed, so no history is lost.

`learner_key` resolves within a household. `phone_household_key` stays the caregiver's handset. Session rows attach to
`student_id`, and `phone_number` on a session is treated as evidence about the handset, not the identity.

## Every mutation is an event

Any write to name, phone, or household key inserts into `sabi_identity_events` with `source`, `actor`,
`call_sid` and `old_value`/`new_value`. That table is append-only at the database level, so a correction can be
audited years later and a "who renamed this child" question always has an answer.

## Consent gate

A learner with no `sabi_consent_records` rows showing `caregiver_consent` and `child_assent` granted is
`pilot_ready = false`. That blocks research export, not the lesson: the child can still learn, but their name,
transcript, and audio do not leave the system. Record consent per type (`audio_recording`, `training_use` are
separate from participation) with method, language, collector, and evidence path.

## Retention

Raw audio: 90 days unless `audio_recording` consent is granted and training use is explicit.
Transcripts: kept redacted, `redacted_transcript` is the exportable one.
Deletion: `withdrawn` consent sets `export_rule.public_export_allowed = false` and purges audio at the next sweep.
