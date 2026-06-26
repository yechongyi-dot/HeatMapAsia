"""Main runner: region-aware parallel scrape → score → dedup → store.

Each market (jp / kr / sg) has its own set of platforms (see
:data:`scraper.regions.REGIONS`). ``run_region`` scrapes one market's platforms
in parallel; ``run_all`` sweeps every market (used by the daily scheduler).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from scraper import youtube, niconico, official
from scraper.regions import REGIONS, REGION_ORDER, get_region, DEFAULT_REGION
from scraper.scorer import score_and_rank
from scraper.dedup import deduplicate
from db import store

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# Map platform name → scrape-all callable. Each callable takes a region id.
PLATFORM_SCRAPERS: dict[str, Callable[[str], list[dict]]] = {
    "youtube": youtube.scrape_all,
    "niconico": niconico.scrape_all_keywords,
    "official": official.scrape_all,
}


def run_platform(
    region: str,
    platform: str,
    progress: Callable[[dict], None] | None = None,
) -> tuple[str, bool]:
    """Scrape, score, dedup, and store one platform's videos for one region.

    Args:
        region: Market id (``"jp"`` / ``"kr"`` / ``"sg"``).
        platform: ``"youtube"`` / ``"niconico"`` / ``"official"``.
        progress: Optional callback receiving ``{region, platform, phase, ...}``
            dicts at each milestone. Callback exceptions are swallowed.

    Returns:
        ``(platform, success)`` tuple.
    """
    def _emit(**kw) -> None:
        if progress is None:
            return
        try:
            progress({"region": region, "platform": platform, **kw})
        except Exception:  # progress must never break scraping
            logger.debug("progress callback raised", exc_info=True)

    logger.info("%s", "=" * 60)
    logger.info("Starting %s/%s scrape", region, platform)
    logger.info("%s", "=" * 60)

    try:
        _emit(phase="scraping")
        start = datetime.now(JST)
        raw_videos = PLATFORM_SCRAPERS[platform](region)
        elapsed = (datetime.now(JST) - start).total_seconds()
        logger.info("%s/%s: %d raw in %.0fs", region, platform, len(raw_videos), elapsed)
        _emit(phase="dedup", raw=len(raw_videos))

        unique = deduplicate(raw_videos)
        logger.info("%s/%s: %d after dedup", region, platform, len(unique))

        windows = score_and_rank(unique, platform=platform, region=region)

        today = datetime.now(JST).strftime("%Y-%m-%d")
        _emit(phase="saving", raw=len(raw_videos), unique=len(unique))
        store.save_ranked_videos(region, platform, windows, today)
        _emit(phase="done", raw=len(raw_videos), unique=len(unique))

        for w, vids in windows.items():
            logger.info("  %s/%s/%s: top 3:", region, platform, w)
            for i, v in enumerate(vids[:3], 1):
                logger.info(
                    "    #%d [%.0f] %s", i, v.get("score", 0), v.get("title", "")[:60],
                )

        return platform, True
    except Exception:
        logger.error("%s/%s failed", region, platform, exc_info=True)
        _emit(phase="failed")
        return platform, False


def run_region(
    region: str = DEFAULT_REGION,
    progress: Callable[[dict], None] | None = None,
) -> dict[str, bool]:
    """Run all of one region's platforms in parallel.

    Returns:
        ``{platform: success}`` mapping.
    """
    store.init()
    platforms = get_region(region)["platforms"]
    results: dict[str, bool] = {}

    with ThreadPoolExecutor(max_workers=max(1, len(platforms))) as pool:
        futures = {
            pool.submit(run_platform, region, platform, progress): platform
            for platform in platforms
        }
        for future in as_completed(futures):
            platform, ok = future.result()
            results[platform] = ok

    success = sum(1 for v in results.values() if v)
    logger.info("Region %s done: %d/%d platforms succeeded", region, success, len(results))
    return results


def run_all(progress: Callable[[dict], None] | None = None) -> dict[str, dict[str, bool]]:
    """Run every region's platforms (used by the daily scheduler).

    Returns:
        ``{region: {platform: success}}`` mapping.
    """
    store.init()
    results: dict[str, dict[str, bool]] = {}
    for region in REGION_ORDER:
        results[region] = run_region(region, progress)
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    run_all()
