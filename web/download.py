#!/usr/bin/env python
"""Video downloader — yt-dlp based, saves to configured downloads directory."""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

from config_paths import DOWNLOAD_DIR as _DL, THUMB_DIR as _TH, COOKIE_PATH as _CK

# 兼容旧代码的路径变量
SAVE_DIR = _DL
COOKIE_PATH = _CK
THUMB_DIR = _TH


def _refresh_path() -> None:
    """Reload PATH from registry so winget tools (ffmpeg) are visible.

    No-op on non-Windows platforms.
    """
    if os.name != "nt":
        return
    try:
        import winreg
        paths = [os.environ.get("PATH", "")]
        for hive, key in [
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, "Environment"),
        ]:
            try:
                with winreg.OpenKey(hive, key) as k:
                    val, _ = winreg.QueryValueEx(k, "PATH")
                    if val:
                        paths.insert(0, val)
            except Exception:
                pass
        os.environ["PATH"] = ";".join(paths)
        os.environ["Path"] = ";".join(paths)
    except ImportError:
        pass


# Refresh PATH on Windows at module load so yt-dlp / ffmpeg are found
if os.name == "nt":
    _refresh_path()


QUALITY_FORMATS = {
    "best": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "audio_only": "bestaudio/best",
}

# ── Speed tuning ──
# How many videos to download at once in a batch (network-bound; yt-dlp releases
# the GIL during I/O so threads give a near-linear speedup).
DOWNLOAD_CONCURRENCY = 3
# Parallel fragments per video (DASH/HLS) when not using an external downloader.
FRAGMENT_CONCURRENCY = 4
# aria2c gives multi-connection downloads (big win for large files). Used only
# when the binary is present on PATH — otherwise we fall back to yt-dlp's native
# downloader, so this is a zero-dependency optimisation.
_ARIA2C = shutil.which("aria2c")


