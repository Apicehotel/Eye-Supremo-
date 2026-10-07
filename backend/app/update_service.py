import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from .config import settings

GITHUB_LATEST_URL = "https://api.github.com/repos/Apicehotel/Eye-Supremo-/releases/latest"
CURRENT_VERSION = "2.0.1"


def _version(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value or "")
    return tuple(int(item) for item in numbers) or (0,)


def latest_release() -> dict:
    request = Request(GITHUB_LATEST_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "Eye-Supremo-Updater"})
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assets = payload.get("assets") or []
    installer = next((item for item in assets if str(item.get("name", "")).lower().endswith("-setup.exe")), None)
    latest = str(payload.get("tag_name", "")).lstrip("v")
    return {
        "current_version": CURRENT_VERSION,
        "latest_version": latest,
        "update_available": bool(latest) and _version(latest) > _version(CURRENT_VERSION),
        "release_url": payload.get("html_url"),
        "published_at": payload.get("published_at"),
        "asset_name": installer.get("name") if installer else None,
        "download_url": installer.get("browser_download_url") if installer else None,
    }


def download_latest_installer(release: dict) -> Path:
    url = release.get("download_url")
    name = Path(str(release.get("asset_name") or "EyeSupremo-Setup.exe")).name
    if not url or not name.lower().endswith("-setup.exe"):
        raise ValueError("Installer Windows non disponibile nella release GitHub")
    target_dir = settings.data_dir / "updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    request = Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "Eye-Supremo-Updater"})
    with urlopen(request, timeout=30) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    return target
