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


def maybe_auto_update() -> None:
    """Se auto_install è attivo e c'è una release nuova, scarica e avvia il Setup."""
    try:
        import httpx

        status = httpx.get(f"{URL}/api/updates/status", timeout=25.0).json()
        if not status.get("auto_check", True):
            write_log("Controllo aggiornamenti disattivato.")
            return
        if not status.get("available"):
            write_log(
                f"Nessun aggiornamento (locale {status.get('current_version')}, "
                f"remoto {status.get('latest_version')})."
            )
            return
        if not status.get("auto_install"):
            write_log(
                f"Aggiornamento disponibile v{status.get('latest_version')} "
                "(attiva «Installa automaticamente» o usa Impostazioni)."
            )
            return
        write_log(f"Auto-install v{status.get('latest_version')}…")
        result = httpx.post(
            f"{URL}/api/updates/download",
            json={"install": True},
            timeout=180.0,
        ).json()
        write_log(f"Esito auto-update: {result}")
    except Exception as exc:
        write_log(f"Controllo aggiornamenti non riuscito: {exc}")


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
    icon_path = _bundled_icon()
    window_kwargs = {
        "title": WINDOW_TITLE,
        "url": URL,
        "width": WINDOW_WIDTH,
        "height": WINDOW_HEIGHT,
        "min_size": (960, 640),
        "confirm_close": False,
        "text_select": True,
    }
    # Su Windows l'icona della taskbar/exe arriva da PyInstaller --icon;
    # se supportato, impostiamo anche l'icona della finestra WebView.
    if icon_path:
        window_kwargs["icon"] = str(icon_path)
    try:
        window = webview.create_window(**window_kwargs)
    except TypeError:
        window_kwargs.pop("icon", None)
        window = webview.create_window(**window_kwargs)
    # Edge WebView2 su Windows: aspetto di un'app, non di un browser.
    webview.start(gui="edgechromium")
    _ = window  # keep reference until start returns


def _bundled_icon() -> Path | None:
    """Icona Eye Supremo (bundled in exe o repo assets/)."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.append(meipass / "assets" / "icons" / "eye-supremo.ico")
        candidates.append(meipass / "eye-supremo.ico")
    root = Path(__file__).resolve().parents[1]
    candidates.append(root / "assets" / "icons" / "eye-supremo.ico")
    for path in candidates:
        if path.exists():
            return path
    return None


def main() -> None:
    # Prima di qualsiasi logging uvicorn: ripristina stdout/stderr se --windowed.
    ensure_stdio()
    # Legacy variable consumed by Settings; keep it for existing installations.
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
        maybe_auto_update()
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
