"""TTS engine catalog.

Vellichor can render with more than one TTS backend. Each engine advertises how
it picks voices ("presets" = a fixed catalog like Kokoro's; "clone" = it mimics a
reference audio clip) and which expressive controls it supports, so the UI can
show the right knobs. Availability is detected at import time — a heavier engine
whose package isn't installed simply shows as unavailable rather than crashing.
"""
import importlib.util


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # noqa: BLE001
        return False


CHATTERBOX_OK = _installed("chatterbox")

# Order matters — first entry is the default. `controls` drives which extra UI
# knobs appear; `voice_mode` drives the voice picker's behaviour.
ENGINES = [
    {
        "id": "kokoro",
        "label": "Kokoro",
        "blurb": "Fast, lightweight, 54 preset voices. Great all-rounder.",
        "voice_mode": "presets",
        "controls": ["speed"],
        "available": True,
    },
    {
        "id": "chatterbox",
        "label": "Chatterbox (expressive)",
        "blurb": "Expressive TTS with an intensity dial and voice cloning. "
                 "Heavier — uses more VRAM and is slower than Kokoro.",
        "voice_mode": "clone",
        "controls": ["exaggeration"],
        "available": CHATTERBOX_OK,
    },
]

DEFAULT = "kokoro"


def get(engine_id: str):
    return next((e for e in ENGINES if e["id"] == engine_id), None)


def is_available(engine_id: str) -> bool:
    e = get(engine_id)
    return bool(e and e["available"])


def resolve(engine_id: str) -> str:
    """Return a usable engine id, falling back to the default if the requested
    one is unknown or unavailable."""
    return engine_id if is_available(engine_id) else DEFAULT


def list_ui():
    return {"engines": ENGINES, "default": DEFAULT}
