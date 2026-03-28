import asyncio
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_DIR = Path.home() / "Projects" / "mosi-downloader"
DOWNLOAD_DIR = Path.home() / "Downloads" / "media"
JOB_DIR = PROJECT_DIR / "jobs"
LOG_DIR = PROJECT_DIR / "logs"
COOKIE_DIR = PROJECT_DIR / "cookies"

JOB_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_DIR.mkdir(parents=True, exist_ok=True)

CONCURRENCY = int(os.getenv("MOSI_CONCURRENCY", "3"))
PUBLIC_BASE_URL = os.getenv(
    "MOSI_PUBLIC_BASE_URL", "https://viddown.tardis.oursquad.rocks"
).rstrip("/")
TELEGRAM_BOT_TOKEN = os.getenv("MOSI_TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("MOSI_TELEGRAM_CHAT_ID", "").strip()

# Job timeout in seconds (30 minutes)
JOB_TIMEOUT = int(os.getenv("MOSI_JOB_TIMEOUT", str(30 * 60)))

# Prefer venv yt-dlp (self-updatable), fall back to system binary
_VENV_YTDLP = PROJECT_DIR / ".venv" / "bin" / "yt-dlp"
_SYSTEM_YTDLP = Path("/usr/local/bin/yt-dlp")
YTDLP_BIN = str(_VENV_YTDLP) if _VENV_YTDLP.exists() else str(_SYSTEM_YTDLP)

# Cookie site → filename mapping
COOKIE_SITES = {
    "youtube": ["youtube.com", "youtu.be", "www.youtube.com"],
    "twitter": ["twitter.com", "x.com", "t.co", "www.twitter.com"],
    "instagram": ["instagram.com", "www.instagram.com"],
    "threads": ["threads.net", "www.threads.net", "threads.com", "www.threads.com"],
    "bluesky": ["bsky.app", "bsky.social", "www.bsky.app"],
}

app = FastAPI(title="Mosi Downloader API")

app.mount(
    "/static", StaticFiles(directory=str(PROJECT_DIR / "web" / "static")), name="static"
)


@app.get("/", response_class=HTMLResponse)
def index():
    return (PROJECT_DIR / "web" / "templates" / "index.html").read_text()


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str):
    return (PROJECT_DIR / "web" / "templates" / "job.html").read_text()


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return (PROJECT_DIR / "web" / "templates" / "admin.html").read_text()


job_lock = threading.Lock()
jobs: Dict[str, Dict[str, Any]] = {}
job_queue: "queue.Queue[str]" = queue.Queue()

PROGRESS_RE = re.compile(
    r"\[download\]\s+(\d+(?:\.\d+)?)%.*?(?:at\s+([^\s]+))?.*?(?:ETA\s+([0-9:]+))?", re.I
)
DEST_RE_1 = re.compile(r"^\[download\] Destination: (.+)$")
DEST_RE_2 = re.compile(r"^\[ExtractAudio\] Destination: (.+)$")
DEST_RE_3 = re.compile(r'^\[Merger\] Merging formats into "(.+)"$')
ALREADY_RE = re.compile(r"^\[download\]\s+(.+?) has already been downloaded$")
TITLE_RE = re.compile(r"^\[info\]\s+\S+: Downloading \d+ format", re.I)


class DownloadRequest(BaseModel):
    url: str
    quality: str = Field(default="best")
    playlist: bool = Field(default=True)


def now_ts() -> float:
    return time.time()


def job_file(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def save_job(job_id: str) -> None:
    with job_lock:
        data = jobs[job_id].copy()
    job_file(job_id).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def update_job(job_id: str, **kwargs: Any) -> None:
    with job_lock:
        jobs[job_id].update(kwargs)
        jobs[job_id]["updated_at"] = now_ts()
    save_job(job_id)


def append_log(job_id: str, line: str) -> None:
    with job_lock:
        jobs[job_id]["logs"].append(line.rstrip())
        jobs[job_id]["logs"] = jobs[job_id]["logs"][-300:]
    save_job(job_id)


def append_file(job_id: str, path_str: str) -> None:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = DOWNLOAD_DIR / path
    if path.exists():
        with job_lock:
            files = jobs[job_id].setdefault("files", [])
            p = str(path)
            if p not in files:
                files.append(p)
        save_job(job_id)


def load_existing_jobs() -> None:
    for jf in JOB_DIR.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
            # Mark any in-flight jobs as interrupted — they were running in a
            # previous process and will never complete now.
            if data.get("status") in ("downloading", "queued"):
                data["status"] = "failed"
                data["error"] = "Interrupted by server restart"
                data["updated_at"] = now_ts()
                jf.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            jobs[data["job_id"]] = data
        except Exception:
            continue


def fallback_find_files(
    started_at: float | None, completed_at: float | None
) -> list[str]:
    if started_at is None:
        return []
    end_ts = completed_at or time.time()
    found = []
    for p in DOWNLOAD_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".part", ".ytdl"}:
            continue
        try:
            mtime = p.stat().st_mtime
        except FileNotFoundError:
            continue
        if started_at - 5 <= mtime <= end_ts + 5:
            found.append((mtime, str(p)))
    found.sort(key=lambda x: x[0])
    return [path for _, path in found]


