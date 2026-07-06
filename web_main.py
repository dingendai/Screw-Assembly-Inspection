"""Launcher for the Web UI (localhost).

Run alongside (but not at the same time as) the desktop GUI ``main.py``:

    python web_main.py            # -> http://127.0.0.1:8000
    python web_main.py --port 9000
    HOST=0.0.0.0 PORT=8080 python web_main.py

The web UI reuses the same ``app/src/valve_gui`` core logic and shares the same
``inspection_data/`` config and CSV files as the desktop GUI.

Note: a camera device can only be opened by one process at a time, so do not run
the desktop GUI and the web UI against real cameras simultaneously.
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from threading import Timer

ROOT_DIR = Path(__file__).resolve().parent
APP_SRC_DIR = ROOT_DIR / "app" / "src"
if str(APP_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(APP_SRC_DIR))


def main():
    parser = argparse.ArgumentParser(description="Screw assembly inspection web UI")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--no-browser", action="store_true", help="不自動開啟瀏覽器")
    args = parser.parse_args()

    import uvicorn

    from valve_web.server import create_app

    app = create_app()

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}"
    print(f"[web] 啟動檢測系統 Web UI： {url}")
    if not args.no_browser:
        Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
