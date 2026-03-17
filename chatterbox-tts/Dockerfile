# -----------------------------------------------------------
# Chatterbox Turbo TTS Docker Image
# Emotionally expressive Nigerian English TTS for Sabi
# Base: NVIDIA CUDA 12.1 + Ubuntu 22.04 + Python 3.11
# -----------------------------------------------------------
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies + Python 3.11
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install pip for Python 3.11
RUN python3.11 -m ensurepip --upgrade \
    && python3.11 -m pip install --no-cache-dir --upgrade pip

WORKDIR /app

# Install Chatterbox TTS (brings its own torch + torchaudio)
RUN pip install --no-cache-dir chatterbox-tts

# Remove torchvision (not needed, causes operator conflict)
RUN pip uninstall -y torchvision 2>/dev/null || true

# Install server dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download model weights at build time (requires HF_TOKEN as build arg)
ARG HF_TOKEN=""
RUN if [ -n "$HF_TOKEN" ]; then \
        HF_TOKEN=$HF_TOKEN python -c "\
from chatterbox.tts_turbo import ChatterboxTurboTTS; \
model = ChatterboxTurboTTS.from_pretrained(device='cpu'); \
print('Model downloaded successfully')"; \
    else \
        echo 'No HF_TOKEN provided, model will download on first run'; \
    fi

# Create directories
RUN mkdir -p /app/reference_audio

# Copy application code
COPY server.py .

# Environment defaults
ENV CHATTERBOX_REFERENCE_DIR=/app/reference_audio
ENV CHATTERBOX_DEFAULT_SPEAKER=bukola
ENV CHATTERBOX_MAX_TEXT_LENGTH=2000

EXPOSE 8001

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
