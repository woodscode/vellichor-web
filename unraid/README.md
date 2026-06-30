# Unraid (Community Applications)

`vellichor-web.xml` is an Unraid Docker template for installing Vellichor from
the published GHCR image (`ghcr.io/woodscode/vellichor-web`).

## Install it now (before it's in the CA store)
On your Unraid box:
1. **Docker** tab → **Add Container**.
2. Set **Template** to the raw URL of this file, or paste the fields manually:
   `https://raw.githubusercontent.com/woodscode/vellichor-web/main/unraid/vellichor-web.xml`
3. Set **Login password** (and ideally **Secret key** = `openssl rand -hex 32`),
   point **App data** at an appdata path, and **Audiobook library** at your
   library share (or clear it).
4. **GPU:** keep `--runtime=nvidia` in *Extra Parameters* only if you have the
   **Nvidia Driver** plugin installed; otherwise clear it to run on CPU.
5. Apply, then browse to `http://<server-ip>:7777`.

## AI Smart cast (optional)
Smart cast uses a local **Ollama** LLM to attribute dialogue to speakers. The
Vellichor container does **not** include Ollama — you run it separately and
point Vellichor at it. Without it, multi-voice casting falls back to the
rule-based **Quick detect**, so this is entirely optional.

**1. Run an Ollama container.** Easiest on Unraid: install **Ollama** from
Community Applications. Or from the command line:
```bash
docker run -d --name ollama --restart unless-stopped \
  --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all \
  -v /mnt/user/appdata/ollama:/root/.ollama \
  -p 11434:11434 ollama/ollama
```
Drop the `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all` flags to run on CPU.

> **Pascal GPUs (GTX 10-series, e.g. the 1080):** recent Ollama dropped the
> Pascal CUDA build, so the model silently falls back to CPU. Pin a version
> that still bundles it — use `ollama/ollama:0.30.11` instead of `ollama/ollama`.

**2. Pull the model once** (use your Ollama container's name):
```bash
docker exec ollama ollama pull llama3.2:3b
```

**3. Point Vellichor at it:** set **Ollama URL** in the Vellichor template to
`http://<unraid-ip>:11434` — use the host IP, not `localhost`, since they're
separate containers.

On a single GPU, Vellichor hands VRAM back and forth between Kokoro and Ollama
automatically (it evicts whichever model is idle before the other runs). This
works across containers via Ollama's API, as long as the Ollama container also
has GPU access.

## Getting it into the Community Applications store
1. Make the GHCR package **public**: GitHub repo → **Packages** →
   `vellichor-web` → **Package settings** → change visibility to Public.
2. Add an **icon**: drop a square PNG at `unraid/icon.png` in this repo (the
   template's `<Icon>` already points there).
3. Create a **support thread** on the Unraid forums (the template references
   the GitHub issues page; CA prefers a forum support URL — update `<Support>`
   if you make one).
4. Submit the template repo to Community Applications via the official thread:
   <https://forums.unraid.net/topic/38582-plug-in-community-applications/> —
   follow "how to add your templates to CA". A moderator reviews it before it
   appears in the store.
