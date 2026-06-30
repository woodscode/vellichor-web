"""Background ambience mixed under narration (with optional ducking). Two
sources of beds:

* SOUNDPACK — real field recordings (rain, ocean, forest, etc.) fetched once
  from Wikimedia Commons, loudness-normalized to a consistent level. Downloaded
  lazily at startup; see CREDITS.md for per-bed source + license.
* BUILTINS — license-free procedural textures generated with ffmpeg, for the
  abstract/musical beds that can't be field-recorded (and as an offline
  fallback).

Plus any user-supplied tracks dropped into USER_DIR.
"""
import json
import os
import shutil
import subprocess
import time

import requests
import soundfile as sf

BUILTIN_DIR = "/data/ambience/builtin"
USER_DIR = "/data/ambience"
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")

# Records which soundpack ids have been fetched, so we don't re-download every
# boot (and so a future bed added to SOUNDPACK is picked up on the next start).
_DONE_MANIFEST = os.path.join(BUILTIN_DIR, ".soundpack.json")
_CREDITS = os.path.join(USER_DIR, "CREDITS.md")
# Master each downloaded bed to a consistent loudness + 24kHz mono.
_NORMALIZE = "highpass=f=35,loudnorm=I=-20:TP=-2:LRA=11,aresample=24000"

# Real recordings from Wikimedia Commons (direct upload.wikimedia.org URLs).
SOUNDPACK = [
    {"id": "rain_thunder", "label": "🌧️ Rain & Thunder", "license": "Public domain",
     "by": "ezwa (Wikimedia Commons)",
     "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Rain_thunder_and_birds.ogg",
     "page": "https://commons.wikimedia.org/wiki/File:Rain_thunder_and_birds.ogg"},
    {"id": "ocean_waves", "label": "🌊 Ocean Waves", "license": "Public domain",
     "by": "Wikimedia Commons",
     "url": "https://upload.wikimedia.org/wikipedia/commons/1/1f/Waves.ogg",
     "page": "https://commons.wikimedia.org/wiki/File:Waves.ogg"},
    {"id": "forest_birds", "label": "🐦 Forest Birds", "license": "CC BY-SA 4.0",
     "by": "Matutinho (Wikimedia Commons)",
     "url": "https://upload.wikimedia.org/wikipedia/commons/e/e7/Birdsong_morning_01.ogg",
     "page": "https://commons.wikimedia.org/wiki/File:Birdsong_morning_01.ogg"},
    {"id": "crickets_night", "label": "🦗 Crickets at Night", "license": "CC BY-SA 4.0",
     "by": "DrTrumpet (Wikimedia Commons)",
     "url": "https://upload.wikimedia.org/wikipedia/commons/e/e0/"
            "Audio_H%C3%B6rbild_Grillenzirpen_-_nachts_um_3_im_F%C3%B6hrenwald_M%C3%B6dling.wav",
     "page": "https://commons.wikimedia.org/wiki/File:Audio_H%C3%B6rbild_Grillenzirpen_"
             "-_nachts_um_3_im_F%C3%B6hrenwald_M%C3%B6dling.wav"},
    {"id": "crackling_fire", "label": "🔥 Crackling Fire", "license": "Public domain",
     "by": "ezwa (Wikimedia Commons)",
     "url": "https://upload.wikimedia.org/wikipedia/commons/d/d8/Dry_grass_burning_in_open_fireplace.ogg",
     "page": "https://commons.wikimedia.org/wiki/File:Dry_grass_burning_in_open_fireplace.ogg"},
    {"id": "stream", "label": "💧 Babbling Stream", "license": "CC0",
     "by": "Ksd5 (Wikimedia Commons)",
     "url": "https://upload.wikimedia.org/wikipedia/commons/8/84/Swale.ogg",
     "page": "https://commons.wikimedia.org/wiki/File:Swale.ogg"},
]

