"""SQLite database models using SQLAlchemy 2.0.

Engine is lazily initialised so that importing this module never touches
the filesystem (important for unit-tests, linting, etc.).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Index,
    create_engine,
    Engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

JST = timezone(timedelta(hours=9))

from config_paths import DB_PATH as _DB_PATH_OBJ
DB_PATH = str(_DB_PATH_OBJ)

# ── Thread-safe lazy init ──

_init_lock = threading.RLock()  # reentrant: get_session() → get_engine() calls within same lock
_engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker[Session]] = None


def _create_engine() -> Engine:
    """Create (or return cached) SQLAlchemy Engine with WAL + busy timeout."""
    global _engine
    if _engine is not None:
        return _engine
    with _init_lock:
        if _engine is not None:
            return _engine
        eng = create_engine(
            f"sqlite:///{DB_PATH}",
            echo=False,
            connect_args={
                "check_same_thread": False,
            },
        )

        @event.listens_for(eng, "connect")
        def _on_connect(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA journal_mode=WAL")
            dbapi_connection.execute("PRAGMA busy_timeout=5000")
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        _engine = eng
        return eng


def get_engine() -> Engine:
    """Return the module-level SQLAlchemy Engine (lazy init)."""
    return _create_engine()


def get_session() -> sessionmaker[Session]:
    """Return the module-level session factory (lazy init)."""
    global SessionLocal
    if SessionLocal is None:
        with _init_lock:
            if SessionLocal is None:
                SessionLocal = sessionmaker(bind=get_engine())
    return SessionLocal


# ── Delete the legacy __getattr__ (SessionLocal is now a module-level var) ──


# ── ORM base ──


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False)
    region = Column(String, nullable=False, default="jp", index=True)  # jp / kr / sg
    platform = Column(String, nullable=False, index=True)  # youtube / niconico / official
    title = Column(String)
    url = Column(String)
    channel = Column(String)
    channel_id = Column(String)
    channel_url = Column(String)
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    duration_seconds = Column(Integer, default=0)
    thumbnail_url = Column(String)
    description_snippet = Column(String)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_text = Column(String)
    score = Column(Float, default=0.0)
    time_window = Column(String, index=True)  # 24h / 3d / 7d
    scraped_date = Column(String, index=True)  # YYYY-MM-DD
    is_short = Column(Integer, default=0)
    is_live = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_region_platform_window_date", "region", "platform", "time_window", "scraped_date"),
    )


def _ensure_region_column(engine: Engine) -> None:
    """Add the ``region`` column to a pre-existing ``videos`` table if missing.

    Lets a database created by an earlier (region-less) build keep working;
    legacy rows default to ``'jp'``. No-op on a fresh database.
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(videos)"))}
        if existing and "region" not in existing:
            conn.execute(text("ALTER TABLE videos ADD COLUMN region VARCHAR DEFAULT 'jp'"))
            conn.execute(text("UPDATE videos SET region = 'jp' WHERE region IS NULL"))


def init_db() -> None:
    """Create all tables if they do not exist (and patch legacy schemas)."""
    engine = get_engine()
    _ensure_region_column(engine)
    Base.metadata.create_all(engine)
