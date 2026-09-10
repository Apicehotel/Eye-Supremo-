from decimal import Decimal
from app.normalization import normalize_text, normalize_unit, normalized_price

def test_unit_variants():
    assert normalize_unit("KG.")[0] == "kg"
    assert normalize_unit("gr") == ("kg", Decimal("0.001"))
    assert normalize_unit("LTR")[0] == "l"
    assert normalize_unit("PCS")[0] == "pz"

def test_price_to_base_unit():
    unit, price = normalized_price(Decimal("9"), Decimal("2"), "kg")
    assert unit == "kg" and price == Decimal("9")
    unit, price = normalized_price(Decimal("0.45"), Decimal("500"), "g")
    assert unit == "kg" and price == Decimal("450")

def test_product_text():
    assert normalize_text("LAMPADINA LED E27 10 W") == "lampadina led e27 10 w"
