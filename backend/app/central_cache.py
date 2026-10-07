import json
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session
from .central_service import central_invoice_page
from .database import SessionLocal
from .models import AppSetting, CentralInvoiceCache


def cache_status(db: Session) -> dict:
    count = db.scalar(select(func.count()).select_from(CentralInvoiceCache)) or 0
    state = db.get(AppSetting, "central_sync_state")
    return {"count": count, "state": state.value if state else "never", "local": True}


def cached_search(db: Session, query: str, limit: int, offset: int = 0) -> dict:
    stmt = select(CentralInvoiceCache).order_by(CentralInvoiceCache.invoice_date.desc()).offset(max(0, offset)).limit(limit)
    if query:
        needle = f"%{query.strip().lower()}%"
        stmt = stmt.where(or_(CentralInvoiceCache.search_text.ilike(needle), CentralInvoiceCache.invoice_number.ilike(needle), CentralInvoiceCache.supplier_name.ilike(needle)))
    items = [json.loads(x.payload_json) for x in db.scalars(stmt).all()]
    total_stmt = select(func.count()).select_from(CentralInvoiceCache)
    if query:
        total_stmt = total_stmt.where(or_(CentralInvoiceCache.search_text.ilike(needle), CentralInvoiceCache.invoice_number.ilike(needle), CentralInvoiceCache.supplier_name.ilike(needle)))
    return {"enabled": True, "local": True, "items": items, "count": len(items), "total": db.scalar(total_stmt) or 0, "offset": max(0, offset), "limit": limit}


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
