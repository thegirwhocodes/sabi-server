FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Install Python + ffmpeg (for audio processing)
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt requests

# Download Whisper model at build time (avoids download at runtime)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')"

# Copy application code
COPY . .

# Create audio cache directory
RUN mkdir -p audio_cache

# 8000 = FastAPI, 4573 = FastAGI fallback, 9019 = AudioSocket realtime media
EXPOSE 8000 4573 9019

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
