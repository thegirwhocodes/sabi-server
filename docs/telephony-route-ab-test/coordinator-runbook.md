# Route Test Coordinator Runbook

Use this document on testing day. The full protocol and decision rules are in `README.md`.

## 24 hours before testing

- [ ] Engineering confirms Routes A, B, and optional C terminate in the same benchmark collector.
- [ ] Engineering completes a synthetic end-to-end call on every route.
- [ ] Caller-only continuous recordings and utterance clips are visible for every route.
- [ ] Route-specific codecs, sample rates, timestamps, and network metrics are saving.
- [ ] The test STT model/configuration is written down and frozen.
- [ ] Route order and Phrase Set A/B are assigned for every participant.
- [ ] Participant-facing route labels contain no provider names.
- [ ] Airtime/data and any international-call reimbursement are prepared.
- [ ] Wi-Fi, Bluetooth, and Wi-Fi Calling can be disabled for the controlled test.
- [ ] Adult consent records are ready.
- [ ] For any later child session, Guardian Consent A, separate Consent B, and child assent are ready; missing any one means no recording.
- [ ] Contact/consent records are stored separately from blind audio data.

## Before each participant

- [ ] Assign a pseudonymous ID such as `T001`; never use the phone number in filenames.
- [ ] Record carrier, handset model, call mode, network mode, approximate signal bars, broad region if volunteered, room condition, and route order.
- [ ] Confirm the same phone and SIM will be used throughout.
- [ ] Ask the participant to silence notifications and remain in the same position.
- [ ] Confirm the participant understands that this tests the system, not their accent or ability.
- [ ] Confirm consent and the right to pause or stop.
- [ ] For a child, confirm guardian consent, separate recording consent, and the child's own willingness immediately before starting.

## Script to read

> We are comparing ways a phone system receives speech. This is not a test of your reading, intelligence, accent, or English. Please use your normal voice and hold the phone the way you normally would. Keep the same phone, SIM, room, and call mode for every call. After each tone, read the phrase shown once. Do not deliberately slow down, exaggerate, or change your accent. If you misread a card, tell me and we will mark it. You may pause or stop at any time.

Do not tell the participant which provider is behind a route or suggest that one should be better.

## Quiet-route session

Run three rounds. Within each round, follow the preassigned rotated route order so every route appears early, middle, and late across the test.

For each route block:

1. Enter the participant ID, route label, call/session ID, phrase set, route-order position, and random seed in the session log.
2. Place/open the route using the same phone, SIM, call mode, and room.
3. Confirm the collector has begun caller-only continuous recording before the first item.
4. Run every assigned phrase once in the generated order for this round.
5. Mark misreads, coughs, interruptions, competing voices, unexpected noise, and disconnections without deleting the audio.
6. End the call cleanly and confirm expected files arrived.
7. Continue to the next route in the assigned order. Offer a brief water/voice break between rounds and a longer break whenever needed.

If fatigue changes the tester's voice, stop and reschedule the remaining route. Record the delay rather than pushing through.

## Controlled acoustic replay

- [ ] Use a consented 48 kHz Nigerian adult source recording, never an already telephone-degraded clip.
- [ ] Fix the phone and loudspeaker on marked stands approximately 20–30 cm apart.
- [ ] Lock playback volume and photograph/document the geometry.
- [ ] Use the same phone, SIM, room, mobile network, and playback file throughout.
- [ ] Disable Wi-Fi, Bluetooth, and Wi-Fi Calling; use that SIM's mobile data for C where supported.
- [ ] Establish at least three separate calls per route.
- [ ] Confirm browser capture settings and save returned `getSettings()` values for C.
- [ ] Save native WebRTC audio and a separately labeled offline G.711/8 kHz simulation.

## Controlled-noise challenge

- [ ] Use only `noise_subset=yes` phrases.
- [ ] Use the same approved noise file, playback device, volume, and measured placement.
- [ ] Record dBA if possible.
- [ ] Run one repetition per phrase per route.
- [ ] Do not combine these results with the quiet primary analysis.

## Immediately after each participant

- [ ] Expected route calls and continuous recordings exist.
- [ ] Every presented item maps to one utterance or a documented missing item.
- [ ] File hashes have been generated.
- [ ] Device/environment changes and reading deviations are recorded.
- [ ] No phone number or personal name appears in a filename.
- [ ] Contact/consent records remain outside the analyst export.
- [ ] Child audio, if any, is inside the consented restricted corpus only.

## End-of-day handoff to data manager

- [ ] Freeze raw audio read-only.
- [ ] Create randomized blind IDs.
- [ ] Complete the restricted route key.
- [ ] Export blind clips and the blind sample manifest.
- [ ] Remove route/provider and target-phrase information from listener filenames and metadata.
- [ ] Run the locked STT once and preserve raw outputs.
- [ ] Send blind audio independently to two Nigerian-English listeners.
- [ ] Do not unblind until STT and human judgments are complete and signed off.

## Stop conditions

Stop and contact the technical owner if:

- routes are using different prompt/VAD/STT behavior;
- caller audio is mixed with prompt audio;
- raw files are missing or mappings are ambiguous;
- a carrier incident causes unusual packet loss/jitter;
- the wrong phone/SIM was used;
- consent status is uncertain;
- a participant, especially a child, wants to stop.
