"""Kokoro voice catalog with rich metadata for the UI.

lang_code is the first letter of the voice id and is what KPipeline expects:
  a=American English, b=British English, e=Spanish, f=French,
  i=Italian, p=Brazilian Portuguese, h=Hindi
"""

# Grade is Kokoro's published quality grade. `story` flags warm, narration-friendly
# voices we surface as "Recommended for stories".
VOICES = [
    # ---- American English ----
    {"id": "af_heart",   "name": "Heart",   "gender": "female", "grade": "A",  "story": True,  "flag": "🇺🇸", "accent": "American", "blurb": "Warm, expressive — our top pick for bedtime stories."},
    {"id": "af_bella",   "name": "Bella",   "gender": "female", "grade": "A-", "story": True,  "flag": "🇺🇸", "accent": "American", "blurb": "Bright and friendly, great for younger kids."},
    {"id": "af_nicole",  "name": "Nicole",  "gender": "female", "grade": "B-", "story": True,  "flag": "🇺🇸", "accent": "American", "blurb": "Soft, intimate — sounds close, like reading beside them."},
    {"id": "af_aoede",   "name": "Aoede",   "gender": "female", "grade": "C+", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Clear, even-toned narration."},
    {"id": "af_kore",    "name": "Kore",    "gender": "female", "grade": "C+", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Calm and steady."},
    {"id": "af_sarah",   "name": "Sarah",   "gender": "female", "grade": "C+", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Neutral, articulate."},
    {"id": "af_nova",    "name": "Nova",    "gender": "female", "grade": "C",  "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Youthful and energetic."},
    {"id": "af_sky",     "name": "Sky",     "gender": "female", "grade": "C-", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Light and airy."},
    {"id": "af_alloy",   "name": "Alloy",   "gender": "female", "grade": "C",  "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Balanced, all-purpose."},
    {"id": "af_jessica", "name": "Jessica", "gender": "female", "grade": "C-", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Conversational."},
    {"id": "af_river",   "name": "River",   "gender": "female", "grade": "C-", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Mellow and relaxed."},
    {"id": "am_michael", "name": "Michael", "gender": "male",   "grade": "C+", "story": True,  "flag": "🇺🇸", "accent": "American", "blurb": "Warm fatherly tone — a natural storyteller."},
    {"id": "am_fenrir",  "name": "Fenrir",  "gender": "male",   "grade": "C+", "story": True,  "flag": "🇺🇸", "accent": "American", "blurb": "Deep and adventurous, good for heroes & dragons."},
    {"id": "am_puck",    "name": "Puck",    "gender": "male",   "grade": "C+", "story": True,  "flag": "🇺🇸", "accent": "American", "blurb": "Playful and characterful."},
    {"id": "am_echo",    "name": "Echo",    "gender": "male",   "grade": "D",  "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Plain narration."},
    {"id": "am_eric",    "name": "Eric",    "gender": "male",   "grade": "D",  "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Neutral male voice."},
    {"id": "am_liam",    "name": "Liam",    "gender": "male",   "grade": "D",  "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Younger male voice."},
    {"id": "am_onyx",    "name": "Onyx",    "gender": "male",   "grade": "D",  "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Low and smooth."},
    {"id": "am_santa",   "name": "Santa",   "gender": "male",   "grade": "D-", "story": True,  "flag": "🎅", "accent": "American", "blurb": "Jolly! Perfect for holiday stories."},
    {"id": "am_adam",    "name": "Adam",    "gender": "male",   "grade": "F+", "story": False, "flag": "🇺🇸", "accent": "American", "blurb": "Basic male voice."},
    # ---- British English ----
    {"id": "bf_emma",     "name": "Emma",     "gender": "female", "grade": "B-", "story": True,  "flag": "🇬🇧", "accent": "British", "blurb": "Lovely British narration, classic storybook feel."},
    {"id": "bf_isabella", "name": "Isabella", "gender": "female", "grade": "C",  "story": True,  "flag": "🇬🇧", "accent": "British", "blurb": "Elegant and clear."},
    {"id": "bf_alice",    "name": "Alice",    "gender": "female", "grade": "C",  "story": False, "flag": "🇬🇧", "accent": "British", "blurb": "Gentle British voice."},
    {"id": "bf_lily",     "name": "Lily",     "gender": "female", "grade": "C",  "story": False, "flag": "🇬🇧", "accent": "British", "blurb": "Sweet and light."},
    {"id": "bm_george",   "name": "George",   "gender": "male",   "grade": "C",  "story": True,  "flag": "🇬🇧", "accent": "British", "blurb": "Distinguished British narrator — grand adventures."},
    {"id": "bm_fable",    "name": "Fable",    "gender": "male",   "grade": "C",  "story": True,  "flag": "🇬🇧", "accent": "British", "blurb": "Made for fables and fairy tales."},
    {"id": "bm_lewis",    "name": "Lewis",    "gender": "male",   "grade": "D+", "story": False, "flag": "🇬🇧", "accent": "British", "blurb": "Deep British voice."},
    {"id": "bm_daniel",   "name": "Daniel",   "gender": "male",   "grade": "D",  "story": False, "flag": "🇬🇧", "accent": "British", "blurb": "Neutral British voice."},
    # ---- Other languages (espeak-ng backed) ----
    {"id": "ef_dora",  "name": "Dora",  "gender": "female", "grade": "C", "story": False, "flag": "🇪🇸", "accent": "Spanish",    "blurb": "Spanish female voice."},
    {"id": "em_alex",  "name": "Alex",  "gender": "male",   "grade": "C", "story": False, "flag": "🇪🇸", "accent": "Spanish",    "blurb": "Spanish male voice."},
    {"id": "ff_siwis", "name": "Siwis", "gender": "female", "grade": "C", "story": False, "flag": "🇫🇷", "accent": "French",     "blurb": "French female voice."},
    {"id": "if_sara",  "name": "Sara",  "gender": "female", "grade": "C", "story": False, "flag": "🇮🇹", "accent": "Italian",    "blurb": "Italian female voice."},
    {"id": "im_nicola","name": "Nicola","gender": "male",   "grade": "C", "story": False, "flag": "🇮🇹", "accent": "Italian",    "blurb": "Italian male voice."},
    {"id": "pf_dora",  "name": "Dora",  "gender": "female", "grade": "C", "story": False, "flag": "🇧🇷", "accent": "Portuguese", "blurb": "Brazilian Portuguese female voice."},
    {"id": "pm_alex",  "name": "Alex",  "gender": "male",   "grade": "C", "story": False, "flag": "🇧🇷", "accent": "Portuguese", "blurb": "Brazilian Portuguese male voice."},
    {"id": "hf_alpha", "name": "Alpha", "gender": "female", "grade": "C", "story": False, "flag": "🇮🇳", "accent": "Hindi",      "blurb": "Hindi female voice."},
    {"id": "hm_omega", "name": "Omega", "gender": "male",   "grade": "C", "story": False, "flag": "🇮🇳", "accent": "Hindi",      "blurb": "Hindi male voice."},
]

_BY_ID = {v["id"]: v for v in VOICES}


def lang_code(voice_id: str) -> str:
    """KPipeline lang code = first letter of the voice id."""
    return voice_id[0]


def get(voice_id: str):
    return _BY_ID.get(voice_id)


def is_valid(voice_id: str) -> bool:
    return voice_id in _BY_ID


DEFAULT_VOICE = "af_heart"
SAMPLE_TEXT = ("Once upon a time, in a land far beyond the hills, "
               "a small and curious hero set off on a very big adventure.")
