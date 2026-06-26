"""Scoring and ranking — multi-signal heat score with quality filtering.

Combines: engagement rate, language preference, freshness boost, time decay.
"""

import math
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import TIME_WINDOWS, TOP_N
from .regions import DEFAULT_REGION
from .utils import is_native_lang

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


def compute_score(
    view_count: int = 0,
    like_count: int = 0,
    comment_count: int = 0,
    published_at: Optional[str] = None,
    title: str = "",
    platform: str = "youtube",
    region: str = DEFAULT_REGION,
) -> float:
    """Compute multi-signal heat score for a video.

    Per-platform formula to keep within-platform rankings fair:

    YouTube (no like/comment data via tubescrape):
      base = views × 1.5
      eng_bonus = 1.0 (no data → neutral)

    Niconico (full engagement data):
      base = views × 1.0 + likes × 1.5 + comments × 3.0
      eng_rate = (likes + comments) / max(views, 1)
      eng_bonus = 1.0 + min(eng_rate × 3.0, 0.5)  → max 1.5×

    Shared:
      lang_bonus = 1.3 if Japanese title, else 1.0
      fresh_bonus = 1.0 + (6 - hours_ago) / 6 × 0.5  → max 1.5× (first 6h)

    Time decay (smooth, strictly monotonically decreasing):
      ≤12h:  1.0  (no decay)
      >12h:  exp(-k × (hours_ago − 12))
             k = -ln(0.7)/12 ≈ 0.0297
             → 0.84 at 18h, 0.70 at 24h, 0.34 at 48h, 0.17 at 72h, 0.01 at 7d

    NOTE: The old formula had two discontinuous upward jumps (at 24h and 72h)
    where a slightly older video would score HIGHER than a fresher one.
    This version uses a single, normalized exp for all age > 12h.
    """
    # ── Base score (per-platform) ──
    if platform == "niconico":
        base = view_count * 1.0 + like_count * 1.5 + comment_count * 3.0
    else:
        # YouTube: no like/comment data, compensate with views multiplier
        base = view_count * 1.5

    # ── Engagement bonus (Niconico only) ──
    if platform == "niconico" and view_count > 0:
        eng_rate = (like_count + comment_count) / view_count
        eng_bonus = 1.0 + min(eng_rate * 3.0, 0.5)
    else:
        eng_bonus = 1.0

    # Local-language content preference (region-aware)
    lang_bonus = 1.3 if is_native_lang(title, region) else 1.0

    # No published time → assume old, heavy penalty
    if not published_at:
        return base * eng_bonus * lang_bonus * 0.2

    try:
        pub_dt = datetime.fromisoformat(published_at)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=JST)
    except (ValueError, TypeError):
        return base * eng_bonus * lang_bonus

    now = datetime.now(JST)
    hours_ago = (now - pub_dt).total_seconds() / 3600

    # Freshness boost (first 6 hours get extra weight)
    if hours_ago <= 6:
        fresh_bonus = 1.0 + (6.0 - hours_ago) / 6.0 * 0.5  # 1.5 → 1.0
    else:
        fresh_bonus = 1.0

    # Time decay — single continuous exp, normalized at 12h
    # k = -ln(0.7)/12 so that decay(24h) == 0.70 exactly (no discontinuities)
    if hours_ago <= 12:
        decay = 1.0
    else:
        _k = 0.029723  # = -math.log(0.7) / 12
        decay = math.exp(-_k * (hours_ago - 12))

    return base * eng_bonus * lang_bonus * fresh_bonus * decay


def assign_windows(videos: list[dict]) -> dict[str, list[dict]]:
    """Assign videos to time windows, sorted by score descending.

    Each video is placed into exactly one window — the most granular
    that fits its age (24h ⊂ 3d ⊂ 7d in terms of age ranges).
    """
    windows: dict[str, list[dict]] = {k: [] for k in TIME_WINDOWS}

    for v in videos:
        pub = v.get("published_at")
        if not pub:
            windows["7d"].append(v)
            continue

        try:
            pub_dt = datetime.fromisoformat(pub)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=JST)
        except (ValueError, TypeError):
            windows["7d"].append(v)
            continue

        hours_ago = (datetime.now(JST) - pub_dt).total_seconds() / 3600
        for label, max_hours in TIME_WINDOWS.items():
            if hours_ago <= max_hours:
                windows[label].append(v)
                break  # assign to the most granular window only

    for label in windows:
        windows[label].sort(key=lambda v: v.get("score", 0), reverse=True)
        windows[label] = windows[label][:TOP_N]

    return windows


def score_and_rank(
    videos: list[dict],
    platform: str = "youtube",
    region: str = DEFAULT_REGION,
) -> dict[str, list[dict]]:
    """Score all videos with per-platform heat formula, return ranked windows."""
    for v in videos:
        v["score"] = compute_score(
            view_count=v.get("view_count", 0),
            like_count=v.get("like_count", 0),
            comment_count=v.get("comment_count", 0),
            published_at=v.get("published_at"),
            title=v.get("title", ""),
            platform=platform,
            region=region,
        )

    windows = assign_windows(videos)
    for label, vids in windows.items():
        logger.info("  %s: %d videos", label, len(vids))

    return windows
