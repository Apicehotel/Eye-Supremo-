import json
from datetime import date
from decimal import Decimal

from app.models import CentralInvoiceCache, Invoice, InvoiceRow, Supplier
from app.report_service import historical_product_report


def _cache_invoice(db, hash_, supplier, number, day, desc, price):
    payload = {"invoice_number": number, "invoice_date": day.isoformat(), "supplier_name": supplier, "total": price,
               "rows": [{"original_description": desc, "normalized_description": desc.lower(), "quantity": 10, "unit_price": price,
                         "line_total": price * 10, "analysis_status": "product"}]}
    db.add(CentralInvoiceCache(source_hash=hash_, invoice_number=number, invoice_date=day, supplier_name=supplier,
                               total=Decimal(str(price * 10)), search_text=f"{number} {supplier} {desc}", payload_json=json.dumps(payload)))


def test_report_lists_suppliers_from_cache_and_local_without_duplicates(db):
    local_supplier = Supplier(ragione_sociale="Forno Locale")
    db.add(local_supplier)
    db.flush()
    inv = Invoice(supplier_id=local_supplier.id, numero="L-1", data=date(2026, 1, 10), imponibile=Decimal("10"), iva=Decimal("0"),
                  totale=Decimal("10"), hash_file="hash-local-dup")
    db.add(inv)
    db.flush()
    db.add(InvoiceRow(invoice_id=inv.id, descrizione_originale="BOMBOLONI CREMA", descrizione_normalizzata="bomboloni crema",
                      quantita=Decimal("10"), unita_normalizzata="pz", prezzo_unitario=Decimal("1.10"), totale_riga=Decimal("11")))
    # stessa fattura anche in cache (non deve contare due volte) + due fornitori solo in cache
    _cache_invoice(db, "hash-local-dup", "Forno Locale", "L-1", date(2026, 1, 10), "BOMBOLONI CREMA", 1.10)
    _cache_invoice(db, "hash-c-1", "Pasticceria Centrale", "C-1", date(2026, 2, 5), "MINIBOMBOLONI ASSORTITI", 0.80)
    _cache_invoice(db, "hash-c-2", "Dolci Srl", "C-2", date(2026, 3, 7), "Bomboloni vuoti", 0.95)
    db.commit()

    report = historical_product_report(db, "bomboloni")
    names = {b["supplier"] for b in report["suppliers"]}
    assert {"Forno Locale", "Pasticceria Centrale", "Dolci Srl"} <= names
    local_block = next(b for b in report["suppliers"] if b["supplier"] == "Forno Locale")
    assert local_block["observations"] == 1
    assert report["sources"]["cache"] == 2 and report["sources"]["suppliers"] >= 3
    central_block = next(b for b in report["suppliers"] if b["supplier"] == "Pasticceria Centrale")
    assert central_block["points"][0]["invoice_id"] == "hash-c-1"
    assert report["summary"]["best_supplier"] == "Pasticceria Centrale"


def test_report_from_cache_only(db):
    _cache_invoice(db, "only-c-1", "Solo Cache A", "A-1", date(2026, 4, 1), "BOMBOLONI", 1.0)
    _cache_invoice(db, "only-c-2", "Solo Cache B", "B-1", date(2026, 4, 2), "BOMBOLONI", 1.2)
    db.commit()
    report = historical_product_report(db, "bomboloni")
    assert {b["supplier"] for b in report["suppliers"]} >= {"Solo Cache A", "Solo Cache B"}
