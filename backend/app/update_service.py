import json
import os
import shutil
import subprocess
import sqlite3
import time
import tempfile
import zipfile
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import settings

GITHUB_LATEST_URL = "https://api.github.com/repos/Apicehotel/Eye-Supremo-/releases/latest"
CURRENT_VERSION = "2.0.29"
CHECK_TIMEOUT_S = 12
DOWNLOAD_TIMEOUT_S = 600


def _version(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value or "")
    return tuple(int(item) for item in numbers) or (0,)


def pick_installer_asset(assets: list[dict] | None) -> dict | None:
    """Sceglie l'installer Windows dalla release GitHub."""
    items = [item for item in (assets or []) if isinstance(item, dict)]
    ranked: list[tuple[int, dict]] = []
    for item in items:
        name = str(item.get("name") or "").lower()
        if not name.endswith(".exe"):
            continue
        if name.endswith("-setup.exe") or name.endswith("_setup.exe"):
            score = 300
        elif "setup" in name and "eye" in name:
            score = 200
        elif name.endswith("setup.exe"):
            score = 150
        elif "eye" in name and "setup" in name:
            score = 120
        else:
            continue
        # Preferisci asset con URL di download pubblico.
        if item.get("browser_download_url"):
            score += 10
        ranked.append((score, item))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def latest_release() -> dict:
    request = Request(
        GITHUB_LATEST_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Eye-Supremo-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=CHECK_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail[:240]}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub non raggiungibile: {exc.reason}") from exc

    installer = pick_installer_asset(payload.get("assets") or [])
    latest = str(payload.get("tag_name", "")).lstrip("v")
    download_url = installer.get("browser_download_url") if installer else None
    asset_name = installer.get("name") if installer else None
    newer = bool(latest) and _version(latest) > _version(CURRENT_VERSION)
    return {
        "current_version": CURRENT_VERSION,
        "latest_version": latest or None,
        "update_available": newer and bool(download_url),
        "installer_available": bool(download_url),
        "release_url": payload.get("html_url"),
        "published_at": payload.get("published_at"),
        "asset_name": asset_name,
        "download_url": download_url,
        "message": (
            None
            if download_url
            else "Release trovata ma senza installer Windows (-Setup.exe)."
        ),
    }


def download_latest_installer(release: dict | None = None) -> Path:
    info = release or latest_release()
    url = info.get("download_url")
    name = Path(str(info.get("asset_name") or "EyeSupremo-Setup.exe")).name
    if not url:
        raise ValueError("Installer Windows non disponibile nella release GitHub")
    if not name.lower().endswith(".exe"):
        raise ValueError(f"Asset non eseguibile: {name}")
    target_dir = settings.data_dir / "updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    partial = target.with_suffix(target.suffix + ".partial")
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "Eye-Supremo-Updater",
        },
    )
    try:
        with urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as response, partial.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        partial.replace(target)
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise
    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError("Download installer incompleto")
    return target


def stage_update(release: dict | None = None) -> dict[str, object]:
    """Download an update and record a rollback point before it can be applied."""
    from .services import create_backup

    backup = create_backup()
    target_dir = settings.data_dir / "updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    previous = sorted(target_dir.glob("*.exe"), key=lambda item: item.stat().st_mtime, reverse=True)
    previous_installer = None
    if previous:
        rollback_dir = target_dir / "rollback"
        rollback_dir.mkdir(parents=True, exist_ok=True)
        previous_installer = rollback_dir / "previous-installer.exe"
        shutil.copy2(previous[0], previous_installer)
    installer = download_latest_installer(release)
    state = settings.data_dir / "updates" / "pending-update.json"
    payload = {
        "installer": str(installer),
        "backup": str(backup),
        "current_version": CURRENT_VERSION,
        "latest_version": (release or {}).get("latest_version"),
        "previous_installer": str(previous_installer) if previous_installer else None,
        "staged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    state.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def launch_staged_update() -> dict[str, object]:
    state = settings.data_dir / "updates" / "pending-update.json"
    if not state.exists():
        raise FileNotFoundError("Nessun aggiornamento preparato")
    payload = json.loads(state.read_text(encoding="utf-8"))
    installer = Path(str(payload.get("installer", ""))).resolve()
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        raise RuntimeError("Installer preparato non valido")
    if os.name != "nt":
        raise RuntimeError("L'installazione automatica è disponibile solo su Windows")
    subprocess.Popen([str(installer), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"], close_fds=True)
    return {"ok": True, "restart_required": True, "version": payload.get("latest_version")}


def rollback_latest_backup() -> dict[str, object]:
    state_path = settings.data_dir / "updates" / "pending-update.json"
    if not state_path.exists():
        raise FileNotFoundError("Nessun punto di ripristino disponibile")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    backup = Path(str(state.get("backup", ""))).resolve()
    if not backup.is_file() or backup.suffix.lower() != ".zip":
        raise RuntimeError("Backup di ripristino non valido")
    with zipfile.ZipFile(backup) as archive:
        names = [name for name in archive.namelist() if Path(name).name == "eye-supremo.db"]
        if not names:
            raise RuntimeError("Il backup non contiene il database locale")
        with tempfile.TemporaryDirectory(prefix="eye-rollback-") as scratch:
            extracted = Path(scratch) / "eye-supremo.db"
            extracted.write_bytes(archive.read(names[0]))
            with sqlite3.connect(extracted) as check:
                if check.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise RuntimeError("Il database di ripristino non è integro")
            target = settings.data_dir / "eye-supremo.db"
            source = sqlite3.connect(extracted)
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
    previous_installer = Path(str(state.get("previous_installer", ""))).resolve()
    binary_rollback = False
    if os.name == "nt" and previous_installer.is_file():
        subprocess.Popen([str(previous_installer), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"], close_fds=True)
        binary_rollback = True
    state_path.unlink(missing_ok=True)
    return {"ok": True, "restored_from": str(backup), "binary_rollback_started": binary_rollback, "restart_required": True}

