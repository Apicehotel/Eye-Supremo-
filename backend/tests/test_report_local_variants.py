from datetime import date

from app.models import Product
from app.report_service import historical_product_report, local_variant_matches
from tests.test_report_brand_and_canonical_match import _row


def test_family_with_different_flavors_and_sizes_offers_variants(db):
    product = Product(nome_canonico="Marmellata")
    db.add(product)
    db.flush()
    _row(db, product, "MARM. ARANCE 25GX100", 0.10, date(2026, 5, 1), "V-1")
    _row(db, product, "CONFETTURA FRAGOLE 350 G", 2.50, date(2026, 5, 2), "V-2")
    _row(db, product, "CONFETTURA FRAGOLE 350 G", 2.60, date(2026, 6, 2), "V-3")
    db.commit()

    matches = local_variant_matches(historical_product_report(db, "marmellata"))
    assert {(m["flavor"], m["content_label"]) for m in matches} == {("arancia", "25 g"), ("fragola", "350 g")}
    fragola = next(m for m in matches if m["flavor"] == "fragola")
    assert fragola["purchases"] == 2 and fragola["canonical_name"] == "CONFETTURA FRAGOLE 350 G"


def test_single_variant_keeps_normal_report(db):
    product = Product(nome_canonico="Marmellata")
    db.add(product)
    db.flush()
    _row(db, product, "CONFETTURA FRAGOLE 350 G", 2.50, date(2026, 5, 2), "W-1")
    _row(db, product, "CONFETTURA FRAGOLE 350 G", 2.60, date(2026, 6, 2), "W-2")
    db.commit()

    assert local_variant_matches(historical_product_report(db, "marmellata")) == []
