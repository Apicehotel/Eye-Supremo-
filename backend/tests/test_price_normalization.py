"""Prezzi normalizzati (€/kg, €/l, €/pz) sulle righe fattura.

Le descrizioni sono inventate ma hanno la stessa struttura di quelle reali che il vecchio parser
sbagliava: nessuna fattura vera nel repository.
"""
import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from app.normalization import (
    extract_content,
    fill_normalized_price,
    normalize_row_price,
    parse_pack,
)


def price(description, unit, quantity, amount):
    result = normalize_row_price(Decimal(amount), Decimal(quantity), unit, description)
    return result.unit, float(result.price)


@pytest.mark.parametrize(
    "description, unit, quantity, amount, expected_unit, expected_price",
    [
        # contenuto semplice: l'unità non deve essere cercata dentro le parole («AMARETTI» contiene «etti»)
        ("BISCOTTI FROLLINI 400G", "PZ", "1", "2.00", "kg", 5.0),
        ("AMARETTI 250G", "PZ", "1", "3.00", "kg", 12.0),
        ("PASTA SEMOLA N5 500G", "PZ", "1", "1.10", "kg", 2.2),
        ("OLIO EXTRA VERGINE LT 5", "PZ", "1", "30.00", "l", 6.0),
        ("DOLCETTO CIOCCOLATO 281,80G", "PZ", "10", "6.06", "kg", 21.5046),
        # moltiplicatori di confezione
        ("ACQUA NATURALE 24X50CL", "PZ", "1", "6.00", "l", 0.5),
        ("BIRRA CHIARA 66CL X 15", "CT", "1", "18.00", "l", 1.8182),
        ("SUCCO FRUTTA CL.20 X 24", "CT", "2", "27.96", "l", 5.825),
        ("LATTE UHT 1L X 6", "CT", "1", "7.20", "l", 1.2),
        ("PANINO MIGNON 40GX105P.GE", "CT", "2", "13.57", "kg", 3.231),
        ("CREMA NOCCIOLA G1000 X12", "SC", "3", "17.60", "kg", 1.4667),
        # notazione col punto e numero di pezzi
        ("CONFETTURA ASSORTITA GR.25 PZ.100", "CARTONI", "1", "39.20", "kg", 15.68),
        ("DOLCETTO MIGNON GR.42 PZ.80", "CARTONI", "1", "39.20", "kg", 11.6667),
        ("MACARON ASSORTITI PZ 48 GR 12", "CT", "2", "26.104", "kg", 45.3194),
        ("DONUT GLASSATO CIOCCOLATO P.36", "CT", "1", "17.00", "pz", 0.4722),
        ("BRIOCHE ALBICOCCA P. 60", "CT", "2", "30.00", "pz", 0.5),
        ("SFILATINO 16 PZ 200 G", "CT", "1", "12.90", "kg", 4.0313),
        ("SIGILLANTE BIANCO Ml.310", "Numero", "1", "5.70", "l", 18.3871),
        ("VERNICE LT.4", "N.", "1", "33.39", "l", 8.3475),
        # codice articolo attaccato all'unità: il contenuto è quello dopo l'unità
        ("FORMAGGINO ART 6317  GR.50 X 50 PZ", "PZ", "1", "28.30", "kg", 11.32),
        ("VERNICE 603 LT 1", "PZ", "1", "4.00", "l", 4.0),
        # prezzo già al kg o al litro: la descrizione non conta
        ("FORMAGGIO STAGIONATO 2,1KG", "KG", "12.8", "9.30", "kg", 9.3),
        ("CAFFE IN GRANI KG 1", "K.", "6", "29.50", "kg", 29.5),
        # solo numero di pezzi: prezzo per pezzo, ma solo per confezioni/cartoni
        ("TOVAGLIOLI 2V 38X38- 50PZ", "CF", "288", "0.63", "pz", 0.0126),
        ("PIATTO CARTA IMB.1000PZ", "CT", "4", "55.34", "pz", 0.0553),
        # pezzo singolo venduto a pezzi (quantità = pezzi della confezione) oppure confezione intera
        ("TARALLINI 32GX32", "PZ", "32", "0.39", "kg", 12.1875),
        ("YOGURT 125gX20", "N.", "1", "5.44", "kg", 2.176),
        # una confezione da 50 non può costare 0,0135 €/l: è il prezzo del singolo bicchiere
        ("BICCHIERE CARTONCINO 120 ml CONF.50 pz", "N", "1", "0.081", "l", 0.675),
        # «16 FETTE» è un conteggio, non 16 g; «PZ 16,5g» non è «16 pezzi»; «LIT» sono litri
        ("PANCARRE 285G 16 FETTE", "PZ", "18", "0.95", "kg", 3.3333),
        ("BISCOTTO CACAO 2PZ 16,5gX150", "N.", "1", "12.02", "kg", 4.8566),
        ("OLIO GIRASOLE PET LT 10 X 2", "LIT", "40", "1.79", "l", 1.79),
    ],
)
def test_price_is_comparable_per_kg_litre_or_piece(description, unit, quantity, amount, expected_unit, expected_price):
    got_unit, got_price = price(description, unit, quantity, amount)
    assert got_unit == expected_unit
    assert got_price == pytest.approx(expected_price, rel=0.002, abs=0.0006)


