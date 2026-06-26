"""Official / authoritative source scraper — curated channels via RSS uploads feed.

YouTube's per-channel Atom feed (no API key, no library) returns each channel's
~15 most recent uploads WITH exact publish timestamps and view counts — exactly
what the "official" platform needs. tubescrape's ``get_channel_videos`` returns
nothing in the pinned version, and ``search_channel`` is relevance-ranked (so it
surfaces old popular videos, not the *recent* uploads from infrequently-posting
government channels). The feed avoids both problems.

Videos are kept if the title OR description looks finance-related. Matching the
description (not just the title) keeps flagship items whose title is vague — e.g.
a Bank of Japan "総裁定例記者会見" whose description mentions 金融政策/物価 — while
dropping off-topic posts from broad news channels (e.g. Reuters war coverage).
"""

from __future__ import annotations

import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import OFFICIAL_WORKERS
from .regions import get_region, DEFAULT_REGION
from .utils import is_investment_related

logger = logging.getLogger(__name__)

_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


def _text(node) -> str:
    return node.text if node is not None and node.text else ""


def _parse_feed(name: str, channel_id: str, region: str, needs_filter: bool = False) -> list[dict]:
    """Fetch and parse one channel's uploads feed into video dicts.

    *needs_filter* applies the finance keyword check (used for broad-news
    channels); trusted official sources keep everything.
    """
    # YouTube's RSS endpoint occasionally returns a transient 404/timeout under
    # load, so retry a couple of times before giving up on the channel.
    root = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(_FEED.format(channel_id), timeout=15) as r:
                root = ET.fromstring(r.read())
            break
        except Exception as e:
            if attempt < 3:
                time.sleep(1.5 * attempt)
            else:
                logger.warning("official RSS fetch failed for %s after 3 tries: %s", name, e)
                return []

    chan_name = _text(root.find("a:author/a:name", _NS)) or name
    chan_url = _text(root.find("a:author/a:uri", _NS))

    out: list[dict] = []
    for e in root.findall("a:entry", _NS):
        vid = _text(e.find("yt:videoId", _NS))
        if not vid:
            continue
        title = _text(e.find("a:title", _NS))
        desc = _text(e.find(".//media:description", _NS))
        if needs_filter and not (is_investment_related(title, region) or is_investment_related(desc, region)):
            continue
        stats = e.find(".//media:community/media:statistics", _NS)
        thumb = e.find(".//media:thumbnail", _NS)
        out.append({
            "video_id": vid,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "channel": chan_name,
            "channel_id": channel_id,
            "channel_url": chan_url,
            "view_count": int(stats.get("views", 0)) if stats is not None else 0,
            "duration_seconds": 0,  # not provided by the RSS feed
            "published_at": _text(e.find("a:published", _NS)) or None,
            "thumbnail_url": thumb.get("url") if thumb is not None else "",
            "description_snippet": desc[:300],
            "is_short": False,
            "is_live": False,
        })
    logger.info("Official RSS %s: %d videos", chan_name, len(out))
    return out


def scrape_all(region: str = DEFAULT_REGION) -> list[dict]:
    """Fetch every curated official channel's uploads feed; return merged videos."""
    channels = get_region(region)["official_channels"]
    workers = max(1, min(OFFICIAL_WORKERS, len(channels)))
    all_videos: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_parse_feed, ch["name"], ch["channel_id"], region, ch.get("filter", False))
            for ch in channels
        ]
        for future in as_completed(futures):
            try:
                for v in future.result():
                    all_videos.setdefault(v["video_id"], v)
            except Exception as e:
                logger.error("official feed future raised: %s", e)

    videos = list(all_videos.values())
    logger.info("Official total unique: %d (%d channels)", len(videos), len(channels))
    return videos
