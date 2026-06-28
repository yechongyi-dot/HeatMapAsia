"""Database read/write operations for ranked video storage.

All public functions handle their own session lifecycle and are safe to call
from multiple threads (SQLite WAL mode is enabled at engine-creation time).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.exc import SQLAlchemyError

from .models import Video, init_db, get_session

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


def init() -> None:
    """Initialise database tables (idempotent) and prune stale snapshots."""
    init_db()
    prune_old()


def prune_old(keep_days: int = 35) -> int:
    """Delete ranked rows older than *keep_days* (across all regions).

    The longest time window is 30d, so snapshots older than ~a month are never
    shown — pruning them keeps the SQLite file from growing without bound and
    keeps queries fast. Returns the number of rows deleted.
    """
    cutoff = (datetime.now(JST) - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    SessionLocal = get_session()
    try:
        with SessionLocal() as session:
            with session.begin():
                result = session.execute(delete(Video).where(Video.scraped_date < cutoff))
            n = result.rowcount or 0
        if n:
            logger.info("Pruned %d ranked rows older than %s", n, cutoff)
        return n
    except SQLAlchemyError as e:
        logger.error("prune_old: %s", e)
        return 0


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 datetime string into a timezone-aware Python ``datetime``.

    Returns ``None`` for empty or unparseable input.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        # SQLAlchemy DateTime(timezone=True) expects tz-aware; fill JST if missing
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt
    except (ValueError, TypeError):
        logger.debug("Could not parse datetime from: %r", raw)
        return None


def save_ranked_videos(
    region: str,
    platform: str,
    windows: dict[str, list[dict]],
    scraped_date: str,
) -> int:
    """Save ranked videos for one region+platform across all time windows.

    Replaces any existing rows for the same *region* + *platform* +
    *scraped_date* combination (run-delete-then-insert in one transaction).

    Returns the total number of rows inserted.
    """
    SessionLocal = get_session()
    total = 0
    try:
        with SessionLocal() as session:
            with session.begin():
                # Remove old data for this region + platform + date combination
                session.execute(
                    delete(Video).where(
                        Video.region == region,
                        Video.platform == platform,
                        Video.scraped_date == scraped_date,
                    )
                )

                for window_label, videos in windows.items():
                    for v in videos:
                        session.add(Video(
                            video_id=v["video_id"],
                            region=region,
                            platform=platform,
                            title=v.get("title", ""),
                            url=v.get("url", ""),
                            channel=v.get("channel", ""),
                            channel_id=v.get("channel_id", ""),
                            channel_url=v.get("channel_url", ""),
                            view_count=v.get("view_count", 0),
                            like_count=v.get("like_count", 0),
                            comment_count=v.get("comment_count", 0),
                            share_count=v.get("share_count", 0),
                            duration_seconds=v.get("duration_seconds", 0),
                            thumbnail_url=v.get("thumbnail_url", ""),
                            description_snippet=v.get("description_snippet", ""),
                            published_at=_parse_dt(v.get("published_at")),
                            published_text=v.get("published_text", ""),
                            score=v.get("score", 0.0),
                            time_window=window_label,
                            scraped_date=scraped_date,
                            is_short=1 if v.get("is_short") else 0,
                            is_live=1 if v.get("is_live") else 0,
                        ))
                        total += 1
        logger.info("Saved %s/%s data for %s: %d rows", region, platform, scraped_date, total)
    except SQLAlchemyError as e:
        logger.error("Failed to save %s/%s data for %s: %s", region, platform, scraped_date, e)
    return total


# Time windows are STORED as mutually-exclusive age buckets, but the UI treats
# them as "last N days" (cumulative): selecting 30d shows everything from the
# last 30 days. So a query for `window` unions all buckets up to & including it.
_WINDOW_ORDER = ["24h", "3d", "7d", "30d"]


def _windows_upto(window: str) -> list[str]:
    try:
        return _WINDOW_ORDER[: _WINDOW_ORDER.index(window) + 1]
    except ValueError:
        return [window]


def _latest_date(session, region: str, platform: str) -> Optional[str]:
    """Most recent ``scraped_date`` for a region+platform (any window), or ``None``."""
    sub = (
        select(Video.scraped_date)
        .where(Video.region == region, Video.platform == platform)
        .order_by(Video.scraped_date.desc())
        .limit(1)
    )
    return session.execute(sub).scalar_one_or_none()


def get_videos(
    region: str,
    platform: str,
    window: str,
    date: Optional[str] = None,
    limit: int = 300,
) -> list[dict]:
    """Retrieve ranked videos from the database.

    Args:
        platform: ``"youtube"`` or ``"niconico"``.
        window: ``"24h"``, ``"3d"``, or ``"7d"``.
        date: ``"YYYY-MM-DD"`` or ``None`` for the latest available date.
        limit: Maximum number of results.

    Returns:
        List of video dicts, ordered by score descending.
    """
    SessionLocal = get_session()
    try:
        with SessionLocal() as session:
            if date is None:
                date = _latest_date(session, region, platform)
                if date is None:
                    return []

            stmt = (
                select(Video)
                .where(
                    Video.region == region,
                    Video.platform == platform,
                    Video.time_window.in_(_windows_upto(window)),
                    Video.scraped_date == date,
                )
                .order_by(Video.score.desc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [_row_to_dict(r) for r in rows]
    except SQLAlchemyError as e:
        logger.error("get_videos(%s, %s, %s, %s): %s", region, platform, window, date, e)
        return []


def get_channel_stats(
    region: str,
    platform: str,
    window: str,
    date: Optional[str] = None,
) -> list[dict]:
    """Aggregate ranked videos by channel for one platform + window + date.

    Channel data is already stored on every :class:`Video` row, so this simply
    groups the existing ranked rows — no extra scraping required.

    Returns:
        List of channel dicts ordered by total heat score descending. Each dict::

            {channel_id, channel, channel_url, video_count,
             total_views, total_score, max_score, avg_score}
    """
    SessionLocal = get_session()
    try:
        with SessionLocal() as session:
            if date is None:
                date = _latest_date(session, region, platform)
                if date is None:
                    return []

            stmt = (
                select(
                    Video.channel_id,
                    func.max(Video.channel).label("channel"),
                    func.max(Video.channel_url).label("channel_url"),
                    func.count(Video.id).label("video_count"),
                    func.sum(Video.view_count).label("total_views"),
                    func.sum(Video.score).label("total_score"),
                    func.max(Video.score).label("max_score"),
                )
                .where(
                    Video.region == region,
                    Video.platform == platform,
                    Video.time_window.in_(_windows_upto(window)),
                    Video.scraped_date == date,
                )
                .group_by(Video.channel_id)
                .order_by(func.sum(Video.score).desc())
            )
            rows = session.execute(stmt).all()
            result = []
            for r in rows:
                vc = r.video_count or 0
                ts = float(r.total_score or 0.0)
                result.append({
                    "channel_id": r.channel_id or "",
                    "channel": r.channel or "(未知频道)",
                    "channel_url": r.channel_url or "",
                    "video_count": vc,
                    "total_views": int(r.total_views or 0),
                    "total_score": round(ts, 1),
                    "max_score": round(float(r.max_score or 0.0), 1),
                    "avg_score": round(ts / vc, 1) if vc else 0.0,
                })
            return result
    except SQLAlchemyError as e:
        logger.error("get_channel_stats(%s, %s, %s, %s): %s", region, platform, window, date, e)
        return []


def get_available_dates(region: str, platform: str) -> list[str]:
    """Get the list of dates that have data for a region+platform (newest first)."""
    SessionLocal = get_session()
    try:
        with SessionLocal() as session:
            stmt = (
                select(Video.scraped_date)
                .where(Video.region == region, Video.platform == platform)
                .distinct()
                .order_by(Video.scraped_date.desc())
                .limit(30)
            )
            return list(session.execute(stmt).scalars().all())
    except SQLAlchemyError as e:
        logger.error("get_available_dates(%s, %s): %s", region, platform, e)
        return []


def latest_scraped_date(region: str, platform: str = "youtube") -> Optional[str]:
    """Most recent ``scraped_date`` for a region+platform across all windows.

    Used to decide whether a region already has fresh data (so the app can skip
    re-scraping it on every switch). ``None`` when the region has no data yet.
    """
    SessionLocal = get_session()
    try:
        with SessionLocal() as session:
            stmt = (
                select(Video.scraped_date)
                .where(Video.region == region, Video.platform == platform)
                .order_by(Video.scraped_date.desc())
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as e:
        logger.error("latest_scraped_date(%s, %s): %s", region, platform, e)
        return None


def _row_to_dict(row: Video) -> dict:
    """Convert an ORM ``Video`` row to a plain dictionary for JSON serialisation."""
    return {
        "video_id": row.video_id,
        "region": row.region,
        "platform": row.platform,
        "title": row.title,
        "url": row.url,
        "channel": row.channel,
        "channel_id": row.channel_id,
        "channel_url": row.channel_url,
        "view_count": row.view_count,
        "like_count": row.like_count,
        "comment_count": row.comment_count,
        "share_count": row.share_count,
        "duration_seconds": row.duration_seconds,
        "thumbnail_url": row.thumbnail_url,
        "description_snippet": row.description_snippet,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "published_text": row.published_text,
        "score": row.score,
        "time_window": row.time_window,
        "scraped_date": row.scraped_date,
        "is_short": bool(row.is_short),
        "is_live": bool(row.is_live),
    }
