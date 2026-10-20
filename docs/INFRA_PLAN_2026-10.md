# Sabi server plan — Oct 2026

Goal: calls never go down again, the server cost grows only with use, and the
runway is protected. Owner: Naomi. Written Oct 19 2026 (session 6d4de6ca).
Removed components are recorded in [REMOVED_COMPONENTS_LOG.md](REMOVED_COMPONENTS_LOG.md).

## Where we are (Oct 19 2026)
- Vultr Johannesburg, vc2-2c-4gb (2 CPU / 4 GB / 80 GB), upgraded today.
- Phone address `139.84.246.103` is now a Vultr **Reserved IP** — a server can
  be replaced without Africa's Talking (Samuel) changing anything.
- Every caller is on Gemini Live (tools off, voice Kore). Fallback/safety voice
  is `chatterbox_only`, which does not exist on this box → silence on failure.
- The $250 Vultr promo expired Oct 8; the card is billed from now on.

## Step-by-step

| # | Step | Status |
|---|---|---|
| 1 | Clear disk (build cache, apt, journal) | ✅ Done Oct 19 (100% → 77%) |
| 2 | Reserved IP for the phone address | ✅ Done Oct 19 |
| 3 | Upgrade to 4 GB | ✅ Done Oct 19 |
| 4 | Slim image: CPU base, no Ollama, no keys in image, pinned versions (`requirements.lock.txt`) | ✅ Live Oct 19 (12.4 GB → 8.45 GB; Ollama 9.2 GB removed; disk 82%) |
| 5 | Delete old image after the slim one handles real calls | ⏳ After step 4 is proven |
| 6 | Recordings → Naomi's Google storage, nightly, verified by checksum; delete local copies older than 14 days only after verified upload | ⏳ Needs Naomi's one-time Google sign-in |
| 7 | Fallback + crisis voice → ElevenLabs (`SABI_TTS_TEST_PRIMARY=elevenlabs`), pay-as-you-go key, Bukola voice `oC2pCZZWEDRe6lmZpaaw` | ✅ Done Oct 19 (verified end to end inside the container). Also fixed: an empty `ELEVENLABS_VOICE_ID` secret file was overriding the default voice → 404 |
| 8 | Billing safety: card + autopay on Vultr, low-balance alert; Gemini spend cap | ✅ Vultr card done by Naomi Oct 19; Gemini spend cap still open |
| 9 | Real cost per call from Gemini `usage_metadata` in past call records | ⏳ |
| 10 | Split: phone gateway (Asterisk, Reserved IP) vs lesson workers; Asterisk asks the server which worker takes each call | ⏳ |
| 11 | Shared call state (Redis/Supabase) instead of in-memory `CALL_REGISTRY` | ⏳ |
| 12 | Callback queue with a max-concurrent-calls cap | ⏳ |
| 13 | Scheduled extra workers on Vultr hourly billing (school hours / pilot weeks) | ⏳ |
| 14 | Automatic scaling on live call count | ⏳ |
| 15 | Rebuild script in git so a fresh box is one command | ⏳ |
| 16 | Second phone gateway + second Africa's Talking whitelist entry (ask Samuel) | ⏳ |

## Open questions for Naomi
- E4E's legal entity type (for startup credit programs).

## Decisions (Oct 19)
- Recordings go to Google Drive on naomi.ivie04@gmail.com (5 TB); Naomi confirms the consent form covers recording.
- Keep Vultr `sabi-dev` (London).
