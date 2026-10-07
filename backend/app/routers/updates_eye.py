from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..update_service import download_latest_installer, latest_release

router = APIRouter(prefix="/api/eye/updates", tags=["Eye Supremo updates"])


@router.get("/check")
def check_update():
    try:
        return latest_release()
    except Exception as exc:
        raise HTTPException(502, f"Impossibile controllare le release GitHub: {exc}")


@router.get("/download")
def download_update():
    try:
        release = latest_release()
        if not release["update_available"]:
            raise HTTPException(409, "Eye Supremo è già aggiornato")
        target = download_latest_installer(release)
        return FileResponse(target, media_type="application/octet-stream", filename=target.name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Impossibile scaricare l'aggiornamento: {exc}")
