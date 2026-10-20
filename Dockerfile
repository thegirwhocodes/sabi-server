# CPU-only base. The production box has no GPU, torch is the +cpu wheel, and
# faster-whisper runs on CPU, so the CUDA runtime image was only dead weight.
FROM python:3.10-slim-bookworm

# ffmpeg converts TTS audio to Asterisk's 8 kHz format; curl backs health checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt requirements.lock.txt ./
# The lock file pins every transitive package to what production runs, so a
# rebuild installs the same versions instead of whatever is newest that day.
RUN pip install --no-cache-dir -r requirements.txt requests -c requirements.lock.txt

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
