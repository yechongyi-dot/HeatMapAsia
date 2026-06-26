"""YouTube channel scraper — scrape top channels found in keyword search.

Uses ``search_channel()`` to get recent videos from each channel (broader than
keyword search, captures all investment content from the channel).

Workflow:
  1. Keyword search already collects videos + their channel IDs.
  2. Extract top channels (most frequent in keyword results).
  3. For each top channel, use ``search_channel("投資")`` to get ALL recent videos.
  4. Merge back (keyword results prioritized for accurate metadata).
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Optional

from tubescrape import YouTube

from .regions import get_region, DEFAULT_REGION
from .utils import is_investment_related, parse_relative_time, parse_view_count

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

VIDEOS_PER_CHANNEL = 30
TOP_CHANNELS = 15  # Max channels to deep-scrape

CHANNEL_DELAY = 2.0
CHANNEL_JITTER = 2.0
# Parallel channel scrapers. Each worker owns its own YouTube() client and keeps
# the per-channel delay, so this multiplies throughput while staying polite.
CHANNEL_WORKERS = 3


def _top_channels_from_videos(videos: list[dict], top_n: int = TOP_CHANNELS) -> list[dict]:
    """Extract most frequent channels from a list of video dicts.

    Returns:
        List of ``{channel_id, channel, channel_url}`` sorted by frequency desc.
    """
    freq: dict[str, dict] = {}
    for v in videos:
        cid = v.get("channel_id")
        if not cid:
            continue
        if cid not in freq:
            freq[cid] = {
                "channel_id": cid,
                "channel": v.get("channel", ""),
                "channel_url": v.get("channel_url", ""),
                "count": 0,
            }
        freq[cid]["count"] += 1

    ranked = sorted(freq.values(), key=lambda x: x["count"], reverse=True)
    result = ranked[:top_n]
    logger.info("Top %d channels (from %d total):", len(result), len(freq))
    for ch in result[:5]:
        logger.info("  %s (%d videos)", ch["channel"][:30], ch["count"])
    return result


def _scrape_channel_batch(
    channels: list[dict], known_ids: set[str], region: str, search_term: str,
) -> dict[str, dict]:
    """Deep-scrape a subset of channels in one thread with its own client.

    Keeps the per-channel delay (politeness) within the batch. Returns a dict of
    ``{video_id: video_dict}`` for newly discovered (investment-related) videos.
    """
    out: dict[str, dict] = {}
    with YouTube() as yt:
        for i, ch in enumerate(channels):
            name = ch["channel"][:30]
            try:
                result = yt.search_channel(
                    ch["channel_id"], search_term, max_results=VIDEOS_PER_CHANNEL,
                )
                for v in result.videos:
                    vid = v.video_id
                    if vid in known_ids or vid in out:
                        continue
                    if not is_investment_related(v.title, region):
                        continue
                    published_at = parse_relative_time(v.published_text)
                    out[vid] = {
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
                        "published_at": published_at.isoformat() if published_at else None,
                        "thumbnail_url": v.thumbnail_url,
                        "description_snippet": v.description_snippet,
                        "is_short": v.is_short,
                        "is_live": v.is_live,
                    }
            except Exception as e:
                logger.error("Channel scrape failed for '%s': %s", name, e)

            if i < len(channels) - 1:
                time.sleep(CHANNEL_DELAY + random.uniform(0, CHANNEL_JITTER))
    return out


def scrape_channels_from_keyword_results(
    keyword_videos: list[dict], region: str = DEFAULT_REGION,
) -> list[dict]:
    """Scrape deep videos from channels found in keyword search results.

    Channels are split round-robin across ``CHANNEL_WORKERS`` threads (each with
    its own client) so the deep-scrape runs in parallel instead of serially.

    Args:
        keyword_videos: Video dicts from keyword search (used to discover channels).
        region: Market id — selects the per-channel search term and title filter.

    Returns:
        New video dicts from channel scraping (not duplicating keyword videos).
    """
    search_term = get_region(region)["channel_search_term"]
    channels = _top_channels_from_videos(keyword_videos)
    known_ids: set[str] = {v["video_id"] for v in keyword_videos if v.get("video_id")}

    workers = max(1, min(CHANNEL_WORKERS, len(channels)))
    # Round-robin split so each worker gets channels spread across the ranking.
    batches = [channels[i::workers] for i in range(workers)]

    all_videos: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_scrape_channel_batch, b, known_ids, region, search_term)
            for b in batches if b
        ]
        for future in as_completed(futures):
            try:
                for vid, v in future.result().items():
                    if vid not in all_videos:
                        all_videos[vid] = v
            except Exception as e:
                logger.error("Channel batch future raised: %s", e)

    videos = list(all_videos.values())
    logger.info("Channel scrape total new unique: %d (%d workers)", len(videos), workers)
    return videos


def scrape_all_channels(keyword_videos: list[dict], region: str = DEFAULT_REGION) -> list[dict]:
    """Convenience wrapper for runner compatibility."""
    return scrape_channels_from_keyword_results(keyword_videos, region)
