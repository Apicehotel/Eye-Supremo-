"""Build the local MARR workbook snapshot used by the Eye Supremo MARR page.

This is a development/import utility. The desktop app reads the generated JSON
and does not need Excel or openpyxl installed at runtime.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook


def serialise(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def clean_row(row):
    return [serialise(value) for value in row]


def main(source: str, destination: str):
    workbook = load_workbook(source, read_only=True, data_only=True)

    detail_rows = [clean_row(row) for row in workbook["Dettaglio articoli"].iter_rows(min_row=2, values_only=True)]
    price_rows = [clean_row(row) for row in workbook["Prezzi da fatture"].iter_rows(min_row=6, values_only=True)]
    invoice_rows = [clean_row(row) for row in workbook["Fatture ricevute"].iter_rows(min_row=5, values_only=True)]

    detail_headers = ["description", "quantity", "unit", "order_date", "article_code", "order_number", "invoice_number", "invoice_date", "document_type", "notes"]
    price_headers = ["invoice_date", "invoice_number", "ddt_date", "document_type", "article_code", "description", "quantity", "unit", "unit_price", "line_total", "vat_percent", "source_row", "product_sheet", "price_cell", "xml_file", "invoice_row"]
    invoice_headers = ["invoice_date", "invoice_number", "ddt_date", "document_type", "product_rows", "taxable_from_rows", "vat_total", "invoice_total", "xml_file", "reconciliation_status", "difference"]

    def mapped(rows, headers):
        return [dict(zip(headers, row)) for row in rows]

    detail = mapped(detail_rows, detail_headers)
    prices = mapped(price_rows, price_headers)
    invoices = mapped(invoice_rows, invoice_headers)
    # The workbook stores these summary cells as formulas, but some readers do
    # not receive the cached formula values. Recompute them from the raw
    # movements so the application always displays complete data.
    grouped = {}
    for row in detail:
        code = str(row.get("article_code") or "").strip()
        if not code:
            continue
        item = grouped.setdefault(code, {
            "description": row.get("description"),
            "article_code": code,
            "unit": row.get("unit"),
            "total_quantity": 0,
            "returned_quantity": 0,
            "movement_count": 0,
            "first_order": None,
            "last_order": None,
        })
        quantity = float(row.get("quantity") or 0)
        item["total_quantity"] += quantity
        if str(row.get("document_type") or "").casefold() == "nota di credito":
            item["returned_quantity"] += quantity
        item["movement_count"] += 1
        movement_date = row.get("order_date") or row.get("invoice_date")
        if movement_date:
            item["first_order"] = min(item["first_order"] or movement_date, movement_date)
            item["last_order"] = max(item["last_order"] or movement_date, movement_date)
    articles = list(grouped.values())
    articles.sort(key=lambda row: str(row.get("description") or "").casefold())
    article_codes = {row.get("article_code") for row in detail if row.get("article_code")}
    invoice_numbers = {row.get("invoice_number") for row in detail if row.get("invoice_number")}
    xml_files = {row.get("xml_file") for row in invoices if row.get("xml_file")}
    credit_notes = sum(1 for row in detail if row.get("document_type") == "Nota di credito")
    missing_order_dates = sum(1 for row in detail if not row.get("order_date"))

    payload = {
        "source": {
            "filename": Path(source).name,
            "as_of": "2026-10-28",
            "sheets": len(workbook.sheetnames),
            "detail_sheet": "Dettaglio articoli",
            "prices_sheet": "Prezzi da fatture",
            "invoices_sheet": "Fatture ricevute",
        },
        "summary": {
            "movements": len(detail),
            "distinct_articles": len(article_codes),
            "invoice_numbers": len(invoice_numbers),
            "xml_invoices": len(xml_files),
            "matched_price_rows": len(prices),
            "missing_order_dates": missing_order_dates,
            "credit_notes": credit_notes,
        },
        "articles": articles,
        "movements": detail,
        "prices": prices,
        "invoices": invoices,
    }
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_marr_snapshot.py INPUT.xlsx OUTPUT.json")
    main(sys.argv[1], sys.argv[2])