# id -> (label, ffmpeg input+filter args) for procedural textures.
BUILTINS = {
    # Cozy low room hum (heater/engine-room feel).
    "warm_hum": ("♨️ Warm Hum", [
        "-f", "lavfi", "-i", "sine=frequency=98:d=60",
        "-f", "lavfi", "-i", "anoisesrc=color=brown:d=60:a=0.3",
        "-filter_complex",
        "[0]volume=0.32,tremolo=f=0.1:d=0.3[a];[1]lowpass=f=320,volume=1.1[b];"
        "[a][b]amix=inputs=2:normalize=0,volume=1.3"]),
    # Soft three-note pad (A–E–A) with echo for an ethereal wash.
    "dreamy": ("✨ Dreamy Pad", [
        "-f", "lavfi", "-i", "sine=frequency=110:d=60",
        "-f", "lavfi", "-i", "sine=frequency=164.81:d=60",
        "-f", "lavfi", "-i", "sine=frequency=220:d=60",
        "-filter_complex",
        "[0]volume=0.5[a];[1]volume=0.35[b];[2]volume=0.25[c];"
        "[a][b][c]amix=inputs=3:normalize=0,tremolo=f=0.1:d=0.4,"
        "aecho=0.8:0.7:120:0.35,lowpass=f=2200,volume=3.0"]),
}

# Display order in the dropdown (recordings first, then procedural textures).
ORDER = ["rain_thunder", "ocean_waves", "forest_birds", "crickets_night",
         "crackling_fire", "stream", "warm_hum", "dreamy"]
LABELS = {**{it["id"]: it["label"] for it in SOUNDPACK},
          **{bid: lbl for bid, (lbl, _) in BUILTINS.items()}}


def ensure_builtins():
    os.makedirs(BUILTIN_DIR, exist_ok=True)
    for bid, (_, args) in BUILTINS.items():
        out = os.path.join(BUILTIN_DIR, f"{bid}.wav")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            continue
        tmp = out + ".gen.wav"
        try:
            subprocess.run(["ffmpeg", "-y", *args, "-ar", "24000", "-ac", "1", tmp],
                           check=True, capture_output=True)
            _seamless_loop(tmp, out)
        except Exception as e:  # noqa: BLE001
            print(f"[ambience] failed to generate {bid}: {e}", flush=True)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _seamless_loop(src: str, out: str, xf: float = 3.0):
    """Rewrite a bed so it loops without an audible click: crossfade its tail
    back over its head. The result is (duration - xf) long and joins to itself
    seamlessly, so ffmpeg's -stream_loop produces continuous ambience."""
    try:
        info = sf.info(src)
        dur = info.frames / info.samplerate
    except Exception:  # noqa: BLE001
        dur = 0
    xf = min(xf, dur / 3.0) if dur > 1.5 else 0
    if xf < 0.5:                      # too short to crossfade — leave as-is
        if os.path.abspath(src) != os.path.abspath(out):
            shutil.copyfile(src, out)
        return
    main_end = dur - xf
    # [a] = body faded in over the first xf; [b] = tail faded out, overlaid on
    # the head. Where they overlap the fades sum back to unity, so the loop
    # point (end -> start) is continuous.
    fc = (f"[0]atrim=0:{main_end:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={xf:.3f}[a];"
          f"[0]atrim={main_end:.3f}:{dur:.3f},asetpts=PTS-STARTPTS,afade=t=out:d={xf:.3f}[b];"
          f"[a][b]amix=inputs=2:duration=first:normalize=0[m]")
    subprocess.run(["ffmpeg", "-y", "-i", src, "-filter_complex", fc, "-map", "[m]",
                    "-ac", "1", "-ar", "24000", out], check=True, capture_output=True)


def _load_done():
    try:
        with open(_DONE_MANIFEST) as f:
            return set(json.load(f))
    except Exception:  # noqa: BLE001
        return set()


