"""Job manager: a single background worker thread runs conversions one at a
time (so the GPU isn't oversubscribed). State is persisted to disk so the job
history survives restarts."""
import json
import os
import queue
import threading
import time
import traceback

import convert

DATA_DIR = "/data"
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
DB_PATH = os.path.join(DATA_DIR, "jobs.json")
MAX_LOG = 200


class JobManager:
    def __init__(self):
        os.makedirs(JOBS_DIR, exist_ok=True)
        self.jobs = {}            # id -> job dict
        self.lock = threading.Lock()
        self.q = queue.Queue()
        self._load()
        self.worker = threading.Thread(target=self._run_loop, daemon=True)
        self.worker.start()

    # ---- persistence ----------------------------------------------------
    def _load(self):
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH) as f:
                    self.jobs = json.load(f)
            except Exception:
                self.jobs = {}
        # any job left "running"/"queued" from a previous run is now stale
        for j in self.jobs.values():
            if j["status"] in ("running", "queued"):
                j["status"] = "interrupted"
                j["stage"] = "Interrupted by restart"

    def _save(self):
        tmp = DB_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.jobs, f)
        os.replace(tmp, DB_PATH)

    # ---- public api -----------------------------------------------------
    def create(self, spec: dict) -> dict:
        jid = spec["id"]
        workdir = os.path.join(JOBS_DIR, jid)
        os.makedirs(workdir, exist_ok=True)
        job = {
            **spec,
            "workdir": workdir,
            "status": "queued",
            "stage": "Queued",
            "percent": 0,
            "log": [],
            "eta": None,
            "chapters_total": None,
            "chunks_total": None,
            "chunks_done": 0,
            "result": None,
            "error": None,
            "created": time.time(),
        }
        with self.lock:
            self.jobs[jid] = job
            self._save()
        self.q.put(jid)
        return self.public(job)

    def public(self, job: dict) -> dict:
        """A JSON-safe view (hide internal paths)."""
        keys = ("id", "status", "stage", "percent", "eta", "title", "author",
                "voice", "engine", "voice_label", "speed", "chapters_total",
                "chunks_total", "chunks_done", "error", "created")
        out = {k: job.get(k) for k in keys}
        out["log"] = job.get("log", [])[-30:]
        res = job.get("result")
        if res:
            out["result"] = {
                "duration_ms": res.get("duration_ms"),
                "chapters": res.get("chapters"),
                "exported_to": res.get("exported_to"),
                "downloads": [{"label": o["label"], "name": o["name"],
                               "kind": o["kind"]} for o in res.get("outputs", [])],
            }
        return out

    def list(self):
        with self.lock:
            return [self.public(j) for j in sorted(
                self.jobs.values(), key=lambda x: x["created"], reverse=True)]

    def get(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            return self.public(j) if j else None

    def get_raw(self, jid):
        with self.lock:
            return self.jobs.get(jid)

    def cancel(self, jid):
        """Signal a running/queued job to stop at the next checkpoint."""
        with self.lock:
            job = self.jobs.get(jid)
            if not job or job["status"] not in ("running", "queued"):
                return False
            job["cancel"] = True
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["stage"] = "Cancelled"
            else:
                job["stage"] = "Stopping…"
            self._save()
        return True

    def delete(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            if j:
                j["cancel"] = True          # stop the worker if it's still running
            j = self.jobs.pop(jid, None)
            self._save()
        if j:
            import shutil
            shutil.rmtree(j["workdir"], ignore_errors=True)
        return bool(j)

    def find_output(self, jid, name):
        job = self.get_raw(jid)
        if not job or not job.get("result"):
            return None
        for o in job["result"].get("outputs", []):
            if o["name"] == name and os.path.exists(o["path"]):
                return o["path"]
        return None

    # ---- worker ---------------------------------------------------------
    def _progress_factory(self, jid):
        def progress(**fields):
            with self.lock:
                job = self.jobs.get(jid)
                if not job:
                    return
                log_msg = fields.pop("log", None)
                job.update(fields)
                if log_msg:
                    job["log"].append({"t": time.time(), "msg": log_msg})
                    job["log"] = job["log"][-MAX_LOG:]
                self._save()
        return progress

    def _run_loop(self):
        while True:
            jid = self.q.get()
            with self.lock:
                job = self.jobs.get(jid)
            if not job or job["status"] != "queued":
                continue
            progress = self._progress_factory(jid)
            with self.lock:
                job["status"] = "running"
                job["stage"] = "Starting"
                self._save()
            try:
                result = convert.run(job, progress)
                with self.lock:
                    job["status"] = "done"
                    job["result"] = result
                    job["percent"] = 100
                    job["stage"] = "Done"
                    job["eta"] = 0
                    self._save()
            except convert.Cancelled:
                with self.lock:
                    if jid in self.jobs:
                        job["status"] = "cancelled"
                        job["stage"] = "Cancelled"
                        job["eta"] = None
                        job["log"].append({"t": time.time(), "msg": "Conversion stopped."})
                        self._save()
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                with self.lock:
                    job["status"] = "error"
                    job["error"] = str(e)
                    job["stage"] = "Failed"
                    job["log"].append({"t": time.time(), "msg": f"Error: {e}"})
                    self._save()
            finally:
                self._notify(jid)

    def _notify(self, jid):
        """Optional push notification on completion (ntfy/gotify via env URL)."""
        url = os.environ.get("NOTIFY_URL")
        if not url:
            return
        try:
            import urllib.request
            job = self.get_raw(jid)
            status = job["status"]
            title = job.get("title", "Audiobook")
            msg = (f"✅ '{title}' is ready" if status == "done"
                   else f"❌ '{title}' failed: {job.get('error')}")
            req = urllib.request.Request(url, data=msg.encode(),
                                         headers={"Title": "Vellichor"})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


MANAGER = JobManager()
