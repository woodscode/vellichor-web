"""Inline narration directives — a small, reserved markup we interpret
ourselves (Kokoro has no SSML / emotion control).

Supported inside the story text:
  [pause]         insert a short silence (default 0.8s)
  [pause 3s]      insert 3 seconds of silence  ([pause 500ms] / [pause 2] also work)
  [beat]          insert a brief silence (0.4s)
  [slow] [slower] read the following prose more slowly
  [fast] [faster] read the following prose more quickly
  [normal]        return to the base reading speed

Speed directives set a multiplier that applies to everything after them (until
the next speed directive) and reset at the start of each chapter. The keyword
list is shared with cast.TAG so a directive like "[pause 3s]" is never mistaken
for a [Name] speaker tag.
"""
import re

# Reserved directive keywords (kept in sync with cast.TAG's negative lookahead).
KEYWORDS = ("pause|beat|slow|slower|fast|faster|normal|"
            "whisper|calm|sad|neutral|happy|tense|excited|angry")

_DIRECTIVE = re.compile(r"\[\s*(" + KEYWORDS + r")\b\s*:?\s*([^\]\n]*)\]", re.I)

_SPEED_MULT = {
    "slow": 0.85, "slower": 0.72,
    "fast": 1.18, "faster": 1.35,
    "normal": 1.0,
}

# Emotion tags map to an "expressiveness" (0–1) value. Engines that support an
# intensity dial (Chatterbox) use it per passage; Kokoro ignores it (no emotion).
# With Chatterbox this is really *intensity*, not distinct emotions.
_EMOTION_EXAG = {
    "whisper": 0.25, "calm": 0.35, "sad": 0.40, "neutral": 0.50,
    "happy": 0.65, "tense": 0.72, "excited": 0.82, "angry": 0.88,
}

DEFAULT_PAUSE = 0.8
BEAT_PAUSE = 0.4
MAX_PAUSE = 30.0


def _pause_seconds(arg: str, default: float) -> float:
    m = re.search(r"([\d.]+)\s*(ms|s|sec|secs|second|seconds)?", (arg or "").lower())
    if not m:
        return default
    try:
        val = float(m.group(1))
    except ValueError:
        return default
    if (m.group(2) or "s") == "ms":
        val /= 1000.0
    return max(0.05, min(MAX_PAUSE, val))


def has_directives(text: str) -> bool:
    return bool(_DIRECTIVE.search(text or ""))


def tokenize(text: str):
    """Split text into an ordered list of tokens, consuming the markup:
      ("text",    str)   — a run of prose to synthesize
      ("pause",   secs)  — insert silence
      ("speed",   mult)  — set the speed multiplier for the following prose
      ("emotion", exag)  — set the expressiveness (0–1) for the following prose
    """
    text = text or ""
    out, pos = [], 0
    for m in _DIRECTIVE.finditer(text):
        pre = text[pos:m.start()]
        if pre.strip():
            out.append(("text", pre))
        kw = m.group(1).lower()
        if kw in ("pause", "beat"):
            default = BEAT_PAUSE if kw == "beat" else DEFAULT_PAUSE
            out.append(("pause", _pause_seconds(m.group(2), default)))
        elif kw in _EMOTION_EXAG:
            out.append(("emotion", _EMOTION_EXAG[kw]))
        else:
            out.append(("speed", _SPEED_MULT.get(kw, 1.0)))
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        out.append(("text", tail))
    return out


def strip(text: str) -> str:
    """Remove all directive markup, leaving only spoken prose."""
    return _DIRECTIVE.sub("", text or "")
