"""The conversion pipeline: chapters -> (multi-voice) per-segment synthesis
-> optional ambience mix -> per-chapter mp3 -> chaptered m4b -> optional export
into the Audiobookshelf library."""
import os
import re
import shutil
import subprocess
import time
import numpy as np
import soundfile as sf

from tts import ENGINE, SAMPLE_RATE
import extract as extractor
import cast as castmod
import ambience as amb
import voices as voicecat
import directives
import engines
import chatterbox_engine as cbx
import myvoices
import gpu

class Cancelled(Exception):
    """Raised when a job is stopped by the user."""


LIBRARY_DIR = "/library"           # bind-mounted Audiobookshelf library
ABS_UID = int(os.environ.get("ABS_UID", "911"))
ABS_GID = int(os.environ.get("ABS_GID", "911"))
def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * max(0.0, seconds)), dtype="float32")


GAP = _silence(0.8)        # lead-in silence before each new chapter / title
SEG_GAP = _silence(0.28)   # between two *different* speakers
TITLE_GAP_S = 0.9          # beat after a chapter title (emitted as a pause op)


def safe_name(name: str) -> str:
    name = re.sub(r"[^\w\s.-]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:120] or "audiobook"


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


def _ffmpeg_progress(args, total_ms, progress, base, span, stage):
    """Run ffmpeg, parsing -progress so long encodes report smooth progress."""
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-nostats", "-progress", "pipe:1", *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    last = -1
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_us=") and total_ms > 0:
            try:
                cur_ms = int(line.split("=", 1)[1]) / 1000.0
            except ValueError:
                continue
            pct = base + min(span, int(cur_ms / total_ms * span))
            if pct != last:
                last = pct
                progress(stage=stage, percent=pct)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode})")


def _wav_duration_ms(path: str) -> int:
    info = sf.info(path)
    return int(round(info.frames / info.samplerate * 1000))


def _write_ffmetadata(meta_path, title, author, chapters_meta):
    lines = [";FFMETADATA1", f"title={title}", f"artist={author}", f"album={title}"]
    for ch in chapters_meta:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000",
                  f"START={ch['start']}", f"END={ch['end']}",
                  f"title={ch['title']}"]
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _chown(path):
    try:
        os.chown(path, ABS_UID, ABS_GID)
    except (PermissionError, OSError):
        pass


def _clamp_speed(x: float) -> float:
    return max(0.5, min(2.0, x))


def _spans_for(text, multivoice, narrator_voice, cast_map):
    """A run of prose -> ordered [(voice, body)] spans."""
    if multivoice:
        return [(s["voice"], s["text"])
                for s in castmod.build_segments(text, narrator_voice, cast_map)]
    return [(narrator_voice, text)]


def _plan_chapter(ch, multivoice, narrator_voice, cast_map, base_speed):
    """Return an ordered op list for one chapter. Each op is either
    {"kind":"speak", voice, text, speed} or {"kind":"pause", seconds}.

    Inline [pause]/[slow] directives become pause/speed ops; a chapter title
    (when present) is read first, followed by a beat before the body begins."""
    ops = []

    spoken_title = ch.get("spoken_title")
    if spoken_title:
        for tchunk in ENGINE.chunk_text(spoken_title):
            ops.append({"kind": "speak", "voice": narrator_voice,
                        "speed": _clamp_speed(base_speed), "text": tchunk})
        if ops:
            ops.append({"kind": "pause", "seconds": TITLE_GAP_S})

    mult = 1.0
    for kind, val in directives.tokenize(ch["text"]):
        if kind == "speed":
            mult = val
        elif kind == "pause":
            ops.append({"kind": "pause", "seconds": val})
        else:  # a run of prose
            for voice, body in _spans_for(val, multivoice, narrator_voice, cast_map):
                for chunk in ENGINE.chunk_text(body):
                    ops.append({"kind": "speak", "voice": voice,
                                "speed": _clamp_speed(base_speed * mult),
                                "text": chunk})

    if not any(o["kind"] == "speak" for o in ops):
        for chunk in ENGINE.chunk_text(directives.strip(ch["text"])):
            ops.append({"kind": "speak", "voice": narrator_voice,
                        "speed": _clamp_speed(base_speed), "text": chunk})
    return ops


