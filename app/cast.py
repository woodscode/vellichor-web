"""Multi-voice / character segmentation.

Turns a chapter of prose into an ordered list of (speaker, text) spans using:
  1. Explicit [Name] markup  (authoritative — set by the author)
  2. Quote detection + dialogue-tag attribution  (automatic fallback)

The result is mapped to per-speaker voices for synthesis.
"""
import re

NARRATOR = "Narrator"

SPEECH_VERBS = (
    r"said|asked|replied|whispered|shouted|cried|murmured|exclaimed|answered|"
    r"called|muttered|growled|laughed|sighed|continued|added|began|yelled|"
    r"gasped|hissed|roared|squeaked|chirped|boomed|sang|snapped|wondered|"
    r"declared|insisted|warned|teased|grumbled|giggled|sobbed|bellowed"
)

# [Name] tag (line-leading or inline), optional trailing colon
TAG = re.compile(r"\[([^\]\n]{1,40})\]\s*:?\s*")
# Double quotes only (straight or curly) — single quotes collide with contractions
QUOTE_SPAN = re.compile(r"[“\"]([^“”\"]{1,2000}?)[”\"]")
_VERB_AFTER = re.compile(r"^\s*[,]?\s*(?:" + SPEECH_VERBS + r")\s+([A-Z][\w'-]+)")
_VERB_BEFORE = re.compile(r"([A-Z][\w'-]+)\s+(?:" + SPEECH_VERBS + r")\s*[:,]?\s*$")


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "")).strip()


def has_markup(text: str) -> bool:
    return bool(TAG.search(text))


def _segment_markup(text: str):
    matches = list(TAG.finditer(text))
    if not matches:
        return None
    segs = []
    if matches[0].start() > 0:
        lead = text[:matches[0].start()].strip()
        if lead:
            segs.append((NARRATOR, lead))
    for i, m in enumerate(matches):
        name = _norm(m.group(1)) or NARRATOR
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if body:
            segs.append((name, body))
    return segs


def _attribute(after: str, before: str):
    m = _VERB_AFTER.match(after)
    if m:
        return _norm(m.group(1))
    m = _VERB_BEFORE.search(before)
    if m:
        return _norm(m.group(1))
    return None


def _segment_auto(text: str):
    segs, idx, last = [], 0, None
    for m in QUOTE_SPAN.finditer(text):
        pre = text[idx:m.start()]
        if pre.strip():
            segs.append((NARRATOR, pre.strip()))
        after = text[m.end():m.end() + 70]
        before = text[max(0, m.start() - 70):m.start()]
        who = _attribute(after, before) or last or "Character"
        last = who
        segs.append((who, m.group(1).strip()))
        idx = m.end()
    tail = text[idx:]
    if tail.strip():
        segs.append((NARRATOR, tail.strip()))
    return segs or [(NARRATOR, text.strip())]


def segment(text: str):
    """List of (speaker, text) in reading order."""
    return _segment_markup(text) if has_markup(text) else _segment_auto(text)


def detect_characters(text: str):
    """Aggregate speakers for the UI cast panel. Narrator first, then by size."""
    agg = {}
    for sp, body in segment(text):
        d = agg.setdefault(sp, {"name": sp, "lines": 0, "chars": 0, "sample": ""})
        d["lines"] += 1
        d["chars"] += len(body)
        if not d["sample"]:
            d["sample"] = body[:90]
    return sorted(agg.values(), key=lambda d: (d["name"] != NARRATOR, -d["chars"]))


def build_segments(text: str, narrator_voice: str, cast_map: dict):
    """Resolve each span to a concrete voice. cast_map: {name(lower): voice_id}."""
    cmap = {(_norm(k).lower()): v for k, v in (cast_map or {}).items() if v}
    out = []
    for sp, body in segment(text):
        key = _norm(sp).lower()
        if key == NARRATOR.lower():
            voice = cmap.get(key) or narrator_voice
        else:
            voice = cmap.get(key) or narrator_voice
        out.append({"speaker": sp, "voice": voice, "text": body})
    return out
