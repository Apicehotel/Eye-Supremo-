"""Supabase Storage adapter: file only. Falls back to local mirror when not configured."""
from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx

from .config import settings


def storage_status() -> dict:
    return {
        "configured": settings.storage_configured,
        "mode": "supabase" if settings.storage_configured else "local_mirror",
        "bucket": settings.supabase_bucket,
        "url": settings.supabase_url,
        "message": None if settings.storage_configured else "Supabase non configurato: i file restano nel mirror locale data/supabase_mirror",
    }


def _mirror_root() -> Path:
    root = settings.data_dir / "supabase_mirror"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key or "",
    }


def upload_bytes(storage_path: str, content: bytes, content_type: str | None = None) -> dict:
    """Upload file to Supabase Storage or local mirror. Returns backend metadata."""
    ctype = content_type or mimetypes.guess_type(storage_path)[0] or "application/octet-stream"
    if not settings.storage_configured:
        target = _mirror_root() / storage_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {"backend": "local_mirror", "path": storage_path, "bytes": len(content), "content_type": ctype}

    url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{settings.supabase_bucket}/{storage_path}"
    headers = {**_headers(), "Content-Type": ctype, "x-upsert": "true"}
    with httpx.Client(timeout=60) as client:
        res = client.post(url, content=content, headers=headers)
        res.raise_for_status()
    return {"backend": "supabase", "path": storage_path, "bytes": len(content), "content_type": ctype}


def download_bytes(storage_path: str) -> bytes:
    if not settings.storage_configured:
        target = _mirror_root() / storage_path
        if not target.exists():
            raise FileNotFoundError(f"File non trovato nel mirror locale: {storage_path}")
        return target.read_bytes()

    url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{settings.supabase_bucket}/{storage_path}"
    with httpx.Client(timeout=60) as client:
        res = client.get(url, headers=_headers())
        res.raise_for_status()
        return res.content
