"""Ogni riga prodotto in fattura deve essere cercabile e confrontabile tra fornitori."""

import asyncio
import json
from datetime import date
from decimal import Decimal

from app.agent_orchestrator import _deterministic_answer, _product_context
from app.models import CentralInvoiceCache, Invoice, InvoiceRow, InvoiceRowPolicy, Supplier
from app.product_taxonomy import (
    description_matches_product,
    extract_product_query,
    product_stem,
    row_matches_product_query,
    search_terms,
)
from app.search_index import invoice_search, invoice_search_page


def _add_row(db, supplier, number, when, price, desc, unit="pz"):
    inv = Invoice(
        supplier_id=supplier.id,
        numero=number,
        data=when,
        imponibile=price,
        iva=0,
        totale=price,
    )
    db.add(inv)
    db.flush()
    row = InvoiceRow(
        invoice_id=inv.id,
        descrizione_originale=desc,
        descrizione_normalizzata=desc.lower(),
        quantita=1,
        unita_normalizzata=unit,
        prezzo_unitario=price,
        totale_riga=price,
        confidence=1,
    )
    db.add(row)
    db.flush()
    db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="product"))
    return row


def test_taxonomy_works_for_products_outside_alias_table():
    assert extract_product_query("Chi mi vende meglio il limoncello?") == "limoncello"
    assert extract_product_query("Quanto costa il detergente pavimenti?") == "detergente pavimenti"
    assert "limoncello" in search_terms("limoncello")
    assert product_stem("limoncello")  # stem generico per composti
    assert description_matches_product("MINILIMONCELLO 20CL", "limoncello")
    assert description_matches_product("DETERGENTE PAVIMENTI LT 5", "detergente pavimenti")
    assert row_matches_product_query("BOMBOLA GAS", "bomboloni") is False
    assert row_matches_product_query("LIMONCELLO IGP", "limoncello") is True


def test_live_search_and_compare_limoncello_across_suppliers(db):
    s1 = Supplier(ragione_sociale="Distilleria A")
    s2 = Supplier(ragione_sociale="Distilleria B")
    s3 = Supplier(ragione_sociale="Cash & Carry")
    db.add_all([s1, s2, s3])
    db.flush()
    for i in range(20):
        _add_row(db, s3, f"CC-{i}", date(2025, 1, 1 + (i % 28)), Decimal("8.50"), f"LIMONCELLO 70CL lotto {i}")
    _add_row(db, s1, "A-1", date(2024, 6, 1), Decimal("7.20"), "MINILIMONCELLO 20CL")
    _add_row(db, s2, "B-1", date(2024, 7, 1), Decimal("6.90"), "Limoncello artigianale")
    db.commit()

    page = invoice_search_page(db, "limoncello", limit=10, offset=0)
    assert page["total"] >= 22
    assert page["supplier_count"] >= 3
    assert len({r["supplier"] for r in page["results"]}) >= 2

    context = asyncio.run(_product_context("Chi mi vende meglio il limoncello?", "developer"))
    assert context["match_total"] >= 22
    assert context["supplier_count"] >= 3
    assert context.get("historical_product", {}).get("summary", {}).get("best_supplier") == "Distilleria B"
    answer = _deterministic_answer(
        "Chi mi vende meglio il limoncello?",
        context,
        {"ok": True, "warnings": []},
    )
    assert answer is not None
    assert "Distilleria B" in answer["answer"]
    assert "Distilleria A" in answer["answer"] or "Cash" in answer["answer"]


def test_ask_compares_any_product_not_only_best_supplier_phrase(db):
    """Anche una domanda semplice sul prodotto deve confrontare i fornitori."""
    s1 = Supplier(ragione_sociale="Pulito Spa")
    s2 = Supplier(ragione_sociale="Igiene Srl")
    db.add_all([s1, s2])
    db.flush()
    _add_row(db, s1, "P1", date(2025, 1, 1), Decimal("12.0"), "DETERGENTE PAVIMENTI LT5")
    _add_row(db, s2, "I1", date(2025, 2, 1), Decimal("9.5"), "detergente per pavimenti")
    db.commit()

    context = asyncio.run(_product_context("detergente pavimenti", "developer"))
    assert context["match_total"] >= 2
    assert context["supplier_count"] >= 2
    assert context.get("historical_product", {}).get("summary")
    answer = _deterministic_answer(
        "detergente pavimenti",
        context,
        {"ok": True, "warnings": []},
    )
    assert answer is not None
    assert "Igiene" in answer["answer"]
    assert "confrontato" in answer["answer"].lower() or "fornitori" in answer["answer"].lower()


def test_cache_rows_for_arbitrary_products_feed_ask(db):
    for idx, (supplier, desc, price) in enumerate(
        [
            ("Alpha", "CARTA IGIENICA 2 VELI", 18.0),
            ("Beta", "c igienica fascettata", 15.5),
            ("Gamma", "CARTA IGIENICA MAXI", 16.0),
        ]
    ):
        payload = {
            "rows": [{
                "original_description": desc,
                "normalized_description": desc.lower(),
                "quantity": 1,
                "unit_price": price,
                "line_total": price,
                "analysis_status": "product",
            }]
        }
        db.add(
            CentralInvoiceCache(
                source_hash=f"carta-{idx}",
                invoice_number=f"CI-{idx}",
                invoice_date=date(2025, 3, 1 + idx),
                supplier_name=supplier,
                total=Decimal(str(price)),
                search_text=f"CI-{idx} {supplier} {desc}",
                payload_json=json.dumps(payload),
            )
        )
    db.commit()

    context = asyncio.run(_product_context("Quanto costa la carta igienica?", "developer"))
    assert context["match_total"] >= 3
    assert context["supplier_count"] >= 3
    answer = _deterministic_answer(
        "Quanto costa la carta igienica?",
        context,
        {"ok": True, "warnings": []},
    )
    assert answer is not None
    assert "Beta" in answer["answer"]


def test_search_still_excludes_bombola_when_asking_bomboloni(db):
    s = Supplier(ragione_sociale="Misto")
    db.add(s)
    db.flush()
    _add_row(db, s, "G1", date(2025, 1, 1), Decimal("40"), "BOMBOLA GAS 10KG")
    _add_row(db, s, "B1", date(2025, 1, 2), Decimal("1"), "Bomboloni crema")
    db.commit()
    rows = invoice_search(db, "bomboloni", limit=None)
    assert rows
    assert all("bombola" not in r["description"].lower() or "bombolon" in r["description"].lower() for r in rows)
