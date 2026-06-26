"""HeatMap 启动入口。

直接运行:
    python main.py

或双击 launch.bat（Windows）
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中，无论从哪里运行都能正确导入
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    from web.desktop import main
    main()