def _loudnorm_af(job):
    """ffmpeg loudness-normalization filter to hit a target LUFS — louder,
    consistent output that carries on quiet playback devices. None = leave
    the audio untouched."""
    try:
        lufs = float(job.get("loudness"))
    except (TypeError, ValueError):
        return None
    if lufs >= 0 or lufs < -30:        # 0 / positive means "off"
        return None
    return f"loudnorm=I={lufs:.1f}:TP=-1.5:LRA=11"


def _render_kokoro_reference(voice: str, workdir: str) -> str:
    """Render a short Kokoro sample of `voice` for use as a Chatterbox cloning
    reference (a "bundled voice pack"). Cached across jobs under /data/refs."""
    refs = os.path.join("/data", "refs")
    os.makedirs(refs, exist_ok=True)
    out = os.path.join(refs, f"{voice}.wav")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    wav = ENGINE.synth_chunk(voicecat.SAMPLE_TEXT, voice, 1.0)
    sf.write(out, wav, SAMPLE_RATE)
    return out


def _prepare_reference(src: str, workdir: str) -> str:
    """Normalize an arbitrary reference clip (upload or browser recording, any
    ffmpeg-readable format incl. .webm) to a clean mono 24 kHz wav for cloning."""
    out = os.path.join(workdir, "ref_prepared.wav")
    _ffmpeg(["-i", src, "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-af", "highpass=f=60,loudnorm=I=-20:TP=-2", out])
    return out


def _resolve_reference(job: dict, voice: str, workdir: str) -> str:
    """Pick the Chatterbox cloning reference, in priority order:
    a one-off uploaded/recorded clip → a saved 'My Voice' → else a Kokoro-rendered
    sample of the selected preset voice."""
    one_off = job.get("reference_path")
    if one_off and os.path.exists(one_off):
        return _prepare_reference(one_off, workdir)
    saved = myvoices.path_for(job.get("reference_voice"))
    if saved:                       # already normalized at save time
        return saved
    return _render_kokoro_reference(voice, workdir)