def cookie_file_for_url(url: str) -> Optional[Path]:
    """Return the cookie file path for a given URL, if one exists."""
    url_lower = url.lower()
    for site, domains in COOKIE_SITES.items():
        if any(d in url_lower for d in domains):
            p = COOKIE_DIR / f"{site}.txt"
            if p.exists():
                return p
    return None


def quality_args(quality: str) -> List[str]:
    q = quality.lower().strip()
    if q == "audio":
        return ["-x", "--audio-format", "mp3"]
    if q == "1080p":
        return ["-f", "bv*[height<=1080]+ba/b[height<=1080]/b"]
    if q == "720p":
        return ["-f", "bv*[height<=720]+ba/b[height<=720]/b"]
    if q == "480p":
        return ["-f", "bv*[height<=480]+ba/b[height<=480]/b"]
    return []


def make_zip(job_id: str, files: List[str]) -> Path:
    zpath = DOWNLOAD_DIR / f"{job_id}.zip"
    if zpath.exists():
        return zpath
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            p = Path(f)
            if p.exists():
                zf.write(p, arcname=p.name)
    return zpath


def telegram_notify(title: str, job_id: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    download_url = f"{PUBLIC_BASE_URL}/api/file/{job_id}"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"⬇️ *Download Complete*\n🎬 {title}",
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[{"text": "⬇️ Download", "url": download_url}]]
        },
    }
    try:
        req = Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urlopen(req)
    except Exception as e:
        print("Telegram error:", e)


