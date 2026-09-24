"""Finestra nativa Ask Fatture (WebView2) — separata da Eye Supremo."""
from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8787
URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE = "Ask Fatture"
WINDOW_WIDTH = 980
WINDOW_HEIGHT = 780


def data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AskFatture"
    root.mkdir(parents=True, exist_ok=True)
    return root


def log_path() -> Path:
    folder = data_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "launcher.log"


def write_log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def headless_mode() -> bool:
    flag = os.environ.get("ASK_FATTURE_HEADLESS") or os.environ.get("ASKFATTURE_HEADLESS")
    return flag == "1"


def show_fatal_error(message: str) -> None:
    if headless_mode():
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Ask Fatture non è riuscito ad avviarsi.\n\n{message}\n\nLog: {log_path()}",
            "Ask Fatture - Errore di avvio",
            0x10,
        )
    except Exception:
        pass


def ensure_stdio() -> None:
    """PyInstaller --windowed lascia stdout/stderr a None; uvicorn crasha su isatty()."""
    log_handle = None
    if sys.stdout is None or sys.stderr is None:
        log_handle = log_path().open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log_handle  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = log_handle  # type: ignore[assignment]


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

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"()": "logging.Formatter", "fmt": "%(levelname)s: %(message)s"},
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "WARNING", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "WARNING", "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        },
    }
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=log_config)


def open_native_window() -> None:
    import webview

    write_log(f"Apro finestra nativa {WINDOW_TITLE} → {URL}")
    webview.create_window(
        WINDOW_TITLE,
        URL,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(720, 560),
    )
    webview.start(gui="edgechromium")


def main() -> None:
    ensure_stdio()
    os.environ.setdefault("ASKFATTURE_DATA_DIR", str(data_dir()))
    write_log("Avvio Ask Fatture desktop nativo.")

    try:
        if headless_mode():
            write_log("Modalità headless (smoke test CI): solo API, nessuna finestra.")
            run_server()
            return

        threading.Thread(target=run_server, name="ask-api", daemon=True).start()
        if not wait_ready():
            raise TimeoutError(f"Server non raggiunto su {URL}")
        write_log(f"Server pronto su {URL}")
        open_native_window()
        write_log("Finestra chiusa; uscita.")
        sys.exit(0)
    except Exception as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        write_log("Errore fatale durante l'avvio:\n" + detail)
        show_fatal_error(str(exc))
        raise


if __name__ == "__main__":
    main()
