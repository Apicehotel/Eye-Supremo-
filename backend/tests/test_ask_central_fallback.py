"""Ask deve trovare bomboloni anche se sono solo in cache o su Supabase."""

import asyncio
import json
from datetime import date
from decimal import Decimal

from app.agent_orchestrator import _deterministic_answer, _product_context, _report_from_rows
from app.central_service import central_invoice_search
from app.models import CentralInvoiceCache


def test_report_from_rows_picks_cheapest_supplier():
    report = _report_from_rows(
        [
            {"supplier": "La Mar", "unit_price": 1.2, "date": "2025-01-01", "description": "MINIBOMBOLONI"},
            {"supplier": "Lasaria", "unit_price": 0.8, "date": "2025-02-01", "description": "Bomboloni"},
            {"supplier": "Salaria", "unit_price": 0.95, "date": "2025-03-01", "description": "mini bomboloni"},
        ],
        "bomboloni",
    )
    assert report is not None
    assert report["summary"]["best_supplier"] == "Lasaria"
    assert len(report["suppliers"]) == 3


def test_ask_uses_cache_when_local_invoices_empty(db):
    for idx, (supplier, desc, price) in enumerate(
        [
            ("La Mar", "MINIBOMBOLONI CREMA", 1.1),
            ("Lasaria", "Bomboloni classici", 0.8),
            ("Salaria", "mini bomboloni", 0.95),
        ]
    ):
        payload = {
            "rows": [
                {
                    "original_description": desc,
                    "normalized_description": desc.lower(),
                    "quantity": 1,
                    "unit_price": price,
                    "line_total": price,
                    "analysis_status": "product",
                }
            ]
        }
        db.add(
            CentralInvoiceCache(
                source_hash=f"ask-cache-{idx}",
                invoice_number=f"C-{idx}",
                invoice_date=date(2025, 4, 1 + idx),
                supplier_name=supplier,
                total=Decimal(str(price)),
                search_text=f"C-{idx} {supplier} {desc}",
                payload_json=json.dumps(payload),
            )
        )
    db.commit()

    context = asyncio.run(_product_context("Chi mi vende meglio i bomboloni?", "developer"))
    assert context["match_total"] >= 3
    assert context["supplier_count"] >= 3
    assert any("mini" in str(r.get("description") or "").lower() for r in context["invoice_rows"])
    answer = _deterministic_answer(
        "Chi mi vende meglio i bomboloni?",
        context,
        {"ok": True, "warnings": []},
    )
    assert answer is not None
    assert "Lasaria" in answer["answer"]
    assert "Altri fornitori" in answer["answer"]


def test_ask_falls_back_to_supabase_when_cache_empty(db, monkeypatch):
    async def fake_central(query: str, limit: int = 50):
        assert "bomboloni" in query.lower() or extract_ok(query)
        return {
            "enabled": True,
            "items": [
                {
                    "id": "s1",
                    "source_hash": "s1",
                    "invoice_number": "S-1",
                    "invoice_date": "2025-05-01",
                    "supplier_name": "Lasaria",
                    "original_description": "BOMBOLONI CREMA",
                    "normalized_description": "bomboloni crema",
                    "quantity": 1,
                    "unit_price": 0.75,
                    "line_total": 0.75,
                },
                {
                    "id": "s2",
                    "source_hash": "s2",
                    "invoice_number": "S-2",
                    "invoice_date": "2025-05-02",
                    "supplier_name": "La Mar",
                    "original_description": "MINIBOMBOLONI",
                    "normalized_description": "minibomboloni",
                    "quantity": 1,
                    "unit_price": 1.0,
                    "line_total": 1.0,
                },
            ],
            "count": 2,
        }

    def extract_ok(query: str) -> bool:
        from app.product_taxonomy import extract_product_query
        return extract_product_query(query) == "bomboloni"

    monkeypatch.setattr("app.agent_orchestrator.central_configured", lambda: True)
    monkeypatch.setattr("app.agent_orchestrator.central_invoice_search", fake_central)

    context = asyncio.run(_product_context("Chi mi vende meglio i bomboloni?", "developer"))
    assert context["match_total"] >= 2
    assert "supabase" in (context.get("data_sources") or [])
    answer = _deterministic_answer(
        "Chi mi vende meglio i bomboloni?",
        context,
        {"ok": True, "warnings": []},
    )
    assert answer is not None
    assert "Lasaria" in answer["answer"]


def test_central_invoice_search_uses_product_needle(monkeypatch):
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, items):
            self._items = items
            self.is_success = True

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": self._items}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            q = (json or {}).get("query", "")
            calls.append(q)
            if q.lower() in {"bomboloni", "minibomboloni", "mini bomboloni", "bombolone"}:
                return FakeResponse([{
                    "id": "1",
                    "original_description": "Bomboloni",
                    "supplier_name": "Lasaria",
                    "unit_price": 1,
                    "line_total": 1,
                }])
            return FakeResponse([])

    monkeypatch.setattr("app.central_service.configured", lambda: True)
    monkeypatch.setattr("app.central_service.settings.supabase_url", "https://example.test")
    monkeypatch.setattr("app.central_service.settings.supabase_publishable_key", "key")
    monkeypatch.setattr("app.central_service.settings.central_username", "u")
    monkeypatch.setattr("app.central_service.settings.central_pin", "000000")
    monkeypatch.setattr("app.central_service.settings.central_function", "eye")
    monkeypatch.setattr("app.central_service.httpx.AsyncClient", FakeClient)

    result = asyncio.run(central_invoice_search("Chi mi vende meglio i bomboloni?", limit=20))
    assert result["count"] >= 1
    assert any(c.lower() == "bomboloni" for c in calls)
    assert not any(c.lower().startswith("chi ") for c in calls)
