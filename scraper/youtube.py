"""YouTube scraper — parallel keyword search + channel deep-scrape (region-aware).

Uses ThreadPoolExecutor for concurrent keyword searches (5x speedup).
Two-tier time filtering: "today" for freshest content, "this_week" for breadth.
Keywords and the finance-title filter are selected by the ``region`` argument.
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone, timedelta

from tubescrape import YouTube

from .config import (
    RESULTS_PER_KEYWORD, REQUEST_DELAY, REQUEST_JITTER, YOUTUBE_WORKERS,
)
from .regions import get_region, DEFAULT_REGION
from .utils import is_investment_related, parse_relative_time, parse_view_count

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# ── Retry configuration ──

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # multiplicative backoff base (seconds)


def _video_from_result(v) -> dict:
    """Build a standardised video dict from a tubescrape ``VideoResult``."""
    published = parse_relative_time(v.published_text)
    return {
        "video_id": v.video_id,
        "title": v.title,
        "url": v.url,
        "channel": v.channel,
        "channel_id": v.channel_id,
        "channel_url": v.channel_url,
        "view_count": parse_view_count(v.view_count),
        "view_count_raw": v.view_count,
        "duration": v.duration,
        "duration_seconds": v.duration_seconds,
        "published_text": v.published_text,
        "published_at": published.isoformat() if published else None,
        "thumbnail_url": v.thumbnail_url,
        "description_snippet": v.description_snippet,
        "is_short": v.is_short,
        "is_live": v.is_live,
    }


def _search_batch(
    keywords: list[str],
    upload_date: str,
    batch_id: int,
    region: str,
) -> list[dict]:
    """Search a batch of keywords sequentially in a single thread.

    Each thread creates its own YouTube client instance so the underlying
    requests session is not shared across threads.
    """
    results: dict[str, dict] = {}
    with YouTube() as yt:
        for keyword in keywords:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    r = yt.search(
                        keyword,
                        max_results=RESULTS_PER_KEYWORD,
                        sort_by="upload_date",
                        upload_date=upload_date,
                        type="video",
                    )
                    for v in r.videos:
                        if v.video_id not in results and is_investment_related(v.title, region):
                            results[v.video_id] = _video_from_result(v)
                    break  # success → don't retry
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        backoff = RETRY_BACKOFF ** attempt
                        logger.debug(
                            "Search retry %d/%d for keyword '%s' after %.1fs: %s",
                            attempt, MAX_RETRIES, keyword, backoff, e,
                        )
                        time.sleep(backoff)
                    else:
                        logger.warning("Search failed '%s' after %d attempts: %s", keyword, MAX_RETRIES, e)
            # Delay between keywords (even after failure) to respect rate limits
            time.sleep(REQUEST_DELAY + random.uniform(0, REQUEST_JITTER))
    logger.info("  Batch %d: %d keywords → %d unique", batch_id, len(keywords), len(results))
    return list(results.values())


def _parallel_search(
    keywords: list[str],
    upload_date: str,
    workers: int,
    label: str,
    region: str,
) -> list[dict]:
    """Parallel keyword search using ThreadPoolExecutor.

    Splits keywords into evenly-sized batches for concurrent execution.
    """
    if not keywords:
        return []

    batch_size = max(1, len(keywords) // workers + 1)
    batches: list[list[str]] = [
        keywords[i:i + batch_size]
        for i in range(0, len(keywords), batch_size)
    ]

    logger.info("  %s: %d keywords → %d batches × %d workers", label, len(keywords), len(batches), workers)

    all_videos: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_search_batch, batch, upload_date, idx, region): idx
            for idx, batch in enumerate(batches, 1)
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                logger.error("Batch search future raised unrecoverable error: %s", e)
                continue
            for v in result:
                if v["video_id"] not in all_videos:
                    all_videos[v["video_id"]] = v

    videos = list(all_videos.values())
    logger.info("  %s total: %d unique", label, len(videos))
    return videos


def scrape_all_keywords(region: str = DEFAULT_REGION) -> list[dict]:
    """Parallel keyword search with a three-tier time filter.

    Phase A: ``upload_date="today"``      → freshest 24 h content (all keywords).
    Phase B: ``upload_date="this_week"``  → 7 d coverage (every other keyword).
    Phase C: ``upload_date="this_month"`` → fills the 7-30 d range the cumulative
             30d window would otherwise miss (every third keyword, sparser).
    """
    keywords = get_region(region)["keywords"]
    all_videos: dict[str, dict] = {}

    def _merge(results, label):
        before = len(all_videos)
        for v in results:
            all_videos.setdefault(v["video_id"], v)
        logger.info("%s added: %d new", label, len(all_videos) - before)

    logger.info("Phase A: upload_date=today (%d keywords)", len(keywords))
    _merge(_parallel_search(keywords, "today", YOUTUBE_WORKERS, "Today", region), "Phase A")

    logger.info("Phase B: upload_date=this_week (%d keywords)", len(keywords[::2]))
    _merge(_parallel_search(keywords[::2], "this_week", YOUTUBE_WORKERS, "Week", region), "Phase B")

    logger.info("Phase C: upload_date=this_month (%d keywords)", len(keywords[::3]))
    _merge(_parallel_search(keywords[::3], "this_month", YOUTUBE_WORKERS, "Month", region), "Phase C")

    videos = list(all_videos.values())
    logger.info("YouTube keyword search total: %d", len(videos))
    return videos


def scrape_all(region: str = DEFAULT_REGION) -> list[dict]:
    """Full YouTube pipeline: parallel keywords + channel deep-scrape."""
    from .channels import scrape_channels_from_keyword_results

    logger.info("=" * 50)
    logger.info("Phase 1: Parallel keyword search (today + this_week) [%s]", region)
    keyword_videos = scrape_all_keywords(region)

    logger.info("=" * 50)
    logger.info("Phase 2: Channel deep-scrape")
    channel_videos = scrape_channels_from_keyword_results(keyword_videos, region)

    merged: dict[str, dict] = {}
    for v in keyword_videos:
        merged[v["video_id"]] = v
    for v in channel_videos:
        if v["video_id"] not in merged:
            merged[v["video_id"]] = v

    videos = list(merged.values())
    logger.info(
        "YouTube total: keywords %d + channels %d new = %d",
        len(keyword_videos), len(channel_videos), len(videos),
    )
    return videos
