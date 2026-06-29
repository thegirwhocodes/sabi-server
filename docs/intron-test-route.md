# Intron STT Test Route

How to test Intron Sahara ASR against Sabi's existing Whisper/Groq lane without
ever touching the working production phone route.

**Production STT lane:** `app.state.stt` → `SABI_STT_PROVIDER` (default `auto`)
→ Groq Whisper API → local `faster-whisper large-v3` fallback. Asterisk
context `[sabi-callback-run]` / `[sabi-inbound]` → AudioSocket `sabi:9019`.

**Intron test STT lane:** `app.state.intron_stt` → `SABI_STT_TEST_PROVIDER`
(default `intron_first`) → Intron Sahara ASR → falls back to Groq/local on any
exception. Asterisk context `[sabi-callback-intron-run]` → AudioSocket
`sabi:9020`. Originated only via the admin endpoint, never via inbound.

Both lanes are physically separate inside `sabi-server`. Switching the test
lane on or off cannot affect any inbound call. This is verified by
`intron_route_isolation_regression.py`, which fails if any of the six
isolation invariants drift.

---

## 1. Switch ON

The test lane is always running on port 9020. To make it actually use Intron
(instead of silently falling back to Groq/Whisper), set the key on Hetzner.

```bash
ssh root@136.243.8.51
cd /opt/sabi/sabi-server

# Back up the current env in case rollback is needed.
cp .env .env.backup-intron-$(date +%Y%m%d-%H%M%S)

# Append the Intron config. SABI_STT_PROVIDER / SABI_LITERACY_STT_PROVIDER
# stay UNSET so the production lane keeps using Groq/Whisper.
cat >> .env <<'EOF'
INTRON_API_KEY=<paste-the-key-from-Intron-dashboard>
SABI_STT_TEST_PROVIDER=intron_first
SABI_LITERACY_STT_TEST_PROVIDER=intron_first
SABI_INTRON_AUDIOSOCKET_PORT=9020
EOF

# Recreate the container so it picks up the new env_file values.
# (docker compose restart does NOT re-read env_file — must use up -d.)
docker compose up -d sabi

# Verify health.
curl -s http://127.0.0.1:8000/health
```

Expected `/health` output:

```json
{"status":"ok","stt":"loaded","tts":"loaded","llm":"loaded"}
```

---

## 2. Switch OFF

Unset the key and recreate. The test lane will keep accepting calls but every
transcription falls through to Groq/Whisper, so behaviour is identical to the
production lane.

```bash
ssh root@136.243.8.51
cd /opt/sabi/sabi-server
sed -i.bak '/^INTRON_API_KEY=/d' .env
docker compose up -d sabi
```

To fully disable the test lane (remove the second AudioSocket listener):

```bash
# Stop sabi-server is enough — port 9020 closes immediately. The dialplan
# context still exists but originate calls into it will fail with
# "Sabi Intron unavailable before callback answer".
docker compose stop sabi
```

---

## 3. Test from your laptop

### 3a. Direct WAV upload (fastest, no phone call needed)

```bash
SABI_API_KEY=$(ssh root@136.243.8.51 'grep ^SABI_API_KEY= /opt/sabi/sabi-server/.env | cut -d= -f2')

curl -X POST https://api.eduforequality.org/admin/stt/intron-test \
  -H "X-API-Key: $SABI_API_KEY" \
  -F "audio=@/path/to/user_turn.wav" \
  -F "mode=general"          # or "literacy" for short-word answers
```

Response shape:

```json
{
  "text": "ten naira",
  "confidence": 0.84,
  "language": "en",
  "duration_seconds": 1.2,
  "mode": "general",
  "provider": "intron",       // or "groq"/"local_whisper" if Intron fell back
  "latency_ms": 1240,
  "test_route": "admin_stt_intron_test"
}
```

If the response shows `provider: "groq"` or `provider: "local_whisper"` when
you asked for Intron, the fallback path fired. Check `docker compose logs
sabi | grep -i intron` for the underlying reason — usually a missing key or
an Intron 503.

