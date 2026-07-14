#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Whisper candidate fine-tuning on mixed Nigerian/telephone English
#
# This script:
#   1. Sets up Python virtual environment
#   2. Installs all dependencies
#   3. Leaves production running unless an approved maintenance flag is set
#   4. Runs fine-tuning
#   5. Converts model to CTranslate2 (faster-whisper format)
#   6. Keeps the candidate isolated for held-out evaluation
#   7. Restarts only services explicitly stopped for the run
#
# Usage: bash run_training.sh
# Monitor: tail -f /opt/sabi/whisper-finetune/logs/training.log
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

WORKDIR="/opt/sabi/whisper-finetune"
VENV_DIR="$WORKDIR/venv"
SABI_DIR="/opt/sabi/sabi-server"
LOG_DIR="$WORKDIR/logs"
LOG_FILE="$LOG_DIR/training.log"
MODEL_NAME="${SABI_FINETUNE_MODEL:-openai/whisper-small}"
RUN_NAME="${SABI_FINETUNE_RUN_NAME:-${MODEL_NAME##*/}-ng-english-telephony-v1}"

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

# ─── Step 3: Preserve production by default ───
echo "[3/7] Checking GPU services..."
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

if [ "${SABI_FINETUNE_STOP_SERVICES:-0}" = "1" ] && [ -n "$RUNNING_CONTAINERS" ]; then
    docker compose stop $RUNNING_CONTAINERS
    echo "  Stopped: $RUNNING_CONTAINERS"
else
    echo "  Leaving production services running. Set SABI_FINETUNE_STOP_SERVICES=1 only for an approved maintenance window."
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
CT2_DIR="$WORKDIR/output/$RUN_NAME/ct2"

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

# ─── Step 6: Never auto-promote an unevaluated model ───
echo "[6/7] Keeping production STT unchanged pending gold-set evaluation..."
# The stt.py inside Docker needs to reference /models/whisper-nigerian-english-ct2
# We mount the model directory as a Docker volume

# ─── Step 7: Restart only if this run was explicitly allowed to stop services ───
echo "[7/7] Finalizing candidate..."
cd "$SABI_DIR"
if [ "${SABI_FINETUNE_STOP_SERVICES:-0}" = "1" ] && [ -n "$RUNNING_CONTAINERS" ]; then
    docker compose up -d $RUNNING_CONTAINERS
fi

echo ""
echo "============================================================"
echo "  FINE-TUNING PIPELINE COMPLETE!"
echo "  $(date)"
echo "============================================================"
echo ""
echo "  Candidate model: $CT2_DIR"
echo "  Logs:  $LOG_FILE"
echo ""
echo "  Verify with:"
echo "    curl -X POST https://api.eduforequality.org/stt -F audio=@test.wav"
echo ""
echo "  VRAM check:"
echo "    nvidia-smi"
echo ""
