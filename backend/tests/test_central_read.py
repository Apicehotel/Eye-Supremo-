"""Test lettura catalogo centrale (gateway + unificazione)."""
from unittest.mock import patch

import httpx


def test_central_read_via_gateway(client, monkeypatch):
    from app.config import settings
    from app import storage_service

    monkeypatch.setattr(
        settings,
        "supabase_central_gateway",
        "https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway",
    )
    monkeypatch.setattr(settings, "supabase_central_gateway_action", "invoice_page")
    monkeypatch.setattr(settings, "supabase_central_pin", "pin-test")
    monkeypatch.setattr(settings, "supabase_central_username", "sviluppatore")
    monkeypatch.setattr(settings, "supabase_url", "https://ooqlfldcrnkudhgjnied.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-test")
    monkeypatch.setattr(settings, "supabase_service_key", None)

    def fake_post(url, json=None, headers=None, **kwargs):
        assert "eye-central-gateway" in str(url)
        assert json["username"] == "sviluppatore"
        assert json["pin"] == "pin-test"
        assert json["action"] == "invoice_page"
        req = httpx.Request("POST", str(url))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "inv-1",
                        "invoice_number": "42/A",
                        "invoice_date": "2024-01-15",
                        "supplier_name": "Alpha Spa",
                        "total": 100.0,
                        "currency": "EUR",
                        "source_hash": "abc123",
                    }
                ],
                "total": 20638,
                "limit": json.get("limit", 50),
                "offset": json.get("offset", 0),
            },
            request=req,
        )

    with patch("httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.post.side_effect = fake_post
        page = storage_service.central_invoice_page(limit=10, offset=0)

    assert page["total"] == 20638
    assert len(page["items"]) == 1
    assert page["items"][0]["invoice_number"] == "42/A"


def test_invoices_api_reads_central(client, monkeypatch):
    from app.config import settings
    from app import storage_service

    monkeypatch.setattr(
        settings,
        "supabase_central_gateway",
        "https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway",
    )
    monkeypatch.setattr(settings, "supabase_central_pin", "pin-test")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon")

    def fake_page(**_kwargs):
        return {
            "items": [
                {
                    "id": "c1",
                    "invoice_number": "SUPA/9",
                    "invoice_date": "2025-03-01",
                    "supplier_name": "Beta Srl",
                    "total": 55.5,
                    "source_hash": "hhh",
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr(storage_service, "central_invoice_page", fake_page)
    res = client.get("/api/invoices?include_central=true")
    assert res.status_code == 200
    body = res.json()
    assert body["central_configured"] is True
    assert any(i["numero"] == "SUPA/9" and i["source"] == "central" for i in body["items"])


def test_live_gateway_requires_pin():
    """Smoke live: senza PIN il gateway rifiuta (rete reale)."""
    import httpx

    url = "https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway"
    res = httpx.post(
        url,
        json={"action": "invoice_page", "username": "sviluppatore", "pin": "WRONG", "limit": 1},
        timeout=30,
    )
    # 200 con error JSON oppure 401
    assert res.status_code in {200, 401}
    data = res.json()
    assert "error" in data
