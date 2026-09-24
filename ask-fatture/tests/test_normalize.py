from decimal import Decimal

from app.normalize import extract_content, is_noise_line, normalize_line


def test_noise_filter():
    assert is_noise_line("SCONTO PROMOZIONE 10%")
    assert is_noise_line("Carburante gasolio agricolo")
    assert is_noise_line("Marca da bollo")
    assert is_noise_line("Contributo CONAI")
    assert not is_noise_line("LATTE UHT 1L")
    assert not is_noise_line("BOMBOLONE OLIO 3 KG")


def test_content_from_description():
    qty, base, in_base = extract_content("BOMBOLONE OLIO 3 KG")
    assert qty == Decimal("3") and base == "kg" and in_base == Decimal("3")
    qty, base, in_base = extract_content("CONF MOZZARELLA 50G")
    assert qty == Decimal("50") and base == "kg" and in_base == Decimal("0.05")
    qty, base, in_base = extract_content("BURRO 2 etti")
    assert in_base == Decimal("0.2")


def test_normalized_price_per_gram():
    row = normalize_line(
        description="SPEZIA",
        quantita=500,
        unita="g",
        prezzo_unitario=0.45,
    )
    assert row["unita_normalizzata"] == "kg"
    assert row["prezzo_unitario"] == 0.45
    assert abs(row["prezzo_normalizzato"] - 450.0) < 1e-6


def test_normalized_price_pack_50g():
    # 2 € a confezione da 50g → 40 €/kg
    row = normalize_line(
        description="YOGURT CONF 50G",
        quantita=1,
        unita="PZ",
        prezzo_unitario=2.0,
    )
    assert row["unita_normalizzata"] == "kg"
    assert row["prezzo_unitario"] == 2.0
    assert abs(row["prezzo_normalizzato"] - 40.0) < 1e-6
    assert abs(row["contenuto_base"] - 0.05) < 1e-9


def test_bombolone_3kg():
    # 30 € il bombolone da 3 kg → 10 €/kg
    row = normalize_line(
        description="BOMBOLONE OLIO DI SEMI 3 KG",
        quantita=1,
        unita="PZ",
        prezzo_unitario=30.0,
    )
    assert abs(row["prezzo_normalizzato"] - 10.0) < 1e-6
    assert row["unita_normalizzata"] == "kg"