def run_download(job_id: str) -> None:
    with job_lock:
        job = jobs[job_id]
        url = job["url"]
        quality = job["quality"]
        playlist = job["playlist"]

    update_job(
        job_id,
        status="downloading",
        started_at=now_ts(),
        progress=0.0,
        speed=None,
        eta=None,
    )

    # Sites that serve VP9/AV1 as default and have poor Apple ecosystem compatibility.
    # For these we skip thumbnail embedding (avoids a phantom second video track) and
    # sort format selection to prefer H.264 + AAC so files play natively on Mac/iOS.
    APPLE_COMPAT_DOMAINS = ["instagram.com", "threads.net", "bsky.app", "bsky.social"]
    apple_compat = any(d in url.lower() for d in APPLE_COMPAT_DOMAINS)

    cmd = [
        YTDLP_BIN,
        "--newline",
        "--progress",
        "--embed-metadata",
        "--geo-bypass-country",
        "US",
        "-P",
        f"home:{DOWNLOAD_DIR}",
    ]

    if apple_compat:
        cmd.extend(
            [
                "--remux-video",
                "mp4",
                "--format-sort",
                "+codec:h264:m4a",
                "--no-embed-thumbnail",
                "--no-embed-metadata",
            ]
        )
    else:
        cmd.append("--embed-thumbnail")

    # Inject cookies if available for this URL
    cookie_path = cookie_file_for_url(url)
    if cookie_path:
        cmd.extend(["--cookies", str(cookie_path)])

    if playlist:
        cmd.append("--yes-playlist")
    else:
        cmd.append("--no-playlist")

    if not apple_compat:
        cmd.extend(quality_args(quality))
    cmd.append(url)

    log_path = LOG_DIR / f"{job_id}.log"
    found_title = None
    started_at = jobs[job_id].get("started_at") or now_ts()

    with open(log_path, "a", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert proc.stdout is not None
        for raw in proc.stdout:
            # Timeout watchdog: kill if running too long
            if now_ts() - started_at > JOB_TIMEOUT:
                proc.kill()
                update_job(
                    job_id, status="failed", error=f"Timed out after {JOB_TIMEOUT}s"
                )
                return

            line = raw.rstrip("\n")
            lf.write(line + "\n")
            lf.flush()
            append_log(job_id, line)

            if line.startswith("[download] Downloading playlist:"):
                found_title = line.split(":", 1)[1].strip()
                update_job(job_id, title=found_title)
            elif line.startswith("[download] Downloading item "):
                update_job(job_id, title=found_title or "Playlist download")

            for rx in (DEST_RE_1, DEST_RE_2, DEST_RE_3, ALREADY_RE):
                m = rx.match(line)
                if m:
                    append_file(job_id, m.group(1))
                    break

            m = PROGRESS_RE.search(line)
            if m:
                progress = float(m.group(1))
                speed = m.group(2)
                eta = m.group(3)
                update_job(job_id, progress=progress, speed=speed, eta=eta)

            # Extract title from yt-dlp info lines like "[youtube] ID: Title"
            if not found_title:
                for prefix in (
                    "[youtube]",
                    "[TikTok]",
                    "[twitter]",
                    "[Instagram]",
                    "[x]",
                ):
                    if line.startswith(prefix) and ": " in line:
                        candidate = line.split(": ", 1)[-1].strip()
                        # Skip lines that are just IDs or operational messages
                        if len(candidate) > 10 and not candidate.startswith(
                            "Downloading"
                        ):
                            found_title = candidate
                            update_job(job_id, title=found_title)
                            break

        rc = proc.wait()

    with job_lock:
        files = [f for f in jobs[job_id].get("files", []) if Path(f).exists()]
        jobs[job_id]["files"] = files

    if rc == 0:
        completed_at = now_ts()
        with job_lock:
            files = [f for f in jobs[job_id].get("files", []) if Path(f).exists()]
            jobs[job_id]["files"] = files

        if not files:
            fallback_files = fallback_find_files(
                jobs[job_id].get("started_at"), completed_at
            )
            if fallback_files:
                update_job(job_id, files=fallback_files)

        final_title = jobs[job_id].get("title") or (
            "Playlist download" if playlist else "Download complete"
        )
        update_job(
            job_id,
            status="completed",
            completed_at=completed_at,
            progress=100.0,
            title=final_title,
        )
        try:
            telegram_notify(jobs[job_id].get("title") or "Download complete", job_id)
        except Exception as e:
            print(f"Telegram error: {e}", flush=True)
    else:
        # Extract a meaningful error from the tail of the log
        with job_lock:
            log_tail = jobs[job_id].get("logs", [])
        error_lines = [
            l for l in log_tail[-20:] if "ERROR" in l or "error" in l.lower()
        ]
        error_msg = error_lines[-1] if error_lines else f"yt-dlp exited with code {rc}"
        update_job(job_id, status="failed", error=error_msg)


def worker_loop() -> None:
    while True:
        job_id = job_queue.get()
        try:
            run_download(job_id)
        except Exception as e:
            update_job(job_id, status="failed", error=str(e))
        finally:
            job_queue.task_done()


@app.on_event("startup")
def startup() -> None:
    load_existing_jobs()
    for i in range(CONCURRENCY):
        t = threading.Thread(
            target=worker_loop, daemon=True, name=f"mosi-worker-{i + 1}"
        )
        t.start()


# ── Health & version ──────────────────────────────────────────────────────────


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "jobs": len(jobs),
        "queue_size": job_queue.qsize(),
        "concurrency": CONCURRENCY,
    }


@app.get("/api/ytdlp-version")
def ytdlp_version() -> Dict[str, Any]:
    try:
        result = subprocess.run(
            [YTDLP_BIN, "--version"], capture_output=True, text=True, timeout=10
        )
        version = result.stdout.strip()
    except Exception as e:
        version = f"error: {e}"
    return {"version": version, "binary": YTDLP_BIN}


# ── Admin: yt-dlp update ─────────────────────────────────────────────────────


