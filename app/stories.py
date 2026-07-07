"""Saved story drafts — a "My Stories" library so a good story isn't lost.
Stored in /data/stories.json: [{id, title, text, created, updated}]."""
import json
import os
import time
import uuid

PATH = os.path.join("/data", "stories.json")


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
    """Metadata only (no full text) — newest first."""
    return [{"id": s["id"], "title": s.get("title") or "Untitled",
             "chars": len(s.get("text", "")), "updated": s.get("updated", 0)}
            for s in sorted(_load(), key=lambda x: x.get("updated", 0), reverse=True)]


def get(sid: str):
    for s in _load():
        if s["id"] == sid:
            return s
    return None


def save(sid: str, title: str, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to save")
    title = (title or "").strip()[:120] or "Untitled"
    items = _load()
    now = int(time.time())
    for s in items:
        if sid and s["id"] == sid:          # update existing
            s.update(title=title, text=text, updated=now)
            _write(items)
            return {"id": s["id"], "title": title, "updated": now}
    sid = uuid.uuid4().hex[:12]             # new
    items.append({"id": sid, "title": title, "text": text,
                  "created": now, "updated": now})
    _write(items)
    return {"id": sid, "title": title, "updated": now}


def delete(sid: str) -> bool:
    items = _load()
    keep = [s for s in items if s["id"] != sid]
    if len(keep) == len(items):
        return False
    _write(keep)
    return True