### 3b. Originate a real test phone call into the Intron lane

This calls a tester back through Asterisk into the experimental context. The
call uses the **same** Sabi UX (lesson, voice, feedback prompt) — only the
STT path differs.

```bash
curl -X POST https://api.eduforequality.org/admin/asterisk/direct-call-intron \
  -H "X-API-Key: $SABI_API_KEY" \
  -F "phone=+18604367048"        # Naomi's US tester line
```

> **Requires the full `SABI_API_KEY`**, not the read-only board PIN, because
> this route can spend money by originating outbound minutes. Production
> `direct-call` (without `-intron`) is the same constraint.

The tester's phone rings; Sabi answers; the lesson runs through Intron STT
first, falling back to Groq/Whisper on per-turn exceptions.

---

## 4. Where to inspect results

The admin Calls index aggregates which STT providers handled each call.
Once the Next.js admin v2 lands, the Calls page will have a `stt_provider`
filter. Until then:

```bash
# List recent calls — look at stt_providers_used in each item.
curl -s "https://api.eduforequality.org/admin/calls?limit=10" \
  -H "X-Admin-Pin: $SABI_ADMIN_PIN" | jq '.items[] | {call_uuid, phone_number, duration_seconds, stt_providers_used}'

# Detail for one call — every turn carries user.stt_provider.
curl -s "https://api.eduforequality.org/admin/calls/<call_uuid>" \
  -H "X-Admin-Pin: $SABI_ADMIN_PIN" | jq '.turns[] | {turn_index, user: {stt_transcript, stt_confidence, stt_provider}}'
```

Or via the current HTML console:

```
https://api.eduforequality.org/admin/review?pin=<SABI_ADMIN_PIN>
```

---

## 5. Promotion gate before any production swap

See [11. Documentation/SABI_PREPILOT_PRODUCT_QA_AND_ENDPOINT_SWITCHING_PLAYBOOK.md](../../11.%20Documentation/SABI_PREPILOT_PRODUCT_QA_AND_ENDPOINT_SWITCHING_PLAYBOOK.md)
for the full ladder. Minimum bar before flipping production to Intron:

1. **Offline replay**: at least 50 saved user-turn WAVs from production calls
   replayed through both lanes via `/admin/stt/intron-test`. Naira amounts
   and short literacy words ("rat/cat/mat", numerals) must come back at
   least as correct as the Groq baseline.
2. **Live canary**: at least 5 adult test calls through
   `direct-call-intron`. No increase in "I didn't catch that" loops. No
   increase in abrupt call endings.
3. **Latency**: P95 turn time within 300 ms of the Groq baseline.
4. **Rollback drill**: confirm `sed -i '/INTRON_API_KEY/d' .env && docker
   compose up -d sabi` restores Groq behaviour within one container cycle
   (~12 seconds).

---

## 6. Rollback (if production was ever flipped, NOT recommended yet)

The production lane reads `SABI_STT_PROVIDER` (default `auto`). To roll back
a hypothetical production flip:

```bash
ssh root@136.243.8.51
cd /opt/sabi/sabi-server
sed -i.bak '/^SABI_STT_PROVIDER=/d' .env
sed -i.bak '/^SABI_LITERACY_STT_PROVIDER=/d' .env
docker compose up -d sabi
curl -s http://127.0.0.1:8000/health
```

The next inbound call uses Groq/Whisper again. The Intron test lane on port
9020 keeps running.

---

## 7. Test that proves isolation

```bash
ssh root@136.243.8.51
cd /opt/sabi/sabi-server
docker compose exec -T sabi python intron_route_isolation_regression.py
```

All 18 checks must pass. The regression fails if:
- the dialplan loses either context,
- production and Intron AudioSocket ports collapse to the same port,
- `direct-call` accidentally starts originating into the Intron context,
- the fallback path or the bearer-auth pattern in `stt.py` is removed,
- per-turn sidecars stop persisting `stt_provider`.

Run this regression before and after any deploy that touches `stt.py`,
`main.py`, or the Asterisk dialplan.
