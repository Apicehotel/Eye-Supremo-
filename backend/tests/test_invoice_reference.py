import json
from datetime import date
from decimal import Decimal

from app.models import CentralInvoiceCache, Invoice, InvoiceRow, Supplier


def _local_invoice(db):
    supplier = Supplier(ragione_sociale="Fornitore Rif Srl")
    db.add(supplier)
    db.flush()
    invoice = Invoice(supplier_id=supplier.id, numero="RIF-1", data=date(2026, 5, 2), imponibile=Decimal("10"), iva=Decimal("2.2"), totale=Decimal("12.2"), hash_file="localhash-ref-1")
    db.add(invoice)
    db.flush()
    db.add(InvoiceRow(invoice_id=invoice.id, descrizione_originale="LIMONCELLO 70CL", descrizione_normalizzata="limoncello 70cl", quantita=Decimal("2"), prezzo_unitario=Decimal("5"), totale_riga=Decimal("10")))
    db.commit()
    return invoice.id


def test_invoice_ref_local_by_id_and_by_hash(client, db):
    invoice_id = _local_invoice(db)
    by_id = client.get(f"/api/eye/invoice-ref/{invoice_id}")
    assert by_id.status_code == 200
    body = by_id.json()
    assert body["source"] == "local"
    assert body["invoice_number"] == "RIF-1"
    assert body["supplier_name"] == "Fornitore Rif Srl"
    assert body["rows"][0]["original_description"] == "LIMONCELLO 70CL"
    by_hash = client.get("/api/eye/invoice-ref/localhash-ref-1")
    assert by_hash.status_code == 200 and by_hash.json()["invoice_number"] == "RIF-1"


def test_invoice_ref_from_cache(client, db):
    payload = {"invoice_number": "C-9", "invoice_date": "2026-04-01", "supplier_name": "Cache Spa", "total": 30,
               "rows": [{"original_description": "CARTA IGIENICA", "quantity": 3, "unit_price": 10, "line_total": 30}]}
    db.add(CentralInvoiceCache(source_hash="cache-ref-1", invoice_number="C-9", invoice_date=date(2026, 4, 1), supplier_name="Cache Spa",
                               total=Decimal("30"), search_text="C-9", payload_json=json.dumps(payload)))
    db.commit()
    response = client.get("/api/eye/invoice-ref/cache-ref-1")
    assert response.status_code == 200
    assert response.json()["source"] == "cache"
    assert response.json()["rows"][0]["original_description"] == "CARTA IGIENICA"


def test_invoice_ref_central_when_not_local(client, monkeypatch):
    async def fake_detail(source_hash):
        return {"invoice_number": "R-1", "supplier_name": "Remoto", "rows": []}
    monkeypatch.setattr("app.routers.eye.central_invoice_detail", fake_detail)
    response = client.get("/api/eye/invoice-ref/remote-hash-xyz")
    assert response.status_code == 200
    assert response.json()["source"] == "central"


def test_invoice_ref_not_found(client, monkeypatch):
    async def boom(source_hash):
        raise RuntimeError("offline")
    monkeypatch.setattr("app.routers.eye.central_invoice_detail", boom)
    assert client.get("/api/eye/invoice-ref/does-not-exist").status_code == 404
    assert client.get("/api/eye/invoice-ref/999999").status_code == 404
