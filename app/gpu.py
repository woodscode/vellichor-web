"""Serialize the two GPU consumers — Kokoro TTS and the Ollama Smart-cast model
— so they never fight over the GTX 1080's 8 GB of VRAM at the same time, and so
the VRAM is handed cleanly from one to the other.

The 1080 cannot hold both models at once: Kokoro sits resident on CUDA, leaving
too little free VRAM for llama3.2:3b, which then silently falls back to running
entirely on the CPU. Whichever consumer is about to run takes LOCK and evicts
the other from VRAM first, so it gets a full GPU offload instead of CPU fallback.
"""
import contextlib
import os
import threading

import requests

# Reentrant so a single thread can nest acquisitions safely; different threads
# (the conversion worker vs. a Smart-cast request) still serialize.
LOCK = threading.RLock()


class GpuBusy(Exception):
    """The GPU lock couldn't be taken within the wait window — a conversion is
    using the card. Interactive endpoints surface this as a 503 rather than
    parking a FastAPI threadpool worker for the (possibly hours-long) job."""


@contextlib.contextmanager
def busy_guard(timeout: float = 3.0):
    """Acquire LOCK for a short *interactive* task (preview / voice sample /
    Smart cast), or give up fast. A running conversion holds LOCK for its whole
    synth phase; without a bounded wait, repeated preview clicks would block
    every threadpool worker behind it and hang the entire app."""
    if not LOCK.acquire(timeout=timeout):
        raise GpuBusy("The GPU is busy with a conversion — try again in a moment.")
    try:
        yield
    finally:
        LOCK.release()

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("SMARTCAST_MODEL", "llama3.2:3b")


def release_kokoro():
    """Drop Kokoro's cached pipelines and free its VRAM (so Ollama can offload
    to the GPU instead of falling back to CPU)."""
    from tts import ENGINE
    ENGINE.unload()


def release_ollama():
    """Ask Ollama to evict the model from VRAM immediately (keep_alive=0) so
    Kokoro can reclaim the GPU. No-op/quick if the model isn't loaded."""
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": MODEL, "keep_alive": 0}, timeout=10)
    except requests.RequestException:
        pass
