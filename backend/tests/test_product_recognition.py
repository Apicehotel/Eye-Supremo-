from app.product_recognition import annotate, recognize


def test_food_with_brand_and_origin():
    r = recognize("BANANE CHIQUITA PROV. ECUADOR")
    assert r["kind"] == "food" and r["category"] == "Frutta" and r["brand"] == "Chiquita" and r["origin"] == "Ecuador"


def test_typical_italian_products_without_off_entry():
    assert recognize("BOMBOLINI CREMA")["subcategory"] == "Bomboloni"
    assert recognize("MOZZARELLA GRIFO 125G")["category"] == "Latticini e formaggi"


def test_non_food_lines():
    assert recognize("IMPOSTA DI BOLLO")["kind"] == "non_food"
    assert recognize("SPESA PER L ENERGIA ELETTRICA")["category"] == "Energia e utenze"
    assert recognize("NASTRO ADESIVO")["category"] == "Materiali e attrezzature"


def test_never_raises_and_unknown():
    assert recognize(None)["kind"] == "unknown"
    assert recognize("xqzwv")["kind"] == "unknown"


def test_annotate_adds_field():
    items = annotate([{"nome_canonico": "LATTE INTERO 1L"}])
    assert "recognition" in items[0]


def test_nonfood_taxonomy_gives_subcategory():
    r = recognize("SHAMPOO 500ML")
    assert r["kind"] == "non_food" and r["category"] == "Pulizia e igiene" and r["subcategory"] == "Shampoo"
    assert recognize("SIGARETTE")["category"] == "Tabacchi"


def test_accounting_lines_not_overridden_by_taxonomy():
    assert recognize("IMPOSTA DI BOLLO")["category"] == "Imposte e voci contabili"
