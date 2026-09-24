"""Finestra nativa Ask Fatture (WebView2) — separata da Eye Supremo."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8787
URL = f"http://{HOST}:{PORT}"


def ensure_stdio() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def wait_ready(timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def run_server() -> None:
    ensure_stdio()
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main() -> None:
    ensure_stdio()
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AskFatture"
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ASKFATTURE_DATA_DIR", str(root))

    threading.Thread(target=run_server, daemon=True).start()
    if not wait_ready():
        raise SystemExit(f"Server non raggiunto su {URL}")

    import webview

    webview.create_window("Ask Fatture", URL, width=980, height=780, min_size=(720, 560))
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
