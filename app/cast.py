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


_NAME_STOPWORDS = {
    "the", "a", "an", "and", "but", "or", "so", "then", "there", "here", "it",
    "praise", "chapter", "part", "book", "contents", "fiction", "nonfiction",
    "also", "by", "for", "this", "that", "what", "who", "why", "when", "yes",
    "no", "oh", "well", "copyright", "isbn", "prologue", "epilogue", "dedication",
}
# A plausible character name: 1-3 capitalized words, letters only. Rejects
# possessives ("Brown's"), ALL-CAPS headings ("PRAISE FOR"), single letters,
# and common stopwords that dialogue tags sometimes pick up.
_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,2}$")


def plausible_name(name: str) -> bool:
    n = _norm(name)
    if len(n) < 2 or len(n) > 40:
        return False
    if n.lower() in _NAME_STOPWORDS:
        return False
    return bool(_NAME_RE.match(n))


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


def _split_tagged_block(name: str, body: str):
    """Within a [Name] block, voice the quoted dialogue as that character and
    keep the surrounding narration ("he decided.", scene description) as the
    Narrator. A block with no quotes is honored as-is (the explicit tag wins)."""
    if name.lower() == NARRATOR.lower() or not QUOTE_SPAN.search(body):
        return [(name, body)]
    spans, idx = [], 0
    for m in QUOTE_SPAN.finditer(body):
        pre = body[idx:m.start()].strip()
        if pre:
            spans.append((NARRATOR, pre))
        quote = m.group(1).strip()
        if quote:
            spans.append((name, quote))
        idx = m.end()
    tail = body[idx:].strip()
    if tail:
        spans.append((NARRATOR, tail))
    return spans


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
            segs.extend(_split_tagged_block(name, body))
    return segs


def _attribute(after: str, before: str):
    for m in (_VERB_AFTER.match(after), _VERB_BEFORE.search(before)):
        if m:
            name = _norm(m.group(1))
            if plausible_name(name):
                return name
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
        # Only give a distinct voice to a real, recurring character — skip junk
        # names from front matter and one-off mis-attributions (they read as
        # narration in the narrator's voice).
        if not plausible_name(c["name"]) or c["lines"] < 2:
            continue
        pal = (FEMALE_VOICES if c.get("gender") == "female"
               else MALE_VOICES if c.get("gender") == "male" else ANY_VOICES)
        pick = next((v for v in pal if v not in used), pal[0])
        result[key] = pick
        used.add(pick)
    return result