def run(job: dict, progress) -> dict:
    workdir = job["workdir"]
    os.makedirs(workdir, exist_ok=True)
    voice, speed = job["voice"], float(job.get("speed", 1.0))
    engine_id = engines.resolve(job.get("engine") or engines.DEFAULT)
    exaggeration = float(job.get("exaggeration", 0.5))
    # Expressive engines render a single cloned voice; multi-voice is Kokoro-only.
    multivoice = bool(job.get("multivoice")) and engine_id == "kokoro"
    cast_map = job.get("cast") or {}

    # ---- 1. Extract chapters --------------------------------------------
    progress(stage="Reading text", percent=2, log="Extracting chapters…")
    if job.get("source"):
        chapters, detected_title = extractor.extract(job["source"])
    else:
        chapters = extractor.from_text(job.get("text", ""), job.get("title") or "Story")
        detected_title = job.get("title") or "Story"
    if not chapters:
        raise ValueError("No readable text found in the input.")

    title = safe_name(job.get("title") or detected_title)
    author = job.get("author") or "Vellichor"

    # Read each chapter's heading aloud as the opening of its narration (so the
    # title is part of the story), rather than dropping it. Only for titles that
    # came from a real heading — never a synthetic/default/file-name title.
    for ch in chapters:
        if ch.get("heading") and ch["title"].strip():
            head = ch["title"].strip()
            if head[-1] not in ".!?:;,":
                head += "."          # give the narrator a natural sentence beat
            ch["spoken_title"] = head

    # Auto-cast: fill in a distinct, gender-matched voice for every detected
    # character (works even with no manual assignments, e.g. uploaded books).
    if multivoice:
        full_text = "\n\n".join(c["text"] for c in chapters)
        cast_map = castmod.auto_cast(full_text, voice, cast_map)
        pretty = ", ".join(
            f"{('Narrator' if k == 'narrator' else k.title())}→"
            f"{(voicecat.get(v) or {}).get('name', v)}"
            for k, v in list(cast_map.items())[:14])
        progress(log=f"Cast: {pretty}")

    # ---- 2. Plan speak/pause ops (for accurate progress) ----------------
    for ch in chapters:
        ch["ops"] = _plan_chapter(ch, multivoice, voice, cast_map, speed)
    total_chunks = sum(1 for c in chapters for o in c["ops"]
                       if o["kind"] == "speak") or 1
    mode = "multi-voice" if multivoice else "single voice"
    progress(stage="Preparing", percent=4,
             chapters_total=len(chapters), chunks_total=total_chunks,
             log=f"{len(chapters)} chapter(s), {total_chunks} segments, {mode}. "
                 f"Synthesizing on {ENGINE.device.upper()}…")

    # ---- 3. Synthesize ---------------------------------------------------
    # Hold the GPU lock for the whole synth phase and evict the Smart-cast model
    # from VRAM first, so Kokoro gets the GPU (the two can't coexist on 8 GB).
    chapter_wavs = []
    done = 0
    t0 = time.time()
    synth = cbx.ENGINE if engine_id == "chatterbox" else ENGINE
    reference_path = None
    with gpu.LOCK:
        gpu.release_ollama()
        if engine_id == "chatterbox":
            # Resolve the cloning reference (one-off clip / saved voice / bundled
            # Kokoro render) BEFORE freeing Kokoro's VRAM.
            reference_path = _resolve_reference(job, voice, workdir)
            ENGINE.unload()          # hand the GPU to Chatterbox (can't coexist on 8 GB)
        try:
            for idx, ch in enumerate(chapters):
                # A short settle before each new chapter/title so it doesn't run
                # straight into the tail of the previous one.
                parts = [GAP] if idx > 0 else []
                prev_voice = None
                for op in ch["ops"]:
                    if job.get("cancel"):
                        raise Cancelled()
                    if op["kind"] == "pause":
                        parts.append(_silence(op["seconds"]))
                        prev_voice = None    # a pause already separates speakers
                        continue
                    # Only gap between *different* speakers — a character with
                    # several lines in a row flows as one continuous turn.
                    if multivoice and prev_voice is not None and op["voice"] != prev_voice:
                        parts.append(SEG_GAP)
                    parts.append(synth.synth_chunk(
                        op["text"], op["voice"], op["speed"],
                        exaggeration=exaggeration, reference_path=reference_path))
                    prev_voice = op["voice"]
                    done += 1
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = int((total_chunks - done) / rate) if rate > 0 else None
                    pct = 4 + int(done / total_chunks * 76)
                    progress(stage=f"Narrating: {ch['title']}", percent=pct,
                             chapters_done=idx, chunks_done=done, eta=eta)
                audio = np.concatenate(parts) if parts else np.zeros(0, dtype="float32")
                wav_path = os.path.join(workdir, f"ch{idx:03d}.wav")
                sf.write(wav_path, audio, SAMPLE_RATE)
                chapter_wavs.append({"path": wav_path, "title": ch["title"]})
        finally:
            if engine_id == "chatterbox":
                synth.unload()       # release VRAM back to Kokoro / Ollama

    # ---- 3b. Mix background ambience ------------------------------------
    bed = job.get("ambience_path") or amb.path_for(job.get("ambience_id"))
    if bed:
        progress(stage="Adding ambience", percent=80,
                 log="Mixing background sound under the narration…")
        nch = len(chapter_wavs)
        for ci, cw in enumerate(chapter_wavs):
            progress(stage=f"Adding ambience ({ci + 1}/{nch})",
                     percent=80 + int(ci / max(1, nch) * 4))
            mixed = cw["path"].replace(".wav", "_mix.wav")
            try:
                amb.mix(cw["path"], bed, mixed,
                        volume=float(job.get("ambience_volume", 0.12)),
                        duck=bool(job.get("ducking", True)))
                cw["path"] = mixed
            except Exception as e:  # noqa: BLE001
                progress(log=f"Ambience mix skipped for a chapter: {e}")

    if job.get("cancel"):
        raise Cancelled()

    # ---- 4. Encode outputs ----------------------------------------------
    outputs = []
    out_base = os.path.join(workdir, "out")
    os.makedirs(out_base, exist_ok=True)
    formats = job.get("formats", ["m4b", "mp3"])
    cover = job.get("cover")
    af = _loudnorm_af(job)          # louder, consistent output (or None)

    nch = len(chapter_wavs)
    if "mp3" in formats:
        progress(stage="Encoding MP3", percent=84, log="Encoding per-chapter MP3 files…")
        mp3_dir = os.path.join(out_base, f"{title} (MP3)")
        os.makedirs(mp3_dir, exist_ok=True)
        for i, cw in enumerate(chapter_wavs):
            progress(stage=f"Encoding MP3 ({i + 1}/{nch})",
                     percent=84 + int(i / max(1, nch) * 8))
            mp3_path = os.path.join(mp3_dir, f"{i + 1:02d} - {safe_name(cw['title'])}.mp3")
            args = ["-i", cw["path"]]
            if cover:
                args += ["-i", cover, "-map", "0:a", "-map", "1:v",
                         "-disposition:v", "attached_pic"]
            if af:
                args += ["-af", af]
            args += ["-c:a", "libmp3lame", "-q:a", "4",
                     "-metadata", f"title={cw['title']}",
                     "-metadata", f"track={i + 1}",
                     "-metadata", f"album={title}",
                     "-metadata", f"artist={author}", mp3_path]
            _ffmpeg(args)
        zip_path = shutil.make_archive(os.path.join(out_base, f"{title}_mp3"), "zip", mp3_dir)
        outputs.append({"label": "MP3 (zip of chapters)", "path": zip_path,
                        "name": os.path.basename(zip_path), "kind": "mp3"})

    m4b_path = None
    if "m4b" in formats:
        progress(stage="Building audiobook", percent=92, log="Assembling chaptered M4B…")
        concat_path = os.path.join(workdir, "concat.txt")
        with open(concat_path, "w", encoding="utf-8") as f:
            for cw in chapter_wavs:
                f.write(f"file '{cw['path']}'\n")
        chapters_meta, cursor = [], 0
        for cw in chapter_wavs:
            dur = _wav_duration_ms(cw["path"])
            chapters_meta.append({"start": cursor, "end": cursor + dur, "title": cw["title"]})
            cursor += dur
        total_ms = cursor
        meta_path = os.path.join(workdir, "meta.txt")
        _write_ffmetadata(meta_path, title, author, chapters_meta)

        m4b_path = os.path.join(out_base, f"{title}.m4b")
        args = ["-f", "concat", "-safe", "0", "-i", concat_path, "-i", meta_path]
        if cover:
            args += ["-i", cover]
        args += ["-map_metadata", "1", "-map_chapters", "1", "-map", "0:a"]
        if cover:
            args += ["-map", "2:v", "-disposition:v", "attached_pic", "-c:v", "mjpeg"]
        if af:
            args += ["-af", af]
        args += ["-c:a", "aac", "-b:a", "96k", m4b_path]
        _ffmpeg_progress(args, total_ms, progress, base=92, span=7,
                         stage="Building audiobook")
        outputs.append({"label": "Audiobook (M4B, chaptered)", "path": m4b_path,
                        "name": os.path.basename(m4b_path), "kind": "m4b"})

    # ---- 5. Export to Audiobookshelf ------------------------------------
    exported_to = None
    if job.get("export_abs") and os.path.isdir(LIBRARY_DIR):
        progress(stage="Adding to Audiobookshelf", percent=97, log="Copying into your library…")
        book_dir = os.path.join(LIBRARY_DIR, author, title)
        os.makedirs(book_dir, exist_ok=True)
        if m4b_path:
            dest = os.path.join(book_dir, os.path.basename(m4b_path))
            shutil.copy2(m4b_path, dest)
            _chown(dest)
        elif "mp3" in formats:
            mp3_dir = os.path.join(out_base, f"{title} (MP3)")
            for fn in os.listdir(mp3_dir):
                dest = os.path.join(book_dir, fn)
                shutil.copy2(os.path.join(mp3_dir, fn), dest)
                _chown(dest)
        if cover:
            dest = os.path.join(book_dir, "cover" + os.path.splitext(cover)[1])
            shutil.copy2(cover, dest)
            _chown(dest)
        _chown(book_dir)
        _chown(os.path.join(LIBRARY_DIR, author))
        exported_to = book_dir

    total_audio_ms = sum(_wav_duration_ms(cw["path"]) for cw in chapter_wavs)
    progress(stage="Done", percent=100, log="Conversion complete! 🎉")
    return {"outputs": outputs, "exported_to": exported_to,
            "duration_ms": total_audio_ms, "chapters": len(chapters),
            "title": title, "author": author}
