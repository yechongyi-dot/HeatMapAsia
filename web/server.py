"""FastAPI web app for the video ranking dashboard.

Run from project root:
    python -m web.server
"""

import asyncio
import json
import os
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

from db import store
from .download import (
    download_single, download_batch, check_status,
    get_save_dir, set_save_dir, open_save_dir,
    list_library, delete_files, open_file, rename_file,
    library_file_path,
    generate_thumbnail,
    start_download_job, get_download_queue, cleanup_job, cancel_download_job,
    THUMB_DIR,
)
from .update import (
    check_for_update, start_update_job, get_update_queue, cleanup_update_job,
    current_version,
)

logger = logging.getLogger(__name__)

# ── Scrape state ──────────────────────────────────────
_scrape_lock = threading.Lock()
_scrape_running = False
_scrape_queues: dict[str, queue.Queue] = {}
_scrape_counter = 0

# 自动迁移旧数据到统一目录
try:
    from config_paths import migrate_legacy
    migrated = migrate_legacy()
    if migrated:
        logger.info("数据迁移完成: %d 项", len(migrated))
except Exception:
    pass

store.init()

app = FastAPI(title="HeatMap-Asia - 亚洲投資動画ランキング")

# Validation patterns shared across the data endpoints.
_REGION_RE = "^(jp|kr|sg)$"
_PLATFORM_RE = "^(youtube|niconico|official)$"
_WINDOW_RE = "^(24h|3d|7d|30d)$"

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/videos")
def api_videos(
    region: str = Query("jp", pattern=_REGION_RE),
    platform: str = Query("youtube", pattern=_PLATFORM_RE),
    window: str = Query("24h", pattern=_WINDOW_RE),
    date: str | None = Query(None),
    limit: int = Query(300, ge=1, le=1000),
):
    """Get ranked videos for a region + platform + time window + date."""
    videos = store.get_videos(region=region, platform=platform, window=window, date=date, limit=limit)
    return {"videos": videos, "count": len(videos)}


@app.get("/api/dates")
def api_dates(
    region: str = Query("jp", pattern=_REGION_RE),
    platform: str = Query("youtube", pattern=_PLATFORM_RE),
):
    """Get available dates for a region + platform."""
    dates = store.get_available_dates(region, platform)
    return {"dates": dates}


@app.get("/api/channels")
def api_channels(
    region: str = Query("jp", pattern=_REGION_RE),
    platform: str = Query("youtube", pattern=_PLATFORM_RE),
    window: str = Query("24h", pattern=_WINDOW_RE),
    date: str | None = Query(None),
):
    """Get channel-level aggregation for a region + platform + window + date."""
    channels = store.get_channel_stats(region=region, platform=platform, window=window, date=date)
    return {"channels": channels, "count": len(channels)}


# ── Download endpoints ──

class DownloadRequest(BaseModel):
    video_id: str
    platform: str
    format: str = "best"
    title: str = ""
    thumbnail_url: str = ""


class BatchDownloadRequest(BaseModel):
    items: list[DownloadRequest]
    format: str = "best"


class SetDirRequest(BaseModel):
    path: str


@app.get("/api/download/status")
def api_download_status():
    return check_status()


@app.post("/api/download")
def api_download(body: DownloadRequest):
    """Download a single video to local save directory."""
    try:
        result = download_single(
            video_id=body.video_id,
            platform=body.platform,
            format_key=body.format,
            title_hint=body.title,
            thumbnail_url=body.thumbnail_url,
        )
        if result["ok"]:
            return result
        raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/download/batch")
def api_download_batch(body: BatchDownloadRequest):
    """Download multiple videos to local save directory."""
    if not body.items:
        raise HTTPException(400, "No items to download")
    try:
        items = [
            {"video_id": it.video_id, "platform": it.platform, "title": it.title, "thumbnail_url": it.thumbnail_url}
            for it in body.items
        ]
        return download_batch(items, format_key=body.format)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/download/batch/start")
