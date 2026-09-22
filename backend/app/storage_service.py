"""Supabase Storage adapter: file only. Falls back to local mirror when not configured.

Locazione MultiHotel:
  bucket: eye-invoices
  path:   {prefix}/{kind}/YYYY/MM/<hash16>_<filename>
  default prefix: apice

Metadati centrali (~20k): RPC eye_central_invoice_page
  params: p_username, p_pin, p_limit, p_offset, p_since
Indice blob: public.eye_invoice_files (hash → path)
"""
from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        "central_configured": settings.central_configured,
        "mode": "supabase" if settings.storage_configured else "local_mirror",
        "project_ref": "ooqlfldcrnkudhgjnied",
        "bucket": settings.supabase_bucket,
        "path_prefix": settings.supabase_path_prefix,
        "url": settings.supabase_url,
        "location_example": (
            f"{settings.supabase_bucket}/{settings.supabase_path_prefix}"
            "/xml/YYYY/MM/<hash16>_<file>.xml"
        ),
        "message": None
        if settings.storage_configured
        else "Supabase non configurato: i file restano nel mirror locale data/supabase_mirror",
    }


def _mirror_root() -> Path:
    root = settings.data_dir / "supabase_mirror"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _rest_key() -> str:
    key = settings.supabase_rest_key
    if not key:
        raise RuntimeError("Chiave Supabase assente (service o anon)")
    return key


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    key = _rest_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if extra:
        headers.update(extra)
    return headers


def _rest_url(path: str) -> str:
    if not settings.supabase_url:
        raise RuntimeError("RANDFATTURE_SUPABASE_URL assente")
    return f"{settings.supabase_url.rstrip('/')}/{path.lstrip('/')}"


def upload_bytes(
    storage_path: str,
    content: bytes,
    content_type: str | None = None,
    *,
    file_hash: str | None = None,
    original_name: str | None = None,
) -> dict:
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
            "indexed": False,
        }

    url = _rest_url(f"storage/v1/object/{settings.supabase_bucket}/{storage_path}")
    headers = {**_headers(), "Content-Type": ctype, "x-upsert": "true"}
    with httpx.Client(timeout=60) as client:
        res = client.post(url, content=content, headers=headers)
        res.raise_for_status()

    indexed = False
    index_error = None
    if file_hash:
        try:
            register_invoice_file(
                source_hash=file_hash,
                source_filename=original_name or Path(storage_path).name,
                storage_path=storage_path,
                content_type=ctype,
                size_bytes=len(content),
            )
            indexed = True
        except Exception as exc:  # noqa: BLE001 — indice best-effort finché la migration non è applicata
            index_error = str(exc)

    out: dict[str, Any] = {
        "backend": "supabase",
        "bucket": settings.supabase_bucket,
        "path": storage_path,
        "bytes": len(content),
        "content_type": ctype,
        "indexed": indexed,
    }
    if index_error:
        out["index_error"] = index_error
    return out


def download_bytes(storage_path: str) -> bytes:
    if not settings.storage_configured:
        target = _mirror_root() / storage_path
        if not target.exists():
            raise FileNotFoundError(f"File non trovato nel mirror locale: {storage_path}")
        return target.read_bytes()

    url = _rest_url(f"storage/v1/object/{settings.supabase_bucket}/{storage_path}")
    with httpx.Client(timeout=60) as client:
        res = client.get(url, headers=_headers())
        res.raise_for_status()
        return res.content


def register_invoice_file(
    *,
    source_hash: str,
    source_filename: str,
    storage_path: str,
    content_type: str | None,
    size_bytes: int,
    invoice_id: str | None = None,
) -> dict | None:
    """Scrive/aggiorna la riga in public.eye_invoice_files (richiede migration applicata)."""
    if not settings.storage_configured:
        return None
    row = {
        "source_hash": source_hash,
        "source_filename": source_filename,
        "storage_bucket": settings.supabase_bucket,
        "storage_path": storage_path,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "invoice_id": invoice_id,
    }
    url = _rest_url("rest/v1/eye_invoice_files?on_conflict=source_hash")
    headers = _headers(
        {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
    )
    with httpx.Client(timeout=30) as client:
        res = client.post(url, json=row, headers=headers)
        res.raise_for_status()
        data = res.json()
        return data[0] if isinstance(data, list) and data else data


def central_invoice_page(
    *,
    limit: int = 50,
    offset: int = 0,
    since: str | None = None,
    username: str | None = None,
    pin: str | None = None,
) -> dict:
    """Legge il catalogo metadati MultiHotel via RPC eye_central_invoice_page."""
    if not settings.central_configured and not (settings.supabase_url and settings.supabase_rest_key and pin):
        raise RuntimeError(
            "Catalogo centrale non configurato: servono URL + chiave Supabase e PIN centrale"
        )
    body = {
        "p_username": username or settings.supabase_central_username,
        "p_pin": pin or settings.supabase_central_pin,
        "p_limit": max(1, min(int(limit), 200)),
        "p_offset": max(0, int(offset)),
        "p_since": since,
    }
    url = _rest_url("rest/v1/rpc/eye_central_invoice_page")
    with httpx.Client(timeout=60) as client:
        res = client.post(url, json=body, headers=_headers({"Content-Type": "application/json"}))
        res.raise_for_status()
        data = res.json()
    if not isinstance(data, dict):
        return {"items": data, "limit": body["p_limit"], "offset": body["p_offset"], "total": None}
    return data
