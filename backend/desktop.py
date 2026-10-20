"""Launcher desktop Windows nativo per Eye Supremo.

EyeSupremo.exe apre una finestra applicazione (Microsoft Edge WebView2),
senza console CMD e senza aprire Chrome/Edge come sito web.
Il server FastAPI resta locale in background; la UI è incorporata nella finestra.
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

# Prima dell'import dell'app: abilita bootstrap cache offline sull'EXE.
os.environ.setdefault("EYESUPREMO_CACHE_BOOTSTRAP_ON_START", "1")

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE = "Eye Supremo"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 920


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
    """Smoke CI / test: solo API, nessuna finestra."""
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


def ensure_stdio() -> None:
    """PyInstaller --windowed lascia stdout/stderr a None; uvicorn crasha su isatty()."""
    log_handle = None
    if sys.stdout is None or sys.stderr is None:
        log_handle = log_path().open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log_handle  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = log_handle  # type: ignore[assignment]


def run_api_server() -> None:
    ensure_stdio()
    import uvicorn
    from app.main import app as fastapi_app

    # Formatter minimale: niente ColourFormatter che chiama isatty() su handle None.
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
    uvicorn.run(
        fastapi_app,
        host=HOST,
        port=PORT,
        log_level="warning",
        log_config=log_config,
    )


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
        min_size=(1100, 700),
        confirm_close=False,
        text_select=True,
    )
    # Edge WebView2 su Windows: finestra app senza barra indirizzi né schede browser.
    # Produzione: niente browser esterno e niente start.bat.
    try:
        webview.start(gui="edgechromium", debug=False)
    except ValueError:
        # Solo su piattaforme senza edgechromium (es. CI Linux): renderer di default.
        write_log("gui=edgechromium non disponibile; uso renderer predefinito pywebview.")
        webview.start(debug=False)
    _ = window


def main() -> None:
    ensure_stdio()
    write_log("Avvio Eye Supremo desktop nativo (WebView2, bootstrap cache abilitato).")

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