def api_start_batch(body: BatchDownloadRequest):
    """Start background download batch, return job_id for SSE progress."""
    if not body.items:
        raise HTTPException(400, "No items to download")
    items = [
        {"video_id": it.video_id, "platform": it.platform, "title": it.title, "thumbnail_url": it.thumbnail_url}
        for it in body.items
    ]
    job_id = start_download_job(items, body.format)
    return {"job_id": job_id, "count": len(items)}


@app.post("/api/download/cancel/{job_id}")
def api_cancel_batch(job_id: str):
    """Cancel a running download batch."""
    if not cancel_download_job(job_id):
        raise HTTPException(404, "job not found")
    return {"ok": True}


@app.get("/api/download/progress/{job_id}")
async def api_progress(job_id: str):
    """SSE endpoint — streams download progress events."""
    from starlette.responses import StreamingResponse

    q = get_download_queue(job_id)
    if not q:
        raise HTTPException(404, "job not found")

    async def generate():
        loop = asyncio.get_event_loop()
        try:
            while True:
                try:
                    # Run blocking q.get() in a thread pool to avoid blocking the event loop
                    event = await loop.run_in_executor(None, lambda: q.get(timeout=3))
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] == "complete":
                        break
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            cleanup_job(job_id)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Online update ──

class ApplyUpdateRequest(BaseModel):
    download_url: str


@app.get("/api/version")
def api_version():
    """Current app version (for display)."""
    return {"version": current_version()}


@app.get("/api/update/check")
def api_update_check():
    """Check GitHub Releases for a newer version."""
    return check_for_update()


@app.post("/api/update/apply")
def api_update_apply(body: ApplyUpdateRequest):
    """Download and stage the update; returns a job_id for SSE progress."""
    if not body.download_url:
        raise HTTPException(400, "download_url is required")
    job_id = start_update_job(body.download_url)
    return {"job_id": job_id}


@app.get("/api/update/progress/{job_id}")
async def api_update_progress(job_id: str):
    """SSE endpoint — streams update download/apply progress."""
    from starlette.responses import StreamingResponse

    q = get_update_queue(job_id)
    if not q:
        raise HTTPException(404, "job not found")

    async def generate():
        loop = asyncio.get_event_loop()
        try:
            while True:
                try:
                    event = await loop.run_in_executor(None, lambda: q.get(timeout=3))
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] in ("done", "error"):
                        break
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            cleanup_update_job(job_id)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/download/dir")
def api_download_dir():
    """Get current save directory."""
    return {"save_dir": get_save_dir()}


