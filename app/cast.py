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


MALE_PRON = re.compile(r"\b(he|him|his|himself)\b", re.I)
FEMALE_PRON = re.compile(r"\b(she|her|hers|herself)\b", re.I)
MALE_TITLES = {"mr", "mister", "sir", "king", "prince", "lord", "father", "dad",
               "daddy", "papa", "grandpa", "grandfather", "uncle", "brother", "boy"}
FEMALE_TITLES = {"mrs", "ms", "miss", "madam", "lady", "queen", "princess",
                 "mother", "mom", "mum", "mommy", "mama", "grandma",
                 "grandmother", "aunt", "sister", "girl"}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "")).strip()


def _infer_gender(name: str, text: str):
    """Best-effort gender guess from honorific titles, then nearby pronouns."""
    for tok in name.lower().replace(".", "").split():
        if tok in MALE_TITLES:
            return "male"
        if tok in FEMALE_TITLES:
            return "female"
    namelc = name.lower()
    low = text.lower()
    male = female = 0
    start = 0
    while True:
        i = low.find(namelc, start)
        if i < 0:
            break
        # window = the name through the END of the NEXT sentence, where the
        # referring pronoun usually sits ("…said Ryan. He grinned…"). Stopping
        # at one sentence keeps it from bleeding into the next character.
        m1 = re.search(r"[.!?]", text[i:])
        e1 = i + m1.end() if m1 else len(text)
        m2 = re.search(r"[.!?]", text[e1:])
        e2 = e1 + m2.end() if m2 else len(text)
        window = text[i:e2]
        male += len(MALE_PRON.findall(window))
        female += len(FEMALE_PRON.findall(window))
        start = i + len(namelc)
    if male > female and male > 0:
        return "male"
    if female > male and female > 0:
        return "female"
    return None


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
    chars = sorted(agg.values(), key=lambda d: (d["name"] != NARRATOR, -d["chars"]))
    for c in chars:
        c["gender"] = (None if c["name"].lower() == NARRATOR.lower()
                       else _infer_gender(c["name"], text))
    return chars


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


# Default voice palettes for auto-assignment (kept in sync with the frontend).
FEMALE_VOICES = ["af_bella", "bf_emma", "af_nova", "af_nicole", "bf_isabella", "af_sarah"]
MALE_VOICES = ["am_michael", "am_fenrir", "bm_george", "am_puck", "bm_fable", "am_onyx"]
ANY_VOICES = ["af_bella", "am_michael", "bf_emma", "am_fenrir", "af_nova", "bm_george"]


def auto_cast(text: str, narrator_voice: str, user_map: dict = None):
    """Build a complete cast_map: keep any user assignments, then auto-assign a
    distinct, gender-matched voice to every other detected character.

    This is what makes multi-voice work with zero manual setup (e.g. uploads).
    """
    user = {_norm(k).lower(): v for k, v in (user_map or {}).items() if v}
    result = dict(user)
    result.setdefault(NARRATOR.lower(), narrator_voice)
    used = {narrator_voice} | set(user.values())
    for c in detect_characters(text):
        key = c["name"].lower()
        if key in result:
            continue
        pal = (FEMALE_VOICES if c.get("gender") == "female"
               else MALE_VOICES if c.get("gender") == "male" else ANY_VOICES)
        pick = next((v for v in pal if v not in used), pal[0])
        result[key] = pick
        used.add(pick)
    return result
