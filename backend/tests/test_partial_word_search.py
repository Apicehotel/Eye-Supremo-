from app.product_taxonomy import is_product_search_match


def test_partial_word_finds_longer_words():
    assert is_product_search_match("BOMBOLINO CREMA", "bombo")
    assert is_product_search_match("MINI BOMBOLINI CIOCCOLATO", "bombo")
    assert is_product_search_match("LIMONCELLO 70CL", "limon")


def test_too_short_fragments_stay_strict():
    assert not is_product_search_match("BOMBOLINO CREMA", "bom")
    assert not is_product_search_match("LIMONCELLO 70CL", "li")


def test_unrelated_products_are_still_rejected():
    assert not is_product_search_match("DETERSIVO PIATTI", "bombo")


def test_carta_igienica_alias_does_not_crash():
    assert is_product_search_match("CARTA IGIENICA 10 ROTOLI", "carta igienica")
    assert not is_product_search_match("DETERSIVO PIATTI", "carta igienica")


def test_carta_search_excludes_packaging_context_and_keeps_paper_products():
    assert is_product_search_match("Carta A4 160 gr", "carta")
    assert is_product_search_match("Carta da forno 60 x 40", "carta")
    assert is_product_search_match("Carta vetrata resinata", "carta")
    assert not is_product_search_match("Capocollo in carta stagionato", "carta")
    assert not is_product_search_match("Bicchiere in carta 240 ml", "carta")
    assert not is_product_search_match("Acqua Acqua 1 l", "carta")
