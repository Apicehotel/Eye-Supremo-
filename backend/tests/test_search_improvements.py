"""Ricerca prodotti (sinonimi, errori di battitura, archivio locale) e costruzione unica del report."""

from datetime import date

import pytest

from app.models import Product
from app.product_taxonomy import search_terms
from app.report_service import historical_product_report, report_from_entries
from tests.test_report_brand_and_canonical_match import _row


def test_multiword_search_terms_cover_every_word_in_the_first_terms():
    first = search_terms("bombolone choco")[:12]
    assert any("bombolon" in t for t in first)
    assert "cioccolato" in first  # i primi N termini bastano a coprire anche il sinonimo


def _add_products(db, *names):
    for name in names:
        db.add(Product(nome_canonico=name))
    db.commit()


def test_products_local_search_any_order_and_synonyms(client, db):
    _add_products(db, "Bombolone cioccolato 80 g", "Bombolone crema 80 g", "Detersivo piatti")
    for q in ("choco bombolone", "bombolone choco", "cioccolato bombolone"):
        names = [p["nome_canonico"] for p in client.get("/api/products", params={"q": q}).json()]
        assert names == ["Bombolone cioccolato 80 g"], q


def test_products_local_search_tolerates_typos(client, db):
    _add_products(db, "Marmellata fragola 350 g", "Detersivo piatti")
    names = [p["nome_canonico"] for p in client.get("/api/products", params={"q": "marmelata"}).json()]
    assert names == ["Marmellata fragola 350 g"]
    assert client.get("/api/products", params={"q": "zzzzqqqq"}).json() == []


def test_report_from_entries_groups_and_summarizes():
    entries = [
        {"supplier": "A", "unit": "pz", "date": "2026-02-01", "price": 1.2, "quantity": 5, "invoice": "2", "invoice_id": "h2", "description": "x"},
        {"supplier": "A", "unit": "pz", "date": "2026-01-01", "price": 1.0, "quantity": 5, "invoice": "1", "invoice_id": "h1", "description": "x"},
        {"supplier": "B", "unit": "pz", "date": "2026-01-15", "price": 0.9, "quantity": 1, "invoice": "3", "invoice_id": "h3", "description": "x"},
        {"supplier": "B", "unit": "pz", "date": "2026-01-16", "price": 0, "quantity": 1, "invoice": "4", "invoice_id": "h4", "description": "x"},
    ]
    report = report_from_entries("q", entries, product="X", manufacturer="Marca", note="n")
    summary = report["summary"]
    assert (summary["initial_price"], summary["latest_price"], summary["best_price"]) == (1.0, 1.2, 0.9)
    assert summary["best_supplier"] == "B" and summary["manufacturers"] == ["Marca"]
    block_a = next(b for b in report["suppliers"] if b["supplier"] == "A")
    assert [p["trend"] for p in block_a["points"]] == ["initial", "up"] and block_a["points"][1]["delta"] == 0.2
    assert report["dates"] == ["2026-01-01", "2026-01-15", "2026-02-01"] and report["units"] == ["pz"]
    assert report_from_entries("q", [], product="X", note="n") is None


def test_cache_failure_is_reported_not_hidden(db, monkeypatch):
    product = Product(nome_canonico="Succo Pago Ace", marca="Pago")
    db.add(product)
    db.flush()
    _row(db, product, "SUCCO ACE 200ML X24", 0.55, date(2026, 5, 2), "E-1")
    db.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("cache corrotta")

    monkeypatch.setattr("app.central_cache.cached_row_search", boom)
    report = historical_product_report(db, "pago")
    assert report["suppliers"], "le righe locali restano disponibili"
    assert "cache corrotta" in report["sources"]["cache_error"]


def test_normalization_config_defined_and_reads_settings(db):
    import json

    from app.models import AppSetting
    from app.routers.reports_eye import _normalization_config

    assert _normalization_config(db, ["Acqua"]) == (None, "pz")
    db.add(AppSetting(key="product_configs", value=json.dumps({"Acqua": {"pieces_per_pack": 6, "normalization_unit": "bott"}})))
    db.commit()
    assert _normalization_config(db, ["Altro", "Acqua"]) == (6.0, "bott")
