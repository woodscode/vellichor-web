"""AI-powered cast detection via a local Ollama model.

The model assigns a speaker to each quoted line; we keep narration handling
deterministic and only trust the LLM for "who said this quote". The result is
emitted as [Name]-tagged text so it flows through the normal markup path.
"""
import json
import os
import re
import requests

import cast as castmod
import gpu

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("SMARTCAST_MODEL", "llama3.2:3b")
MAX_CHARS = 60000          # cap so a huge upload can't hang the request
BATCH_CHARS = 5000
NARRATOR = castmod.NARRATOR
QUOTE_SPAN = castmod.QUOTE_SPAN

PROMPT = """You are an expert at identifying who speaks each line of dialogue in a story.

Read this passage carefully:

{passage}

Here are the quoted lines, in order:
{quotes}

For EACH quoted line, decide who says it. Use evidence from the text:
- A dialogue tag names the speaker: "...," said Mia -> Mia; she whispered -> the
  female character just established; it rumbled -> the non-human just mentioned.
- A split quote joined by a tag ("Because," said Mia, "he is lost.") is ONE
  speaker (Mia) for both halves.
- Consecutive quotes in the SAME paragraph separated only by a narration beat
  about that speaker ("...," he decided. "And besides...") are the SAME speaker
  continuing — do NOT switch speakers unless the text clearly shows someone
  else now replies.
- With no tag, infer from who is being addressed and what makes sense; untagged
  exchanges often (not always) alternate between the two speakers present.

Return ONLY JSON:
{{"speakers": ["<name for line 1>", "<name for line 2>", ...],
  "characters": [{{"name": "<Name>", "gender": "male"|"female"|"unknown"}}]}}
Use the character's name exactly as written in the passage; keep names consistent."""


def available() -> bool:
    """True if Ollama is reachable and the model is pulled."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return False
        base = MODEL.split(":")[0]
        return any(base in m.get("name", "") for m in r.json().get("models", []))
    except requests.RequestException:
        return False


def _ask(passage: str, quotes):
    body = {
        "model": MODEL,
        "prompt": PROMPT.format(
            passage=passage,
            quotes="\n".join(f'{i + 1}: "{q}"' for i, q in enumerate(quotes))),
        "stream": False,
        "format": "json",
        "keep_alive": "30s",
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=90)
    r.raise_for_status()
    return json.loads(r.json()["response"])


def _batches(text: str):
    paras = re.split(r"\n\s*\n", text)
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > BATCH_CHARS:
            out.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        out.append(cur)
    return out


def _clean_name(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:40] or "Character"


def _analyze_batches(text: str, segments: list, char_gender: dict):
    """Run the Ollama attribution batch-by-batch, appending (speaker, body)
    tuples to `segments` and learned genders to `char_gender`. Assumes the GPU
    lock is held by the caller."""
    for batch in _batches(text):
        quotes = [m.group(1) for m in QUOTE_SPAN.finditer(batch)]
        if not quotes:
            if batch.strip():
                segments.append((NARRATOR, batch.strip()))
            continue
        speakers = []
        try:
            data = _ask(batch, quotes)
            speakers = data.get("speakers", []) or []
            for c in data.get("characters", []):
                name = _clean_name(c.get("name"))
                g = c.get("gender")
                if name and g in ("male", "female"):
                    char_gender[name.lower()] = g
        except Exception:  # noqa: BLE001 — fall back to last-speaker heuristic
            speakers = []
        idx, qi, last = 0, 0, None
        for m in QUOTE_SPAN.finditer(batch):
            pre = batch[idx:m.start()]
            if pre.strip():
                segments.append((NARRATOR, pre.strip()))
            sp = _clean_name(speakers[qi]) if qi < len(speakers) else (last or "Character")
            last = sp
            segments.append((sp, m.group(1).strip()))
            idx, qi = m.end(), qi + 1
        if batch[idx:].strip():
            segments.append((NARRATOR, batch[idx:].strip()))


def analyze(text: str):
    """Returns {"tagged": <[Name]-tagged text>, "characters": [...]}."""
    text = (text or "").strip()[:MAX_CHARS]
    segments, char_gender = [], {}

    # Serialize against TTS and free Kokoro's VRAM first, so Ollama offloads the
    # model to the GPU instead of falling back to (very slow) CPU inference.
    with gpu.busy_guard():
        gpu.release_kokoro()
        try:
            _analyze_batches(text, segments, char_gender)
        finally:
            gpu.release_ollama()    # hand the VRAM back to Kokoro

    # Canonicalize speaker names so casing variants ("The dragon" / "the dragon")
    # collapse to one character (and therefore one voice).
    canon = {}
    for sp, _ in segments:
        canon.setdefault(sp.lower(), sp)
    segments = [(canon[sp.lower()], body) for sp, body in segments]

    tagged = "\n".join(f"[{sp}] {body}" for sp, body in segments)

    agg = {}
    for sp, body in segments:
        d = agg.setdefault(sp, {"name": sp, "lines": 0, "chars": 0, "sample": ""})
        d["lines"] += 1
        d["chars"] += len(body)
        if not d["sample"]:
            d["sample"] = body[:90]
    chars = sorted(agg.values(), key=lambda d: (d["name"] != NARRATOR, -d["chars"]))
    for c in chars:
        if c["name"].lower() == NARRATOR.lower():
            c["gender"] = None
        else:
            c["gender"] = (char_gender.get(c["name"].lower())
                           or castmod._infer_gender(c["name"], text))
    return {"tagged": tagged, "characters": chars}
