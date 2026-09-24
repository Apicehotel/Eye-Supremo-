from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import audit
from ..update_service import (
    SETTING_AUTO_CHECK,
    SETTING_AUTO_INSTALL,
    download_setup,
    fetch_latest_release,
    get_flag,
    launch_installer,
    set_flag,
)
from ..version import APP_NAME, APP_VERSION, GITHUB_REPO

router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("/status")
def updates_status(check: bool = True, db: Session = Depends(get_db)):
    auto_check = get_flag(db, SETTING_AUTO_CHECK, default=True)
    auto_install = get_flag(db, SETTING_AUTO_INSTALL, default=False)
    base = {
        "app": APP_NAME,
        "current_version": APP_VERSION,
        "github_repo": GITHUB_REPO,
        "auto_check": auto_check,
        "auto_install": auto_install,
    }
    if not check:
        return {**base, "checked": False}
    try:
        remote = fetch_latest_release()
    except Exception as exc:
        return {
            **base,
            "checked": True,
            "error": str(exc),
            "available": False,
            "update_available": False,
        }
    return {**base, "checked": True, **remote}


@router.put("/settings")
def updates_settings(payload: dict, db: Session = Depends(get_db)):
    if "auto_check" in payload:
        set_flag(db, SETTING_AUTO_CHECK, bool(payload["auto_check"]))
    if "auto_install" in payload:
        set_flag(db, SETTING_AUTO_INSTALL, bool(payload["auto_install"]))
    audit(db, "updates.settings", "Preferenze aggiornamenti modificate")
    db.commit()
    return {
        "auto_check": get_flag(db, SETTING_AUTO_CHECK, default=True),
        "auto_install": get_flag(db, SETTING_AUTO_INSTALL, default=False),
    }


@router.post("/download")
def updates_download(payload: dict | None = None, db: Session = Depends(get_db)):
    payload = payload or {}
    install = bool(payload.get("install", True))
    try:
        remote = fetch_latest_release()
    except Exception as exc:
        raise HTTPException(502, f"Impossibile contattare GitHub: {exc}") from exc
    if not remote.get("asset_url"):
        raise HTTPException(404, remote.get("reason") or "Nessun installer nella release")
    if not remote.get("available"):
        raise HTTPException(409, remote.get("reason") or "Sei già aggiornato all'ultima versione")
    try:
        saved = download_setup(remote["asset_url"], remote.get("asset_name"))
    except Exception as exc:
        raise HTTPException(502, f"Download fallito: {exc}") from exc
    audit(
        db,
        "updates.downloaded",
        f"Scaricato {saved['filename']} ({remote.get('latest_version')})",
    )
    db.commit()
    result = {"downloaded": True, **saved, "latest_version": remote.get("latest_version")}
    if install:
        try:
            launched = launch_installer(saved["path"])
            result["install"] = launched
            audit(db, "updates.install_launched", f"Avviato installer {saved['filename']}")
            db.commit()
        except Exception as exc:
            result["install"] = {"launched": False, "error": str(exc)}
    return result
