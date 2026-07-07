"""User pronunciation dictionary.

A simple word → spoken-form map applied to the text just before synthesis, so
character names and odd words come out right (e.g. "Hermione" → "Her-my-oh-nee").
Whole-word, case-insensitive. Stored in /data/pronunciations.json.
"""
import json
import os
import re

PATH = os.path.join("/data", "pronunciations.json")


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
        return [i for i in items if isinstance(i, dict) and i.get("from")]
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


def save(frm: str, to: str):
    """Add or update a rule (matched case-insensitively by `from`)."""
    frm = (frm or "").strip()
    to = (to or "").strip()
    if not frm:
        raise ValueError("Empty 'from' word")
    items = [i for i in _load() if i["from"].lower() != frm.lower()]
    items.append({"from": frm, "to": to})
    items.sort(key=lambda i: i["from"].lower())
    _write(items)
    return items


def delete(frm: str) -> bool:
    items = _load()
    keep = [i for i in items if i["from"].lower() != (frm or "").lower()]
    if len(keep) == len(items):
        return False
    _write(keep)
    return True


def apply(text: str) -> str:
    """Replace each dictionary word (whole-word, case-insensitive) in `text`."""
    if not text:
        return text
    for it in _load():
        frm, to = it["from"], it.get("to", "")
        # \b doesn't hug non-alphanumerics well; guard with lookarounds on word chars.
        text = re.sub(r"(?<!\w)" + re.escape(frm) + r"(?!\w)", to, text,
                      flags=re.IGNORECASE)
    return text
