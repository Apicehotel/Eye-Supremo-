from app.product_recognition import collapse_to_product


def _item(name, purchases, avg):
    return {"nome_canonico": name, "purchases": purchases, "avg_price": avg, "min_price": avg - 1, "max_price": avg + 1}


def test_crostata_variants_become_one_product_with_all_names():
    items = [_item("CROSTATE ALLE MARMELLATE", 4, 10.0), _item("CROSTATA MARM. PRUGNE", 1, 12.0), _item("crostata marmellata", 3, 11.0), _item("CROSTATINE MARMELLATA", 2, 1.0)]
    out = collapse_to_product(items, "crostata")
    assert len(out) == 1
    assert out[0]["nome_canonico"] == "Crostata"
    assert out[0]["purchases"] == 10
    assert set(out[0]["canonical_names"]) == {i["nome_canonico"] for i in items}
    assert out[0]["merged_variants"] == 4


def test_variant_searches_stay_separate():
    items = [_item("ACQUA NATURALE 0,5 L", 5, 0.3), _item("ACQUA FRIZZANTE 1,5 L", 3, 0.5)]
    assert collapse_to_product(items, "acqua") == items


def test_single_match_and_unknown_unchanged():
    one = [_item("CROSTATA", 1, 5.0)]
    assert collapse_to_product(one, "crostata") == one
    two = [_item("QWXZ UNO", 1, 5.0), _item("QWXZ DUE", 1, 5.0)]
    assert collapse_to_product(two, "qwxz") == two


def test_incompatible_rows_are_dropped_when_collapsing():
    items = [_item("NESTLE Marmellata Arance 120x25g IT", 5, 11.0), _item("CONFETTURA DI SAMBUCO", 2, 2.2), _item("CORNETTI MARMELLATA", 1, 0.7), _item("DISPENSER VASO CONFETTURA 3 PZ", 1, 100.0)]
    out = collapse_to_product(items, "marmellata")
    assert len(out) == 1 and out[0]["merged_variants"] == 2
    assert set(out[0]["canonical_names"]) == {"NESTLE Marmellata Arance 120x25g IT", "CONFETTURA DI SAMBUCO"}
