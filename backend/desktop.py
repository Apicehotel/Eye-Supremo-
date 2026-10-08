import ctypes
import os
import socket
import threading
import time
import traceback
from pathlib import Path

# Prima dell'import dell'app: abilita bootstrap cache offline sull'EXE.
os.environ.setdefault("EYESUPREMO_CACHE_BOOTSTRAP_ON_START", "1")

import uvicorn
import webview
from app.main import app as fastapi_app

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


def wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                write_log(f"Server pronto su {URL}.")
                return True
        except OSError:
            time.sleep(0.25)
    write_log(f"Timeout: server non raggiungibile su {URL} dopo {timeout:.0f}s.")
    return False


def show_fatal_error(message: str) -> None:
    if os.environ.get("EYE_SUPREMO_NO_BROWSER") == "1":
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


if __name__ == "__main__":
    write_log("Avvio Eye Supremo desktop (bootstrap cache offline abilitato).")
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(fastapi_app, host=HOST, port=PORT, log_level="warning"),
        daemon=True,
    )
    server_thread.start()
    try:
        if not wait_for_server():
            raise RuntimeError(f"server non raggiungibile su {URL}")

        # La smoke test CI deve poter interrogare l'API senza aprire una finestra.
        if os.environ.get("EYE_SUPREMO_NO_BROWSER") == "1":
            server_thread.join()
        else:
            # pywebview usa WebView2 su Windows: l'app resta una finestra desktop
            # autonoma e non passa più dal browser esterno dell'utente.
            webview.create_window(
                "Eye Supremo",
                URL,
                width=1440,
                height=920,
                min_size=(1100, 700),
                text_select=True,
            )
            webview.start(debug=False)
    except Exception as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        write_log("Errore fatale durante l'avvio:\n" + detail)
        show_fatal_error(str(exc))
        raise