@pytest.mark.parametrize(
    "description, unit, amount",
    [
        ("CARTA IGIENICA 12 ROTOLI", "PZ", "4.80"),
        ("LICENZA SOFTWARE dal 06.06.2025 al 05.06.2026", "N.", "120"),
        ("PANNELLO forex spessore 5 mm f.to 90 x 140cm", "PZ", "25"),
        ("FILO OTTONE D0,4MM L30M", None, "2.38"),
        ("LAMPADA LED E27 10 W", "PZ", "3.50"),
        ("PRODOTTO CON CODICE T3X24", "CU", "1.35"),
        # cartone con il peso di un solo articolo e nessun numero di pezzi: meglio il prezzo grezzo di 1.411 €/kg
        ("CUORE MIGNON PANNA gr.25", "CT", "35.28"),
        ("DIETETICO 300 BUSTINE X GR.0,8", "CF", "8.10"),
    ],
)
def test_price_stays_raw_when_nothing_reliable_can_be_read(description, unit, amount):
    result = normalize_row_price(Decimal(amount), Decimal("1"), unit, description)
    assert result.basis == "raw"
    assert result.price == Decimal(amount)


def test_p_dot_is_a_piece_count_only_with_dot_and_number():
    assert parse_pack("DONUT P.36").count == 36
    assert parse_pack("PANINO 40GX105P.GE").count == 105
    assert parse_pack("CODICE P 200").count is None
    # «PRZ.14» sono porzioni, non pezzi: il prezzo resta al kg della torta
    assert price("CROSTATA DI MELE GR.1400 PRZ.14", "CARTONI", "2", "24.859") == ("kg", pytest.approx(17.7564, rel=0.002))


def test_fractional_unit_with_piece_price_stays_raw():
    # unità «ML» con prezzo da pezzo: 455 €/ml non è un prezzo al litro credibile
    result = normalize_row_price(Decimal("455.24"), Decimal("1"), "ML", "PRODOTTO GENERICO")
    assert result.basis == "raw"


def test_unrelated_units_and_non_positive_prices_are_left_alone():
    hours = normalize_row_price(Decimal("40"), Decimal("3"), "ORA", "Installazione 2 kg di materiale")
    assert hours.basis == "raw" and hours.unit == "ora"
    credit = normalize_row_price(Decimal("-8.19"), Decimal("1"), None, "SCONTO 5 % su 500G")
    assert credit.basis == "raw"


def test_quantity_follows_the_normalized_price():
    result = normalize_row_price(Decimal("27.96"), Decimal("2"), "CT", "SUCCO FRUTTA CL.20 X 24")
    assert result.unit == "l"
    assert Decimal("2") * result.base_per_unit == Decimal("9.6")


def test_pack_parser_reads_content_and_count():
    info = parse_pack("PAGO CL.20 X 24")
    assert (info.content_base, info.content_in_base, info.count) == ("l", Decimal("0.20"), 24)
    assert parse_pack("MORETTI 66CL").content_in_base == Decimal("0.66")
    assert parse_pack("nessun contenuto qui") == parse_pack("")


