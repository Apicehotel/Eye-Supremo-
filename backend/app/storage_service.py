"""Supabase Storage adapter: file only. Falls back to local mirror when not configured.

Locazione MultiHotel:
  bucket: eye-invoices
  path:   {prefix}/{kind}/YYYY/MM/<hash16>_<filename>
  default prefix: apice
"""
from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import settings

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def build_storage_path(original_name: str, file_hash: str, when: datetime | None = None) -> str:
    """Path relativo nel bucket: apice/xml|pdf|doc/YYYY/MM/<hash16>_<safe_name>."""
    suffix = Path(original_name).suffix.lower()
    if suffix in {".xml", ".xml.p7m"}:
        kind = "xml"
    elif suffix == ".pdf":
        kind = "pdf"
    else:
        kind = "doc"
    stamp = when or datetime.now(timezone.utc)
    safe = _SAFE_NAME.sub("_", Path(original_name).name).strip("._") or "documento"
    if len(safe) > 120:
        stem = Path(safe).stem[:100]
        safe = f"{stem}{Path(safe).suffix}"
    hash16 = (file_hash or "")[:16] or "unknown"
    prefix = (settings.supabase_path_prefix or "apice").strip("/")
    return f"{prefix}/{kind}/{stamp:%Y}/{stamp:%m}/{hash16}_{safe}"


def storage_status() -> dict:
    return {
        "configured": settings.storage_configured,
        "mode": "supabase" if settings.storage_configured else "local_mirror",
        "project_ref": "ooqlfldcrnkudhgjnied",
        "bucket": settings.supabase_bucket,
        "path_prefix": settings.supabase_path_prefix,
        "url": settings.supabase_url,
        "location_example": f"{settings.supabase_bucket}/{settings.supabase_path_prefix}/xml/YYYY/MM/<hash16>_<file>.xml",
        "message": None
        if settings.storage_configured
        else "Supabase non configurato: i file restano nel mirror locale data/supabase_mirror",
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
        return {
            "backend": "local_mirror",
            "bucket": settings.supabase_bucket,
            "path": storage_path,
            "bytes": len(content),
            "content_type": ctype,
        }

    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_bucket}/{storage_path}"
    )
    headers = {**_headers(), "Content-Type": ctype, "x-upsert": "true"}
    with httpx.Client(timeout=60) as client:
        res = client.post(url, content=content, headers=headers)
        res.raise_for_status()
    return {
        "backend": "supabase",
        "bucket": settings.supabase_bucket,
        "path": storage_path,
        "bytes": len(content),
        "content_type": ctype,
    }


def download_bytes(storage_path: str) -> bytes:
    if not settings.storage_configured:
        target = _mirror_root() / storage_path
        if not target.exists():
            raise FileNotFoundError(f"File non trovato nel mirror locale: {storage_path}")
        return target.read_bytes()

    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_bucket}/{storage_path}"
    )
    with httpx.Client(timeout=60) as client:
        res = client.get(url, headers=_headers())
        res.raise_for_status()
        return res.content
