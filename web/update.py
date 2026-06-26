#!/usr/bin/env python
"""In-app online updater.

Checks the project's GitHub Releases for a newer version, downloads the packaged
build, and swaps it in via a small batch script that runs *after* the app exits
(a running .exe can't overwrite itself). Only active in the frozen (PyInstaller)
build; from source it reports that updates aren't applicable.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from version import GITHUB_OWNER, GITHUB_REPO, __version__

logger = logging.getLogger(__name__)

_API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
_UA = {"User-Agent": f"HeatMap-Updater/{__version__}",
       "Accept": "application/vnd.github+json"}


def is_frozen() -> bool:
    """True when running as the PyInstaller-built app (where updates apply)."""
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Directory holding the running app (only meaningful when frozen)."""
    return Path(sys.executable).parent


def current_version() -> str:
    return __version__


def _vtuple(v: str) -> tuple[int, ...]:
    """Parse a version/tag string into a comparable int tuple ('v1.2.0' → (1,2,0))."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def _pick_asset(assets: list[dict]) -> dict | None:
    """Choose the build .zip from a release's assets."""
    zips = [a for a in assets if str(a.get("name", "")).lower().endswith(".zip")]
    if not zips:
        return None
    for a in zips:
        if "heatmap" in str(a.get("name", "")).lower():
            return a
    return zips[0]


def check_for_update(timeout: int = 10) -> dict:
    """Query GitHub for the latest release and compare against the current version."""
    req = Request(_API_LATEST, headers=_UA)
    try:
        with urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:  # repo has no releases yet
            return {"ok": True, "current": __version__, "latest": None,
                    "update_available": False, "frozen": is_frozen()}
        return {"ok": False, "error": f"HTTP {e.code}"}
    except (URLError, TimeoutError) as e:
        return {"ok": False, "error": str(getattr(e, "reason", e))}
    except Exception as e:  # noqa: BLE001 — surface any parsing/network issue to the UI
        return {"ok": False, "error": str(e)}

    latest_tag = str(data.get("tag_name", "")).lstrip("v")
    asset = _pick_asset(data.get("assets", []) or [])
    newer = bool(latest_tag) and _vtuple(latest_tag) > _vtuple(__version__)
    return {
        "ok": True,
        "current": __version__,
        "latest": latest_tag or None,
        "update_available": newer and asset is not None,
        "notes": (data.get("body") or "").strip(),
        "download_url": asset["browser_download_url"] if asset else None,
        "size": int(asset.get("size", 0)) if asset else 0,
        "frozen": is_frozen(),
    }


# ── Background apply job (download + swap), progress over a queue/SSE ──

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def get_update_queue(job_id: str) -> queue.Queue | None:
    with _jobs_lock:
        j = _jobs.get(job_id)
    return j["queue"] if j else None


def cleanup_update_job(job_id: str) -> None:
    with _jobs_lock:
        _jobs.pop(job_id, None)


def start_update_job(download_url: str) -> str:
    """Download the build and prepare the swap in a background thread."""
    job_id = str(uuid.uuid4())[:8]
    q: queue.Queue = queue.Queue()
    with _jobs_lock:
        _jobs[job_id] = {"queue": q}

    def _work() -> None:
        try:
            if not is_frozen():
                raise RuntimeError("在线更新仅在打包版可用（开发模式请用 git pull）")
            if not download_url:
                raise RuntimeError("没有可用的更新包")

            tmp = Path(tempfile.mkdtemp(prefix="hm_update_"))
            zip_path = tmp / "update.zip"
            q.put({"type": "progress", "phase": "download", "pct": 0})
            _download(download_url, zip_path, q)

            q.put({"type": "progress", "phase": "extract", "pct": 100})
            extract_dir = tmp / "extracted"
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            new_root = _find_app_root(extract_dir)
            if new_root is None:
                raise RuntimeError("更新包结构异常：未找到 HeatMapAsia.exe")

            bat = _write_updater_script(new_root, install_dir(), tmp)
            _spawn_detached(bat)
            q.put({"type": "done"})
            # Let the SSE deliver 'done', then exit so the script can replace files.
            threading.Timer(1.5, lambda: os._exit(0)).start()
        except Exception as e:  # noqa: BLE001
            logger.error("Update failed: %s", e)
            q.put({"type": "error", "error": str(e)})

    threading.Thread(target=_work, daemon=True).start()
    return job_id


def _download(url: str, dst: Path, q: queue.Queue) -> None:
    """Stream a download to *dst*, emitting progress events on *q*."""
    req = Request(url, headers=_UA)
    with urlopen(req, timeout=30) as r:
        total = int(r.headers.get("Content-Length", 0) or 0)
        done = 0
        last = -1
        with open(dst, "wb") as f:
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = int(done / total * 100)
                    if pct != last and (pct - last >= 2 or pct >= 99):
                        last = pct
                        q.put({"type": "progress", "phase": "download", "pct": pct})


def _find_app_root(base: Path) -> Path | None:
    """Locate the folder containing HeatMapAsia.exe (zip root or one level down)."""
    if (base / "HeatMapAsia.exe").exists():
        return base
    for sub in base.iterdir():
        if sub.is_dir() and (sub / "HeatMapAsia.exe").exists():
            return sub
    return None


def _write_updater_script(new_root: Path, target: Path, tmp: Path) -> Path:
    """Write a .bat that waits for the app to exit, mirrors the new build over the
    install dir, relaunches, and cleans up after itself.

    The script lives in the system temp root (not inside *tmp*) so it can delete
    the extraction directory without locking itself.
    """
    bat = Path(tempfile.gettempdir()) / f"hm_update_{uuid.uuid4().hex[:8]}.bat"
    exe = target / "HeatMapAsia.exe"
    script = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "echo ============================================\r\n"
        "echo   HeatMap-Asia is updating, please wait...\r\n"
        "echo ============================================\r\n"
        ":waitloop\r\n"
        'tasklist /fi "imagename eq HeatMapAsia.exe" 2>nul | find /i "HeatMapAsia.exe" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto waitloop\r\n"
        ")\r\n"
        f'robocopy "{new_root}" "{target}" /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul\r\n'
        f'start "" "{exe}"\r\n'
        f'rmdir /s /q "{tmp}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )
    bat.write_text(script, encoding="utf-8")
    return bat


def _spawn_detached(bat: Path) -> None:
    """Launch the updater script in its own console, surviving this app's exit."""
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=creationflags, close_fds=True)
