import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from .central_service import central_invoice_page
from .database import SessionLocal
from .models import AppSetting, CentralInvoiceCache
from .product_taxonomy import QUESTION_FILLERS, extract_product_query, search_terms


def cache_status(db: Session) -> dict:
    count = db.scalar(select(func.count()).select_from(CentralInvoiceCache)) or 0
    state = db.get(AppSetting, "central_sync_state")
    return {"count": count, "state": state.value if state else "never", "local": True}


def cached_search(db: Session, query: str, limit: int, offset: int = 0) -> dict:
    stmt = select(CentralInvoiceCache).order_by(CentralInvoiceCache.invoice_date.desc()).offset(max(0, offset)).limit(limit)
    if query:
        needle = extract_product_query(query) or query.strip().lower()
        patterns = [f"%{normalize}%" for normalize in dict.fromkeys(
            [needle.lower()] + [t.lower() for t in search_terms(needle)]
        ) if normalize]
        if patterns:
            clause = or_(*[
                or_(
                    CentralInvoiceCache.search_text.ilike(pattern),
                    CentralInvoiceCache.invoice_number.ilike(pattern),
                    CentralInvoiceCache.supplier_name.ilike(pattern),
                )
                for pattern in patterns
            ])
            stmt = stmt.where(clause)
    items = [json.loads(x.payload_json) for x in db.scalars(stmt).all()]
    total_stmt = select(func.count()).select_from(CentralInvoiceCache)
    if query:
        needle = extract_product_query(query) or query.strip().lower()
        patterns = [f"%{normalize}%" for normalize in dict.fromkeys(
            [needle.lower()] + [t.lower() for t in search_terms(needle)]
        ) if normalize]
        if patterns:
            total_stmt = total_stmt.where(or_(*[
                or_(
                    CentralInvoiceCache.search_text.ilike(pattern),
                    CentralInvoiceCache.invoice_number.ilike(pattern),
                    CentralInvoiceCache.supplier_name.ilike(pattern),
                )
                for pattern in patterns
            ]))
    return {"enabled": True, "local": True, "items": items, "count": len(items), "total": db.scalar(total_stmt) or 0, "offset": max(0, offset), "limit": limit}


def _query_tokens(query: str) -> list[str]:
    product = extract_product_query(query)
    variants = [normalize_text for normalize_text in (
        [product] + list(search_terms(product or query))
    ) if normalize_text]
    tokens: list[str] = []
    for variant in variants:
        for token in re.findall(r"[a-zàèéìòù0-9]+", variant.lower()):
            if len(token) >= 3 and token not in QUESTION_FILLERS and token not in tokens:
                tokens.append(token)
    if tokens:
        return tokens
    return [t for t in re.findall(r"[a-zàèéìòù0-9]+", (query or "").lower()) if len(t) >= 4 and t not in QUESTION_FILLERS]


