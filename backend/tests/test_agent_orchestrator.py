import asyncio
import json
from datetime import date
from decimal import Decimal

from app.agent_orchestrator import (
    AGENTS,
    _compact_for_llm,
    _deterministic_answer,
    _needs_price_history,
    _product_context,
    _review_context,
    classify_intent,
)
from app.models import CentralInvoiceCache, CentralReviewCache, Hotel


def test_router_sends_price_question_to_product_price_and_verifier():
    plan = classify_intent("Chi mi vende meglio i bomboloni e qual è il prezzo medio?")
    assert plan[:2] == ["products", "prices"]
    assert plan[-2:] == ["verifier", "answer"]


def test_router_sends_review_question_to_reviews():
    plan = classify_intent("Quali sono le camere con le recensioni peggiori?")
    assert plan[0] == "reviews"
    assert "products" not in plan


def test_ask_default_area_includes_reviews_for_ambiguous_questions():
    plan = classify_intent("Cosa risulta dall'archivio?", area="all")
    assert "products" in plan
    assert "reviews" in plan


def test_ask_invoices_area_skips_reviews():
    plan = classify_intent("Quanto abbiamo speso per limoncello?", area="invoices")
    assert "products" in plan
    assert "prices" in plan
    assert "invoices" in plan
    assert "reviews" not in plan


def test_ask_invoices_area_ignores_review_words():
    plan = classify_intent("Quanto costa la colazione in fattura?", area="invoices")
    assert "products" in plan
    assert "reviews" not in plan


def test_ask_review_area_forces_reviews_agent():
    plan = classify_intent("Fammi un riepilogo", area="reviews")
    assert plan[0] == "reviews"
    assert "products" not in plan


def test_better_rooms_do_not_trigger_product_agent():
    plan = classify_intent("Quali sono le 5 camere migliori?")
    assert "reviews" in plan
    assert "products" not in plan


def test_agent_registry_is_small_and_specialized():
    assert {"router", "products", "classifier", "invoices", "prices", "reviews", "verifier", "answer"} == set(AGENTS)
    assert all(spec.tools for spec in AGENTS.values())


def test_agent_registry_endpoint(client):
    response = client.get("/api/eye/agents/registry")
    assert response.status_code == 200
    payload = response.json()
    assert any(x["name"] == "verifier" for x in payload)
    assert any(x["name"] == "products" for x in payload)


def test_ask_endpoint_accepts_reviews_area(client, db):
    hotel = db.query(Hotel).filter(Hotel.code == "gio").one()
    db.add(CentralReviewCache(
        sync_uuid="ask-area-rev",
        hotel_code="gio",
        review_date=date(2026, 6, 1),
        source="Booking",
        author="Luca",
        rating=Decimal("7.5"),
        room_code="12",
        text="Colazione scarsa ma staff gentile",
        payload_json="{}",
    ))
    db.commit()
    response = client.post(
        "/api/eye/agents/ask",
        json={"question": "Come è la colazione?", "area": "reviews", "hotel_code": "gio"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "reviews" in payload.get("plan", [])
    assert payload.get("context", {}).get("reviews")


def test_compact_context_limits_rows_and_text():
    compact = _compact_for_llm({
        "invoice_rows": [
            {"description": "x" * 400, "supplier": "A", "unit_price": 1, "invoice": "1", "date": "2024-01-01"}
            for _ in range(30)
        ],
        "invoice_summary": {"rows": 30, "invoices": 3, "row_total": 10},
        "reviews": [{"text": "y" * 500, "hotel": "Giò"} for _ in range(20)],
    })
    assert len(compact["invoice_rows"]) <= 12
    assert len(compact["invoice_rows"][0]["description"]) <= 140
    assert len(compact["reviews"]) <= 8
    assert len(compact["reviews"][0]["text"]) <= 220


def test_deterministic_short_circuit_for_max_invoice():
    result = _deterministic_answer(
        "Qual è la fattura con il totale più alto?",
        {
            "max_invoice": {
                "invoice_number": "42",
                "supplier_name": "Acme",
                "invoice_date": "2024-05-01",
                "total": 999.5,
            }
        },
        {"ok": True, "warnings": []},
    )
    assert result is not None
    assert "42" in result["answer"]
    assert result["confidence"] == "high"


def test_price_history_gate_skips_heavy_report_for_plain_lookup():
    assert _needs_price_history("Chi mi vende meglio i bomboloni?") is True
    assert _needs_price_history("mostra solo il codice fattura XYZ") is False


def test_product_context_uses_local_cache_not_supabase(db, monkeypatch):
    payload = {
        "rows": [{
            "original_description": "ACQUA NATURALE 1.5L",
            "normalized_description": "acqua naturale 1.5l",
            "quantity": 10,
            "unit_price": 0.4,
            "line_total": 4.0,
            "analysis_status": "product",
        }]
    }
    db.add(CentralInvoiceCache(
        source_hash="cache-acqua",
        invoice_number="A-1",
        invoice_date=date(2026, 2, 1),
        supplier_name="Acqua Spa",
        total=Decimal("4"),
        search_text="A-1 Acqua Spa ACQUA NATURALE 1.5L",
        payload_json=json.dumps(payload),
    ))
    db.commit()

    async def boom(*_a, **_k):
        raise AssertionError("Ask non deve chiamare Supabase se la cache locale ha dati")

    monkeypatch.setattr("app.central_service.central_invoice_search", boom)
    context = asyncio.run(_product_context("acqua naturale", "developer"))
    assert context["invoice_rows"]
    assert context["invoice_rows"][0]["source"] == "sqlite-cache"
    assert "ACQUA" in str(context["invoice_rows"][0]["description"]).upper()


def test_review_context_uses_local_review_cache(db, monkeypatch):
    hotel = db.query(Hotel).filter(Hotel.code == "choco").one()
    db.add(CentralReviewCache(
        sync_uuid="ask-rev-1",
        hotel_code="choco",
        review_date=date(2026, 5, 1),
        source="Google",
        author="Anna",
        rating=Decimal("4.0"),
        room_code="205",
        text="Staff gentile ma pulizia insufficiente",
        payload_json="{}",
    ))
    db.commit()

    async def boom(*_a, **_k):
        raise AssertionError("Ask recensioni non deve chiamare Supabase")

    monkeypatch.setattr("app.central_service.central_review_page", boom)
    context = _review_context("pulizia staff", hotel_id=hotel.id)
    assert context["reviews"]
    assert context["reviews"][0]["source_origin"] == "sqlite-cache"
    assert "pulizia" in context["reviews"][0]["text"].lower()
