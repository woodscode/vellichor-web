"""Server-side "Book library" — a managed folder of source files (epub, pdf,
txt, md, docx) that can be converted one-by-one or in a batch.

The folder lives under /data (so it persists and is reachable on the appdata
share): dropping files straight into it via SMB works just as well as uploading
through the UI. list_all() reconciles the on-disk folder with a small JSON index
on every read, so drop-ins appear and deletions disappear automatically.
"""
import json
import os
import re
import shutil
import time
import uuid

from extract import SUPPORTED_EXTS

BOOKS_DIR = "/data/books"
INDEX = os.path.join(BOOKS_DIR, ".books.json")


def _load():
    try:
        with open(INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _write(items):
    os.makedirs(BOOKS_DIR, exist_ok=True)
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, INDEX)


def _public(it: dict) -> dict:
    return {"id": it["id"], "name": it["name"], "filename": it["filename"],
            "ext": os.path.splitext(it["filename"])[1].lower(),
            "size": it.get("size", 0), "added": it.get("added", 0)}


def _reconcile(items):
    """Sync the index against what's actually on disk: keep ids for files still
    present, mint ids for new drop-ins, and forget entries whose file is gone."""
    os.makedirs(BOOKS_DIR, exist_ok=True)
    by_name = {it["filename"]: it for it in items}
    out = []
    for fn in sorted(os.listdir(BOOKS_DIR)):
        full = os.path.join(BOOKS_DIR, fn)
        if fn.startswith(".") or not os.path.isfile(full):
            continue
        if os.path.splitext(fn)[1].lower() not in SUPPORTED_EXTS:
            continue
        it = by_name.get(fn) or {
            "id": uuid.uuid4().hex[:12], "filename": fn,
            "name": os.path.splitext(fn)[0][:120], "added": int(time.time())}
        it["size"] = os.path.getsize(full)
        out.append(it)
    return out


def list_all():
    items = _load()
    recon = _reconcile(items)
    if recon != items:
        _write(recon)
    return [_public(it) for it in
            sorted(recon, key=lambda x: x.get("name", "").lower())]


def _safe(filename: str) -> str:
    base, ext = os.path.splitext(os.path.basename(filename))
    base = re.sub(r"[^\w\s.-]", "", base).strip()
    base = re.sub(r"\s+", " ", base)[:120] or "book"
    return base + ext.lower()


def _unique(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    cand, n = filename, 1
    while os.path.exists(os.path.join(BOOKS_DIR, cand)):
        n += 1
        cand = f"{base} ({n}){ext}"
    return cand


def save(src_path: str, original_filename: str) -> dict:
    """Copy an uploaded file into the library under a safe, unique name and
    index it. Returns the public record. Raises ValueError on an unsupported
    extension."""
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type: {ext}")
    os.makedirs(BOOKS_DIR, exist_ok=True)
    fn = _unique(_safe(original_filename))
    shutil.copyfile(src_path, os.path.join(BOOKS_DIR, fn))
    items = _reconcile(_load())
    _write(items)
    rec = next((it for it in items if it["filename"] == fn), None)
    return _public(rec) if rec else {}


def get(bid: str):
    if not bid:
        return None
    for it in _reconcile(_load()):
        if it["id"] == bid:
            return _public(it)
    return None


def path_for(bid: str):
    """Resolve a book id to its source-file path (or None)."""
    if not bid:
        return None
    for it in _reconcile(_load()):
        p = os.path.join(BOOKS_DIR, it["filename"])
        if it["id"] == bid and os.path.exists(p):
            return p
    return None


def delete(bid: str) -> bool:
    items = _reconcile(_load())
    keep, removed = [], False
    for it in items:
        if it["id"] == bid:
            removed = True
            try:
                os.remove(os.path.join(BOOKS_DIR, it["filename"]))
            except OSError:
                pass
        else:
            keep.append(it)
    if removed:
        _write(keep)
    return removed
