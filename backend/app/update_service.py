import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import settings

GITHUB_LATEST_URL = "https://api.github.com/repos/Apicehotel/Eye-Supremo-/releases/latest"
CURRENT_VERSION = "2.0.5"
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
