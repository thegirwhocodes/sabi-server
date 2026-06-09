#!/bin/bash
# ============================================================
# Afro-TTS Deployment Script
# Deploy to Hetzner GPU server (136.243.8.51)
# ============================================================
set -e

SERVER="root@136.243.8.51"
REMOTE_DIR="/opt/sabi/sabi-server"

echo "=== Deploying Afro-TTS to Hetzner server ==="

# 1. Copy the afro-tts directory to the server
echo "[1/5] Uploading Afro-TTS files..."
rsync -avz --progress \
    "$(dirname "$0")/" \
    "${SERVER}:${REMOTE_DIR}/afro-tts/"

# 2. Copy updated docker-compose.yml
echo "[2/5] Uploading docker-compose.yml..."
scp "$(dirname "$0")/../docker-compose.yml" "${SERVER}:${REMOTE_DIR}/docker-compose.yml"

# 3. Create reference_audio directory on server if needed
echo "[3/5] Creating directories..."
ssh "${SERVER}" "mkdir -p ${REMOTE_DIR}/afro-tts/reference_audio"

# 4. Build the Docker image (this downloads the 6GB model)
echo "[4/5] Building Afro-TTS Docker image (this will take 10-20 minutes on first build)..."
ssh "${SERVER}" "cd ${REMOTE_DIR} && docker compose build afro-tts"

# 5. Start the service
echo "[5/5] Starting Afro-TTS service..."
ssh "${SERVER}" "cd ${REMOTE_DIR} && docker compose up -d afro-tts"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Check status:  ssh ${SERVER} 'cd ${REMOTE_DIR} && docker compose logs -f afro-tts'"
echo "Health check:  ssh ${SERVER} 'curl -s http://localhost:8001/health | python3 -m json.tool'"
echo "Test TTS:      ssh ${SERVER} 'curl -s -X POST http://localhost:8001/tts -H \"Content-Type: application/json\" -d \"{\\\"text\\\": \\\"Hello, I am Sabi.\\\"}\" -o /tmp/test_afro.wav && echo \"Saved to /tmp/test_afro.wav\"'"
echo ""
