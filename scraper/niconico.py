"""Niconico scraper — parallel keyword search via Snapshot Search API v2.

Uses ThreadPoolExecutor for concurrent keyword searches (3× speedup).
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

from nicovideo_api_client.api.v2.snapshot_search_api_v2 import SnapshotSearchAPIV2
from nicovideo_api_client.api.v2.json_filter import JsonFilterOperator
from nicovideo_api_client.constants import FieldType

from .config import (
    RESULTS_PER_KEYWORD, NICONICO_DELAY, NICONICO_JITTER, NICONICO_WORKERS,
)
from .regions import get_region, DEFAULT_REGION
from .utils import is_investment_related

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# ── Retry configuration ──

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # multiplicative base (seconds)

# ── Fields requested from the Snapshot Search API ──

NICO_FIELDS: set[FieldType] = {
    FieldType.TITLE,
    FieldType.CONTENT_ID,
    FieldType.VIEW_COUNTER,
    FieldType.COMMENT_COUNTER,
    FieldType.MYLIST_COUNTER,
    FieldType.LIKE_COUNTER,
    FieldType.START_TIME,
    FieldType.THUMBNAIL_URL,
    FieldType.LENGTH_SECONDS,
    FieldType.DESCRIPTION,
}


def parse_start_time(text: Optional[str]) -> Optional[datetime]:
    """Parse a Niconico ``startTime`` field into a timezone-aware ``datetime``.

    Falls back to JST when the API returns a naïve timestamp.
    """
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt
    except (ValueError, TypeError):
        return None


def _build_time_filter() -> JsonFilterOperator:
    """Build a 30-day rolling range filter for startTime.

    niconico finance content is sparse, so we pull 30 days to feed the 30d
    window; the scorer/assign_windows still bucket each video by actual age.
    """
    now = datetime.now(JST)
    cutoff = now - timedelta(days=30)
    return JsonFilterOperator({
        "type": "range",
        "field": "startTime",
        "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "include_lower": True,
        "include_upper": True,
    })


def _search_single(keyword: str, region: str) -> list[dict]:
    """Search Niconico for a single keyword with retry on transient errors."""
    videos: list[dict] = []
    time_filter = _build_time_filter()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = (
                SnapshotSearchAPIV2()
                .keywords()
                .single_query(keyword)
                .field(NICO_FIELDS)
                .sort(FieldType.START_TIME)
                .json_filter(time_filter)
                .limit(RESULTS_PER_KEYWORD)
                .user_agent("HeatMap", "1.0.0")
                .request()
                .json()
            )
            for item in result.get("data", []):
                published = parse_start_time(item.get("startTime"))
                content_id = item.get("contentId", "")
                title = item.get("title", "")
                description = item.get("description", "") or ""
                # Filter out non-investment content. niconico finance videos are
                # sparse and often carry the finance terms in the description/tags
                # rather than the title, so match on title OR description here
                # (the Snapshot API already keyword-matched the query).
                if not (is_investment_related(title, region) or is_investment_related(description, region)):
                    continue
                videos.append({
                    "video_id": content_id,
                    "title": title,
                    "url": f"https://www.nicovideo.jp/watch/{content_id}",
                    "view_count": item.get("viewCounter", 0),
                    "comment_count": item.get("commentCounter", 0),
                    "mylist_count": item.get("mylistCounter", 0),
                    "like_count": item.get("likeCounter", 0),
                    "duration_seconds": item.get("lengthSeconds", 0),
                    "thumbnail_url": item.get("thumbnailUrl", ""),
                    "description": item.get("description", ""),
                    "published_at": published.isoformat() if published else None,
                })
            break  # success
        except Exception as e:
            if attempt < MAX_RETRIES:
                backoff = RETRY_BACKOFF ** attempt
                logger.debug(
                    "Niconico retry %d/%d for '%s' after %.1fs: %s",
                    attempt, MAX_RETRIES, keyword, backoff, e,
                )
                time.sleep(backoff)
            else:
                logger.warning("Niconico search failed '%s' after %d attempts: %s", keyword, MAX_RETRIES, e)
    return videos


def _search_batch(keywords: list[str], batch_id: int, region: str) -> list[dict]:
    """Search a batch of keywords sequentially in one thread.

    Deduplicates by ``video_id`` within the batch.
    """
    results: dict[str, dict] = {}
    for keyword in keywords:
        for v in _search_single(keyword, region):
            if v["video_id"] not in results:
                results[v["video_id"]] = v
        delay = NICONICO_DELAY + random.uniform(0, NICONICO_JITTER)
        time.sleep(delay)
    logger.info("  Nico batch %d: %d kw → %d unique", batch_id, len(keywords), len(results))
    return list(results.values())


def scrape_all_keywords(region: str = DEFAULT_REGION) -> list[dict]:
    """Parallel keyword search across Niconico (Japan only).

    Distributes the region's keywords evenly across NICONICO_WORKERS threads.
    """
    keywords = get_region(region)["keywords"]
    batch_size = max(1, len(keywords) // NICONICO_WORKERS + 1)
    batches: list[list[str]] = [
        keywords[i:i + batch_size]
        for i in range(0, len(keywords), batch_size)
    ]

    logger.info(
        "Niconico: %d keywords → %d batches × %d workers",
        len(keywords), len(batches), NICONICO_WORKERS,
    )

    all_videos: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=NICONICO_WORKERS) as pool:
        futures = {
            pool.submit(_search_batch, batch, idx, region): idx
            for idx, batch in enumerate(batches, 1)
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                logger.error("Niconico batch future raised unrecoverable error: %s", e)
                continue
            for v in result:
                if v["video_id"] not in all_videos:
                    all_videos[v["video_id"]] = v

    videos = list(all_videos.values())
    logger.info("Niconico total unique: %d", len(videos))
    return videos
