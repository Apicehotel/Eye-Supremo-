"""Varianti prodotto (mini bomboloni) e diversità fornitori in ricerca + Ask."""

import asyncio
import json
from datetime import date
from decimal import Decimal

from app.agent_orchestrator import _deterministic_answer, _product_context
from app.central_cache import cached_row_search
from app.models import CentralInvoiceCache, Invoice, InvoiceRow, InvoiceRowPolicy, Supplier
from app.product_taxonomy import extract_product_query, product_stem, search_terms
from app.report_service import historical_product_report
from app.search_index import invoice_search, invoice_search_page


def _add_row(db, supplier, number, when, price, desc):
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
        unita_normalizzata="pz",
        prezzo_unitario=price,
        totale_riga=price,
        confidence=1,
    )
    db.add(row)
    db.flush()
    db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="product"))
    return row


def test_taxonomy_includes_mini_bomboloni_variants():
    assert extract_product_query("Chi mi vende i bomboloni?") == "bomboloni"
    assert product_stem("bomboloni") == "bombolon"
    terms = search_terms("bomboloni")
    assert "minibomboloni" in terms
    assert "mini bomboloni" in terms


def test_live_search_finds_mini_and_compound_bomboloni(db):
    s1 = Supplier(ragione_sociale="La Mar")
    s2 = Supplier(ragione_sociale="Lasaria")
    s3 = Supplier(ragione_sociale="Fornitore Dominante")
    db.add_all([s1, s2, s3])
    db.flush()
    # Un fornitore molto frequente non deve nascondere gli altri / le varianti.
    for i in range(30):
        _add_row(db, s3, f"DOM-{i}", date(2025, 1, 1 + (i % 28)), Decimal("1.10"), f"BOMBOLONI CREMA X12 lotto {i}")
    _add_row(db, s1, "MM-1", date(2024, 6, 1), Decimal("0.95"), "MINIBOMBOLONI CREMA")
    _add_row(db, s2, "LS-1", date(2024, 5, 1), Decimal("0.88"), "mini bomboloni vuoti")
    db.commit()

    rows = invoice_search(db, "bomboloni", limit=None)
    descriptions = " ".join(r["description"].lower() for r in rows)
    assert "minibomboloni" in descriptions
    assert "mini bomboloni" in descriptions

    page = invoice_search_page(db, "bomboloni", limit=12, offset=0)
    assert page["total"] >= 32
    assert page["supplier_count"] >= 3
    page_suppliers = {r["supplier"] for r in page["results"]}
    # Prima pagina diversificata: almeno 2 fornitori, non solo il dominante.
    assert len(page_suppliers) >= 2
    assert "Fornitore Dominante" in page_suppliers


def test_live_search_excludes_bombola_gas(db):
    s = Supplier(ragione_sociale="Tech Gas")
    db.add(s)
    db.flush()
    _add_row(db, s, "G-1", date(2025, 1, 1), Decimal("40"), "BOMBOLA GAS 10KG")
    _add_row(db, s, "B-1", date(2025, 1, 2), Decimal("1"), "Bombolone crema")
    db.commit()
    rows = invoice_search(db, "bomboloni", limit=None)
    assert rows
    assert all("bombola" not in r["description"].lower() for r in rows)


def test_cached_row_search_finds_minibomboloni_and_many_suppliers(db):
    for idx, (supplier, desc) in enumerate(
        [
            ("La Mar", "MINIBOMBOLONI CREMA"),
            ("Lasaria", "Bomboloni classici"),
            ("Salaria Forno", "mini bomboloni"),
            ("Dominante Spa", "BOMBOLONI CREMA X12"),
        ]
    ):
        payload = {
            "rows": [
                {
                    "original_description": desc,
                    "normalized_description": desc.lower(),
                    "quantity": 1,
                    "unit_price": 1.0 + idx * 0.1,
                    "line_total": 1.0 + idx * 0.1,
                    "analysis_status": "product",
                }
            ]
        }
        db.add(
            CentralInvoiceCache(
                source_hash=f"mini-{idx}",
                invoice_number=f"N-{idx}",
                invoice_date=date(2025, 3, 1 + idx),
                supplier_name=supplier,
                total=Decimal("1"),
                search_text=f"N-{idx} {supplier} {desc}",
                payload_json=json.dumps(payload),
            )
        )
    db.commit()

    page = cached_row_search(db, "bomboloni", limit=10)
    descs = " ".join(str(i.get("original_description") or "").lower() for i in page["items"])
    assert "minibomboloni" in descs
    assert page["supplier_count"] >= 3
    assert len({i["supplier_name"] for i in page["items"][:4]}) >= 2


def test_historical_report_includes_mini_and_lists_suppliers(db):
    s1 = Supplier(ragione_sociale="La Mar")
    s2 = Supplier(ragione_sociale="Lasaria")
    db.add_all([s1, s2])
    db.flush()
    _add_row(db, s1, "A1", date(2025, 1, 1), Decimal("1.20"), "MINIBOMBOLONI")
    _add_row(db, s2, "A2", date(2025, 2, 1), Decimal("0.90"), "Bomboloni crema")
    db.commit()
    report = historical_product_report(db, "bomboloni")
    names = {b["supplier"] for b in report["suppliers"]}
    assert names == {"La Mar", "Lasaria"}
    assert report["summary"]["best_supplier"] == "Lasaria"


def test_ask_lists_multiple_suppliers_in_deterministic_answer(db):
    s1 = Supplier(ragione_sociale="La Mar")
    s2 = Supplier(ragione_sociale="Lasaria")
    s3 = Supplier(ragione_sociale="Salaria")
    db.add_all([s1, s2, s3])
    db.flush()
    _add_row(db, s1, "M1", date(2025, 1, 1), Decimal("1.10"), "MINIBOMBOLONI")
    _add_row(db, s2, "L1", date(2025, 2, 1), Decimal("0.80"), "Bomboloni")
    _add_row(db, s3, "S1", date(2025, 3, 1), Decimal("0.95"), "mini bomboloni")
    db.commit()

    context = asyncio.run(_product_context("Chi mi vende meglio i bomboloni?", "developer"))
    assert context.get("supplier_count", 0) >= 3
    assert any("mini" in str(r.get("description") or "").lower() for r in context.get("invoice_rows") or [])
    answer = _deterministic_answer(
        "Chi mi vende meglio i bomboloni?",
        context,
        {"ok": True, "warnings": []},
    )
    assert answer is not None
    assert "Lasaria" in answer["answer"]
    # Non solo il migliore: devono comparire altri fornitori.
    assert "La Mar" in answer["answer"] or "Salaria" in answer["answer"]
    assert "Altri fornitori" in answer["answer"]
