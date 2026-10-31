import json
import hashlib
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

SUPABASE_UPDATE_FUNCTION = "eye-updates"
CURRENT_VERSION = "2.0.44"
CHECK_TIMEOUT_S = 12
DOWNLOAD_TIMEOUT_S = 600


def _version(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value or "")
    return tuple(int(item) for item in numbers) or (0,)


def _central_update_identity() -> tuple[str, str]:
    from .central_identity import current_identity

    identity = current_identity.get()
    if identity is None:
        raise RuntimeError("Sessione centrale necessaria per controllare gli aggiornamenti")
    return identity.username, identity.token


def latest_release() -> dict:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise RuntimeError("Supabase non configurato")
    username, token = _central_update_identity()
    request = Request(
        settings.supabase_url.rstrip("/") + "/functions/v1/" + SUPABASE_UPDATE_FUNCTION,
        data=json.dumps({"username": username}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {token}",
            "User-Agent": "Eye-Supremo-Updater",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=CHECK_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"Supabase HTTP {exc.code}: {detail[:240]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Supabase non raggiungibile: {exc.reason}") from exc

    latest = str(payload.get("version", "")).lstrip("v")
    download_url = payload.get("download_url")
    asset_name = payload.get("filename")
    newer = bool(latest) and _version(latest) > _version(CURRENT_VERSION)
    return {
        "current_version": CURRENT_VERSION,
        "latest_version": latest or None,
        "update_available": newer and bool(download_url),
        "installer_available": bool(download_url),
        "release_url": None,
        "published_at": payload.get("published_at"),
        "asset_name": asset_name,
        "download_url": download_url,
        "sha256": payload.get("sha256"),
        "size": payload.get("size"),
        "message": (
            None
            if download_url
            else "Aggiornamento trovato su Supabase ma senza installer Windows."
        ),
    }


def download_latest_installer(release: dict | None = None) -> Path:
    info = release or latest_release()
    url = info.get("download_url")
    name = Path(str(info.get("asset_name") or "EyeSupremo-Setup.exe")).name
    if not url:
        raise ValueError("Installer Windows non disponibile su Supabase")
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
    expected_size = info.get("size")
    if expected_size and target.stat().st_size != int(expected_size):
        target.unlink(missing_ok=True)
        raise RuntimeError("Dimensione installer non valida")
    expected_sha = str(info.get("sha256") or "").lower()
    if expected_sha:
        digest = hashlib.sha256()
        with target.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha:
            target.unlink(missing_ok=True)
            raise RuntimeError("Firma SHA-256 installer non valida")
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

