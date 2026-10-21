# Removed components — institutional memory

Every component taken out of the Sabi phone server, why it existed, why it
went, and exactly how to bring it back. Add a row whenever something is
removed. Nothing here is lost: every item is re-downloadable or rebuildable,
and the column "How to restore" says how.

Server: Vultr Johannesburg `139.84.246.103` (Reserved IP "sabi-phone-line"),
plan vc2-2c-4gb, code at `/opt/sabi/sabi-server`, deployed branch
`server-snapshot-2026-08-20` of `thegirwhocodes/sabi-server`.

---

## 2026-10-19 — slim rebuild (session 6d4de6ca)

Context: the 65 GB disk filled to 100% (found Oct 19; it had also filled on
Oct 12). Call recordings were only 232 MB. The space was GPU-era tooling
carried over from the Hetzner GEX44 GPU box (RTX 4000, Mar–Sep 2026), which
was suspended for non-payment on Sep 4 2026. The Vultr box is CPU-only.

| # | What was removed | Size | What it was for | Why removed | Can we get it back? / How |
|---|---|---|---|---|---|
| 1 | **Ollama container** `sabi-ollama` (image `ollama/ollama:latest`) and its `ollama` service in `docker-compose.yml`, plus the `OLLAMA_URL` env line and `depends_on: ollama` | 9.19 GB image | Offline, last-resort LLM for the *turn-based* lane: Llama 3.1 8B (`llama3.1:8b-instruct-q4_K_M`). Chain was Cerebras → Claude Haiku → Groq → **Ollama**, so a lesson could continue if every cloud LLM was down. Added spring 2026 on the GPU box. | It had **no model installed** on Vultr (`ollama list` empty, volume 32 KB), so it could never answer. An 8B model needs ~5 GB RAM; this box has 4 GB. The compose file also asked for an NVIDIA GPU that doesn't exist. `llm.py` already catches Ollama failures, so removing it changes nothing at runtime. | **Yes.** Re-add the `ollama` service from `docker-compose.yml.bak-20261019` (on the box) or git history before this commit, then `docker compose up -d ollama` and `docker exec sabi-ollama ollama pull llama3.1:8b-instruct-q4_K_M` (~4.9 GB download). Needs a box with ≥8 GB RAM (ideally a GPU). |
| 2 | **NVIDIA CUDA base image** `nvidia/cuda:12.1.0-runtime-ubuntu22.04` in `Dockerfile` → replaced by `python:3.10-slim-bookworm` | several GB of the 12.4 GB image | GPU acceleration for local Whisper STT and Chatterbox TTS on the Hetzner RTX 4000. | No GPU on Vultr. `torch` was already the `+cpu` wheel and faster-whisper runs `device=cpu` (`SABI_LOCAL_WHISPER_DEVICE=cpu`), so CUDA was unused weight. Python stays 3.10 (same as before). | **Yes.** Restore the `FROM` line from `Dockerfile.bak-20261019` (on the box) or git history. Only worth it on a GPU server. |
| 3 | **API keys baked into the image.** There was no `.dockerignore`, so `COPY . .` copied `secrets/` and `.env` into the image (`/app/secrets/*` was readable inside the container). | small | Nothing — this was an accident. The app reads keys from Docker secrets at `/run/secrets` (`secret_loader.py`), falling back to env vars. | Security: anyone with the image had every key. Added `.dockerignore`. | Not applicable — keys still reach the container through Docker secrets exactly as before. |
| 4 | **Files excluded from the image** (NOT deleted — still in the repo and in `/opt/sabi/sabi-server`): `whisper-finetune/`, `voice-auditions/`, `chatterbox-tts/`, `afro-tts/`, `fake_child_harness/outputs/`, loose `*.wav`/`*.mp3` test clips, `*.bak*`, `audio_cache/` (mounted as a volume anyway) | ~25 MB in image | Research and training material: Nigerian-English Whisper fine-tune scripts, the Aug 13 Gemini voice auditions, the self-hosted Chatterbox/Afro-TTS servers (GPU, run as separate containers on Hetzner), fake-child test harness output. | The running server never imports them (checked by grep, Oct 19). | **Yes**, they are still on disk and in git. Remove the line from `.dockerignore` if one is ever needed inside the container. |
| 5 | **Docker build cache** | 13.54 GB | Speeds up repeat builds. Built up from every rebuild on the box (several on Sep 6 for prompt and literacy-lane changes). | Disposable. | **Yes**, regenerated automatically by the next `docker compose build`. Prune after big builds: `docker builder prune -af`. |
| 6 | **Old production image** `sabi-server-sabi:pre-slim-20261019` (ID `3f33a64bbd5c`) | 12.4 GB | The image that served calls Sep 6 – Oct 19. | Replaced by the slim image. **Kept as a rollback until the slim image has handled real calls**, then deleted. | **Yes.** Rollback while it exists: `docker tag sabi-server-sabi:pre-slim-20261019 sabi-server-sabi:latest && docker compose up -d sabi`. After deletion: rebuild from `Dockerfile.bak-20261019` / git (~15 min). |
| 7 | apt package cache, systemd journal trimmed to 50 MB | <0.5 GB | Package downloads, old logs. | Disposable. | Regenerated automatically. |

