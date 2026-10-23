from app.deterministic_product_search import product_score, rank_products


def test_smart_box_description():
    assert product_score("trova SMART BOX 1814", "SMART BOX detergente eco bag 12 kg 1814") > 0.9


def test_different_code_not_mistaken_for_same_product():
    assert product_score("SMART BOX 1814", "SMART BOX detergente 1815") == 0


def test_no_hallucinated_products():
    assert rank_products("prodotto inesistente 9999", [{"description": "SMART BOX 1814"}]) == []


def test_code_field_exact():
    assert product_score("1814", "Detergente SMART BOX", code="1814") == 1


def test_non_mutating_ranking():
    products = [{"description": "SMART BOX 1814"}]
    assert rank_products("SMART BOX 1814", products)[0]["match_score"] > 0.9
    assert "match_score" not in products[0]


def test_code_matches_when_description_does_not_contain_code():
    assert product_score("SMART BOX 1814", "SMART BOX detergente", code="1814") == 1


def test_code_mismatch_is_rejected_even_when_description_similar():
    assert product_score("SMART BOX 1814", "SMART BOX detergente 1815", code="1815") == 0


def test_accent_insensitive():
    assert product_score("caffe", "CAFFÈ") == 1


def test_different_numeric_pack_size_is_not_fuzzy_matched():
    assert product_score("ACQUA 500", "ACQUA 750") == 0
