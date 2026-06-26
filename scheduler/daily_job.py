"""
Daily job — scrape all platforms, score, and store.

Delegates to ``scraper.runner`` for platform execution (no duplication).

Run from project root:
    python -m scheduler.daily_job

Or schedule with Windows Task Scheduler (set "起始目录" to project root):
    python main.py --job   # 或直接运行此文件
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 确保无论从哪里运行，项目根目录都在 sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.runner import run_all

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


def run():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    logger.info("Daily scrape started: %s (all regions)", today)

    run_all()

    logger.info("Daily scrape complete!")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    run()