@app.post("/api/download/dir")
def api_set_download_dir(body: SetDirRequest):
    """Set save directory."""
    if not body.path:
        raise HTTPException(400, "path is required")
    p = Path(body.path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(400, f"Cannot create directory: {e}")
    set_save_dir(str(p))
    return {"save_dir": str(p)}


@app.post("/api/download/open-dir")
def api_open_download_dir():
    """Open save directory in Explorer / Finder / file manager."""
    try:
        open_save_dir()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Library (material management) ──

@app.get("/api/library")
def api_library(sort: str = "date"):
    """List all downloaded media files."""
    return list_library(sort=sort)


@app.delete("/api/library")
def api_delete_files(body: dict):
    """Delete media files from library."""
    filenames = body.get("filenames", [])
    if not filenames:
        raise HTTPException(400, "filenames required")
    return delete_files(filenames)


@app.post("/api/library/open")
def api_open_file(body: dict):
    """Open a file with default OS handler."""
    filename = body.get("filename", "")
    if not filename:
        raise HTTPException(400, "filename required")
    result = open_file(filename)
    if not result["ok"]:
        raise HTTPException(404, result["error"])
    return result


@app.post("/api/library/rename")
def api_rename_file(body: dict):
    """Rename a media file (and its thumbnail) inside the save directory."""
    old = body.get("old", "")
    new = body.get("new", "")
    if not old or not new:
        raise HTTPException(400, "old and new are required")
    result = rename_file(old, new)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@app.get("/api/library/file/{filename:path}")
def api_serve_media(filename: str):
    """Stream a media file from the save directory for in-app preview.

    ``FileResponse`` handles HTTP Range requests, so the browser's media
    element can seek without downloading the whole file.
    """
    path = library_file_path(filename)
    if path is None:
        raise HTTPException(404, "file not found")
    return FileResponse(str(path))


@app.get("/api/library/thumb/file/{filename:path}")
def api_serve_thumb(filename: str):
    """Serve thumbnail image file from thumbnails/ directory."""
    from .download import _thumb_path
    path = _thumb_path(os.path.basename(filename))
    if not path.exists():
        raise HTTPException(404, "thumb not found")
    return FileResponse(str(path), media_type="image/jpeg")


@app.post("/api/library/thumb")
def api_generate_thumb(body: dict):
    """Generate thumbnail for a file."""
    fn = body.get("filename", "")
    if not fn:
        raise HTTPException(400, "filename required")
    path = str(Path(get_save_dir()) / os.path.basename(fn))
    thumb = generate_thumbnail(path, force=True)
    if thumb:
        return {"ok": True, "thumb": thumb}
    raise HTTPException(500, "failed")


@app.post("/api/library/thumb/batch")
def api_generate_thumbs_batch():
    """Generate thumbnails for library files that don't have one."""
    from .download import _thumb_path
    library = list_library()
    generated = 0
    for f in library["files"]:  # list_library() returns a dict — iterate the "files" key
        thumb = _thumb_path(f["filename"])
        if thumb.exists():
            continue
        result = generate_thumbnail(f["path"])
        if result:
            generated += 1
    return {"generated": generated, "total": library["count"]}


# ── Scrape endpoint ──────────────────────────────────
@app.get("/api/scrape/status")
def api_scrape_status():
    """Check if scraping is in progress."""
    return {"running": _scrape_running}


_REGION_NAMES = {"jp": "日本", "kr": "韩国", "sg": "新加坡"}


def _run_scrape(job_id: str, region: str, q: queue.Queue) -> None:
    """Run one region's scrape in a background thread, pushing progress to queue."""
    global _scrape_running
    try:
        from scraper.runner import run_region
        rname = _REGION_NAMES.get(region, region)
        q.put({"type": "start", "region": region, "message": f"正在采集{rname}数据..."})

        def _on_progress(ev: dict) -> None:
            # Forward per-platform milestone events to the SSE stream
            q.put({"type": "platform", **ev})

        results = run_region(region, progress=_on_progress)
        ok_count = sum(1 for v in results.values() if v)
        total = len(results)
        q.put({
            "type": "complete",
            "region": region,
            "ok": ok_count == total,
            "message": f"{rname}采集完成: {ok_count}/{total} 个平台成功",
            "results": results,
        })
    except Exception as e:
        logger.error("Scrape failed", exc_info=True)
        q.put({"type": "complete", "ok": False, "message": f"采集失败: {e}"})
    finally:
        _scrape_running = False
        _scrape_queues.pop(job_id, None)


@app.post("/api/scrape/start")
def api_scrape_start(region: str = Query("jp", pattern=_REGION_RE)):
    """Start background scraping for one region, return job_id for SSE progress."""
    global _scrape_running, _scrape_counter

    with _scrape_lock:
        if _scrape_running:
            raise HTTPException(409, "Scraping already in progress")
        _scrape_running = True
        _scrape_counter += 1
        job_id = f"scrape_{_scrape_counter}"
        q = queue.Queue()
        _scrape_queues[job_id] = q

    t = threading.Thread(target=_run_scrape, args=(job_id, region, q), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "采集已启动"}


@app.get("/api/scrape/progress/{job_id}")
async def api_scrape_progress(job_id: str):
    """SSE endpoint — streams scrape progress events."""
    from starlette.responses import StreamingResponse

    q = _scrape_queues.get(job_id)
    if not q:
        raise HTTPException(404, "job not found")

    async def generate():
        loop = asyncio.get_event_loop()
        try:
            while True:
                try:
                    event = await loop.run_in_executor(None, lambda: q.get(timeout=30))
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] == "complete":
                        break
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            _scrape_queues.pop(job_id, None)

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="127.0.0.1", port=8080, reload=True)
