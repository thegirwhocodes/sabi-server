#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Whisper large-v3 Fine-tuning on AfriSpeech-200
# Nigerian-accented English — Full Pipeline
#
# This script:
#   1. Sets up Python virtual environment
#   2. Installs all dependencies
#   3. Stops GPU-using Docker containers (frees VRAM)
#   4. Runs fine-tuning (~6-10 hours)
#   5. Converts model to CTranslate2 (faster-whisper format)
#   6. Copies model to sabi-server
#   7. Restarts Docker containers with fine-tuned model
#
# Usage: bash run_training.sh
# Monitor: tail -f /opt/sabi/whisper-finetune/logs/training.log
# ─────────────────────────────────────────────────────────────────

set -e

WORKDIR="/opt/sabi/whisper-finetune"
VENV_DIR="$WORKDIR/venv"
SABI_DIR="/opt/sabi/sabi-server"
LOG_DIR="$WORKDIR/logs"
LOG_FILE="$LOG_DIR/training.log"

echo "============================================================"
echo "  Whisper Fine-tuning Pipeline"
echo "  $(date)"
echo "============================================================"

# ─── Create directories ───
mkdir -p "$WORKDIR/output" "$LOG_DIR"

# ─── Step 1: Python Virtual Environment ───
echo "[1/7] Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  Created new venv at $VENV_DIR"
else
    echo "  Existing venv found at $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel 2>&1 | tail -1

# ─── Step 2: Install Dependencies ───
echo "[2/7] Installing dependencies (this may take 10-15 minutes)..."
pip install -r "$WORKDIR/requirements.txt" 2>&1 | tail -5
echo "  Dependencies installed."

# Verify CUDA is accessible
python3 -c "import torch; print(f'  PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}')"
python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA NOT AVAILABLE — cannot fine-tune!'"

# ─── Step 3: Stop GPU Docker Containers ───
echo "[3/7] Stopping GPU Docker containers to free VRAM..."
cd "$SABI_DIR"

# Record which containers were running so we can restart them later
RUNNING_CONTAINERS=""
if docker compose ps --status running | grep -q sabi-server; then
    RUNNING_CONTAINERS="$RUNNING_CONTAINERS sabi"
fi
if docker compose ps --status running | grep -q chatterbox; then
    RUNNING_CONTAINERS="$RUNNING_CONTAINERS chatterbox-tts"
fi
if docker compose ps --status running | grep -q ollama; then
    RUNNING_CONTAINERS="$RUNNING_CONTAINERS ollama"
fi

echo "  Currently running GPU containers: $RUNNING_CONTAINERS"

if [ -n "$RUNNING_CONTAINERS" ]; then
    docker compose stop $RUNNING_CONTAINERS
    echo "  Stopped: $RUNNING_CONTAINERS"
else
    echo "  No GPU containers running."
fi

# Verify VRAM is free
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
echo ""

# ─── Step 4: Run Fine-tuning ───
echo "[4/7] Starting Whisper fine-tuning..."
echo "  Monitor progress: tail -f $LOG_FILE"
echo "  Expected duration: 6-10 hours"
echo "  Started at: $(date)"
echo ""

cd "$WORKDIR"
python3 finetune_whisper.py 2>&1 | tee -a "$LOG_FILE"

TRAIN_EXIT=$?

echo ""
echo "  Training finished at: $(date)"
echo "  Exit code: $TRAIN_EXIT"

if [ $TRAIN_EXIT -ne 0 ]; then
    echo "  ERROR: Training failed! Check $LOG_FILE"
    echo "[RECOVERY] Restarting Docker containers..."
    cd "$SABI_DIR"
    docker compose up -d $RUNNING_CONTAINERS
    exit 1
fi

# ─── Step 5: Verify Model Output ───
echo "[5/7] Verifying model output..."
CT2_DIR="/opt/sabi/sabi-server/models/whisper-nigerian-english-ct2"

if [ -f "$CT2_DIR/model.bin" ]; then
    echo "  CTranslate2 model found at $CT2_DIR"
    ls -lh "$CT2_DIR/"
else
    echo "  ERROR: CTranslate2 model not found at $CT2_DIR"
    echo "  Check the training log for conversion errors."
    echo "[RECOVERY] Restarting Docker containers with original model..."
    cd "$SABI_DIR"
    docker compose up -d $RUNNING_CONTAINERS
    exit 1
fi

# ─── Step 6: Update stt.py to use fine-tuned model ───
echo "[6/7] Updating stt.py to use fine-tuned model..."
# The stt.py inside Docker needs to reference /models/whisper-nigerian-english-ct2
# We mount the model directory as a Docker volume

# Backup original stt.py
cp "$SABI_DIR/stt.py" "$SABI_DIR/stt.py.backup"

# Update the model path in stt.py
python3 -c "
import re
with open('$SABI_DIR/stt.py', 'r') as f:
    content = f.read()

# Update default model_size to use our fine-tuned model path
content = content.replace(
    'model_size: str = \"large-v3\"',
    'model_size: str = \"/models/whisper-nigerian-english-ct2\"'
)

with open('$SABI_DIR/stt.py', 'w') as f:
    f.write(content)

print('  stt.py updated to use fine-tuned model.')
"

# ─── Step 7: Update docker-compose and restart ───
echo "[7/7] Updating Docker and restarting services..."

# Add model volume mount to docker-compose.yml if not already present
cd "$SABI_DIR"
if ! grep -q "whisper-nigerian-english" docker-compose.yml; then
    python3 -c "
import yaml
import sys

with open('docker-compose.yml', 'r') as f:
    compose = yaml.safe_load(f)

# Add volume mount for the fine-tuned model
sabi_service = compose.get('services', {}).get('sabi', {})
volumes = sabi_service.get('volumes', [])

model_volume = './models/whisper-nigerian-english-ct2:/models/whisper-nigerian-english-ct2:ro'
if model_volume not in volumes:
    volumes.append(model_volume)
    sabi_service['volumes'] = volumes
    compose['services']['sabi'] = sabi_service

    with open('docker-compose.yml', 'w') as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)
    print('  docker-compose.yml updated with model volume mount.')
else:
    print('  docker-compose.yml already has model volume mount.')
" 2>/dev/null || echo "  Note: PyYAML not available on host. Add volume mount manually."
fi

# Restart all previously-running containers
echo "  Restarting containers: $RUNNING_CONTAINERS"
docker compose up -d $RUNNING_CONTAINERS

echo ""
echo "============================================================"
echo "  FINE-TUNING PIPELINE COMPLETE!"
echo "  $(date)"
echo "============================================================"
echo ""
echo "  Model: $CT2_DIR"
echo "  Logs:  $LOG_FILE"
echo ""
echo "  Verify with:"
echo "    curl -X POST https://api.eduforequality.org/stt -F audio=@test.wav"
echo ""
echo "  VRAM check:"
echo "    nvidia-smi"
echo ""
