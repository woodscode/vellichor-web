# Audiblez Web 🎧

A self-hosted web app that turns your written stories (and ebooks) into
narrated audiobooks using the **Kokoro-82M** TTS model, GPU-accelerated on the
GTX 1080. Built for writing & converting stories.

- **URL:** http://192.168.8.165:7777
- **Login password:** see `AUDIBLEZ_PASSWORD` in `.env` (save it in Bitwarden)
- **Project dir:** `/mnt/user/appdata/audiblez-web`

## Features
- Built-in **story editor** (type/paste, `#` lines become chapters) + upload
  `.txt`, `.md`, `.epub`, `.pdf`, `.docx`.
- **Voice picker** with 35 voices, grouped/filterable, each with a ▶ sample.
  Story-friendly voices are starred (★). `af_heart` is the default.
- **Live preview** — hear your chosen voice read the current text before
  committing to a full conversion.
- Reading-speed slider, optional cover art, author label.
- **Live progress** (stage, segment count, ETA) + per-job log.
- **🎭 Multi-voice cast** — give each character their own voice. Three ways:
  - **🪄 Smart cast (AI)** — a local Ollama model (Llama 3.2 3B) reads the story,
    attributes each line to a speaker, and auto-inserts `[Name]` tags for you to
    review. Best for messy/untagged dialogue. Falls back to Quick detect if the
    model isn't ready.
  - **🔎 Quick detect** — fast rule-based: quotes + dialogue tags, with gender
    inference (honorifics + pronouns) to pick matching-gender voices.
  - **`[Name]` markup** — tag speakers yourself for exact control, e.g.
    `[Pip] "I can do it!"`.
  The cast panel lets you assign/preview a voice per character before converting.
  Works for **uploaded files too**: multi-voice auto-assigns distinct gender-matched
  voices to detected characters with zero setup, and 🔎/🪄 read the file's text so
  you can review/override the cast first.
- **🎵 Background ambience** — mix a bed under the narration: built-in
  license-free beds (Soft Rain, Gentle Night, Warm Hum, Dreamy Pad), or upload
  your own / drop files in `data/ambience/`. Volume slider + auto-ducking
  (music dips under speech).
- Output: **chaptered M4B** + **per-chapter MP3** (zip). Both downloadable.
- **Auto-export** to your Audiobookshelf library at
  `/mnt/user/eMedia/eMedia/Audiobooks/<Author>/<Title>/` (owned 911:911).
- Password login; job history survives restarts.

## Managing it
```bash
cd /mnt/user/appdata/audiblez-web
docker compose up -d            # start / apply changes
docker compose logs -f          # watch logs
docker compose down             # stop
docker compose up -d --build    # rebuild after editing app/ code
```

## AI Smart cast (Ollama)
The `ollama` service (in docker-compose) runs the local LLM on the GPU. After
first `docker compose up -d`, pull the model once:
```bash
docker exec audiblez-ollama ollama pull llama3.2:3b
```
Both models share the 1080; `OLLAMA_KEEP_ALIVE=2m` unloads the LLM from VRAM
after use so Kokoro has room. To try a more accurate (heavier) model, pull it
and set `SMARTCAST_MODEL` in `.env` (e.g. `qwen2.5:7b`), then `up -d`.

## Configuration (`.env`)
- `AUDIBLEZ_PASSWORD` — login password (change anytime, then `up -d`).
- `SECRET_KEY` — session-cookie signing key (don't change or logins reset).
- `NOTIFY_URL` — optional. Set to an ntfy/gotify URL to get a push when a
  conversion finishes, e.g. `http://192.168.8.165:8087/audiblez`.

## Data
- `./data/` — uploads, job workdirs, job history (`jobs.json`), cached voice
  samples (`samples/`), and the Hugging Face model cache (`hf-cache/`).
- Models download on first use and are cached in `./data/hf-cache`.

## Notes
- GPU is used automatically (`⚡ GPU` chip in the header). Falls back to CPU if
  the NVIDIA runtime is unavailable.
- Conversions run one at a time (single worker) so the GPU isn't oversubscribed.
