from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse

from ..update_service import download_latest_installer, launch_staged_update, latest_release, rollback_latest_backup, stage_update

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


@router.post("/stage")
def stage_update_route():
    try:
        release = latest_release()
        if not release.get("download_url"):
            raise HTTPException(404, release.get("message") or "Installer Windows non disponibile")
        return stage_update(release)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Impossibile preparare l'aggiornamento: {exc}") from exc


@router.post("/apply")
def apply_update():
    try:
        result = launch_staged_update()
        return result
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Aggiornamento non avviato: {exc}") from exc


@router.post("/rollback")
def rollback_update():
    try:
        return rollback_latest_backup()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Ripristino non riuscito: {exc}") from exc
