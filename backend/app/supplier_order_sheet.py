"""Foglio ordini del fornitore (formato «Ordini <fornitore> … fatture.xlsx»): lettura e viste.

Il file ha un foglio «Dettaglio articoli» (ordini/consegne), «Prezzi da fatture» (righe dagli XML) e
«Fatture ricevute» (registro). Le altre viste del foglio (riepilogo, consegne giornaliere, verifiche,
controlli XML, schede articolo) sono formule: qui si ricalcolano dagli stessi dati, senza inventare nulla.
"""
from __future__ import annotations

import io
import json
from collections import defaultdict
from datetime import date, datetime

from .normalization import fill_normalized_price

_TOLERANCE = 0.02  # come il foglio: |imponibile + IVA - totale| <= 0,02


def _d(value) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return None
    return None


def _f(value) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _s(value) -> str:
    return "" if value is None else str(value).strip()


def parse_order_workbook(content: bytes) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    needed = ["Dettaglio articoli"]
    missing = [name for name in needed if name not in wb.sheetnames]
    if missing:
        raise ValueError(f"Foglio mancante: {', '.join(missing)}. Atteso il formato «Dettaglio articoli / Prezzi da fatture / Fatture ricevute».")

    movements = []
    for row_no, row in enumerate(wb["Dettaglio articoli"].iter_rows(min_row=2, max_col=10, values_only=True), start=2):
        if not row or not _s(row[0]):
            continue
        movements.append({
            "origin_row": row_no, "article": _s(row[0]), "quantity": _f(row[1]) or 0.0, "unit": _s(row[2]),
            "order_date": _d(row[3]), "code": _s(row[4]), "order_number": _s(row[5]),
            "invoice_number": _s(row[6]), "invoice_date": _d(row[7]),
            "document_type": _s(row[8]) or "Fattura", "note": _s(row[9]),
        })

    prices = []
    if "Prezzi da fatture" in wb.sheetnames:
        for row_no, row in enumerate(wb["Prezzi da fatture"].iter_rows(min_row=6, max_col=16, values_only=True), start=6):
            if not row or not _s(row[1]):
                continue
            prices.append({
                "invoice_date": _d(row[0]), "invoice_number": _s(row[1]), "ddt_date": _d(row[2]), "doc_type": _s(row[3]),
                "code": _s(row[4]), "description": _s(row[5]), "quantity": _f(row[6]) or 0.0, "unit": _s(row[7]),
                "unit_price": _f(row[8]), "line_total": _f(row[9]), "vat_rate": _f(row[10]),
                "origin_row": row[11], "xml_file": _s(row[14]), "invoice_line": row[15],
            })

    invoices = []
    if "Fatture ricevute" in wb.sheetnames:
        for row in wb["Fatture ricevute"].iter_rows(min_row=5, max_col=11, values_only=True):
            if not row or not _s(row[1]):
                continue
            invoices.append({
                "invoice_date": _d(row[0]), "invoice_number": _s(row[1]), "ddt_date": _d(row[2]), "doc_type": _s(row[3]),
                "vat": _f(row[6]) or 0.0, "total": _f(row[7]) or 0.0, "xml_file": _s(row[8]),
            })

    title = ""
    for name in ("Dettaglio articoli",):
        title = name
    return {"movements": movements, "prices": prices, "invoices": invoices, "sheet": title}


