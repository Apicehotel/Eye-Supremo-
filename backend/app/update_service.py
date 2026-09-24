"""Controllo e download aggiornamenti da GitHub Releases."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .models import AppSetting
from .version import APP_VERSION, GITHUB_REPO, RELEASE_ASSET_NAME

SETTING_AUTO_CHECK = "update_auto_check"
SETTING_AUTO_INSTALL = "update_auto_install"


def _parse_version(value: str) -> tuple[int, ...]:
    clean = value.strip().lstrip("vV")
    parts = re.findall(r"\d+", clean)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def is_newer(remote: str, local: str = APP_VERSION) -> bool:
    a, b = _parse_version(remote), _parse_version(local)
    # Confronta lunghezza allineata
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def get_flag(db: Session, key: str, default: bool = True) -> bool:
    row = db.get(AppSetting, key)
    if not row:
        return default
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}


def set_flag(db: Session, key: str, value: bool) -> None:
    db.merge(AppSetting(key=key, value="1" if value else "0"))


def updates_dir() -> Path:
    root = Path(os.environ.get("RANDFATTURE_DATA_DIR") or "")
    if not root:
        from .config import settings

        root = settings.data_dir
    folder = root / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def fetch_latest_release(timeout: float = 20.0) -> dict:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"EyeSupremo/{APP_VERSION}",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        if response.status_code == 404:
            return {"available": False, "reason": "Nessuna release pubblicata su GitHub."}
        response.raise_for_status()
        data = response.json()

    tag = str(data.get("tag_name") or "")
    assets = data.get("assets") or []
    setup = next(
        (
            a
            for a in assets
            if str(a.get("name", "")).lower() == RELEASE_ASSET_NAME.lower()
            or str(a.get("name", "")).lower().endswith("-setup.exe")
        ),
        None,
    )
    if not setup:
        setup = next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)

    newer = is_newer(tag) if tag else False
    has_asset = bool(setup)
    available = newer and has_asset
    reason = None
    if not tag:
        reason = "Nessuna release pubblicata su GitHub."
    elif not has_asset:
        reason = "Release trovata ma manca l'asset EyeSupremo-Setup.exe."
    elif not newer:
        reason = f"Sei già aggiornato (v{APP_VERSION})."
    return {
        "available": available,
        "update_available": available,
        "current_version": APP_VERSION,
        "latest_version": tag.lstrip("vV") if tag else None,
        "tag_name": tag or None,
        "release_name": data.get("name"),
        "release_notes": (data.get("body") or "")[:4000],
        "html_url": data.get("html_url"),
        "published_at": data.get("published_at"),
        "asset_name": setup.get("name") if setup else None,
        "asset_url": setup.get("browser_download_url") if setup else None,
        "asset_size": setup.get("size") if setup else None,
        "reason": reason,
    }


def download_setup(asset_url: str, asset_name: str | None = None) -> dict:
    name = asset_name or RELEASE_ASSET_NAME
    target = updates_dir() / name
    partial = target.with_suffix(target.suffix + ".part")
    headers = {"User-Agent": f"EyeSupremo/{APP_VERSION}"}
    digest = hashlib.sha256()
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        with client.stream("GET", asset_url, headers=headers) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    digest.update(chunk)
    partial.replace(target)
    return {
        "path": str(target),
        "filename": name,
        "sha256": digest.hexdigest(),
        "size": target.stat().st_size,
    }


def launch_installer(setup_path: str | Path) -> dict:
    path = Path(setup_path)
    if not path.exists():
        raise FileNotFoundError(f"Installer non trovato: {path}")
    # /SILENT mantiene wizard minimo; i dati utente restano in LOCALAPPDATA
    args = [str(path), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"]
    if sys.platform.startswith("win"):
        subprocess.Popen(args, close_fds=True)
    else:
        # Su non-Windows non si può installare l'exe; utile solo in test/dev.
        raise RuntimeError("L'installazione automatica è disponibile solo su Windows.")
    return {"launched": True, "path": str(path), "args": args}
