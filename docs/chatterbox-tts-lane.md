# Chatterbox TTS Lane — the $0 voice path off ElevenLabs

Created: 2026-07-02

Per [pilot/budget/Sabi Costs.md](../../pilot/budget/Sabi%20Costs.md) the phone
path is costed as **"TTS: Chatterbox Turbo (self-hosted, $0). ElevenLabs
Impact Program for web demo only."** Until 2026-07-02 the live phone chain was
ElevenLabs-first and the Chatterbox container had been removed (~Jun 10, during
the Qwen3 experiments), so every call and every web-demo utterance was hitting
paid ElevenLabs. This lane closes that gap safely.

## Current state (deployed 2026-07-02, commit `2d1b9a0`)

| Lane | AudioSocket | TTS chain | Cost |
|---|---|---|---|
| Production (`sabi-callback` / `sabi-inbound`) | 9019 | ElevenLabs → YarnGPT (**unchanged**) | paid |
| Test lane (`sabi-callback-intron`) | 9020 | **Chatterbox → ElevenLabs → YarnGPT** | $0 when Chatterbox answers |
| Web demo (`/afro-tts/*` via nginx) | — | Chatterbox direct (restored) | $0 |

- Container: `sabi-chatterbox` (image `sabi-server-chatterbox-tts:latest`, built Jun 29),
  `--restart unless-stopped`, on the `sabi-server_default` network with alias `chatterbox`,
  publishing `127.0.0.1:8001`. Voices loaded: `naomi` (default), `bukola`, `lagos295`, `wura`.
- Recreate command if it ever disappears again:

```bash
docker run -d --name sabi-chatterbox --restart unless-stopped --gpus all \
  --network sabi-server_default --network-alias chatterbox \
  -p 127.0.0.1:8001:8001 \
  -v /opt/sabi/sabi-server/chatterbox-tts/reference_audio:/app/reference_audio \
  -e CHATTERBOX_DEFAULT_SPEAKER=naomi \
  sabi-server-chatterbox-tts:latest
```

- Env on Hetzner (`/opt/sabi/sabi-server/.env`):
  `SABI_TTS_PRIMARY=elevenlabs` (prod, unchanged) ·
  `SABI_TTS_TEST_PRIMARY=chatterbox` · `SABI_CHATTERBOX_URL=http://chatterbox:8001/tts` ·
  `SABI_CHATTERBOX_SPEAKER=naomi`
- Evidence: every turn sidecar records `assistant.tts_provider`; calls roll up
  `tts_providers_used` (mirrors the STT provider evidence).
- Measured 2026-07-02: warm short-turn synthesis **1.24 s** (vs ~0.4–0.9 s
  ElevenLabs flash). Sample: `voice-tests/chatterbox_phone_lane_sample.mp3`.

## How to canary (same flow as the Intron STT lane)

```bash
curl -X POST https://api.eduforequality.org/admin/asterisk/direct-call-intron \
  -H "X-API-Key: $SABI_API_KEY" -F "phone=+18604367048"
```

The 9020 lane now differs from production in TWO ways: Intron-first STT (falls
back to Groq while INTRON_API_KEY is unset) and Chatterbox-first TTS. Inspect
afterwards: `GET /admin/calls/<uuid>` → each turn's `assistant.tts_provider`
should read `chatterbox`; listen to the Sabi-side clips.

## Promotion gate (playbook Tier 3 — do not skip)

Flip production only after, per `SABI_PREPILOT_PRODUCT_QA_AND_ENDPOINT_SWITCHING_PLAYBOOK.md`:
at least 5 adult canary calls on the lane, no increase in turn latency
complaints or abrupt endings, Sabi-side audio quality judged >= ElevenLabs, and
`tts_providers_used=["chatterbox"]` on those calls (no silent fallbacks).

```bash
# Promote (after canary passes):
ssh root@136.243.8.51 "cd /opt/sabi/sabi-server && sed -i.bak 's/^SABI_TTS_PRIMARY=.*/SABI_TTS_PRIMARY=chatterbox/' .env && docker compose up -d sabi"
# Rollback (one container cycle, ~12 s):
ssh root@136.243.8.51 "cd /opt/sabi/sabi-server && sed -i.bak 's/^SABI_TTS_PRIMARY=.*/SABI_TTS_PRIMARY=elevenlabs/' .env && docker compose up -d sabi"
```

ElevenLabs stays configured as automatic per-turn fallback either way — a
Chatterbox outage degrades to the paid voice instead of silence.

## Voice quality path

The current `naomi` voice is a 29-second zero-shot clone. Recording
**session 00** from `2. The Solution/voice-training/recording-sessions/`
(~10 min at the Focusrite) upgrades the reference clip the same day — see
`2. The Solution/voice-training/RECORDING_SESSION_PLAN.md`. Regression:
`python tts_provider_config_regression.py` (13 checks, runs in the container).