def cached_row_search(db: Session, query: str, limit: int = 50, offset: int = 0) -> dict:
    """Cerca righe fattura in tutta la cache SQLite locale (niente rete Supabase)."""
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))
    tokens = _query_tokens(query)
    needle = (extract_product_query(query) or query or "").strip().lower()
    stmt = select(CentralInvoiceCache).order_by(CentralInvoiceCache.invoice_date.desc())
    if tokens:
        clauses = []
        for term in tokens:
            pattern = f"%{term}%"
            clauses.append(
                or_(
                    CentralInvoiceCache.search_text.ilike(pattern),
                    CentralInvoiceCache.supplier_name.ilike(pattern),
                    CentralInvoiceCache.invoice_number.ilike(pattern),
                )
            )
        # OR tra varianti prodotto: trova tutte le fatture candidate nell'archivio.
        stmt = stmt.where(or_(*clauses))
    elif needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                CentralInvoiceCache.search_text.ilike(pattern),
                CentralInvoiceCache.supplier_name.ilike(pattern),
                CentralInvoiceCache.invoice_number.ilike(pattern),
            )
        )
    # Nessun tetto a 400: se il filtro SQL c'è, scandiamo tutti i match (cap di sicurezza alto).
    records = list(db.scalars(stmt.limit(20000)).all())
    if not records and tokens:
        term = tokens[0]
        records = list(
            db.scalars(
                select(CentralInvoiceCache)
                .where(CentralInvoiceCache.search_text.ilike(f"%{term}%"))
                .order_by(CentralInvoiceCache.invoice_date.desc())
                .limit(20000)
            ).all()
        )

    ranked: list[tuple[float, dict]] = []
    for record in records:
        try:
            payload = json.loads(record.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        rows = payload.get("rows") or []
        invoice_date = record.invoice_date.isoformat() if record.invoice_date else None
        if not rows:
            hay = f"{record.search_text} {record.supplier_name} {record.invoice_number}".lower()
            score = 100.0 if (not needle or any(t in hay for t in (tokens or [needle]))) else fuzz.WRatio(needle, hay)
            if score < 70:
                continue
            ranked.append((float(score), {
                "id": record.source_hash,
                "source_hash": record.source_hash,
                "source_filename": payload.get("source_filename"),
                "invoice_number": record.invoice_number,
                "invoice_date": invoice_date,
                "supplier_name": record.supplier_name,
                "original_description": record.supplier_name,
                "normalized_description": record.supplier_name,
                "quantity": 1,
                "unit_price": float(record.total or 0),
                "line_total": float(record.total or 0),
                "analysis_status": "product",
                "local_cache": True,
            }))
            continue
        for idx, row in enumerate(rows):
            desc = str(row.get("original_description") or row.get("normalized_description") or "")
            norm = str(row.get("normalized_description") or desc)
            hay = f"{desc} {norm} {record.supplier_name}".lower()
            words = re.findall(r"[a-zàèéìòù0-9]+", hay)
            if tokens:
                if any(t in hay for t in tokens):
                    score = 95.0
                else:
                    # Fuzzy stretto parola-per-parola: evita bomboloni↔bombola.
                    score = max(
                        (
                            fuzz.ratio(token, word)
                            for token in tokens
                            for word in words
                            if abs(len(token) - len(word)) <= 2
                        ),
                        default=0,
                    )
                    if score < 90:
                        continue
            elif needle:
                if needle in hay:
                    score = 95.0
                else:
                    score = max((fuzz.ratio(needle, word) for word in words), default=0)
                    if score < 90:
                        continue
            else:
                score = 80.0
            ranked.append((float(score), {
                "id": f"{record.source_hash}:{idx}",
                "source_hash": record.source_hash,
                "source_filename": payload.get("source_filename"),
                "invoice_number": record.invoice_number,
                "invoice_date": invoice_date,
                "supplier_name": record.supplier_name,
                "original_description": desc,
                "normalized_description": norm,
                "quantity": float(row.get("quantity") or 0),
                "unit_price": float(row.get("unit_price") or 0),
                "line_total": float(row.get("line_total") or 0),
                "analysis_status": row.get("analysis_status") or "product",
                "local_cache": True,
            }))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    total = len(ranked)
    page = [item for _, item in ranked[offset: offset + limit]]
    return {
        "items": page,
        "count": len(page),
        "total": total,
        "offset": offset,
        "limit": limit,
        "local": True,
        "scope": "full-cache",
    }


async def refresh_central_cache() -> dict:
    db = SessionLocal()
    try:
        setting = db.get(AppSetting, "central_sync_state") or AppSetting(key="central_sync_state", value="running")
        setting.value = "running"; db.add(setting); db.commit()
        offset = 0; total = None; imported = 0
        checkpoint = db.get(AppSetting, "central_sync_at")
        while True:
            # 50 keeps the nested line payload below Supabase gateway limits.
            page = await central_invoice_page(offset, 500, checkpoint.value if checkpoint else None)
            items = page.get("items", [])
            total = page.get("total", total)
            if not items: break
            for item in items:
                source_hash = str(item.get("source_hash") or item.get("id"))
                text = " ".join(str(item.get(k, "")) for k in ("invoice_number", "supplier_name", "source_filename"))
                for row in item.get("rows", []): text += " " + str(row.get("normalized_description") or row.get("original_description") or "")
                existing = db.get(CentralInvoiceCache, source_hash)
                values = dict(source_hash=source_hash, invoice_number=str(item.get("invoice_number") or ""), invoice_date=date.fromisoformat(str(item.get("invoice_date"))[:10]), supplier_name=str(item.get("supplier_name") or ""), total=Decimal(str(item.get("total") or 0)), search_text=text, payload_json=json.dumps(item, default=str), synced_at=datetime.now())
                if existing:
                    for key, value in values.items(): setattr(existing, key, value)
                else: db.add(CentralInvoiceCache(**values))
                imported += 1
            db.commit(); offset += len(items)
            if len(items) < 500 or (total is not None and offset >= total): break
        setting.value = f"ok:{imported}"; db.add(setting)
        checkpoint = db.get(AppSetting, "central_sync_at") or AppSetting(key="central_sync_at", value="")
        checkpoint.value = datetime.now(UTC).isoformat(); db.add(checkpoint); db.commit()
        return {"ok": True, "imported": imported, "total": total}
    except Exception as exc:
        setting = db.get(AppSetting, "central_sync_state") or AppSetting(key="central_sync_state", value="")
        setting.value = f"error:{exc}"; db.add(setting); db.commit()
        return {"ok": False, "message": str(exc)}
    finally: db.close()
