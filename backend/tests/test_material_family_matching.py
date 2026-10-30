"""Regole di ricerca: materiali, sinonimi/ordine parole, famiglie per gusto e grammatura."""

import pytest

from app.product_taxonomy import is_product_search_match as match, search_terms
from app.product_variants import annotate_variants, grammage, flavors, sort_variants


@pytest.mark.parametrize("query,description,expected", [
    ("carta", "Carta igienica 2 veli 10 rotoli", True),
    ("carta", "Bicchiere in carta 240 ml", True),
    ("carta", "Carta per muffin 50 pz", True),
    ("carta", "Capocollo in carta", False),
    ("carta", "Caramelle assortite avvolte in carta", False),
    ("carta", "Contributo CONAI carta", False),
    ("plastica", "Bicchieri plastica 200 ml", True),
    ("plastica", "Posate pvc 100 pz", True),
    ("plastica", "Caramelle in plastica 1 kg", False),
])
def test_material_queries_return_objects_not_wrapped_food(query, description, expected):
    assert match(description, query) is expected


@pytest.mark.parametrize("query", ["bombolone choco", "choco bombolone", "bombolone cioccolato", "cioccolato bombolone"])
def test_bombolone_choco_any_order_and_synonym(query):
    assert match("Choco bombolone 90 g", query)
    assert match("Bombolone cioccolato 80g", query)
    assert not match("Bombolone crema 80g", query)


def test_multiword_search_terms_expand_synonyms_for_retrieval():
    assert "cioccolato" in search_terms("bombolone choco")


@pytest.mark.parametrize("description", ["Marm. arance 25gx100", "Confet albic 650 gr", "Confettura extra fragole 1 kg", "Marmellata di ciliegie 350 g"])
def test_marmellata_family_matches_any_wording(description):
    assert match(description, "marmellata")


@pytest.mark.parametrize("description", ["Crostata marmellata 80 g", "Marmo bianco", "Confetti bomboniera"])
def test_marmellata_family_excludes_lookalikes(description):
    assert not match(description, "marmellata")


def test_grammage_and_flavor_extraction():
    assert grammage("marm s day arance pvc 25gx100")["label"] == "25 g"
    assert grammage("confettura 60 lampone ciocc mantea kg1 9")["label"] == "1,9 kg"
    assert flavors("confettura 60 lampone ciocc mantea kg1 9") == ["lampone", "cioccolato"]
    assert flavors("pescato fresco") == []


def test_variants_sorted_by_flavor_then_grammage():
    items = annotate_variants([
        {"nome_canonico": "Marmellata fragola 1 kg"},
        {"nome_canonico": "Marmellata arancia 350 g"},
        {"nome_canonico": "Marmellata fragola 350 g"},
    ])
    names = [i["nome_canonico"] for i in sort_variants(items)]
    assert names == ["Marmellata arancia 350 g", "Marmellata fragola 350 g", "Marmellata fragola 1 kg"]