## 2026-10-20 — recordings retention (session 6d4de6ca)

| # | What | What it was for | Why | Can we get it back? / How |
|---|---|---|---|---|
| 8 | Call audio, per-turn audio, call records, sidecars older than **14 days** in the `sabi-server_shared_audio` volume | Evidence for review (`/admin/calls`, `/admin/feedback`), pilot evidence, future STT training data | Nothing ever deleted them; they would refill the disk. Now moved nightly to Google Drive. | **Yes, every file is in Drive** at `Sabi Call Recordings/shared_audio` (naomi.ivie04@gmail.com), uploaded and checksum-verified before local deletion. Restore: `rclone copy "gdrive:Sabi Call Recordings/shared_audio" <volume path>`. Note: the admin console only lists what is on the server, so calls older than 14 days no longer appear there. |

### Deliberately NOT removed
- **Whisper large-v3** baked in the image (`/root/.cache/huggingface`, ~2.9 GB). Still used by the turn-based fallback lane and the numeric sidecar's second opinion. Removing it would change behavior. (It is slow on 2 CPUs — ~11–14 s per clip — a candidate to replace with Groq-only later, as a separate decision.)
- **`/swapfile` (6.4 GB)**. Could shrink to ~2 GB now that RAM is 4 GB. Separate decision.
- **`sabi_literacy_prompt.md` at the repo root on the box.** It differs from `prompts/sabi_literacy_prompt.md` (the file the code loads). Kept until someone confirms which version is wanted.
- **Vultr instance `sabi-dev`** (London, vc2-1c-1gb, ~$5/mo, created Oct 12, IP 78.141.233.143). Purpose unconfirmed; awaiting Naomi.

## 2026-10-20 — dead AI providers on the fallback lane (session 6d4de6ca)

| # | What | What it was for | Why | Can we get it back? / How |
|---|---|---|---|---|
| 9 | `CEREBRAS_API_KEY` commented out in `/opt/sabi/sabi-server/.env` (backup `.env.bak-20261020`) | First, fastest LLM on the turn-based lane (Llama 3.3 70B on Cerebras) | Key returns 401; every call wasted a round trip before falling through | Put a valid key back and uncomment the line, then `docker compose up -d sabi`. |
| 10 | Groq default model `llama-3.3-70b-versatile` → `openai/gpt-oss-120b` (with `reasoning_effort: low`) in `llm.py` | Groq is the fallback-lane brain and the per-turn "is this an answer?" check | Groq retired Llama 3.3; every Groq chat call returned 404, so with Claude's key also rejected (401) the lane answered "Sorry, I had a little problem" on every turn (Lagos caller …4773, Oct 20 07:4x UTC) | Set env `GROQ_MODEL` to any model in Groq's `/models` list. Without low reasoning, gpt-oss returns empty text at Sabi's 80–200 token limits. |
