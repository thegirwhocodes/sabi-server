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

# Open audio-native endpoint detector used after Silero finds a pause. Pin the
# exact Hugging Face revision and checksum so production builds are repeatable.
RUN mkdir -p /app/models && python -c "import hashlib, pathlib, urllib.request; url='https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/f766f81d3cfdf7737ac64aad813d91bbfd56bf93/smart-turn-v3.2-cpu.onnx'; path=pathlib.Path('/app/models/smart-turn-v3.2-cpu.onnx'); urllib.request.urlretrieve(url, path); digest=hashlib.sha256(path.read_bytes()).hexdigest(); expected='2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f'; assert digest == expected, (digest, expected)"

# Download Whisper model at build time (avoids download at runtime)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')"

# Copy application code
COPY . .

# Create audio cache directory
RUN mkdir -p audio_cache

# 8000 = FastAPI, 4573 = FastAGI fallback, 9019 = AudioSocket realtime media
EXPOSE 8000 4573 9019

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
