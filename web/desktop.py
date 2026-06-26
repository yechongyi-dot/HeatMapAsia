"""Desktop app — native Windows window wrapping the HeatMap web panel.

Run:
    python main.py

Requires: pywebview, WebView2 (built into Win10+).
"""

from __future__ import annotations

import logging
import sys
import threading
import time

logger = logging.getLogger(__name__)

TITLE = "HeatMap-Asia - 日韩新投資動画ランキング"
WIDTH = 1200
HEIGHT = 800
START_PORT = 8090
MAX_PORTS = 10


def _find_port() -> int:
    """Find a free port starting from START_PORT."""
    import socket
    for port in range(START_PORT, START_PORT + MAX_PORTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in range {START_PORT}-{START_PORT + MAX_PORTS}")


def _start_server(port: int) -> None:
    """Start FastAPI on a specific port in a background thread."""
    import uvicorn
    from web.server import app  # import object directly — works regardless of cwd
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    import webview
    import urllib.request

    port = _find_port()
    print(f"Starting server on http://127.0.0.1:{port}")

    # JS API exposed to the frontend
    class Api:
        def pick_folder(self):
            """Open native folder picker, return selected path or empty string."""
            result = webview.windows[0].create_file_dialog(
                webview.FileDialog.FOLDER, directory=""
            )
            return result[0] if result else ""

        def open_url(self, url: str):
            """Open an external URL in the user's real default browser.

            ``window.open`` is unreliable inside the embedded WebView2, so the
            frontend calls this for video links when running as a desktop app.
            """
            if url and (url.startswith("http://") or url.startswith("https://")):
                import webbrowser
                webbrowser.open(url)
            return True

    server_thread = threading.Thread(target=_start_server, args=(port,), daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    else:
        print(f"ERROR: Server failed to start on port {port}")
        sys.exit(1)

    # 采集由前端在加载后自动触发（owns the SSE job for live progress）

    window = webview.create_window(
        title=TITLE,
        url=url,
        width=WIDTH,
        height=HEIGHT,
        min_size=(800, 500),
        resizable=True,
        text_select=True,
        js_api=Api(),
    )

    webview.start(gui="edgechromium", debug=False)
