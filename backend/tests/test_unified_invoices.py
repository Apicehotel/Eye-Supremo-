"""Test lista fatture unificata PC + Supabase."""


def test_unified_local_only(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_central_pin", None)
    res = client.get("/api/invoices")
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert body["central_configured"] is False
    assert isinstance(body["items"], list)


def test_unified_merges_central(client, monkeypatch):
    from app.config import settings
    from app import storage_service

    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-test")
    monkeypatch.setattr(settings, "supabase_central_pin", "123456")

    def fake_page(*, limit=50, offset=0, since=None, username=None, pin=None):
        return {
            "items": [
                {
                    "id": "abc-1",
                    "invoice_number": "CENTRALE/1",
                    "invoice_date": "2024-06-01",
                    "supplier_name": "Fornitore Cloud Spa",
                    "total": 12.5,
                    "currency": "EUR",
                    "source_hash": "aaa",
                    "source_filename": "a.xml",
                }
            ],
            "total": 20638,
            "limit": limit,
            "offset": offset,
        }

    monkeypatch.setattr(storage_service, "central_invoice_page", fake_page)
    res = client.get("/api/invoices?include_central=true")
    assert res.status_code == 200
    body = res.json()
    assert body["central_configured"] is True
    assert body["central_total"] == 20638
    assert body["central_count"] >= 1
    assert any(i.get("source") == "central" and i.get("numero") == "CENTRALE/1" for i in body["items"])


def test_dashboard_exposes_central_flag(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_central_pin", None)
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    body = res.json()
    assert "central_configured" in body
    assert "central_invoices" in body["kpis"]