@app.post("/api/admin/update-ytdlp")
def update_ytdlp() -> Dict[str, Any]:
    """Update yt-dlp via pip in the project venv."""
    pip_bin = PROJECT_DIR / ".venv" / "bin" / "pip"
    if not pip_bin.exists():
        raise HTTPException(status_code=500, detail="venv pip not found")
    try:
        result = subprocess.run(
            [str(pip_bin), "install", "-U", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        # Get new version
        ver_result = subprocess.run(
            [YTDLP_BIN, "--version"], capture_output=True, text=True, timeout=10
        )
        new_version = ver_result.stdout.strip()
        return {"ok": result.returncode == 0, "version": new_version, "output": output}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Update timed out")


# ── Admin: cookies ────────────────────────────────────────────────────────────


@app.get("/api/admin/cookies")
def list_cookies() -> List[Dict[str, Any]]:
    result = []
    for site in COOKIE_SITES:
        p = COOKIE_DIR / f"{site}.txt"
        if p.exists():
            stat = p.stat()
            result.append(
                {
                    "site": site,
                    "domains": COOKIE_SITES[site],
                    "size": stat.st_size,
                    "updated_at": stat.st_mtime,
                }
            )
        else:
            result.append(
                {
                    "site": site,
                    "domains": COOKIE_SITES[site],
                    "size": None,
                    "updated_at": None,
                }
            )
    return result


@app.post("/api/admin/cookies")
async def upload_cookies(
    site: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    if site not in COOKIE_SITES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown site '{site}'. Valid: {list(COOKIE_SITES.keys())}",
        )
    content = await file.read()
    # Sanity-check: must look like a Netscape cookie file
    if (
        b"# Netscape HTTP Cookie File" not in content[:200]
        and b"# HTTP Cookie File" not in content[:200]
    ):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a Netscape cookie file. "
            "Export using 'Get cookies.txt LOCALLY' extension.",
        )
    dest = COOKIE_DIR / f"{site}.txt"
    dest.write_bytes(content)
    return {"ok": True, "site": site, "size": len(content)}


@app.delete("/api/admin/cookies/{site}")
def delete_cookies(site: str) -> Dict[str, Any]:
    if site not in COOKIE_SITES:
        raise HTTPException(status_code=400, detail=f"Unknown site '{site}'")
    p = COOKIE_DIR / f"{site}.txt"
    if p.exists():
        p.unlink()
        return {"ok": True, "deleted": site}
    return {"ok": True, "deleted": None, "note": "File did not exist"}


# ── Jobs ──────────────────────────────────────────────────────────────────────


@app.post("/api/download")
def create_download(req: DownloadRequest) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "url": req.url,
        "quality": req.quality,
        "playlist": req.playlist,
        "status": "queued",
        "title": None,
        "progress": 0.0,
        "speed": None,
        "eta": None,
        "files": [],
        "logs": [],
        "error": None,
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "started_at": None,
        "completed_at": None,
    }
    with job_lock:
        jobs[job_id] = job
    save_job(job_id)
    job_queue.put(job_id)
    return {
        "job_id": job_id,
        "status": "queued",
        "events_url": f"/api/events/{job_id}",
        "status_url": f"/api/status/{job_id}",
        "file_url": f"/api/file/{job_id}",
    }


@app.get("/api/status/{job_id}")
def status(job_id: str) -> Dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    out = job.copy()
    out["log_tail"] = out.pop("logs", [])[-30:]
    return out


@app.get("/api/events/{job_id}")
async def events(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def gen():
        last = None
        while True:
            job = jobs.get(job_id)
            if not job:
                yield 'event: error\ndata: {"error":"Job not found"}\n\n'
                return

            payload = {
                "job_id": job["job_id"],
                "status": job["status"],
                "title": job.get("title"),
                "progress": job.get("progress"),
                "speed": job.get("speed"),
                "eta": job.get("eta"),
                "error": job.get("error"),
                "file_url": f"/api/file/{job_id}"
                if job["status"] == "completed"
                else None,
            }
            serialized = json.dumps(payload, ensure_ascii=False)
            if serialized != last:
                yield f"event: update\ndata: {serialized}\n\n"
                last = serialized

            if job["status"] in {"completed", "failed"}:
                event_type = "complete" if job["status"] == "completed" else "failed"
                yield f"event: {event_type}\ndata: {serialized}\n\n"
                return

            await asyncio.sleep(1)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/file/{job_id}")
def get_file(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Job not completed")

    files = [Path(f) for f in job.get("files", []) if Path(f).exists()]
    if not files:
        raise HTTPException(status_code=404, detail="No output file found")

    if len(files) == 1:
        p = files[0]
        return FileResponse(
            path=str(p), filename=p.name, media_type="application/octet-stream"
        )

    zpath = make_zip(job_id, [str(p) for p in files])
    return FileResponse(
        path=str(zpath), filename=zpath.name, media_type="application/zip"
    )


@app.get("/api/jobs")
def list_jobs():
    with job_lock:
        ordered = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return ordered[:100]


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> Dict[str, Any]:
    with job_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs.pop(job_id)
    jf = job_file(job_id)
    if jf.exists():
        jf.unlink()
    lf = LOG_DIR / f"{job_id}.log"
    if lf.exists():
        lf.unlink()
    return {"ok": True, "deleted": job_id}
