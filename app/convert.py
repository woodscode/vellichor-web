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

LIBRARY_DIR = "/library"           # bind-mounted Audiobookshelf library
ABS_UID = int(os.environ.get("ABS_UID", "911"))
ABS_GID = int(os.environ.get("ABS_GID", "911"))
GAP = np.zeros(int(SAMPLE_RATE * 0.6), dtype="float32")   # between chapters
SEG_GAP = np.zeros(int(SAMPLE_RATE * 0.28), dtype="float32")  # between speakers


def safe_name(name: str) -> str:
    name = re.sub(r"[^\w\s.-]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:120] or "audiobook"


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


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


def _plan_chapter(ch, multivoice, narrator_voice, cast_map):
    """Return a list of segments: [{voice, chunks:[...]}] for one chapter."""
    if multivoice:
        segs = castmod.build_segments(ch["text"], narrator_voice, cast_map)
        out = []
        for s in segs:
            chunks = ENGINE.chunk_text(s["text"])
            if chunks:
                out.append({"voice": s["voice"], "chunks": chunks})
        return out or [{"voice": narrator_voice, "chunks": ENGINE.chunk_text(ch["text"])}]
    return [{"voice": narrator_voice, "chunks": ENGINE.chunk_text(ch["text"])}]


def run(job: dict, progress) -> dict:
    workdir = job["workdir"]
    os.makedirs(workdir, exist_ok=True)
    voice, speed = job["voice"], float(job.get("speed", 1.0))
    multivoice = bool(job.get("multivoice"))
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
    author = job.get("author") or "Audiblez"

    # ---- 2. Plan segments/chunks (for accurate progress) ----------------
    for ch in chapters:
        ch["segments"] = _plan_chapter(ch, multivoice, voice, cast_map)
    total_chunks = sum(len(s["chunks"]) for c in chapters for s in c["segments"]) or 1
    mode = "multi-voice" if multivoice else "single voice"
    progress(stage="Preparing", percent=4,
             chapters_total=len(chapters), chunks_total=total_chunks,
             log=f"{len(chapters)} chapter(s), {total_chunks} segments, {mode}. "
                 f"Synthesizing on {ENGINE.device.upper()}…")

    # ---- 3. Synthesize ---------------------------------------------------
    chapter_wavs = []
    done = 0
    t0 = time.time()
    for idx, ch in enumerate(chapters):
        parts = []
        multi_seg = len(ch["segments"]) > 1
        for seg in ch["segments"]:
            for chunk in seg["chunks"]:
                parts.append(ENGINE.synth_chunk(chunk, seg["voice"], speed))
                done += 1
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = int((total_chunks - done) / rate) if rate > 0 else None
                pct = 4 + int(done / total_chunks * 78)
                progress(stage=f"Narrating: {ch['title']}", percent=pct,
                         chapters_done=idx, chunks_done=done, eta=eta)
            if multi_seg:
                parts.append(SEG_GAP)
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype="float32")
        wav_path = os.path.join(workdir, f"ch{idx:03d}.wav")
        sf.write(wav_path, audio, SAMPLE_RATE)
        chapter_wavs.append({"path": wav_path, "title": ch["title"]})

    # ---- 3b. Mix background ambience ------------------------------------
    bed = job.get("ambience_path") or amb.path_for(job.get("ambience_id"))
    if bed:
        progress(stage="Adding ambience", percent=84,
                 log="Mixing background sound under the narration…")
        for cw in chapter_wavs:
            mixed = cw["path"].replace(".wav", "_mix.wav")
            try:
                amb.mix(cw["path"], bed, mixed,
                        volume=float(job.get("ambience_volume", 0.12)),
                        duck=bool(job.get("ducking", True)))
                cw["path"] = mixed
            except Exception as e:  # noqa: BLE001
                progress(log=f"Ambience mix skipped for a chapter: {e}")

    # ---- 4. Encode outputs ----------------------------------------------
    outputs = []
    out_base = os.path.join(workdir, "out")
    os.makedirs(out_base, exist_ok=True)
    formats = job.get("formats", ["m4b", "mp3"])
    cover = job.get("cover")

    if "mp3" in formats:
        progress(stage="Encoding MP3", percent=86, log="Encoding per-chapter MP3 files…")
        mp3_dir = os.path.join(out_base, f"{title} (MP3)")
        os.makedirs(mp3_dir, exist_ok=True)
        for i, cw in enumerate(chapter_wavs):
            mp3_path = os.path.join(mp3_dir, f"{i + 1:02d} - {safe_name(cw['title'])}.mp3")
            args = ["-i", cw["path"]]
            if cover:
                args += ["-i", cover, "-map", "0:a", "-map", "1:v",
                         "-disposition:v", "attached_pic"]
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
        meta_path = os.path.join(workdir, "meta.txt")
        _write_ffmetadata(meta_path, title, author, chapters_meta)

        m4b_path = os.path.join(out_base, f"{title}.m4b")
        args = ["-f", "concat", "-safe", "0", "-i", concat_path, "-i", meta_path]
        if cover:
            args += ["-i", cover]
        args += ["-map_metadata", "1", "-map_chapters", "1", "-map", "0:a"]
        if cover:
            args += ["-map", "2:v", "-disposition:v", "attached_pic", "-c:v", "mjpeg"]
        args += ["-c:a", "aac", "-b:a", "96k", m4b_path]
        _ffmpeg(args)
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
