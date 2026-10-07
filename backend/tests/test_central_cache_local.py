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
    rows = cached_row_search(db, "bomboloni crema", limit=10)
    assert rows
    assert all(item.get("local_cache") for item in rows)
    assert any("BOMBOLONI" in str(item.get("original_description") or "").upper() for item in rows)
    assert not any("BOMBOLA GAS" in str(item.get("original_description") or "").upper() for item in rows)


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
    assert called["supabase"] == 0
