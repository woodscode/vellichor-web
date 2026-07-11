"""Saved setting presets — a named bundle of UI settings (engine, voice, loudness,
ambience, …) the user can reapply per kid/series. Stored in /data/presets.json.
Settings are an opaque dict written by the frontend and applied back by it."""
import json
import os
import time
import uuid

PATH = os.path.join("/data", "presets.json")


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _write(items):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, PATH)


def list_all():
    return _load()


def save(name: str, settings: dict, pid: str = None) -> dict:
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("Preset needs a name")
    if not isinstance(settings, dict):
        raise ValueError("Invalid settings")
    items = _load()
    # Update in place — by explicit id, else by matching name (case-insensitive)
    # — so re-saving overwrites rather than piling up duplicates.
    target = None
    if pid:
        target = next((p for p in items if p.get("id") == pid), None)
    if target is None:
        target = next((p for p in items
                       if p.get("name", "").lower() == name.lower()), None)
    if target is not None:
        target["name"] = name
        target["settings"] = settings
        target["updated"] = int(time.time())
        _write(items)
        return target
    rec = {"id": uuid.uuid4().hex[:12], "name": name, "settings": settings,
           "created": int(time.time())}
    items.append(rec)
    _write(items)
    return rec


def delete(pid: str) -> bool:
    items = _load()
    keep = [p for p in items if p.get("id") != pid]
    if len(keep) == len(items):
        return False
    _write(keep)
    return True
