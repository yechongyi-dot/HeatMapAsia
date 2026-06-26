"""
统一数据路径管理。

默认数据根目录: ~/AppData/Local/HeatMap/ (Windows) / ~/.heatmap/ (其他)
可通过环境变量 HEATMAP_DATA_DIR 覆盖。

目录结构:
    ~/AppData/Local/HeatMap/   (Windows)
    ├── data/
    │   └── videos_v2.db       # SQLite 数据库
    ├── downloads/             # 下载的媒体文件
    ├── thumbnails/            # 视频缩略图 (.jpg)
    └── cookies.txt            # Niconico cookie

用法:
    from config_paths import DATA_DIR, DB_PATH, DOWNLOAD_DIR, THUMB_DIR, COOKIE_PATH
"""

import os
from pathlib import Path

# ── 数据根目录 ──
# 独立于原 HeatMap 应用：使用 HeatMapAsia 目录和独立的环境变量，
# 这样两个应用的数据库、下载、cookie 互不影响。
DATA_DIR = Path(os.environ.get(
    "HEATMAPASIA_DATA_DIR",
    Path.home() / "AppData" / "Local" / "HeatMapAsia" if os.name == "nt"
    else Path.home() / ".heatmap-asia"
))

# ── 子目录 ──
DB_PATH = DATA_DIR / "data" / "videos_v2.db"
DOWNLOAD_DIR = DATA_DIR / "downloads"
THUMB_DIR = DATA_DIR / "thumbnails"
COOKIE_PATH = DATA_DIR / "cookies.txt"

# ── 向后兼容: 旧路径迁移（见 migrate_legacy） ──


def ensure_dirs() -> None:
    """确保所有数据目录存在。"""
    for d in (DB_PATH.parent, DOWNLOAD_DIR, THUMB_DIR):
        d.mkdir(parents=True, exist_ok=True)


def migrate_legacy() -> list[str]:
    """No-op for HeatMap-Asia.

    This is a standalone app with its own data directory (HeatMapAsia). It must
    never touch the original HeatMap app's data, so legacy migration is disabled.
    """
    return []


def _migrate_legacy_disabled() -> list[str]:
    """Original HeatMap migration logic, kept for reference but not called."""
    import shutil

    migrated: list[str] = []

    # 1. 旧数据库文件
    for old_db in (
        Path("videos_v2.db"), Path("videos.db"),
        Path.home() / "HeatMap" / "data" / "videos_v2.db",  # v1 unified path
    ):
        if old_db.exists() and not DB_PATH.exists():
            try:
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_db), str(DB_PATH))
                migrated.append(f"{old_db} → {DB_PATH}")
            except Exception:
                pass

    # 1b. 从旧统一目录迁移所有数据
    old_hm = Path.home() / "HeatMap"
    if old_hm.is_dir() and old_hm != DATA_DIR:
        for sub in ("data", "downloads", "thumbnails"):
            old_sub = old_hm / sub
            new_sub = DATA_DIR / sub
            if old_sub.is_dir():
                new_sub.mkdir(parents=True, exist_ok=True)
                for item in list(old_sub.iterdir()):
                    dest = new_sub / item.name
                    if not dest.exists():
                        try:
                            shutil.move(str(item), str(dest))
                            migrated.append(f"{item.name}: {old_sub} → {new_sub}")
                        except Exception:
                            pass
        # 迁移 cookies
        old_ck = old_hm / "cookies.txt"
        if old_ck.exists() and not COOKIE_PATH.exists():
            try:
                shutil.move(str(old_ck), str(COOKIE_PATH))
                migrated.append(f"{old_ck} → {COOKIE_PATH}")
            except Exception:
                pass

    # 2. 旧下载目录 (~/Downloads/HeatMap/ → ~/HeatMap/downloads/)
    old_dl = Path.home() / "Downloads" / "HeatMap"
    if old_dl.is_dir() and DOWNLOAD_DIR.is_dir():
        for item in list(old_dl.iterdir()):
            # .jpg 缩略图移到 thumbnails/ (先检查，优先级更高)
            if item.suffix.lower() == '.jpg':
                thumb_dest = THUMB_DIR / item.name
                if not thumb_dest.exists():
                    try:
                        THUMB_DIR.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(item), str(thumb_dest))
                        migrated.append(f"{item.name}: {old_dl} → {THUMB_DIR}")
                    except Exception:
                        pass
            elif item.is_file():
                dest = DOWNLOAD_DIR / item.name
                if not dest.exists():
                    try:
                        shutil.move(str(item), str(dest))
                        migrated.append(f"{item.name}: {old_dl} → {DOWNLOAD_DIR}")
                    except Exception:
                        pass
        # 清理空目录
        try:
            remaining = list(old_dl.iterdir())
            if not remaining:
                old_dl.rmdir()
        except Exception:
            pass

    # 3. 旧 cookies.txt（项目目录 → 数据目录）
    old_ck = Path(__file__).resolve().parent / "cookies.txt"
    if old_ck.exists() and not COOKIE_PATH.exists():
        try:
            shutil.move(str(old_ck), str(COOKIE_PATH))
            migrated.append(f"{old_ck} → {COOKIE_PATH}")
        except Exception:
            pass

    return migrated


# 模块加载时确保目录存在
ensure_dirs()
