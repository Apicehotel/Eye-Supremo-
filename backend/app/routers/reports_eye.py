from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Hotel, Invoice, InvoiceMeta
from ..central_service import central_invoice_search, central_product_detail, central_product_page
from ..product_taxonomy import is_catalog_product, is_family_match, is_product_search_match, merge_product_catalog, search_terms
from ..report_service import historical_product_report

router = APIRouter(prefix="/api/eye", tags=["Eye Supremo reports"])


@router.get("/reports/history-product")
async def history_product(q: str = Query(min_length=1, max_length=180), db: Session = Depends(get_db)):
    result = historical_product_report(db, q)
    # Family searches must pass through the same semantic guards for both the
    # local database and the central catalogue. Otherwise an old local broad
    # match could reintroduce ``lampada`` when the user asked for ``lampadine``.
    normalized_query = q.strip().lower()
    if result.get("summary") and normalized_query not in {"lampadine", "a4", "carta a4", "acqua"}:
        return result
    if q.strip().lower() in {"a4", "carta a4"}:
        matches = await central_invoice_search(q, 500)
        grouped = {}
        for row in matches.get("items", []):
            if not is_family_match(row.get("original_description") or row.get("normalized_description") or "", q):
                continue
            if row.get("analysis_status") not in (None, "product"):
                continue
            price = row.get("unit_price")
            if price is None or float(price) <= 0:
                continue
            unit = str(row.get("normalized_unit") or row.get("original_unit") or "unità").lower()
            key = (str(row.get("supplier_name") or "Fornitore"), unit)
            points = grouped.setdefault(key, [])
            previous = points[-1]["price"] if points else None
            delta = None if previous is None else round(float(price) - previous, 4)
            points.append({"date": str(row.get("invoice_date"))[:10], "price": round(float(price), 4), "quantity": row.get("quantity"), "delta": delta, "delta_pct": None if previous in (None, 0) else round(delta / previous * 100, 2), "trend": "initial" if previous is None else ("up" if delta > 0 else "down" if delta < 0 else "same"), "unit": unit, "invoice": row.get("invoice_number") or "", "description": row.get("original_description") or q})
        blocks = []
        for (supplier, unit), points in grouped.items():
            prices = [p["price"] for p in points]; best = min(points, key=lambda p: p["price"])
            blocks.append({"supplier_id": supplier, "supplier": supplier, "unit": unit, "manufacturer": None, "initial_price": prices[0], "initial_date": points[0]["date"], "average_price": round(sum(prices) / len(prices), 4), "best_price": best["price"], "best_date": best["date"], "latest_price": prices[-1], "latest_date": points[-1]["date"], "observations": len(points), "points": points})
        if blocks:
            all_points = [p for b in blocks for p in b["points"]]; best = min(all_points, key=lambda p: p["price"]); cheapest = min(blocks, key=lambda b: b["average_price"])
            return {"query": q, "summary": {"product": q.strip().upper(), "manufacturers": [], "unit": blocks[0]["unit"], "initial_price": min(all_points, key=lambda p: p["date"])["price"], "initial_date": min(p["date"] for p in all_points), "average_price": round(sum(p["price"] for p in all_points) / len(all_points), 4), "best_price": best["price"], "best_date": best["date"], "latest_price": max(all_points, key=lambda p: p["date"])["price"], "latest_date": max(p["date"] for p in all_points), "best_supplier": cheapest["supplier"], "best_supplier_average": cheapest["average_price"], "best_supplier_observations": cheapest["observations"]}, "suppliers": blocks, "dates": sorted({p["date"] for p in all_points}), "units": sorted({p["unit"] for p in all_points}), "comparison_note": "Confronto famiglia A4: sono incluse le righe prodotto A4 di tutti i fornitori."}
    # Local-first installations may have no Invoice rows while the shared
    # catalogue is already populated. Adapt the central product detail to the
    # same report contract used by the Excel-inspired UI.
    report_terms = list(search_terms(q))
    if len(q.split()) > 1:
        report_terms.append(q.split()[0])
    pages = [await central_product_page(term, 2000) for term in dict.fromkeys(report_terms)]
    merged = {}
    for page_item in pages:
        for item in page_item.get("items", []):
            if item.get("nome_canonico") and is_catalog_product(item["nome_canonico"]) and is_product_search_match(item["nome_canonico"], q):
                merged[item["nome_canonico"]] = item
    # The historical report has its own variant picker. Keep it aligned with
    # the product catalogue: equivalent descriptions with the same content
    # must appear as one product, while the source names remain available for
    # the detail/history lookup.
    page = {"items": merge_product_catalog(list(merged.values()))}
    product = next((x for x in page["items"] if x.get("nome_canonico")), None)
    if not product:
        return result
    matches = [{"canonical_name": x.get("nome_canonico"), "canonical_names": x.get("canonical_names") or [x.get("nome_canonico")], "brand": x.get("marca"), "purchases": x.get("purchases"), "avg_price": x.get("avg_price")} for x in page.get("items", []) if x.get("nome_canonico")]
    # A one-word family search (for example "acqua") is intentionally not
    # collapsed into the first catalogue row: let the user choose the exact
    # product variant so older purchases cannot hide newer ones.
    if len(matches) > 1 and len(q.split()) == 1:
        return {**result, "matches": matches}
    detail = await central_product_detail(product["nome_canonico"])
    history = detail.get("history", [])
    if not history:
        return result
    grouped = {}
    for row in sorted(history, key=lambda x: (str(x.get("invoice_date") or ""), str(x.get("supplier_name") or ""))):
        unit = str(row.get("normalized_unit") or row.get("original_unit") or "unità").lower()
        price = row.get("normalized_price") or row.get("unit_price")
        if price is None or float(price) <= 0:
            continue
        key = (str(row.get("supplier_name") or "Fornitore"), unit)
        points = grouped.setdefault(key, [])
        previous = points[-1]["price"] if points else None
        delta = None if previous is None else round(float(price) - previous, 4)
        points.append({"date": str(row.get("invoice_date"))[:10], "price": round(float(price), 4), "quantity": row.get("quantity"), "delta": delta, "delta_pct": None if previous in (None, 0) else round(delta / previous * 100, 2), "trend": "initial" if previous is None else ("up" if delta > 0 else "down" if delta < 0 else "same"), "unit": unit, "invoice": row.get("invoice_number") or "", "description": product["nome_canonico"]})
    blocks = []
    for (supplier, unit), points in grouped.items():
        prices = [x["price"] for x in points]
        best = min(points, key=lambda x: x["price"])
        blocks.append({"supplier_id": supplier, "supplier": supplier, "unit": unit, "manufacturer": product.get("marca"), "initial_price": prices[0], "initial_date": points[0]["date"], "average_price": round(sum(prices) / len(prices), 4), "best_price": best["price"], "best_date": best["date"], "latest_price": prices[-1], "latest_date": points[-1]["date"], "observations": len(points), "points": points})
    if not blocks:
        return result
    all_points = [p for b in blocks for p in b["points"]]
    best = min(all_points, key=lambda x: x["price"])
    best_supplier = min(blocks, key=lambda x: x["average_price"])
    return {"query": q, "summary": {"product": product["nome_canonico"], "manufacturers": [product["marca"]] if product.get("marca") else [], "unit": blocks[0]["unit"], "initial_price": min(all_points, key=lambda x: x["date"])["price"], "initial_date": min(x["date"] for x in all_points), "average_price": round(sum(x["price"] for x in all_points) / len(all_points), 4), "best_price": best["price"], "best_date": best["date"], "latest_price": max(all_points, key=lambda x: x["date"])["price"], "latest_date": max(x["date"] for x in all_points), "best_supplier": best_supplier["supplier"], "best_supplier_average": best_supplier["average_price"], "best_supplier_observations": best_supplier["observations"]}, "suppliers": blocks, "dates": sorted({x["date"] for x in all_points}), "units": sorted({x["unit"] for x in all_points}), "comparison_note": "I confronti tra fornitori usano solo prezzi con la stessa unità normalizzata."}