def _resolve_ffmpeg_dir() -> str | None:
    """Directory holding a usable ffmpeg, or ``None`` to fall back to PATH.

    When frozen by PyInstaller we ship a slim ffmpeg under ``_internal/ffmpeg/``
    so the distributed app works on machines without ffmpeg installed. In a
    normal source checkout this returns ``None`` and ffmpeg is taken from PATH.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        cand = base / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if cand.exists():
            return str(cand.parent)
    return None


# Directory of the bundled ffmpeg (None → use PATH).
FFMPEG_DIR = _resolve_ffmpeg_dir()


def _ffmpeg_exe() -> str:
    """Path to the ffmpeg binary (bundled if present, else the name on PATH)."""
    if FFMPEG_DIR:
        return os.path.join(FFMPEG_DIR, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    return "ffmpeg"


def _ffprobe_exe() -> str:
    """Path to the ffprobe binary (bundled if present, else the name on PATH)."""
    if FFMPEG_DIR:
        return os.path.join(FFMPEG_DIR, "ffprobe.exe" if os.name == "nt" else "ffprobe")
    return "ffprobe"

# ── State ──

_save_dir_lock = threading.Lock()
_current_save_dir: Path = SAVE_DIR


def get_save_dir() -> str:
    """Return current save directory path."""
    return str(_current_save_dir)


def set_save_dir(path: str) -> None:
    """Change save directory, create it."""
    global _current_save_dir
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    with _save_dir_lock:
        _current_save_dir = p


def check_status() -> dict:
    """Return downloader status."""
    has_cookies = COOKIE_PATH.exists()
    try:
        import yt_dlp  # noqa: F401
        return {
            "yt_dlp_ok": True,
            "nico_cookie_ok": has_cookies,
            "available_formats": list(QUALITY_FORMATS.keys()),
            "save_dir": str(_current_save_dir),
            "save_dir_exists": _current_save_dir.exists(),
        }
    except ImportError:
        return {"yt_dlp_ok": False, "error": "yt-dlp not installed"}


def _safe_name(title: str, video_id: str, ext: str = ".mp4") -> str:
    """Build a safe filename from title."""
    base = "".join(c for c in title[:50] if c.isalnum() or c in " _-（）()").strip()
    return f"{base or video_id}{ext}"


# Serialises the "pick a unique name + move into place" step so that concurrent
# downloads (DOWNLOAD_CONCURRENCY > 1) can't both claim the same name and clobber
# each other. The move is a same-filesystem rename, so the lock is held briefly.
_move_lock = threading.Lock()


def _unique_path(directory: Path, filename: str) -> str:
    """Return a non-colliding path inside *directory* for *filename*."""
    dst = directory / filename
    base, ext = os.path.splitext(str(dst))
    counter = 1
    while os.path.exists(dst):
        dst = Path(f"{base} ({counter}){ext}")
        counter += 1
    return str(dst)


def _yt_dlp_opts(format_key: str, out_dir: str) -> dict:
    """Build yt-dlp options."""
    fmt = QUALITY_FORMATS.get(format_key, QUALITY_FORMATS["best"])
    opts: dict = {
        "format": fmt,
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,  # progress reaches the UI via progress_hooks, not stdout
        "windowsfilenames": True,
        # Speed + resilience
        "concurrent_fragment_downloads": FRAGMENT_CONCURRENCY,
        "retries": 5,
        "fragment_retries": 5,
    }
    if FFMPEG_DIR:
        # Point yt-dlp at our bundled ffmpeg/ffprobe for stream merging.
        opts["ffmpeg_location"] = FFMPEG_DIR
    if _ARIA2C:
        # Multi-connection download via aria2c (ignores concurrent_fragment_downloads).
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = {"aria2c": ["-x", "16", "-s", "16", "-k", "1M"]}
    if COOKIE_PATH.exists():
        opts["cookiefile"] = str(COOKIE_PATH)
    return opts


def _get_url(video_id: str, platform: str) -> str:
    # "official" rows are curated YouTube channels — same watch URL as youtube.
    if platform in ("youtube", "official"):
        return f"https://www.youtube.com/watch?v={video_id}"
    if platform == "niconico":
        return f"https://www.nicovideo.jp/watch/{video_id}"
    raise ValueError(f"Unknown platform: {platform}")


def _find_downloaded(directory: str) -> str | None:
    """Find the downloaded file in a directory, preferring .mp4."""
    files = os.listdir(directory)
    for ext in (".mp4", ".webm", ".mkv", ".mp3", ".m4a"):
        for f in files:
            if f.lower().endswith(ext):
                return os.path.join(directory, f)
    return os.path.join(directory, files[0]) if files else None


_TMP_PREFIX = ".hm_dl_"


def _sweep_orphan_tmp(directory: Path) -> None:
    """Remove leftover download temp dirs from crashed runs (best effort).

    Only sweeps dirs older than an hour so in-flight downloads are never touched.
    """
    cutoff = time.time() - 3600
    try:
        for entry in directory.iterdir():
            if entry.is_dir() and entry.name.startswith(_TMP_PREFIX):
                try:
                    if entry.stat().st_mtime < cutoff:
                        shutil.rmtree(entry, ignore_errors=True)
                except OSError:
                    pass
    except OSError:
        pass


def download_single(
    video_id: str,
    platform: str,
    format_key: str = "best",
    title_hint: str = "",
    thumbnail_url: str = "",
    progress_hook: callable | None = None,
) -> dict:
    """Download a single video to SAVE_DIR. Returns result dict.

    *progress_hook* receives yt-dlp progress dicts for real-time updates.
    """
    import yt_dlp

    url = _get_url(video_id, platform)
    with _save_dir_lock:
        save_dir = _current_save_dir
    save_dir.mkdir(parents=True, exist_ok=True)
    # Download into a temp subdir *inside* the save dir so the final move is a
    # same-filesystem rename (instant) instead of a cross-drive copy of a
    # potentially multi-GB file — the OS temp dir is usually on C: while the
    # save dir may live on another drive.
    tmpdir = tempfile.mkdtemp(prefix=_TMP_PREFIX, dir=str(save_dir))

    try:
        opts = _yt_dlp_opts(format_key, tmpdir)
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)

        src = _find_downloaded(tmpdir)
        if not src:
            raise FileNotFoundError("No output file produced")

        ext = os.path.splitext(src)[1] or ".mp4"
        dst_name = _safe_name(title_hint, video_id, ext)
        # Reserve a unique name and move under one lock so concurrent downloads
        # can't race on the same filename.
        with _move_lock:
            dst = _unique_path(save_dir, dst_name)
            shutil.move(src, dst)

        size_mb = os.path.getsize(dst) / 1e6
        logger.info("Downloaded %s/%s → %s (%.1f MB)", platform, video_id, dst, size_mb)

        # Prefer the platform's real thumbnail; fall back to an ffmpeg frame grab.
        if not (thumbnail_url and _download_thumb_url(thumbnail_url, dst)):
            generate_thumbnail(dst)

        return {
            "ok": True,
            "path": dst,
            "filename": os.path.basename(dst),
            "size_mb": round(size_mb, 1),
        }
    except Exception as e:
        logger.error("Download failed %s/%s: %s", platform, video_id, e)
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def download_batch(
    items: list[dict],
    format_key: str = "best",
) -> dict:
    """Download multiple videos to SAVE_DIR, up to DOWNLOAD_CONCURRENCY at once."""
    results = {"ok": [], "failed": [], "save_dir": str(_current_save_dir)}

    def _one(item: dict) -> tuple[dict, dict]:
        r = download_single(
            video_id=item["video_id"],
            platform=item["platform"],
            format_key=format_key,
            title_hint=item.get("title", ""),
            thumbnail_url=item.get("thumbnail_url", ""),
        )
        return item, r

    workers = max(1, min(DOWNLOAD_CONCURRENCY, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item, r in pool.map(_one, items):
            if r["ok"]:
                results["ok"].append(r)
            else:
                results["failed"].append({"video_id": item["video_id"], "error": r["error"]})

    logger.info("Batch done: %d ok, %d failed", len(results["ok"]), len(results["failed"]))
    return results


def open_save_dir() -> None:
    """Open save directory in the OS file manager (cross-platform)."""
    with _save_dir_lock:
        d = _current_save_dir
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.Popen(["explorer", str(d)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(d)])
    else:
        subprocess.Popen(["xdg-open", str(d)])


# ── Library (material management) ──

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".ts"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".opus", ".wav", ".flac"}
ALL_MEDIA = VIDEO_EXTS | AUDIO_EXTS

# ── Media duration (probed via ffprobe, cached by filename+mtime) ──

_DUR_CACHE_PATH = THUMB_DIR / "_durations.json"
_dur_cache_lock = threading.Lock()


def _probe_duration(path: str) -> int:
    """Return media duration in whole seconds via ffprobe (0 on failure)."""
    try:
        out = subprocess.run(
            [_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, timeout=20, text=True,
        )
        return int(float(out.stdout.strip()))
    except Exception:
        return 0


def _load_dur_cache() -> dict:
    try:
        return json.loads(_DUR_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_dur_cache(cache: dict) -> None:
    try:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        _DUR_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass


def _fill_durations(files: list[dict]) -> None:
    """Attach ``duration_seconds`` to each file, probing only new/changed ones."""
    with _dur_cache_lock:
        cache = _load_dur_cache()
        dirty = False
        for f in files:
            key = f["filename"]
            mtime = int(f["modified"])
            ent = cache.get(key)
            if ent and ent.get("mtime") == mtime:
                f["duration_seconds"] = ent.get("dur", 0)
            else:
                dur = _probe_duration(f["path"])
                f["duration_seconds"] = dur
                cache[key] = {"dur": dur, "mtime": mtime}
                dirty = True
        if dirty:
            present = {f["filename"] for f in files}
            cache = {k: v for k, v in cache.items() if k in present}
            _save_dur_cache(cache)


def list_library(sort: str = "date") -> dict:
    """List all downloaded media files with metadata."""
    _current_save_dir.mkdir(parents=True, exist_ok=True)
    files = []
    total_size = 0

    for entry in _current_save_dir.iterdir():
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext not in ALL_MEDIA:
            continue
        stat = entry.stat()
        size_mb = stat.st_size / 1e6
        total_size += size_mb
        thumb_path = _thumb_path(entry.name)
        files.append({
            "filename": entry.name,
            "path": str(entry),
            "size": stat.st_size,
            "size_mb": round(size_mb, 1),
            "ext": ext,
            "type": "video" if ext in VIDEO_EXTS else "audio",
            "modified": stat.st_mtime,
            "thumb": str(thumb_path) if thumb_path.exists() else None,
        })

    _fill_durations(files)

    if sort == "date":
        files.sort(key=lambda f: f["modified"], reverse=True)
    elif sort == "size":
        files.sort(key=lambda f: f["size"], reverse=True)
    elif sort == "name":
        files.sort(key=lambda f: f["filename"].lower())

    return {
        "files": files,
        "count": len(files),
        "total_size_mb": round(total_size, 1),
        "save_dir": str(_current_save_dir),
    }


def delete_files(filenames: list[str]) -> dict:
    """Delete media files from library (also removes thumbnails)."""
    deleted, failed, freed = [], [], 0.0
    for name in filenames:
        safe = os.path.basename(name)
        path = _current_save_dir / safe
        if not path.exists():
            failed.append({"filename": safe, "error": "not found"})
            continue
        try:
            sz = path.stat().st_size
            path.unlink()
            thumb = _thumb_path(path.name)
            if thumb.exists():
                thumb.unlink()
            freed += sz / 1e6
            deleted.append(safe)
        except Exception as e:
            failed.append({"filename": safe, "error": str(e)})
    return {"deleted": deleted, "failed": failed, "freed_mb": round(freed, 1)}


_ILLEGAL_NAME_CHARS = '<>:"/\\|?*'


def rename_file(old_name: str, new_name: str) -> dict:
    """Rename a media file (and its thumbnail) inside the save directory.

    The new name is sanitised (path components and illegal characters stripped);
    if the user omits an extension the original one is preserved. Refuses to
    overwrite an existing different file.
    """
    old_safe = os.path.basename(old_name)
    new_safe = os.path.basename(new_name).strip()
    for ch in _ILLEGAL_NAME_CHARS:
        new_safe = new_safe.replace(ch, "")
    new_safe = new_safe.strip()
    if not new_safe:
        return {"ok": False, "error": "新文件名不能为空"}

    src = _current_save_dir / old_safe
    if not src.exists():
        return {"ok": False, "error": "文件不存在"}

    # Preserve the original extension if the user didn't supply one
    if not Path(new_safe).suffix:
        new_safe += src.suffix
    dst = _current_save_dir / new_safe

    if dst.exists() and dst.resolve() != src.resolve():
        return {"ok": False, "error": "目标文件名已存在"}

    try:
        old_thumb = _thumb_path(src.name)
        src.rename(dst)
        if old_thumb.exists():
            old_thumb.rename(_thumb_path(dst.name))
        logger.info("Renamed %s → %s", old_safe, new_safe)
        return {"ok": True, "filename": dst.name}
    except Exception as e:
        logger.error("Rename failed %s → %s: %s", old_safe, new_safe, e)
        return {"ok": False, "error": str(e)}


def open_file(filename: str) -> dict:
    """Open a file with the default OS handler (cross-platform)."""
    safe = os.path.basename(filename)
    path = _current_save_dir / safe
    if not path.exists():
        return {"ok": False, "error": "file not found"}
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"ok": True, "path": str(path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def library_file_path(filename: str) -> Path | None:
    """Resolve a media filename to a real path inside the save dir, or ``None``.

    Guards against directory traversal (only ``basename`` is honoured) and only
    returns paths for recognised media files that actually exist.
    """
    safe = os.path.basename(filename)
    path = _current_save_dir / safe
    if path.suffix.lower() not in ALL_MEDIA:
        return None
    if not path.exists() or not path.is_file():
        return None
    return path


def _thumb_path(video_filename: str) -> Path:
    """Get thumbnail path for a video file (in thumbnails/ directory)."""
    return THUMB_DIR / (Path(video_filename).stem + ".jpg")


def _download_thumb_url(url: str, video_path: str) -> str | None:
    """Download thumbnail from URL, save to thumbnails/ directory."""
    from urllib.request import urlopen
    thumb = _thumb_path(Path(video_path).name)
    if thumb.exists():
        return str(thumb)
    try:
        with urlopen(url, timeout=15) as resp:
            THUMB_DIR.mkdir(parents=True, exist_ok=True)
            thumb.write_bytes(resp.read())
        return str(thumb)
    except Exception:
        return None


def generate_thumbnail(filepath: str, force: bool = False) -> str | None:
    """Extract a single frame as a thumbnail. Returns thumb path or None.

    Seeks to 10s for normal videos but falls back to the first frame for clips
    shorter than that (e.g. Shorts), where a 10s seek yields no frame.
    """
    path = Path(filepath)
    thumb = _thumb_path(path.name)
    if not force and thumb.exists():
        return str(thumb)
    try:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    for seek in ("10", "0"):
        try:
            subprocess.run(
                [_ffmpeg_exe(), "-y", "-ss", seek, "-i", str(path),
                 "-vframes", "1", "-q:v", "3", "-s", "480x270", str(thumb)],
                capture_output=True, timeout=15, check=True,
            )
            if thumb.exists() and thumb.stat().st_size > 0:
                return str(thumb)
        except Exception:
            continue
    return None


# ── Background download jobs with progress streaming ──

_download_jobs: dict[str, dict] = {}
_download_jobs_lock = threading.Lock()


class _DownloadCancelled(Exception):
    """Raised inside a progress hook to abort an in-flight yt-dlp download."""


def _start_cleanup_worker() -> None:
    """Daemon thread: remove completed jobs older than 10 minutes."""
    while True:
        time.sleep(60)
        now = time.time()
        with _download_jobs_lock:
            stale = [
                jid for jid, j in _download_jobs.items()
                if j.get("status") == "done" and (now - j.get("finished_at", now)) > 600
            ]
            for jid in stale:
                _download_jobs.pop(jid, None)


_cleanup_thread = threading.Thread(target=_start_cleanup_worker, daemon=True)
_cleanup_thread.start()


def start_download_job(items: list[dict], format_key: str) -> str:
    """Start a background download batch, return job_id."""
    with _save_dir_lock:
        _sweep_orphan_tmp(_current_save_dir)
    job_id = str(uuid.uuid4())[:8]
    q: queue.Queue = queue.Queue()
    cancel = threading.Event()
    with _download_jobs_lock:
        _download_jobs[job_id] = {"queue": q, "status": "running", "cancel": cancel}

    total = len(items)

    def _download_one(i: int, item: dict) -> None:
        # Skip items that haven't started yet once the batch is cancelled.
        if cancel.is_set():
            q.put({"type": "done", "index": i, "total": total, "ok": False,
                   "title": item.get("title", ""), "error": "已取消", "cancelled": True})
            return
        # progress events carry the item index, so concurrent downloads
        # interleave safely on the single (thread-safe) queue.
        q.put({"type": "start", "index": i, "total": total, "title": item.get("title", "")})
        last_pct = [-1]

        def _progress_hook(d, _i=i, _last=last_pct):
            # Raising from the hook aborts the in-flight yt-dlp download.
            if cancel.is_set():
                raise _DownloadCancelled()
            if d.get("status") != "downloading":
                return
            # Prefer exact byte counts; _percent_str can be "N/A" or carry ANSI codes.
            tb = d.get("total_bytes") or d.get("total_bytes_estimate")
            db = d.get("downloaded_bytes")
            if tb and db is not None:
                pct = db / tb * 100
            else:
                pct_str = "".join(c for c in d.get("_percent_str", "") if c.isdigit() or c == ".")
                try:
                    pct = float(pct_str)
                except (ValueError, TypeError):
                    return
            if pct - _last[0] >= 3 or pct >= 99:
                _last[0] = pct
                q.put({"type": "progress", "index": _i, "total": total,
                       "pct": round(pct, 1), "speed": (d.get("_speed_str") or "").strip(),
                       "eta": (d.get("_eta_str") or "").strip()})

        try:
            r = download_single(
                video_id=item["video_id"], platform=item["platform"],
                format_key=format_key, title_hint=item.get("title", ""),
                thumbnail_url=item.get("thumbnail_url", ""),
                progress_hook=_progress_hook,
            )
        except Exception as e:
            # download_single usually returns an error dict, but guard against
            # anything raised before its try-block (e.g. an unknown platform) so
            # the 'done' event — and thus the UI row — is ALWAYS emitted.
            # Otherwise the row hangs at 0%% and the auto-clear (which fires when
            # no row is marked failed) silently wipes the whole queue.
            logger.error("download worker error for %s: %s", item.get("video_id"), e)
            r = {"ok": False, "error": str(e)}
        cancelled = cancel.is_set() and not r["ok"]
        q.put({"type": "done", "index": i, "total": total,
               "ok": r["ok"], "title": item.get("title", ""),
               "error": "已取消" if cancelled else r.get("error"),
               "cancelled": cancelled})

    def _worker() -> None:
        workers = max(1, min(DOWNLOAD_CONCURRENCY, total))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for i, item in enumerate(items):
                    pool.submit(_download_one, i, item)
            # ThreadPoolExecutor context exit waits for all submitted tasks
        finally:
            q.put({"type": "complete"})
            with _download_jobs_lock:
                if job_id in _download_jobs:
                    _download_jobs[job_id]["status"] = "done"
                    _download_jobs[job_id]["finished_at"] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def get_download_queue(job_id: str) -> queue.Queue | None:
    """Return the progress queue for a job, or None."""
    with _download_jobs_lock:
        j = _download_jobs.get(job_id)
    return j["queue"] if j else None


def cancel_download_job(job_id: str) -> bool:
    """Signal a running job to stop. In-flight downloads abort at the next
    progress tick; not-yet-started items are skipped. Returns False if unknown.
    """
    with _download_jobs_lock:
        j = _download_jobs.get(job_id)
        ev = j.get("cancel") if j else None
    if ev is None:
        return False
    ev.set()
    return True


def cleanup_job(job_id: str) -> None:
    """Remove a finished job from memory (called on SSE disconnect)."""
    with _download_jobs_lock:
        _download_jobs.pop(job_id, None)
