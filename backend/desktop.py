"""Launcher desktop Windows nativo per Eye Supremo.

EyeSupremo.exe = finestra applicazione (WebView2), senza console CMD
e senza aprire Chrome/Edge come sito web. Il server FastAPI resta
locale in background; la UI è incorporata nella finestra.
"""
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
PORT = 8765
URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE = "Eye Supremo"
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 900


def data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "EyeSupremo"
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
    flag = os.environ.get("EYE_SUPREMO_HEADLESS") or os.environ.get("EYE_SUPREMO_NO_BROWSER")
    return flag == "1"


def show_fatal_error(message: str) -> None:
    if headless_mode():
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Eye Supremo non è riuscito ad avviarsi.\n\n{message}\n\nLog: {log_path()}",
            "Eye Supremo - Errore di avvio",
            0x10,
        )
    except Exception:
        pass


def wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def run_api_server() -> None:
    import uvicorn
    from app.main import app as fastapi_app

    uvicorn.run(fastapi_app, host=HOST, port=PORT, log_level="warning")


def open_native_window() -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "Modulo pywebview mancante. Reinstalla Eye Supremo o esegui "
            "pip install pywebview."
        ) from exc

    write_log(f"Apro finestra nativa {WINDOW_TITLE} → {URL}")
    window = webview.create_window(
        WINDOW_TITLE,
        URL,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(960, 640),
        confirm_close=False,
        text_select=True,
    )
    # Edge WebView2 su Windows: aspetto di un'app, non di un browser.
    webview.start(gui="edgechromium")
    _ = window  # keep reference until start returns


def main() -> None:
    os.environ.setdefault("RANDFATTURE_DATA_DIR", str(data_dir()))
    write_log("Avvio Eye Supremo desktop nativo.")

    try:
        if headless_mode():
            write_log("Modalità headless (smoke test CI): solo API, nessuna finestra.")
            run_api_server()
            return

        server = threading.Thread(target=run_api_server, name="eye-api", daemon=True)
        server.start()
        if not wait_for_server():
            raise TimeoutError(f"Server locale non raggiungibile su {URL}")
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
