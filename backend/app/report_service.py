from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Invoice, InvoiceRow, InvoiceRowPolicy, Product, Supplier
from .normalization import normalize_text


def _money(value) -> float:
    return round(float(value or 0), 4)


def historical_product_report(db: Session, query: str, limit: int = 1200) -> dict:
    q = normalize_text(query)
    if not q:
        return {"query": query, "summary": None, "suppliers": [], "dates": [], "units": []}

    stmt = (
        select(InvoiceRow, Invoice, Supplier, Product, InvoiceRowPolicy)
        .join(Invoice, Invoice.id == InvoiceRow.invoice_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(Product, Product.id == InvoiceRow.product_id)
        .outerjoin(InvoiceRowPolicy, InvoiceRowPolicy.row_id == InvoiceRow.id)
        .where(
            or_(
                InvoiceRow.descrizione_normalizzata.ilike(f"%{q}%"),
                InvoiceRow.descrizione_originale.ilike(f"%{query.strip()}%"),
                Product.nome_canonico.ilike(f"%{query.strip()}%"),
                Product.marca.ilike(f"%{query.strip()}%"),
            )
        )
        .where(or_(InvoiceRowPolicy.analysis_status.is_(None), InvoiceRowPolicy.analysis_status == "product"))
        .order_by(Invoice.data.asc(), InvoiceRow.id.asc())
        .limit(limit)
    )
    records = db.execute(stmt).all()

    grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
    manufacturers: set[str] = set()
    product_names: list[str] = []
    for row, invoice, supplier, product, _policy in records:
        unit = (row.unita_normalizzata or row.unita_originale or (product.unita_base if product else None) or "pz").lower()
        raw_price = row.prezzo_normalizzato if row.prezzo_normalizzato not in (None, Decimal("0")) else row.prezzo_unitario
        price = _money(raw_price)
        if price <= 0:
            continue
        manufacturer = (product.marca if product and product.marca else "").strip()
        if manufacturer:
            manufacturers.add(manufacturer)
        if product and product.nome_canonico:
            product_names.append(product.nome_canonico)
        grouped[(supplier.id, unit)].append({
            "row_id": row.id,
            "invoice_id": invoice.id,
            "invoice": invoice.numero,
            "date": invoice.data.isoformat(),
            "price": price,
            "quantity": _money(row.quantita),
            "unit": unit,
            "description": row.descrizione_originale,
            "manufacturer": manufacturer or None,
        })

    supplier_blocks = []
    all_points = []
    for (supplier_id, unit), points in grouped.items():
        points.sort(key=lambda x: (x["date"], x["row_id"]))
        previous = None
        for point in points:
            delta = None if previous is None else round(point["price"] - previous, 4)
            pct = None if previous in (None, 0) else round((point["price"] - previous) / previous * 100, 2)
            point["delta"] = delta
            point["delta_pct"] = pct
            point["trend"] = "initial" if previous is None else ("up" if delta > 0 else "down" if delta < 0 else "same")
            previous = point["price"]
        prices = [p["price"] for p in points]
        supplier = db.get(Supplier, supplier_id)
        best_point = min(points, key=lambda p: p["price"])
        latest = points[-1]
        block = {
            "supplier_id": supplier_id,
            "supplier": supplier.ragione_sociale if supplier else f"Fornitore {supplier_id}",
            "unit": unit,
            "manufacturer": next((p["manufacturer"] for p in points if p["manufacturer"]), None),
            "initial_price": prices[0],
            "initial_date": points[0]["date"],
            "average_price": round(sum(prices) / len(prices), 4),
            "best_price": best_point["price"],
            "best_date": best_point["date"],
            "latest_price": latest["price"],
            "latest_date": latest["date"],
            "observations": len(points),
            "points": points,
        }
        supplier_blocks.append(block)
        all_points.extend([(block, p) for p in points])

    if not supplier_blocks:
        return {"query": query, "summary": None, "suppliers": [], "dates": [], "units": []}

    # Do not compare unlike units. The dominant unit is the one with the most observations.
    unit_counts: dict[str, int] = defaultdict(int)
    for block in supplier_blocks:
        unit_counts[block["unit"]] += block["observations"]
    dominant_unit = max(unit_counts, key=unit_counts.get)
    comparable = [b for b in supplier_blocks if b["unit"] == dominant_unit]
    comparable_points = [p for b, p in all_points if b["unit"] == dominant_unit]
    first_point = min(comparable_points, key=lambda p: (p["date"], p["row_id"]))
    last_point = max(comparable_points, key=lambda p: (p["date"], p["row_id"]))
    best_point = min(comparable_points, key=lambda p: p["price"])
    best_supplier = min(comparable, key=lambda b: b["average_price"])
    summary = {
        "product": product_names[0] if product_names else query.strip(),
        "manufacturers": sorted(manufacturers),
        "unit": dominant_unit,
        "initial_price": first_point["price"],
        "initial_date": first_point["date"],
        "average_price": round(sum(p["price"] for p in comparable_points) / len(comparable_points), 4),
        "best_price": best_point["price"],
        "best_date": best_point["date"],
        "latest_price": last_point["price"],
        "latest_date": last_point["date"],
        "best_supplier": best_supplier["supplier"],
        "best_supplier_average": best_supplier["average_price"],
        "best_supplier_observations": best_supplier["observations"],
    }
    dates = sorted({p["date"] for block in comparable for p in block["points"]})
    supplier_blocks.sort(key=lambda b: (b["unit"] != dominant_unit, b["average_price"], b["supplier"].lower()))
    return {
        "query": query,
        "summary": summary,
        "suppliers": supplier_blocks,
        "dates": dates,
        "units": sorted(unit_counts),
        "comparison_note": "I confronti tra fornitori usano solo prezzi con la stessa unità normalizzata.",
    }
