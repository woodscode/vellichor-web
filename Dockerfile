FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/data/hf-cache \
    PYTHONPATH=/app

# ffmpeg = audio encoding/m4b assembly; espeak-ng = Kokoro G2P fallback /
# non-English phonemization; libsndfile1 = soundfile backend.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg espeak-ng libsndfile1 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CUDA 12.4 PyTorch — still supports the GTX 1080 (Pascal, sm_61). Pinned to
# 2.6.0 to satisfy chatterbox-tts's exact torch pin; Pascal was only dropped from
# the CUDA 12.8 builds of torch 2.8+, so 2.6.0+cu124 keeps the 1080 working.
RUN pip install --retries 10 --timeout 300 torch==2.6.0 torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ /app/

EXPOSE 7777
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD curl -fsS http://localhost:7777/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7777"]
