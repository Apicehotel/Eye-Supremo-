from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse

from ..update_service import download_latest_installer, latest_release

router = APIRouter(prefix="/api/eye/updates", tags=["Eye Supremo updates"])


@router.get("/check")
def check_update():
    try:
        return latest_release()
    except Exception as exc:
        raise HTTPException(502, f"Impossibile controllare le release GitHub: {exc}") from exc


@router.get("/download")
def download_update(mode: str = Query("redirect", pattern="^(redirect|proxy)$")):
    """Scarica l'installer.

    - redirect (default): apre il download GitHub diretto (affidabile su PC ufficio)
    - proxy: scarica via backend locale (fallback)
    """
    try:
        release = latest_release()
    except Exception as exc:
        raise HTTPException(502, f"Impossibile controllare le release GitHub: {exc}") from exc

    if not release.get("download_url"):
        raise HTTPException(404, release.get("message") or "Installer Windows non disponibile")
    if not release.get("update_available"):
        # Consenti comunque il re-download dell'ultima release se l'asset c'è.
        # Evita il falso "già aggiornato" quando serve solo riprendere il file.
        if mode == "redirect":
            return RedirectResponse(url=str(release["download_url"]), status_code=302)
        # proxy: continua sotto

    if mode == "redirect":
        return RedirectResponse(url=str(release["download_url"]), status_code=302)

    try:
        target = download_latest_installer(release)
        return FileResponse(
            target,
            media_type="application/octet-stream",
            filename=target.name,
            headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Impossibile scaricare l'aggiornamento: {exc}") from exc
