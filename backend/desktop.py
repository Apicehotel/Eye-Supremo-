import ctypes
import os
import socket
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import uvicorn

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


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


def wait_and_open_browser(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                write_log(f"Server pronto su {URL}; apro il browser.")
                webbrowser.open(URL)
                return
        except OSError:
            time.sleep(0.25)
    write_log(f"Timeout: server non raggiungibile su {URL} dopo {timeout:.0f}s.")


def show_fatal_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Eye Supremo non è riuscito ad avviarsi.\n\n{message}\n\nLog: {log_path()}",
            "Eye Supremo - Errore di avvio",
            0x10,
        )
    except Exception:
        pass


if __name__ == "__main__":
    write_log("Avvio Eye Supremo desktop.")
    threading.Thread(target=wait_and_open_browser, daemon=True).start()
    try:
        uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
    except Exception as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        write_log("Errore fatale durante l'avvio:\n" + detail)
        show_fatal_error(str(exc))
        raise
