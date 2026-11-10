"""Ordini per fornitore: dati inventati, nessuna fattura reale nel repository."""
import asyncio
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
        data = asyncio.run(supplier_orders(db, "FORNITORE PROVA SRL"))
        assert data["checks"]["invoices"] == 2 and data["checks"]["distinct_articles"] == 2
    finally:
        db.query(CentralInvoiceCache).delete(); db.commit(); db.close()


def test_supplier_name_matches_without_legal_form():
    from app.supplier_orders import supplier_match_key
    assert supplier_match_key("MARR Spa") == supplier_match_key("MARR S.P.A.") == "marr"
    assert supplier_match_key("Marmi Batta SRL") != supplier_match_key("MARR Spa")


def test_orders_use_local_invoices_and_download_missing_rows(monkeypatch):
    """Nessun foglio da caricare: fatture locali + cache, e righe mancanti scaricate dal centrale."""
    from app import central_service
    from app.database import SessionLocal
    from app.models import Invoice, InvoiceRow, Supplier
    from app.supplier_orders import collect_invoices
    calls = []

    async def fake_detail(source_hash):
        calls.append(source_hash)
        return {"rows": [row("ARTICOLO CENTRALE", 2, 3)], "taxable": 6.0, "vat": 0.0}

    monkeypatch.setattr(central_service, "central_invoice_detail", fake_detail)
    monkeypatch.setattr(central_service, "configured", lambda: True)
    db = SessionLocal()
    try:
        db.query(CentralInvoiceCache).delete()
        supplier = Supplier(ragione_sociale="ZETA TEST S.P.A.")
        db.add(supplier); db.flush()
        invoice = Invoice(supplier_id=supplier.id, numero="L1", data=date(2026, 3, 1), imponibile=Decimal("10"), iva=Decimal("0"), totale=Decimal("10"), hash_file="hl1")
        db.add(invoice); db.flush()
        db.add(InvoiceRow(invoice_id=invoice.id, descrizione_originale="ARTICOLO LOCALE", descrizione_normalizzata="articolo locale", quantita=Decimal("1"), prezzo_unitario=Decimal("10"), totale_riga=Decimal("10")))
        db.add(CentralInvoiceCache(source_hash="hc1", invoice_number="C1", invoice_date=date(2026, 3, 2), supplier_name="Zeta Test Spa",
                                   total=Decimal("6"), search_text="x", payload_json=json.dumps({"rows": []})))
        db.commit()
        invoices = asyncio.run(collect_invoices(db, "Zeta Test Spa"))
        assert [i["invoice_number"] for i in invoices] == ["L1", "C1"]
        assert invoices[1]["rows"] and calls == ["hc1"]
        # le righe scaricate restano nella cache: la seconda volta niente chiamate
        asyncio.run(collect_invoices(db, "Zeta Test Spa"))
        assert calls == ["hc1"]
    finally:
        db.query(CentralInvoiceCache).delete(); db.query(InvoiceRow).delete(); db.query(Invoice).delete(); db.query(Supplier).delete(); db.commit(); db.close()


def test_central_download_has_a_time_budget(monkeypatch):
    """Se il centrale non risponde la pagina non resta in attesa: i dati disponibili arrivano comunque."""
    from app import central_service, supplier_orders as so
    from app.database import SessionLocal
    monkeypatch.setattr(so, "_CENTRAL_BUDGET_SECONDS", 0.2)

    async def slow_detail(source_hash):
        await asyncio.sleep(30)

    monkeypatch.setattr(central_service, "central_invoice_detail", slow_detail)
    monkeypatch.setattr(central_service, "configured", lambda: True)
    db = SessionLocal()
    try:
        db.query(CentralInvoiceCache).delete()
        db.add(CentralInvoiceCache(source_hash="s1", invoice_number="S1", invoice_date=date(2026, 4, 1), supplier_name="Lento Srl",
                                   total=Decimal("5"), search_text="x", payload_json=json.dumps({"rows": []})))
        db.commit()
        import time
        started = time.monotonic()
        data = asyncio.run(so.supplier_orders(db, "Lento Srl"))
        assert time.monotonic() - started < 5
        assert data["checks"]["invoices_without_rows"] == 1
    finally:
        db.query(CentralInvoiceCache).delete(); db.commit(); db.close()