@router.get("/invoice-destinations")
def invoice_destinations(limit: int = Query(250, ge=1, le=1000), db: Session = Depends(get_db)):
    items = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.supplier), selectinload(Invoice.meta).selectinload(InvoiceMeta.hotel))
        .order_by(Invoice.data.desc(), Invoice.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": inv.id,
            "number": inv.numero,
            "date": inv.data.isoformat(),
            "supplier": inv.supplier.ragione_sociale,
            "total": float(inv.totale or 0),
            "destination": inv.meta.hotel.code if inv.meta and inv.meta.hotel else None,
            "destination_name": inv.meta.hotel.name if inv.meta and inv.meta.hotel else "Generale / Apice",
        }
        for inv in items
    ]


@router.put("/invoice-destinations/{invoice_id}")
def set_invoice_destination(invoice_id: int, payload: dict, db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.meta)).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(404, "Fattura non trovata")
    if not invoice.meta:
        from ..eye_services import ensure_invoice_metadata
        ensure_invoice_metadata(db, invoice, None)
        db.flush()
    code = str(payload.get("hotel_code") or "").strip().lower()
    if not code or code == "general":
        invoice.meta.hotel_id = None
        db.commit()
        return {"ok": True, "destination": None, "destination_name": "Generale / Apice"}
    hotel = db.scalar(select(Hotel).where(Hotel.code == code, Hotel.active.is_(True)))
    if not hotel:
        raise HTTPException(404, "Destinazione hotel non trovata")
    invoice.meta.hotel_id = hotel.id
    db.commit()
    return {"ok": True, "destination": hotel.code, "destination_name": hotel.name}
