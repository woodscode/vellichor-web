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

# CUDA 12.4 PyTorch — supports the GTX 1080 (Pascal, sm_61).
RUN pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ /app/

EXPOSE 7777
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD curl -fsS http://localhost:7777/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7777"]