def test_extract_content_keeps_its_original_contract():
    assert extract_content("24 pz Acqua naturale lt 0 500") == (Decimal("0.500"), "l", Decimal("0.500"))
    assert extract_content("acqua cl 50x24vp nat") == (Decimal("50"), "l", Decimal("0.5"))
    assert extract_content("bicchieri 24 pz")[1:] == ("pz", Decimal("24"))
    assert extract_content("") == (None, None, None)


def test_central_row_without_normalized_price_is_completed_on_read():
    row = {"unit_price": 27.96, "quantity": 2, "original_unit": "CT", "original_description": "SUCCO FRUTTA CL.20 X 24", "normalized_price": None}
    fill_normalized_price(row)
    assert row["normalized_unit"] == "l"
    assert row["normalized_price"] == pytest.approx(5.825)

    # una riga che ha già il prezzo normalizzato non viene toccata
    done = {"unit_price": 10, "quantity": 1, "original_unit": "KG", "normalized_price": 7.5, "normalized_unit": "kg"}
    assert fill_normalized_price(done)["normalized_price"] == 7.5

    # senza nulla di affidabile non si inventa un valore
    plain = {"unit_price": 4.8, "quantity": 1, "original_unit": "PZ", "original_description": "CARTA IGIENICA 12 ROTOLI"}
    fill_normalized_price(plain)
    assert plain.get("normalized_price") is None and "normalized_unit" not in plain


def test_central_history_row_uses_the_description_passed_in():
    row = {"unit_price": 18, "quantity": 1, "original_unit": "CT"}
    fill_normalized_price(row, description="BIRRA CHIARA 66CL X 15")
    assert row["normalized_unit"] == "l"
    assert row["normalized_price"] == pytest.approx(1.8182, rel=0.001)


def test_report_quantity_matches_the_normalized_price():
    from app.models import InvoiceRow
    from app.report_service import _comparable_quantity

    row = InvoiceRow(
        descrizione_originale="SUCCO FRUTTA CL.20 X 24", descrizione_normalizzata="succo frutta",
        quantita=Decimal("2"), unita_originale="CT", prezzo_unitario=Decimal("27.96"),
    )
    assert _comparable_quantity(row, "l") == 9.6
    assert _comparable_quantity(row, "kg") == 2.0


def test_migration_recomputes_stored_normalized_prices(tmp_path, monkeypatch):
    from app import db_migrations
    from app.config import settings

    database = tmp_path / "eye-supremo.db"
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, created_at TEXT)")
        connection.execute("CREATE TABLE sync_state (id INTEGER PRIMARY KEY, status TEXT)")
        connection.execute("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE invoice_rows (id INTEGER PRIMARY KEY, descrizione_originale TEXT, quantita REAL, "
            "unita_originale TEXT, prezzo_unitario REAL, unita_normalizzata TEXT, prezzo_normalizzato REAL)"
        )
        connection.executemany(
            "INSERT INTO invoice_rows VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                # valori sbagliati salvati dal vecchio parser
                (1, "AMARETTI 250G", 1, "PZ", 3.0, "kg", 0.12),
                (2, "ACQUA NATURALE 24X50CL", 1, "PZ", 6.0, "l", 12.0),
                (3, "CARTA IGIENICA 12 ROTOLI", 1, "PZ", 4.8, "pz", 4.8),
            ],
        )
        connection.commit()

    db_migrations.run_safe_migrations(create_engine(f"sqlite:///{database}"))

    with sqlite3.connect(database) as connection:
        rows = {r[0]: r[1:] for r in connection.execute("SELECT id, unita_normalizzata, prezzo_normalizzato, descrizione_originale FROM invoice_rows")}
    assert rows[1][:2] == ("kg", pytest.approx(12.0))
    assert rows[2][:2] == ("l", pytest.approx(0.5))
    assert rows[3][:2] == ("pz", pytest.approx(4.8))
    # le descrizioni originali non si toccano
    assert rows[1][2] == "AMARETTI 250G"
