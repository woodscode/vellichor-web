"""Background ambience: license-free procedural beds generated with ffmpeg,
plus user-supplied tracks, mixed under narration (with optional ducking)."""
import os
import subprocess
import soundfile as sf

BUILTIN_DIR = "/data/ambience/builtin"
USER_DIR = "/data/ambience"
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")

# id -> (label, ffmpeg input+filter args producing a ~60s mono bed)
BUILTINS = {
    "soft_rain": ("🌧️ Soft Rain", [
        "-f", "lavfi", "-i", "anoisesrc=color=pink:d=60:a=0.6",
        "-af", "highpass=f=500,lowpass=f=8000,tremolo=f=0.1:d=0.2"]),
    "gentle_night": ("🌙 Gentle Night", [
        "-f", "lavfi", "-i", "anoisesrc=color=brown:d=60:a=0.7",
        "-af", "lowpass=f=450,volume=1.3,tremolo=f=0.1:d=0.3"]),
    "warm_hum": ("🔥 Warm Hum", [
        "-f", "lavfi", "-i", "sine=frequency=98:d=60",
        "-f", "lavfi", "-i", "anoisesrc=color=brown:d=60:a=0.3",
        "-filter_complex",
        "[0]volume=0.25,tremolo=f=0.1:d=0.3[a];[1]lowpass=f=350[b];"
        "[a][b]amix=inputs=2:normalize=0"]),
    "dreamy": ("✨ Dreamy Pad", [
        "-f", "lavfi", "-i", "sine=frequency=220:d=60",
        "-f", "lavfi", "-i", "sine=frequency=329.6:d=60",
        "-filter_complex",
        "[0]volume=0.18[a];[1]volume=0.12[b];"
        "[a][b]amix=inputs=2:normalize=0,tremolo=f=0.12:d=0.5,"
        "aecho=0.8:0.7:60:0.3,lowpass=f=2500"]),
}


def ensure_builtins():
    os.makedirs(BUILTIN_DIR, exist_ok=True)
    for bid, (_, args) in BUILTINS.items():
        out = os.path.join(BUILTIN_DIR, f"{bid}.wav")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            continue
        try:
            subprocess.run(["ffmpeg", "-y", *args, "-ar", "24000", "-ac", "1", out],
                           check=True, capture_output=True)
        except Exception as e:  # noqa: BLE001
            print(f"[ambience] failed to generate {bid}: {e}", flush=True)


def list_beds():
    beds = []
    for bid, (label, _) in BUILTINS.items():
        if os.path.exists(os.path.join(BUILTIN_DIR, f"{bid}.wav")):
            beds.append({"id": bid, "label": label, "builtin": True})
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