def ensure_soundpack():
    """Download + normalize any not-yet-fetched soundpack beds. Idempotent and
    safe to call at every startup: already-fetched beds are skipped, and beds
    that fail (Wikimedia rate-limit / offline) are simply retried next time."""
    os.makedirs(BUILTIN_DIR, exist_ok=True)
    done = _load_done()
    sess = requests.Session()
    sess.headers["User-Agent"] = "vellichor/1.0 ambience fetch (self-hosted personal use)"
    for it in SOUNDPACK:
        if it["id"] in done:
            continue
        raw = None
        for attempt in range(4):
            try:
                r = sess.get(it["url"], timeout=300)
                if r.status_code == 200 and len(r.content) > 50000:
                    raw = r.content
                    break
            except requests.RequestException:
                pass
            time.sleep(8 * (attempt + 1))   # back off; Wikimedia rate-limits
        if not raw:
            continue
        tmp = os.path.join(BUILTIN_DIR, it["id"] + ".src")
        norm = os.path.join(BUILTIN_DIR, it["id"] + ".norm.wav")
        out = os.path.join(BUILTIN_DIR, it["id"] + ".wav")
        try:
            with open(tmp, "wb") as f:
                f.write(raw)
            # loudness-normalize, then make it loop seamlessly
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp, "-af", _NORMALIZE, "-ac", "1", "-ar", "24000", norm],
                check=True, capture_output=True)
            _seamless_loop(norm, out)
            done.add(it["id"])
            try:
                with open(_DONE_MANIFEST, "w") as f:
                    json.dump(sorted(done), f)
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            print(f"[ambience] soundpack {it['id']} failed: {e}", flush=True)
        finally:
            for p in (tmp, norm):
                try:
                    os.remove(p)
                except OSError:
                    pass
        time.sleep(5)
    _write_credits(done)


def _write_credits(done):
    present = [it for it in SOUNDPACK if it["id"] in done]
    if not present:
        return
    lines = ["# Background ambience — sound credits", "",
             "Bundled recording beds, their sources and licenses:", ""]
    for it in present:
        lines.append(f"- **{it['label']}** — {it['by']} — {it['license']} — {it['page']}")
    lines += ["",
              "Public-domain / CC0 beds carry no obligations. CC BY-SA beds require the",
              "attribution above; if you publicly distribute audiobooks containing them,",
              "ShareAlike terms may apply. For personal/self-hosted use there are no issues."]
    try:
        with open(_CREDITS, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def list_beds():
    beds = []
    for bid in ORDER:
        if os.path.exists(os.path.join(BUILTIN_DIR, f"{bid}.wav")):
            beds.append({"id": bid, "label": LABELS.get(bid, bid), "builtin": True})
    if os.path.isdir(USER_DIR):
        for fn in sorted(os.listdir(USER_DIR)):
            full = os.path.join(USER_DIR, fn)
            if os.path.isfile(full) and fn.lower().endswith(AUDIO_EXTS):
                beds.append({"id": "user:" + fn, "label": "📁 " + fn, "builtin": False})
    return beds


def path_for(bed_id: str):
    if not bed_id:
        return None
    if bed_id.startswith("user:"):
        p = os.path.join(USER_DIR, bed_id[5:])
    else:
        p = os.path.join(BUILTIN_DIR, f"{bed_id}.wav")
    return p if os.path.exists(p) else None


def mix(voice_wav: str, bed_path: str, out_wav: str,
        volume: float = 0.12, duck: bool = True) -> str:
    """Mix a looped, faded bed under the narration. Output length = narration."""
    info = sf.info(voice_wav)
    dur = info.frames / info.samplerate
    fade_out = max(0.1, dur - 1.5)
    vol = max(0.0, min(1.0, volume))
    bg = (f"[1:a]volume={vol:.3f},afade=t=in:d=1.5,"
          f"afade=t=out:st={fade_out:.2f}:d=1.5[bg]")
    if duck:
        chain = (f"{bg};[bg][0:a]sidechaincompress="
                 f"threshold=0.03:ratio=6:attack=15:release=350[bgd];"
                 f"[0:a][bgd]amix=inputs=2:duration=first:normalize=0[mix]")
    else:
        chain = f"{bg};[0:a][bg]amix=inputs=2:duration=first:normalize=0[mix]"
    subprocess.run(
        ["ffmpeg", "-y", "-i", voice_wav, "-stream_loop", "-1", "-i", bed_path,
         "-filter_complex", chain, "-map", "[mix]", "-t", f"{dur:.3f}",
         "-ar", "24000", "-ac", "1", out_wav],
        check=True, capture_output=True)
    return out_wav
