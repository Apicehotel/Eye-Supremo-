"""Endpoint per la modalità offline-first e sincronizzazione del catalogo."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .. import offline_cache

router = APIRouter(prefix="/api/offline", tags=["offline"])


@router.get("/status")
def offline_status():
    return offline_cache.status()


@router.post("/sync")
def offline_sync(
    download_documents: bool = Query(False),
    max_items: int | None = Query(None, ge=1),
):
    try:
        return offline_cache.sync_catalog(
            download_documents=download_documents,
            max_items=max_items,
        )
    except Exception as exc:
        raise HTTPException(503, f"Sincronizzazione non riuscita: {exc}") from exc


@router.get("/documents/{source_hash}")
def offline_document(source_hash: str, filename: str | None = None):
    path = offline_cache.local_document_for(source_hash, filename)
    if not path:
        raise HTTPException(404, "Documento non presente nella copia offline")
    return FileResponse(path, filename=path.name)