def build_sheet_views(data: dict, year: int | None = None) -> dict:
    movements = data.get("movements") or []
    prices = data.get("prices") or []
    registry = data.get("invoices") or []

    price_by_key: dict[tuple[str, str], dict] = {}
    for p in prices:
        price_by_key.setdefault((p["code"], p["invoice_number"]), p)
    prices_by_code: dict[str, list[dict]] = defaultdict(list)
    for p in prices:
        prices_by_code[p["code"]].append(p)

    rows = []
    for m in movements:
        used = m["order_date"] or m["invoice_date"]
        price = price_by_key.get((m["code"], m["invoice_number"]))
        unit_price = price["unit_price"] if price else None
        normalized = fill_normalized_price({
            "unit_price": unit_price, "quantity": m["quantity"], "original_unit": m["unit"], "original_description": m["article"],
        }) if unit_price else {}
        credit = m["document_type"].lower().startswith("nota") or m["quantity"] < 0
        rows.append({
            **m, "date": used, "uses_invoice_date": not m["order_date"], "credit": credit,
            "unit_price": unit_price, "price_from_xml": price is not None,
            "normalized_price": normalized.get("normalized_price"), "normalized_unit": normalized.get("normalized_unit"),
        })

    # Riepilogo per articolo (per codice, come il foglio).
    by_code: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_code[r["code"] or r["article"]].append(r)
    summary = []
    for code, items in by_code.items():
        order_dates = sorted(i["order_date"] for i in items if i["order_date"])
        summary.append({
            "code": items[0]["code"], "article": items[0]["article"], "unit": items[0]["unit"],
            "net_quantity": round(sum(i["quantity"] for i in items), 4),
            "credited_quantity": round(sum(i["quantity"] for i in items if i["quantity"] < 0), 4),
            "rows": len(items),
            "first_date": order_dates[0] if order_dates else None, "last_date": order_dates[-1] if order_dates else None,
        })
    summary.sort(key=lambda r: r["article"].lower())

    # Consegne giornaliere: articolo × giorno (data ordine, altrimenti fattura) con riga prezzo.
    years = sorted({int(r["date"][:4]) for r in rows if r["date"]})
    chosen = year if year in years else (years[-1] if years else None)
    grid: dict[str, dict] = {}
    for r in rows:
        if not r["date"] or chosen is None or int(r["date"][:4]) != chosen:
            continue
        key = r["code"] or r["article"]
        entry = grid.setdefault(key, {"code": r["code"], "article": r["article"], "unit": r["unit"], "days": {}, "prices": {}, "invoice_date_days": []})
        entry["days"][r["date"]] = round(entry["days"].get(r["date"], 0) + r["quantity"], 4)
        if r["unit_price"] is not None:
            entry["prices"][r["date"]] = r["unit_price"]
        if r["uses_invoice_date"] and r["date"] not in entry["invoice_date_days"]:
            entry["invoice_date_days"].append(r["date"])
    delivery_rows = sorted(grid.values(), key=lambda r: r["article"].lower())

    # Registro fatture con quadratura come il foglio.
    lines_by_invoice: dict[str, list[dict]] = defaultdict(list)
    for p in prices:
        lines_by_invoice[p["invoice_number"]].append(p)
    invoice_rows = []
    for inv in registry:
        lines = lines_by_invoice.get(inv["invoice_number"], [])
        amount = round(sum(l["line_total"] or 0 for l in lines), 2)
        diff = round(amount + inv["vat"] - inv["total"], 2)
        invoice_rows.append({**inv, "product_rows": len(lines), "rows_amount": amount, "difference": diff,
                             "outcome": "OK" if abs(diff) <= _TOLERANCE else "VERIFICARE"})
    invoice_rows.sort(key=lambda r: (r["invoice_date"] or "", r["invoice_number"]))

    # Controlli XML: fatture dei movimenti senza XML ricevuto.
    have_xml = {i["invoice_number"] for i in registry}
    missing: dict[str, dict] = {}
    for r in rows:
        if not r["invoice_number"] or r["invoice_number"] in have_xml:
            continue
        e = missing.setdefault(r["invoice_number"], {"invoice_number": r["invoice_number"], "invoice_date": r["invoice_date"], "movements": 0, "note": "", "xml_received": False})
        e["movements"] += 1
        if r["credit"]:
            e["note"] = "Include nota di credito"
    missing_rows = sorted(missing.values(), key=lambda r: (r["invoice_date"] or "", r["invoice_number"]))

    # Scostamenti: righe prezzo il cui movimento (codice + fattura) ha quantità diversa.
    qty_by_key: dict[tuple[str, str], float] = defaultdict(float)
    for r in rows:
        qty_by_key[(r["code"], r["invoice_number"])] += r["quantity"]
    mismatches = 0
    price_qty: dict[tuple[str, str], float] = defaultdict(float)
    for p in prices:
        price_qty[(p["code"], p["invoice_number"])] += p["quantity"]
    for key, q in price_qty.items():
        if key in qty_by_key and abs(qty_by_key[key] - q) > 1e-6:
            mismatches += 1

    undated = [r for r in rows if r["uses_invoice_date"]]
    verify_rows = [{
        "origin_row": r["origin_row"], "code": r["code"], "article": r["article"], "quantity": r["quantity"], "unit": r["unit"],
        "date_used": r["date"], "document_type": r["document_type"],
        "reason": " / ".join(x for x in ("Senza data ordine" if r["uses_invoice_date"] else "", "Nota di credito" if r["credit"] else "") if x),
    } for r in rows if r["uses_invoice_date"] or r["credit"]]
    verify_rows.sort(key=lambda r: (r["date_used"] or "", r["origin_row"]))

    checks = {
        "distinct_articles": len(by_code), "movements": len(rows), "undated_movements": len(undated),
        "credit_notes": sum(1 for r in rows if r["document_type"].lower().startswith("nota")),
        "invoices": len(invoice_rows), "price_rows": len(prices),
        "invoices_balanced": sum(1 for r in invoice_rows if r["outcome"] == "OK"),
        "invoices_with_difference": sum(1 for r in invoice_rows if r["outcome"] != "OK"),
        "missing_prices": len(rows) - len(prices),
        "missing_xml_invoices": len(missing_rows),
        "quantity_mismatches": mismatches,
        "not_available": [],
        "verify_rows": verify_rows,
    }
    rows.sort(key=lambda r: (r["date"] or "", r["article"].lower()))
    return {
        "source": "sheet", "movements": rows, "summary": summary,
        "deliveries": {"year": chosen, "years": years, "rows": delivery_rows},
        "prices": prices, "invoices": invoice_rows, "xml_checks": missing_rows, "checks": checks,
    }


def article_page(data: dict, code: str) -> dict:
    views = build_sheet_views(data)
    items = [m for m in views["movements"] if (m["code"] or m["article"]) == code]
    if not items:
        return {"code": code, "movements": []}
    return {
        "code": items[0]["code"], "article": items[0]["article"], "unit": items[0]["unit"],
        "movements": items,
        "net_quantity": round(sum(i["quantity"] for i in items), 4),
        "credited_quantity": round(sum(i["quantity"] for i in items if i["quantity"] < 0), 4),
        "without_order_date": sum(1 for i in items if i["uses_invoice_date"]),
    }


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)
