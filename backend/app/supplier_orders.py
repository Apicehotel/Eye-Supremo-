"""Ordini per fornitore: le stesse viste di un foglio ordini (dettaglio, riepilogo, consegne, prezzi,
registro fatture, verifiche), calcolate dalle righe fattura già presenti in app.

Non si inventa nulla: numero d'ordine, data d'ordine, DDT e codice articolo non sono nei dati importati,
quindi la data di riferimento è quella della fattura e gli articoli si raggruppano per descrizione.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime

from .models import CentralInvoiceCache, SupplierOrderSheet
from .normalization import fill_normalized_price, normalize_text

# Tolleranza per la quadratura (centesimi di arrotondamento tra righe e riepilogo IVA).
_TOLERANCE = 0.05


def _num(value) -> float:
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return 0.0


def _iso(value) -> str | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _article_key(description: str) -> str:
    return normalize_text(description).strip() or description.strip().lower()


def load_cached_invoices(db: Session, supplier_name: str) -> list[dict]:
    """Fatture (con righe) del fornitore dalla cache locale del centrale."""
    wanted = normalize_text(supplier_name).strip()
    invoices: list[dict] = []
    for record in db.scalars(select(CentralInvoiceCache).order_by(CentralInvoiceCache.invoice_date)).all():
        if normalize_text(record.supplier_name or "").strip() != wanted:
            continue
        try:
            payload = json.loads(record.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        invoices.append({
            "invoice_number": record.invoice_number,
            "invoice_date": record.invoice_date.isoformat() if record.invoice_date else None,
            "taxable": payload.get("taxable"),
            "vat": payload.get("vat"),
            "total": float(record.total or 0),
            "source_filename": payload.get("source_filename"),
            "rows": payload.get("rows") or [],
        })
    return invoices


def build_supplier_orders(invoices: list[dict], year: int | None = None) -> dict:
    movements: list[dict] = []
    register: list[dict] = []
    for invoice in invoices:
        rows = invoice.get("rows") or []
        total = _num(invoice.get("total"))
        credit_note = total < 0 or any(_num(r.get("quantity")) < 0 for r in rows)
        product_rows = 0
        rows_amount = 0.0
        for row in rows:
            if (row.get("analysis_status") or "product") != "product":
                continue
            product_rows += 1
            line_total = _num(row.get("line_total"))
            rows_amount += line_total
            description = str(row.get("original_description") or row.get("normalized_description") or "").strip()
            if not description:
                continue
            quantity = _num(row.get("quantity"))
            if credit_note and quantity > 0 and total < 0:
                quantity = -quantity
            item = fill_normalized_price({
                "unit_price": row.get("unit_price"), "quantity": row.get("quantity"),
                "original_unit": row.get("original_unit"), "original_description": description,
                "normalized_price": row.get("normalized_price"), "normalized_unit": row.get("normalized_unit"),
            })
            movements.append({
                "article": description,
                "key": _article_key(description),
                "quantity": quantity,
                "unit": row.get("original_unit") or "",
                "date": _iso(invoice.get("invoice_date")),
                "invoice_number": invoice.get("invoice_number"),
                "document_type": "Nota di credito" if credit_note else "Fattura",
                "unit_price": _num(row.get("unit_price")),
                "line_total": line_total,
                "normalized_price": item.get("normalized_price"),
                "normalized_unit": item.get("normalized_unit"),
            })
        taxable = invoice.get("taxable")
        vat = invoice.get("vat")
        difference = None
        outcome = "Dati insufficienti"
        if taxable is not None and product_rows:
            difference = round(rows_amount - _num(taxable), 2)
            outcome = "Quadra" if abs(difference) <= _TOLERANCE else "Differenza"
        register.append({
            "invoice_date": _iso(invoice.get("invoice_date")),
            "invoice_number": invoice.get("invoice_number"),
            "type": "Nota di credito" if credit_note else "Fattura",
            "product_rows": product_rows,
            "rows_amount": round(rows_amount, 2),
            "taxable": None if taxable is None else round(_num(taxable), 2),
            "vat": None if vat is None else round(_num(vat), 2),
            "total": round(total, 2),
            "outcome": outcome,
            "difference": difference,
            "source_filename": invoice.get("source_filename"),
        })

    # Riepilogo per articolo.
    groups: dict[str, list[dict]] = defaultdict(list)
    for m in movements:
        groups[m["key"]].append(m)
    summary = []
    prices = []
    for key, items in groups.items():
        dates = sorted(m["date"] for m in items if m["date"])
        credits = sum(-m["quantity"] for m in items if m["quantity"] < 0)
        units = sorted({m["unit"] for m in items if m["unit"]})
        name = items[0]["article"]
        summary.append({
            "article": name, "unit": ", ".join(units),
            "net_quantity": round(sum(m["quantity"] for m in items), 4),
            "credited_quantity": round(credits, 4),
            "rows": len(items), "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
        })
        dated = sorted((m for m in items if m["date"] and m["unit_price"] > 0), key=lambda m: m["date"])
        if dated:
            unit_prices = [m["unit_price"] for m in dated]
            last = dated[-1]
            prices.append({
                "article": name, "unit": ", ".join(units), "rows": len(dated),
                "last_date": last["date"], "last_price": last["unit_price"],
                "min_price": min(unit_prices), "max_price": max(unit_prices),
                "last_normalized_price": last["normalized_price"], "normalized_unit": last["normalized_unit"],
                "history": [{"date": m["date"], "price": m["unit_price"], "invoice_number": m["invoice_number"]} for m in dated],
            })
    summary.sort(key=lambda r: r["article"].lower())
    prices.sort(key=lambda r: r["article"].lower())

    # Consegne giornaliere: articolo × giorno, per anno.
    years = sorted({int(m["date"][:4]) for m in movements if m["date"]})
    chosen = year if year in years else (years[-1] if years else None)
    deliveries: dict[str, dict] = {}
    for m in movements:
        if not m["date"] or chosen is None or int(m["date"][:4]) != chosen:
            continue
        entry = deliveries.setdefault(m["key"], {"article": m["article"], "unit": m["unit"], "days": {}})
        entry["days"][m["date"]] = round(entry["days"].get(m["date"], 0) + m["quantity"], 4)
    delivery_rows = sorted(deliveries.values(), key=lambda r: r["article"].lower())

    movements.sort(key=lambda m: (m["date"] or "", m["article"].lower()))
    undated = sum(1 for m in movements if not m["date"])
    checks = {
        "distinct_articles": len(groups),
        "movements": len(movements),
        "invoices": len(register),
        "credit_notes": sum(1 for r in register if r["type"] == "Nota di credito"),
        "undated_movements": undated,
        "invoices_balanced": sum(1 for r in register if r["outcome"] == "Quadra"),
        "invoices_with_difference": sum(1 for r in register if r["outcome"] == "Differenza"),
        "invoices_without_data": sum(1 for r in register if r["outcome"] == "Dati insufficienti"),
        "not_available": ["numero ordine", "data ordine", "DDT", "codice articolo", "controlli XML"],
    }
    register.sort(key=lambda r: (r["invoice_date"] or "", r["invoice_number"] or ""))
    return {
        "movements": movements,
        "summary": summary,
        "deliveries": {"year": chosen, "years": years, "rows": delivery_rows},
        "prices": prices,
        "invoices": register,
        "checks": checks,
    }


def supplier_orders(db: Session, supplier_name: str, year: int | None = None) -> dict:
    return build_supplier_orders(load_cached_invoices(db, supplier_name), year)


def _key(supplier_name: str) -> str:
    return normalize_text(supplier_name).strip()[:180]


def sheet_for_supplier(db: Session, supplier_name: str) -> dict | None:
    record = db.get(SupplierOrderSheet, _key(supplier_name))
    if not record:
        return None
    return {"data": json.loads(record.payload_json), "filename": record.filename, "imported_at": record.imported_at.isoformat()}


def save_sheet(db: Session, supplier_name: str, filename: str | None, data: dict) -> None:
    record = db.get(SupplierOrderSheet, _key(supplier_name))
    payload = json.dumps(data, ensure_ascii=False)
    if record:
        record.supplier_name, record.filename, record.payload_json, record.imported_at = supplier_name, filename, payload, datetime.now()
    else:
        db.add(SupplierOrderSheet(supplier_key=_key(supplier_name), supplier_name=supplier_name, filename=filename, payload_json=payload))
    db.commit()
