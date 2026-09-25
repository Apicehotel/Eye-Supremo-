"""Lista fatture unificata: SQLite locale + catalogo Supabase MultiHotel."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .models import Invoice, Supplier
from . import offline_cache, storage_service


def _local_row(inv: Invoice) -> dict[str, Any]:
    return {
        "id": inv.id,
        "source": "local",
        "central_id": None,
        "numero": inv.numero,
        "data": inv.data.isoformat() if inv.data else None,
        "imponibile": float(inv.imponibile),
        "iva": float(inv.iva),
        "totale": float(inv.totale),
        "valuta": inv.valuta,
        "stato_importazione": inv.stato_importazione,
        "file_originale": inv.file_originale,
        "hash_file": inv.hash_file,
        "supplier": {
            "id": inv.supplier.id if inv.supplier else None,
            "ragione_sociale": inv.supplier.ragione_sociale if inv.supplier else "—",
        },
        "row_count": len(inv.rows),
        "openable": True,
    }


def _central_row(item: dict[str, Any]) -> dict[str, Any]:
    cid = str(item.get("id") or item.get("source_hash") or "")
    return {
        "id": f"c:{cid}",
        "source": "central",
        "central_id": cid,
        "numero": item.get("invoice_number") or "—",
        "data": item.get("invoice_date"),
        "imponibile": None,
        "iva": None,
        "totale": float(item["total"]) if item.get("total") is not None else None,
        "valuta": item.get("currency") or "EUR",
        "stato_importazione": "centrale",
        "file_originale": item.get("source_filename"),
        "hash_file": item.get("source_hash"),
        "supplier": {
            "id": None,
            "ragione_sociale": item.get("supplier_name") or "—",
        },
        "row_count": None,
        "openable": False,
        "offline_file_available": bool(
            item.get("source_hash")
            and offline_cache.local_document_for(
                str(item.get("source_hash")), item.get("source_filename")
            )
        ),
    }


def _match_key_local(inv: Invoice) -> set[str]:
    keys: set[str] = set()
    if inv.hash_file:
        keys.add(f"h:{inv.hash_file.lower()}")
    if inv.numero and inv.data:
        keys.add(f"n:{inv.numero.strip().lower()}|{inv.data.isoformat()}")
    return keys


def _match_key_central(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    h = item.get("source_hash")
    if h:
        keys.add(f"h:{str(h).lower()}")
    num = (item.get("invoice_number") or "").strip().lower()
    dt = item.get("invoice_date") or ""
    if num and dt:
        keys.add(f"n:{num}|{dt}")
    return keys


def _matches_query(row: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    needle = q.strip().lower()
    hay = " ".join(
        [
            str(row.get("numero") or ""),
            str((row.get("supplier") or {}).get("ragione_sociale") or ""),
            str(row.get("file_originale") or ""),
        ]
    ).lower()
    return needle in hay


def list_unified_invoices(
    db: Session,
    *,
    q: str = "",
    year: int | None = None,
    supplier_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
    include_central: bool = True,
) -> dict[str, Any]:
    """Restituisce fatture locali + centrali in un'unica lista (dedup per hash/numero+data)."""
    stmt = select(Invoice).options(selectinload(Invoice.supplier), selectinload(Invoice.rows))
    if q:
        stmt = stmt.join(Supplier).where(
            (Invoice.numero.ilike(f"%{q}%")) | (Supplier.ragione_sociale.ilike(f"%{q}%"))
        )
    if year:
        from sqlalchemy import func

        stmt = stmt.where(func.strftime("%Y", Invoice.data) == str(year))
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)

    # Carica un po' più del necessario per merge/paginazione
    fetch_n = min(max(limit + skip, limit) * 2, 500)
    local_invoices = list(
        db.scalars(stmt.order_by(Invoice.data.desc()).limit(fetch_n)).unique().all()
    )
    local_rows = [_local_row(i) for i in local_invoices]
    local_keys: set[str] = set()
    for inv in local_invoices:
        local_keys |= _match_key_local(inv)

    central_rows: list[dict[str, Any]] = []
    central_total = None
    central_error = None
    central_configured = bool(settings.central_configured)
    central_source = "none"

    if include_central and supplier_id is None:
        cache = offline_cache.load_catalog()
        items = cache.get("items") if isinstance(cache, dict) else []
        if not isinstance(items, list):
            items = []

        # Offline-first: se esiste una cache valida, la lista non dipende mai dalla rete.
        if items:
            central_source = "offline_cache"
            central_total = cache.get("total") or len(items)
        elif central_configured:
            # Primo avvio prima della sincronizzazione: manteniamo un piccolo fallback live.
            try:
                page = storage_service.central_invoice_page(
                    limit=min(200, max(limit * 3, 50)), offset=0
                )
                items = page.get("items") if isinstance(page, dict) else page
                if not isinstance(items, list):
                    items = []
                central_total = page.get("total") if isinstance(page, dict) else None
                central_source = "live"
            except Exception as exc:  # pragma: no cover - rete
                central_error = str(exc)
                items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            keys = _match_key_central(item)
            if keys & local_keys:
                # già sul PC → marca la riga locale come both
                for row in local_rows:
                    row_keys = set()
                    if row.get("hash_file"):
                        row_keys.add(f"h:{str(row['hash_file']).lower()}")
                    if row.get("numero") and row.get("data"):
                        row_keys.add(
                            f"n:{str(row['numero']).strip().lower()}|{row['data']}"
                        )
                    if row_keys & keys:
                        row["source"] = "both"
                        row["stato_importazione"] = (
                            row.get("stato_importazione") or "confermata"
                        )
                        row["central_id"] = str(item.get("id") or "")
                        break
                continue
            crow = _central_row(item)
            if year and crow.get("data") and not str(crow["data"]).startswith(str(year)):
                continue
            if not _matches_query(crow, q):
                continue
            central_rows.append(crow)

    merged = local_rows + central_rows

    def sort_key(row: dict[str, Any]):
        return row.get("data") or "", row.get("numero") or ""

    merged.sort(key=sort_key, reverse=True)
    page_items = merged[skip : skip + limit]

    return {
        "items": page_items,
        "local_count": len(local_rows),
        "central_count": len(central_rows),
        "central_total": central_total,
        "central_configured": central_configured,
        "central_source": central_source,
        "offline_cache": offline_cache.status(),
        "central_error": central_error,
        "skip": skip,
        "limit": limit,
    }
