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


def test_normalized_price_per_ml_to_liter():
    # 0,002 €/ml → 2 €/l
    row = normalize_line(
        description="DETERGENTE",
        quantita=1000,
        unita="ml",
        prezzo_unitario=0.002,
    )
    assert row["unita_normalizzata"] == "l"
    assert abs(row["prezzo_normalizzato"] - 2.0) < 1e-9
    assert row["prezzo_unitario"] == 0.002


def test_bottle_15l_unit_price():
    # Prezzo unitario 1,50 € bottiglia 1,5L → 1 €/l
    row = normalize_line(
        description="ACQUA NATURALE 1,5L",
        quantita=6,
        unita="PZ",
        prezzo_unitario=1.5,
    )
    assert row["unita_normalizzata"] == "l"
    assert abs(row["prezzo_normalizzato"] - 1.0) < 1e-9
    assert row["prezzo_unitario"] == 1.5


def test_lt_unit_measure():
    row = normalize_line(
        description="LATTE FRESCO",
        quantita=10,
        unita="LT",
        prezzo_unitario=1.2,
    )
    assert row["unita_normalizzata"] == "l"
    assert abs(row["prezzo_normalizzato"] - 1.2) < 1e-9


def test_prezzo_unitario_solo_pezzo():
    row = normalize_line(
        description="PIATTO MONOUSO",
        quantita=100,
        unita="PZ",
        prezzo_unitario=0.08,
    )
    assert row["unita_normalizzata"] == "pz"
    assert abs(row["prezzo_normalizzato"] - 0.08) < 1e-9


def test_75cl_wine():
    row = normalize_line(
        description="VINO ROSSO 75CL",
        quantita=1,
        unita="conf",
        prezzo_unitario=3.0,
    )
    assert row["unita_normalizzata"] == "l"
    assert abs(row["prezzo_normalizzato"] - 4.0) < 1e-9  # 3 / 0.75
