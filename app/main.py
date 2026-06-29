"""Audiblez Web — FastAPI app: routes, uploads, conversion jobs, downloads."""
import os
import shutil
import threading
import time
import uuid

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import (JSONResponse, FileResponse, HTMLResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles

import auth
import voices as voicecat
import cast as castmod
import ambience as amb
from tts import ENGINE
from jobs import MANAGER

DATA_DIR = "/data"
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Audiblez Web")

# Pre-generate samples for the story-recommended voices in the background.
_PREWARM = [v["id"] for v in voicecat.VOICES if v["story"]]
threading.Thread(target=ENGINE.prewarm, args=(_PREWARM,), daemon=True).start()
# Generate the built-in ambience beds in the background.
threading.Thread(target=amb.ensure_builtins, daemon=True).start()


# ---- auth middleware ----------------------------------------------------
PUBLIC_PATHS = {"/login", "/api/login", "/favicon.ico", "/healthz"}


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if (not auth.ENABLED or path in PUBLIC_PATHS
            or path.startswith("/static/")):
        return await call_next(request)
    if not auth.is_authed(request):
        if path.startswith("/api/"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return RedirectResponse("/login")
    return await call_next(request)


# ---- pages --------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if not auth.check_password(body.get("password", "")):
        raise HTTPException(status_code=401, detail="Wrong password")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.MAX_AGE,
                    httponly=True, samesite="lax")
    return resp


@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


# ---- voices -------------------------------------------------------------
@app.get("/api/voices")
def list_voices():
    return {"voices": voicecat.VOICES, "default": voicecat.DEFAULT_VOICE,
            "device": ENGINE.device}


@app.get("/api/voice-sample/{voice}")
def voice_sample(voice: str):
    if not voicecat.is_valid(voice):
        raise HTTPException(404, "Unknown voice")
    try:
        path = ENGINE.ensure_sample(voice)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Sample generation failed: {e}")
    return FileResponse(path, media_type="audio/mpeg")


@app.post("/api/analyze")
async def analyze_cast(request: Request):
    """Detect speaking characters in pasted text for the cast panel."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return {"characters": [], "has_markup": False}
    return {"characters": castmod.detect_characters(text),
            "has_markup": castmod.has_markup(text)}


@app.get("/api/ambience")
def ambience_list():
    return {"beds": amb.list_beds()}


@app.get("/api/ambience-sample/{bed_id}")
def ambience_sample(bed_id: str):
    path = amb.path_for(bed_id)
    if not path:
        raise HTTPException(404, "Unknown ambience bed")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/preview")
async def preview(request: Request):
    """Synthesize a short live preview of arbitrary text in a chosen voice."""
    body = await request.json()
    voice = body.get("voice", voicecat.DEFAULT_VOICE)
    text = (body.get("text") or "").strip()[:400]
    speed = float(body.get("speed", 1.0))
    if not voicecat.is_valid(voice):
        raise HTTPException(400, "Unknown voice")
    if not text:
        raise HTTPException(400, "Nothing to preview")
    import soundfile as sf
    import subprocess
    pid = uuid.uuid4().hex
    wav = os.path.join(UPLOAD_DIR, f"prev_{pid}.wav")
    mp3 = os.path.join(UPLOAD_DIR, f"prev_{pid}.mp3")
    audio = ENGINE.synth_chunk(text, voice, speed)
    sf.write(wav, audio, 24000)
    subprocess.run(["ffmpeg", "-y", "-i", wav, "-c:a", "libmp3lame", "-q:a", "5", mp3],
                   check=True, capture_output=True)
    os.remove(wav)
    return FileResponse(mp3, media_type="audio/mpeg",
                        background=_cleanup(mp3))


def _cleanup(path):
    from starlette.background import BackgroundTask

    def rm():
        time.sleep(30)
        try:
            os.remove(path)
        except OSError:
            pass
    return BackgroundTask(lambda: threading.Thread(target=rm, daemon=True).start())


# ---- conversion ---------------------------------------------------------
@app.post("/api/convert")
async def convert_endpoint(
    request: Request,
    voice: str = Form(...),
    speed: float = Form(1.0),
    title: str = Form(""),
    author: str = Form("Audiblez"),
    formats: str = Form("m4b,mp3"),
    export_abs: bool = Form(False),
    text: str = Form(""),
    multivoice: bool = Form(False),
    cast: str = Form(""),
    ambience: str = Form(""),
    ambience_volume: float = Form(0.12),
    ducking: bool = Form(True),
    file: UploadFile = File(None),
    cover: UploadFile = File(None),
    ambience_file: UploadFile = File(None),
):
    if not voicecat.is_valid(voice):
        raise HTTPException(400, "Unknown voice")

    cast_map = {}
    if multivoice and cast:
        import json as _json
        try:
            raw = _json.loads(cast)
            cast_map = {k: v for k, v in raw.items() if voicecat.is_valid(v)}
        except Exception:
            cast_map = {}

    jid = uuid.uuid4().hex
    workdir = os.path.join(DATA_DIR, "jobs", jid)
    os.makedirs(workdir, exist_ok=True)

    source = None
    if file is not None and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        from extract import SUPPORTED_EXTS
        if ext not in SUPPORTED_EXTS:
            raise HTTPException(400, f"Unsupported file type: {ext}")
        source = os.path.join(workdir, "input" + ext)
        with open(source, "wb") as f:
            shutil.copyfileobj(file.file, f)
        if not title:
            title = os.path.splitext(file.filename)[0]
    elif not text.strip():
        raise HTTPException(400, "Provide some text or a file to convert.")

    cover_path = None
    if cover is not None and cover.filename:
        cext = os.path.splitext(cover.filename)[1].lower()
        if cext in (".jpg", ".jpeg", ".png"):
            cover_path = os.path.join(workdir, "cover" + cext)
            with open(cover_path, "wb") as f:
                shutil.copyfileobj(cover.file, f)

    # Uploaded ambience track takes precedence over a built-in/library bed id
    ambience_path = None
    if ambience_file is not None and ambience_file.filename:
        aext = os.path.splitext(ambience_file.filename)[1].lower()
        if aext in amb.AUDIO_EXTS:
            ambience_path = os.path.join(workdir, "ambience" + aext)
            with open(ambience_path, "wb") as f:
                shutil.copyfileobj(ambience_file.file, f)

    spec = {
        "id": jid,
        "source": source,
        "text": text,
        "title": title or "Story",
        "author": author or "Audiblez",
        "voice": voice,
        "speed": max(0.5, min(2.0, speed)),
        "formats": [f for f in formats.split(",") if f in ("m4b", "mp3")] or ["m4b"],
        "export_abs": bool(export_abs),
        "cover": cover_path,
        "multivoice": bool(multivoice),
        "cast": cast_map,
        "ambience_id": ambience or "",
        "ambience_path": ambience_path,
        "ambience_volume": max(0.0, min(1.0, ambience_volume)),
        "ducking": bool(ducking),
    }
    return MANAGER.create(spec)


@app.get("/api/jobs")
def jobs_list():
    return {"jobs": MANAGER.list()}


@app.get("/api/jobs/{jid}")
def job_get(jid: str):
    job = MANAGER.get(jid)
    if not job:
        raise HTTPException(404, "No such job")
    return job


@app.delete("/api/jobs/{jid}")
def job_delete(jid: str):
    if not MANAGER.delete(jid):
        raise HTTPException(404, "No such job")
    return {"ok": True}


@app.get("/api/download/{jid}/{name}")
def download(jid: str, name: str):
    path = MANAGER.find_output(jid, name)
    if not path:
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@app.get("/healthz")
def health():
    return {"ok": True, "device": ENGINE.device}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
