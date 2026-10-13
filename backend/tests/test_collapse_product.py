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


def test_uova_non_trova_nuova_e_mozz_abbreviato():
    from app.product_taxonomy import is_product_search_match
    assert not is_product_search_match("KIWI NUOVA ZELANDA", "uova")
    assert is_product_search_match("UOVA FRESCHE VASSOIO", "uova")
    assert is_product_search_match("MOZZ. FIOR DI LATTE 1KG", "mozzarella")
    assert is_product_search_match("LIMONCELLO 70CL", "limon")


def test_alimento_con_parola_di_confezione_resta():
    from app.product_recognition import compatible, recognize
    wanted = recognize("prosciutto")
    assert compatible(wanted, recognize("PROSCIUTTO COTTO SGRASSATO 1KG"))
    assert compatible(recognize("mozzarella"), recognize("MOZZARELLA IN BUSTA 125G"))


def test_parole_corte_solo_a_inizio_parola():
    from app.product_taxonomy import description_matches_product
    assert not description_matches_product("MACINATO BOVINO ADULTO", "vino")
    assert not description_matches_product("GASOLIO", "olio")
    assert description_matches_product("VINO BIANCO UMBRIA 75CL", "vino")
    assert description_matches_product("OLIO EVO 5 L", "olio")


def test_tovaglioli_di_carta_sono_monouso():
    from app.product_recognition import recognize
    assert recognize("TOVAGLIOLO 33X33 2V BIANCO 2700PZ")["category"] == "Monouso e tavola"
    assert recognize("Servizio di Lavanolo per TOVAGLIOLO CREMA")["category"] == "Lavanderia e biancheria a noleggio"


def test_virgolette_ricerca_esatta():
    from app.product_taxonomy import (description_matches_product, exact_phrases, extract_product_query,
                                      is_product_search_match, row_matches_product_query)
    assert exact_phrases('chi vende "olio"?') == ["olio"]
    assert extract_product_query('chi vende "olio"?') == '"olio"'
    for fn in (is_product_search_match, description_matches_product, row_matches_product_query):
        assert fn("OLIO EVO 5 L", '"olio"')
        assert not fn("GASOLIO AUTOTRAZIONE", '"olio"')
        assert not fn("OLIOSO", '"olio"')
