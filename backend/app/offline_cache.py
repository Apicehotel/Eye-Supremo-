"""Cache locale offline-first del catalogo fatture centrale.

Eye Supremo legge sempre questa cache quando disponibile. La rete serve solo a
sincronizzare il catalogo e, opzionalmente, i file originali.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from . import storage_service

CACHE_VERSION = 1


def cache_dir() -> Path:
    root = settings.data_dir / "offline"
    root.mkdir(parents=True, exist_ok=True)
    (root / "documents").mkdir(exist_ok=True)
    return root


def catalog_path() -> Path:
    return cache_dir() / "central_invoices.json"


def documents_dir() -> Path:
    return cache_dir() / "documents"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_catalog() -> dict[str, Any]:
    path = catalog_path()
    if not path.exists():
        return {
            "version": CACHE_VERSION,
            "items": [],
            "total": 0,
            "synced_at": None,
            "complete": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": CACHE_VERSION,
            "items": [],
            "total": 0,
            "synced_at": None,
            "complete": False,
            "error": "Cache locale non leggibile",
        }
    if not isinstance(data, dict):
        return {"version": CACHE_VERSION, "items": [], "total": 0, "complete": False}
    data.setdefault("items", [])
    data.setdefault("total", len(data["items"]))
    data.setdefault("complete", False)
    return data


def cached_items() -> list[dict[str, Any]]:
    data = load_catalog()
    items = data.get("items")
    return items if isinstance(items, list) else []


def status() -> dict[str, Any]:
    data = load_catalog()
    docs = documents_dir()
    document_count = sum(1 for p in docs.rglob("*") if p.is_file())
    return {
        "catalog_path": str(catalog_path()),
        "documents_path": str(docs),
        "cached_invoices": len(data.get("items") or []),
        "reported_total": data.get("total"),
        "complete": bool(data.get("complete")),
        "synced_at": data.get("synced_at"),
        "cached_documents": document_count,
        "central_configured": settings.central_configured,
        "storage_configured": settings.storage_configured,
    }


def _document_target(item: dict[str, Any]) -> Path | None:
    digest = str(item.get("source_hash") or "").strip().lower()
    filename = str(item.get("source_filename") or "").strip()
    if len(digest) < 16 or not filename:
        return None
    suffix = "".join(Path(filename).suffixes) or ""
    return documents_dir() / digest[:2] / f"{digest}{suffix.lower()}"


def _download_document(item: dict[str, Any]) -> tuple[bool, str | None]:
    if not settings.storage_configured:
        return False, "storage_non_configurato"
    target = _document_target(item)
    if target is None:
        return False, "metadati_file_incompleti"
    if target.exists() and target.stat().st_size > 0:
        return True, None
    try:
        storage_path = storage_service.build_storage_path(
            str(item.get("source_filename") or ""), str(item.get("source_hash") or "")
        )
        content = storage_service.download_bytes(storage_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(content)
        partial.replace(target)
        return True, None
    except Exception as exc:  # best-effort: il catalogo deve restare utilizzabile offline
        return False, str(exc)


def sync_catalog(*, download_documents: bool = False, max_items: int | None = None) -> dict[str, Any]:
    """Scarica tutte le pagine del catalogo centrale e le salva localmente.

    Il file cache viene sostituito solo a sincronizzazione completata, quindi una
    perdita di rete non distrugge mai l'ultima copia valida.
    """
    if not settings.central_configured:
        raise RuntimeError("Catalogo centrale non configurato")

    page_size = 200
    offset = 0
    items: list[dict[str, Any]] = []
    reported_total: int | None = None

    while True:
        page = storage_service.central_invoice_page(limit=page_size, offset=offset)
        batch = page.get("items") if isinstance(page, dict) else []
        if not isinstance(batch, list):
            batch = []
        if reported_total is None and isinstance(page, dict) and page.get("total") is not None:
            try:
                reported_total = int(page["total"])
            except (TypeError, ValueError):
                reported_total = None
        if not batch:
            break
        items.extend(x for x in batch if isinstance(x, dict))
        offset += len(batch)
        if max_items is not None and len(items) >= max_items:
            items = items[:max_items]
            break
        if reported_total is not None and offset >= reported_total:
            break
        if len(batch) < page_size and reported_total is None:
            break

    # Dedup centrale per hash; fallback id/numero+data+fornitore.
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        digest = str(item.get("source_hash") or "").strip().lower()
        key = digest or str(item.get("id") or "").strip()
        if not key:
            key = "|".join(
                [
                    str(item.get("invoice_number") or "").strip().lower(),
                    str(item.get("invoice_date") or ""),
                    str(item.get("supplier_name") or "").strip().lower(),
                ]
            )
        unique[key] = item
    items = list(unique.values())

    docs_ok = 0
    docs_failed = 0
    document_errors: list[str] = []
    if download_documents:
        for item in items:
            ok, error = _download_document(item)
            if ok:
                docs_ok += 1
            else:
                docs_failed += 1
                if error and len(document_errors) < 20:
                    document_errors.append(error)

    now = datetime.now(timezone.utc).isoformat()
    complete = max_items is None and (reported_total is None or len(items) >= reported_total)
    payload = {
        "version": CACHE_VERSION,
        "synced_at": now,
        "complete": complete,
        "total": reported_total if reported_total is not None else len(items),
        "items": items,
    }
    _atomic_write_json(catalog_path(), payload)
    return {
        "ok": True,
        "synced_at": now,
        "cached_invoices": len(items),
        "reported_total": payload["total"],
        "complete": complete,
        "documents_downloaded": docs_ok,
        "documents_failed": docs_failed,
        "document_errors": document_errors,
    }


def local_document_for(source_hash: str, source_filename: str | None = None) -> Path | None:
    digest = (source_hash or "").strip().lower()
    if len(digest) < 16:
        return None
    base = documents_dir() / digest[:2]
    if source_filename:
        suffix = "".join(Path(source_filename).suffixes).lower()
        candidate = base / f"{digest}{suffix}"
        if candidate.exists():
            return candidate
    matches = list(base.glob(f"{digest}*")) if base.exists() else []
    return matches[0] if matches else None
