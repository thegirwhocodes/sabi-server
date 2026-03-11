# -----------------------------------------------------------
# Afro-TTS Docker Image
# African-accented English TTS using intronhealth/afro-tts
# Base: NVIDIA CUDA 12.1 + Ubuntu 22.04
# -----------------------------------------------------------
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Install PyTorch with CUDA 12.1 support first (separate layer for caching)
RUN pip install --no-cache-dir \
    torch==2.2.2+cu121 \
    torchaudio==2.2.2+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Install TTS and other dependencies
COPY requirements.txt .

# Step 1: Install coqpit-config FIRST (the forked version coqui-tts requires)
RUN pip install --no-cache-dir coqpit-config

# Step 2: Install coqui-tts without deps (prevents PyTorch override)
RUN pip install --no-cache-dir --no-deps coqui-tts

# Step 3: Install trainer without deps (prevents it pulling original coqpit)
RUN pip install --no-cache-dir --no-deps trainer

# Step 4: Install all other dependencies
RUN pip install --no-cache-dir \
    fastapi==0.115.6 \
    "uvicorn[standard]==0.34.0" \
    python-multipart==0.0.20 \
    "huggingface-hub>=0.20.0" \
    "scipy>=1.11.2" \
    "soundfile>=0.12.0" \
    "numpy<2.0.0" \
    "pydantic>=2.0.0" \
    transformers librosa inflect pypinyin g2pkk jamo gruut num2words anyascii

# Step 5: Verify coqpit-config is installed and original coqpit is NOT
RUN pip uninstall -y coqpit 2>/dev/null; \
    pip install --no-cache-dir coqpit-config && \
    python -c "from TTS.tts.configs.xtts_config import XttsConfig; print('TTS import OK')"

# Download the Afro-TTS model at build time (6GB, avoids runtime download)
# This creates a cached layer so rebuilds don't re-download
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download( \
    repo_id='intronhealth/afro-tts', \
    local_dir='/app/models/afro-tts', \
    allow_patterns=['*.pth', '*.json', 'audios/*'] \
)"

# Create directories
RUN mkdir -p /app/reference_audio /app/models

# Copy the bundled reference audio as default voice
RUN cp /app/models/afro-tts/audios/reference_accent.wav /app/reference_audio/default.wav

# Copy application code
COPY server.py .

# Environment defaults
ENV AFRO_TTS_MODEL_DIR=/app/models/afro-tts
ENV AFRO_TTS_REFERENCE_DIR=/app/reference_audio
ENV AFRO_TTS_DEFAULT_SPEAKER=default
ENV AFRO_TTS_MAX_TEXT_LENGTH=2000

EXPOSE 8001

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
