"""User-recorded / uploaded voice references ("My Voices").

Chatterbox clones a voice zero-shot from a short clip — there's no training. So a
"saved voice" is just a cleaned reference clip on disk plus a name. We normalize
every clip to mono 24 kHz with light loudness levelling (good, consistent cloning
input) and keep a small JSON index. Stored under /data/voices so it persists.
"""
import json
import os
import subprocess
import time
import uuid

VOICES_DIR = "/data/voices"
INDEX = os.path.join(VOICES_DIR, "voices.json")
SR = 24000


def _load():
    try:
        with open(INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _write(items):
    os.makedirs(VOICES_DIR, exist_ok=True)
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, INDEX)


def list_all():
    """Public list (no filesystem paths) for the UI."""
    return [{"id": v["id"], "name": v["name"], "created": v.get("created", 0)}
            for v in _load()]


def path_for(vid: str):
    """Resolve a saved-voice id to its clip path (or None)."""
    if not vid:
        return None
    for v in _load():
        if v["id"] == vid and os.path.exists(v.get("path", "")):
            return v["path"]
    return None


def save(name: str, src_path: str) -> dict:
    """Normalize `src_path` (any ffmpeg-readable audio, e.g. a webm recording) to
    a mono 24 kHz wav, store it, and index it. Returns the public record."""
    os.makedirs(VOICES_DIR, exist_ok=True)
    vid = uuid.uuid4().hex[:12]
    out = os.path.join(VOICES_DIR, f"{vid}.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", src_path, "-ac", "1", "-ar", str(SR),
         "-af", "highpass=f=60,loudnorm=I=-20:TP=-2", out],
        check=True, capture_output=True,
    )
    rec = {"id": vid, "name": (name or "My voice").strip()[:60] or "My voice",
           "path": out, "created": int(time.time())}
    items = _load()
    items.append(rec)
    _write(items)
    return {"id": rec["id"], "name": rec["name"], "created": rec["created"]}


def delete(vid: str) -> bool:
    items = _load()
    keep, removed = [], False
    for v in items:
        if v["id"] == vid:
            removed = True
            try:
                os.remove(v.get("path", ""))
            except OSError:
                pass
        else:
            keep.append(v)
    if removed:
        _write(keep)
    return removed
