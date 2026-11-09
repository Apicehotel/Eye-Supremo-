"""Ordini per fornitore: dati inventati, nessuna fattura reale nel repository."""
import json
from datetime import date
from decimal import Decimal

from app.models import CentralInvoiceCache
from app.supplier_orders import build_supplier_orders, supplier_orders


def row(desc, qty, price, total=None, unit="N."):
    return {"original_description": desc, "quantity": qty, "unit_price": price,
            "line_total": total if total is not None else qty * price, "original_unit": unit, "analysis_status": "product"}


INVOICES = [
    {"invoice_number": "F1", "invoice_date": "2026-05-10", "taxable": 30.0, "vat": 3.0, "total": 33.0,
     "rows": [row("ACQUA NATURALE 24X50CL", 2, 6.0), row("AMARETTI 250G", 6, 3.0)]},
    {"invoice_number": "F2", "invoice_date": "2026-06-02", "taxable": 12.0, "vat": 1.2, "total": 13.2,
     "rows": [row("ACQUA NATURALE 24X50CL", 2, 6.5)]},
    {"invoice_number": "NC1", "invoice_date": "2026-06-20", "taxable": -6.5, "vat": -0.65, "total": -7.15,
     "rows": [row("ACQUA NATURALE 24X50CL", 1, 6.5, -6.5)]},
    {"invoice_number": "F3", "invoice_date": "2025-12-01", "taxable": 99.0, "vat": 0, "total": 99.0,
     "rows": [row("AMARETTI 250G", 1, 3.0)]},
]


def test_summary_nets_credit_notes_and_counts_rows():
    data = build_supplier_orders(INVOICES)
    water = next(r for r in data["summary"] if r["article"].startswith("ACQUA"))
    assert water["net_quantity"] == 3      # 2 + 2 - 1
    assert water["credited_quantity"] == 1
    assert water["rows"] == 3
    assert (water["first_date"], water["last_date"]) == ("2026-05-10", "2026-06-20")
    assert data["checks"]["credit_notes"] == 1 and data["checks"]["distinct_articles"] == 2


def test_register_reconciles_rows_against_taxable():
    reg = {r["invoice_number"]: r for r in build_supplier_orders(INVOICES)["invoices"]}
    assert reg["F1"]["outcome"] == "Quadra" and reg["F1"]["difference"] == 0
    assert reg["F3"]["outcome"] == "Differenza" and reg["F3"]["difference"] == -96.0
    assert reg["NC1"]["type"] == "Nota di credito"


def test_prices_have_history_and_normalized_price():
    prices = {p["article"]: p for p in build_supplier_orders(INVOICES)["prices"]}
    water = prices["ACQUA NATURALE 24X50CL"]
    assert (water["min_price"], water["max_price"], water["last_price"]) == (6.0, 6.5, 6.5)
    assert water["normalized_unit"] == "l" and water["last_normalized_price"] == 0.5417


def test_daily_deliveries_follow_the_year():
    data = build_supplier_orders(INVOICES, year=2026)
    assert data["deliveries"]["years"] == [2025, 2026]
    water = next(r for r in data["deliveries"]["rows"] if r["article"].startswith("ACQUA"))
    assert water["days"] == {"2026-05-10": 2, "2026-06-02": 2, "2026-06-20": -1}
    assert build_supplier_orders(INVOICES, year=2025)["deliveries"]["rows"][0]["days"] == {"2025-12-01": 1}


def test_missing_fields_are_declared_not_invented():
    checks = build_supplier_orders(INVOICES)["checks"]
    assert "numero ordine" in checks["not_available"]
    assert build_supplier_orders([])["deliveries"]["year"] is None


def test_reads_the_supplier_from_the_local_cache(db_session=None):
    from app.database import SessionLocal, Base, engine
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.query(CentralInvoiceCache).delete()
        for hash_, inv in (("h1", INVOICES[0]), ("h2", INVOICES[1])):
            db.add(CentralInvoiceCache(
                source_hash=hash_, invoice_number=inv["invoice_number"], invoice_date=date.fromisoformat(inv["invoice_date"]),
                supplier_name="Fornitore Prova Srl", total=Decimal(str(inv["total"])), search_text="x",
                payload_json=json.dumps({"taxable": inv["taxable"], "vat": inv["vat"], "rows": inv["rows"]})))
        db.add(CentralInvoiceCache(source_hash="h3", invoice_number="X", invoice_date=date(2026, 1, 1), supplier_name="Altro",
                                   total=Decimal("1"), search_text="x", payload_json=json.dumps({"rows": [row("ZZZ", 1, 1)]})))
        db.commit()
        data = supplier_orders(db, "FORNITORE PROVA SRL")
        assert data["checks"]["invoices"] == 2 and data["checks"]["distinct_articles"] == 2
    finally:
        db.query(CentralInvoiceCache).delete(); db.commit(); db.close()
