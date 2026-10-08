import json
from datetime import date
from decimal import Decimal

from app.central_cache import cached_row_search
from app.models import CentralInvoiceCache


def _seed_cache(db):
    payload = {
        "source_hash": "hash-bomboloni",
        "source_filename": "fattura.xml",
        "invoice_number": "B-10",
        "invoice_date": "2026-03-01",
        "supplier_name": "Forno Locale",
        "rows": [
            {
                "original_description": "BOMBOLONI CREMA X12",
                "normalized_description": "bomboloni crema x12",
                "quantity": 2,
                "unit_price": 8.5,
                "line_total": 17.0,
                "analysis_status": "product",
            },
            {
                "original_description": "BOMBOLA GAS 10KG",
                "normalized_description": "bombola gas 10kg",
                "quantity": 1,
                "unit_price": 40,
                "line_total": 40,
                "analysis_status": "product",
            },
        ],
    }
    db.add(
        CentralInvoiceCache(
            source_hash="hash-bomboloni",
            invoice_number="B-10",
            invoice_date=date(2026, 3, 1),
            supplier_name="Forno Locale",
            total=Decimal("57"),
            search_text="B-10 Forno Locale BOMBOLONI CREMA X12 BOMBOLA GAS 10KG",
            payload_json=json.dumps(payload),
        )
    )
    db.commit()


def test_cached_row_search_finds_product_rows_locally(db):
    _seed_cache(db)
    page = cached_row_search(db, "bomboloni crema", limit=10)
    rows = page["items"]
    assert rows
    assert page["total"] >= 1
    assert page.get("scope") == "full-cache-unlimited"
    assert all(item.get("local_cache") for item in rows)
    assert any("BOMBOLONI" in str(item.get("original_description") or "").upper() for item in rows)
    assert not any("BOMBOLA GAS" in str(item.get("original_description") or "").upper() for item in rows)


def test_cached_row_search_understands_natural_language(db):
    _seed_cache(db)
    page = cached_row_search(db, "Chi mi vende meglio i bomboloni?", limit=10)
    assert page["total"] >= 1
    assert any("BOMBOLONI" in str(item.get("original_description") or "").upper() for item in page["items"])


def test_central_invoices_prefers_sqlite_cache_over_supabase(client, db, monkeypatch):
    _seed_cache(db)
    called = {"supabase": 0}

    async def boom(*_args, **_kwargs):
        called["supabase"] += 1
        return {"enabled": True, "items": [], "message": "should-not-call"}

    monkeypatch.setattr("app.routers.eye.central_invoice_search", boom)
    response = client.get("/api/eye/central/invoices", params={"q": "bomboloni"})
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("source") == "sqlite-cache"
    assert payload.get("count", 0) >= 1
    assert payload.get("total", 0) >= 1
    assert called["supabase"] == 0


def test_live_search_accepts_large_page_size(client, db):
    """La UI usa pageSize fino a 150: non deve più fallire con 422."""
    response = client.get("/api/eye/search/live", params={"q": "bomboloni", "limit": 150})
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("engine") == "fts5+rapidfuzz"
    assert payload.get("scope") == "full-archive-unlimited"


def test_live_search_has_no_hidden_archive_cap(client, db):
    """total riflette tutti i match, non un tetto interno (es. 500/2000)."""
    from datetime import date
    from decimal import Decimal
    from app.models import Invoice, InvoiceRow, InvoiceRowPolicy, Supplier

    supplier = Supplier(ragione_sociale="Archivio Esteso")
    db.add(supplier)
    db.flush()
    for i in range(120):
        inv = Invoice(
            supplier_id=supplier.id,
            numero=f"EXT-{i}",
            data=date(2015 + (i % 10), 1 + (i % 12), 1),
            imponibile=1,
            iva=0,
            totale=1,
        )
        db.add(inv)
        db.flush()
        row = InvoiceRow(
            invoice_id=inv.id,
            descrizione_originale=f"Bombolone crema lotto {i}",
            descrizione_normalizzata=f"bombolone crema lotto {i}",
            quantita=1,
            prezzo_unitario=1,
            totale_riga=1,
            confidence=1,
        )
        db.add(row)
        db.flush()
        db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="product"))
    db.commit()

    response = client.get("/api/eye/search/live", params={"q": "bomboloni", "limit": 10, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 120
    assert payload["count"] == 10
    assert payload["summary"]["rows"] >= 120
    assert len(payload["results"]) == 10
