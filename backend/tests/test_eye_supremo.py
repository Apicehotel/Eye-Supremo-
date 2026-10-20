from datetime import date, datetime
from app.models import CentralReviewCache
from decimal import Decimal
from unittest.mock import AsyncMock
from sqlalchemy import select
from app.eye_services import add_review, classify_review_text, invoice_search_summary
from app.search_index import invoice_search
from app.models import AppSetting, CentralInvoiceCache, Hotel, Invoice, InvoiceRow, InvoiceRowPolicy, Review, Supplier, UserProfile
from app.agent_orchestrator import _max_invoice_context
from app.report_service import historical_product_report
from app.review_importers import _author, _rating, _room, clean_review_text, split_review_blocks
from app.product_taxonomy import is_family_match, is_product_search_match, normalize_product_display_name, search_terms
from app.normalization import extract_content, normalized_price_with_content
from app.product_taxonomy import is_catalog_product, merge_product_catalog, product_content_group, product_family_similarity


def test_core_seed(db):
    hotels = db.scalars(select(Hotel).order_by(Hotel.code)).all()
    assert {h.code for h in hotels} == {"gio", "choco", "brigantino"}
    roles = {u.role_name for u in db.scalars(select(UserProfile)).all()}
    assert roles == {"developer", "supremo"}


def test_search_sums_only_matching_rows(db):
    supplier = Supplier(ragione_sociale="Test Fornitore"); db.add(supplier); db.flush()
    inv = Invoice(supplier_id=supplier.id, numero="F1", data=date(2026, 1, 1), imponibile=110, iva=22, totale=132)
    db.add(inv); db.flush()
    lamp = InvoiceRow(invoice_id=inv.id, descrizione_originale="Lampadina LED E27", descrizione_normalizzata="lampadina led e27", quantita=2, prezzo_unitario=5, totale_riga=10, confidence=1)
    other = InvoiceRow(invoice_id=inv.id, descrizione_originale="Carta igienica", descrizione_normalizzata="carta igienica", quantita=10, prezzo_unitario=10, totale_riga=100, confidence=1)
    db.add_all([lamp, other]); db.flush()
    db.add_all([InvoiceRowPolicy(row_id=lamp.id, analysis_status="product"), InvoiceRowPolicy(row_id=other.id, analysis_status="product")]); db.commit()
    rows = invoice_search(db, "quanto abbiamo speso per lampadina", limit=20)
    summary = invoice_search_summary(rows)
    assert summary["rows"] == 1
    assert summary["row_total"] == 10


def test_supplier_search_finds_supplier_from_invoice_line_text(client, db):
    supplier = Supplier(ragione_sociale="Fornitore Consegne Test"); db.add(supplier); db.flush()
    invoice = Invoice(supplier_id=supplier.id, numero="SUP-1", data=date(2026, 1, 1), imponibile=10, iva=2, totale=12)
    db.add(invoice); db.flush()
    db.add(InvoiceRow(invoice_id=invoice.id, descrizione_originale="Omaggio consegna merce", descrizione_normalizzata="omaggio consegna merce", quantita=1, prezzo_unitario=0, totale_riga=0, confidence=1))
    db.commit()
    response = client.get("/api/suppliers", params={"q": "consegna"})
    assert response.status_code == 200
    assert any(item["ragione_sociale"] == "Fornitore Consegne Test" for item in response.json())


def test_product_taxonomy_respects_word_boundaries():
    from app.product_taxonomy import extract_product_query
    assert "lamp" not in search_terms("lampadine")
    assert is_family_match("lampadina LED E27", "lampadine")
    assert not is_family_match("lamponi surgelati", "lampadine")
    assert is_family_match("carta fotoc A4 risma 500ff", "a4")
    assert not is_family_match("plastificatrice formato A4", "a4")
    assert is_family_match("acqua naturale 0,5 lt", "acqua")
    assert not is_family_match("acquedotto tariffa base", "acqua")
    assert "bombolino" in search_terms("bomboloni")
    assert extract_product_query("Chi mi vende meglio i bomboloni?") == "bomboloni"
    assert "bombolone" in search_terms("Chi mi vende meglio i bomboloni?")
    assert extract_product_query("Quanto abbiamo speso per limoncello?") == "limoncello"


def test_pack_content_normalizes_piece_price_to_comparable_unit():
    unit, price = normalized_price_with_content(Decimal("0.40"), Decimal("1"), "pz", "BOMBOLONE 50G")
    assert unit == "kg"
    assert price == Decimal("8")


def test_content_parser_groups_half_litre_variants_after_text_normalization():
    quantity, unit, base_quantity = extract_content("24 pz Acqua naturale lt 0 500")
    assert quantity == Decimal("0.500")
    assert unit == "l"
    assert base_quantity == Decimal("0.500")


def test_content_parser_accepts_attached_package_marker_after_content():
    assert extract_content("lilia acqua cl 50x24vp nat") == (Decimal("50"), "l", Decimal("0.5"))


def test_product_catalog_normalizes_ocr_split_litre_decimal():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "acqua frizzante 75cl", "purchases": 2, "avg_price": 2},
        {"id": 2, "nome_canonico": "acqua naturale 0 75 cl", "purchases": 1, "avg_price": 3},
    ])
    natural_group = next(row for row in rows if row["nome_canonico"] == "Acqua Naturale 0,75 l")
    sparkling_group = next(row for row in rows if row["nome_canonico"] == "Acqua Frizzante 0,75 l")
    assert natural_group["purchases"] == 1
    assert sparkling_group["purchases"] == 2


def test_product_display_name_normalizes_spacing_without_losing_alias():
    assert normalize_product_display_name("acqua naturale 0 5 l cl50x24") == "Acqua naturale 0,5 l 50 cl x 24"
    assert normalize_product_display_name("acqua gas 0 75") == "Acqua gas 0,75"


def test_product_catalog_groups_acquaragia_brands_by_content():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "acquaragia 603 lt 1", "purchases": 2, "avg_price": 4},
        {"id": 2, "nome_canonico": "acquaragia silver 603 lt 1", "purchases": 3, "avg_price": 5},
        {"id": 3, "nome_canonico": "acquaragia inodore lt 1", "purchases": 1, "avg_price": 6},
    ])
    group = next(row for row in rows if row["nome_canonico"] == "Acquaragia 1 l")
    assert group["purchases"] == 6
    assert len(group["canonical_names"]) == 3


def test_product_catalog_groups_brand_variants_for_every_product_family():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "biscotti marca a 500g", "purchases": 2, "avg_price": 4},
        {"id": 2, "nome_canonico": "biscotti marca b 0,5 kg", "purchases": 3, "avg_price": 5},
    ])
    assert len(rows) == 1
    assert rows[0]["purchases"] == 5
    assert len(rows[0]["canonical_names"]) == 2


def test_product_search_does_not_return_water_for_crema():
    assert is_product_search_match("acqua 0,5 l", "crema") is False
    assert is_product_search_match("crema pasticcera 1 kg", "crema") is True


def test_product_search_accepts_small_typo_in_carta_igienica():
    assert is_product_search_match("carta igienica 500 cf10x4rt", "carta igenica") is True


def test_acquaviva_is_not_classified_as_acqua():
    family, _ = product_content_group({"nome_canonico": "acquaviva krapfen crema 80gr 24pz"})
    assert family != "acqua"


def test_water_family_accepts_brand_only_invoice_descriptions():
    assert is_family_match("TULLIA L'UNICA NAT VR 75x12", "acqua") is True
    assert is_family_match("BAP 4 CON 4 LUPPOLI 24 bt 33 cl", "acqua") is False


def test_product_catalog_groups_equivalent_packaging_abbreviations():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "carta igienica bauletto maxi cf8x12rt", "purchases": 4, "avg_price": 18},
        {"id": 2, "nome_canonico": "carta igienica bauletto maxi ct8x12r", "purchases": 2, "avg_price": 20},
    ])
    assert len(rows) == 1
    assert rows[0]["purchases"] == 6
    assert rows[0]["nome_canonico"].endswith("cf8x12rt")


def test_product_catalog_keeps_different_toilet_paper_formats_separate():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "carta igienica 500 cf10x4rt", "purchases": 27, "avg_price": 24},
        {"id": 2, "nome_canonico": "carta igienica bauletto maxi cf8x12rt", "purchases": 4, "avg_price": 18},
        {"id": 3, "nome_canonico": "carta igienica fascettata cf24x4rt", "purchases": 36, "avg_price": 21},
    ])
    assert len(rows) == 3


def test_product_catalog_merges_bicchieri_volume_and_packaging_variants():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "bicchieri 330 cl in conf da 50", "purchases": 1, "avg_price": 2},
        {"id": 2, "nome_canonico": "bicchieri 330cl x 50 pz", "purchases": 7, "avg_price": 2.17},
        {"id": 3, "nome_canonico": "bicchieri trasparen pp 400cc isap 50pz", "purchases": 1, "avg_price": 5.34},
        {"id": 4, "nome_canonico": "bicchieri pp trasparen 400cc isap pz50", "purchases": 2, "avg_price": 4.01},
    ])
    assert len(rows) == 2
    assert sorted(row["purchases"] for row in rows) == [3, 8]


def test_product_family_similarity_tolerates_word_order_and_small_typo():
    assert product_family_similarity("bicchieri pp trasparen isap", "bicchieri trasparente pp isap") >= 92


def test_catalog_excludes_services_delivery_and_fuel_but_keeps_real_products():
    assert is_catalog_product("Bicchieri 330 cl conf da 50") is True
    assert is_catalog_product("Carburante gasolio") is False
    assert is_catalog_product("Consegna merce") is False
    assert is_catalog_product("Servizio trasporto") is False
    assert is_product_search_match("Boccione 18,9 lt consegnati", "consegna") is False
    assert is_product_search_match("Boccione 18,9 lt consegnati", "boccione") is True


def test_product_catalog_merges_half_litre_water_variants():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "acqua naturale 0 5 l", "purchases": 2, "min_price": 1, "avg_price": 2, "max_price": 3},
        {"id": 2, "nome_canonico": "acqua frizzante 500 ml", "purchases": 3, "min_price": 2, "avg_price": 4, "max_price": 5},
        {"id": 3, "nome_canonico": "acqua naturale 0 75 l", "purchases": 1, "min_price": 3, "avg_price": 3, "max_price": 3},
    ])
    natural_half_litre = next(row for row in rows if row["nome_canonico"] == "Acqua Naturale 0,5 l")
    assert natural_half_litre["purchases"] == 2
    assert any(row["nome_canonico"] == "Acqua Frizzante 0,5 l" for row in rows)
    assert any(row["nome_canonico"] == "Acqua Naturale 0,75 l" for row in rows)


def test_product_catalog_can_collapse_explicit_water_family_search():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "acqua naturale 0 5 l", "purchases": 2, "avg_price": 2},
        {"id": 2, "nome_canonico": "acqua frizzante 0 75 l", "purchases": 3, "avg_price": 4},
        {"id": 3, "nome_canonico": "6 pz acqua s benedetto gas", "purchases": 4, "avg_price": 5},
    ], collapse_family="acqua")
    assert len(rows) == 3
    assert {row["nome_canonico"] for row in rows} == {"Acqua Naturale 0,5 l", "Acqua Frizzante 0,75 l", "Acqua Frizzante"}


def test_product_catalog_merges_same_content_for_non_water_products():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "Bombolone crema 50g", "purchases": 2, "min_price": 1, "avg_price": 2, "max_price": 3},
        {"id": 2, "nome_canonico": "Bombolone crema 0,05 kg", "purchases": 3, "min_price": 2, "avg_price": 4, "max_price": 5},
        {"id": 3, "nome_canonico": "Bombolone cioccolato 50g", "purchases": 1, "min_price": 3, "avg_price": 3, "max_price": 3},
    ])
    crema = [row for row in rows if "crema" in row["nome_canonico"]]
    assert len(crema) == 1
    assert crema[0]["purchases"] == 5
    assert any("cioccolato" in row["nome_canonico"] for row in rows)


def test_product_catalog_merges_equivalent_packs_for_same_product():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "bev pago ace 24x200 ml", "purchases": 1, "avg_price": 16.9},
        {"id": 2, "nome_canonico": "pago ace cl 20 x 24", "purchases": 2, "avg_price": 15.4},
    ])
    assert len(rows) == 1
    assert rows[0]["purchases"] == 3
    assert len(rows[0]["canonical_names"]) == 2


def test_product_catalog_keeps_pago_flavours_separate():
    rows = merge_product_catalog([
        {"id": 1, "nome_canonico": "nett pago albicocca 24x200 ml", "purchases": 1},
        {"id": 2, "nome_canonico": "nett pago pera 24x200 ml", "purchases": 1},
    ])
    assert len(rows) == 2
    assert {row["nome_canonico"] for row in rows} == {"Nett pago albicocca 24 x 200 ml", "Nett pago pera 24 x 200 ml"}


def test_max_invoice_context_chooses_highest_between_local_and_central(db):
    supplier = Supplier(ragione_sociale="Locale Test"); db.add(supplier); db.flush()
    db.add(Invoice(supplier_id=supplier.id, numero="LOCAL-1", data=date(2026, 1, 1), imponibile=900, iva=198, totale=1098))
    db.add(CentralInvoiceCache(
        source_hash="central-max-1", invoice_number="CENTRAL-154", invoice_date=date(2024, 12, 15),
        supplier_name="APICE S.R.L. - ENOTECA GIO", total=146400,
        search_text="central max", payload_json='{"taxable": 120000, "vat": 26400, "source_filename": "max.xml"}'
    ))
    db.commit()
    result = _max_invoice_context(db)
    assert result["invoice_number"] == "CENTRAL-154"
    assert result["supplier_name"] == "APICE S.R.L. - ENOTECA GIO"
    assert result["total"] == 146400.0


def test_live_search_endpoint_uses_row_total(client, db):
    supplier = Supplier(ragione_sociale="Elettrica Test"); db.add(supplier); db.flush()
    inv = Invoice(supplier_id=supplier.id, numero="LED-1", data=date(2026, 5, 1), imponibile=40, iva=8.8, totale=48.8)
    db.add(inv); db.flush()
    row = InvoiceRow(invoice_id=inv.id, descrizione_originale="LAMP LED E27 12W", descrizione_normalizzata="lamp led e27 12w", quantita=4, prezzo_unitario=10, totale_riga=40, confidence=1)
    db.add(row); db.flush(); db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="product")); db.commit()
    response = client.get("/api/eye/search/live", params={"q":"lamp"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "fts5+rapidfuzz"
    assert payload["scope"] == "full-archive-unlimited"
    assert payload["summary"]["row_total"] == 40
    assert payload["results"][0]["description"] == "LAMP LED E27 12W"


def test_product_configuration_preserves_source_name_and_round_trips(client, db):
    response = client.put("/api/product-config", json={
        "source_name": "LAMP LED E27 12W",
        "configured_name": "Lampadina LED E27 12W",
        "manufacturer": "Philips",
    })
    assert response.status_code == 200
    assert response.json() == {
        "configured_name": "Lampadina LED E27 12W",
        "manufacturer": "Philips",
    }
    stored = db.get(AppSetting, "product_configs")
    assert stored is not None
    assert "LAMP LED E27 12W" in stored.value
    assert client.get("/api/product-config").json()["LAMP LED E27 12W"]["configured_name"] == "Lampadina LED E27 12W"


def test_product_price_tracking_round_trips(client):
    response = client.put("/api/product-tracking", json={"source_name": "Lampadina LED E27 12W", "enabled": True})
    assert response.status_code == 200
    assert response.json() == {"source_name": "Lampadina LED E27 12W", "enabled": True}
    assert client.get("/api/product-tracking").json() == {"Lampadina LED E27 12W": True}
    response = client.put("/api/product-tracking", json={"source_name": "Lampadina LED E27 12W", "enabled": False})
    assert response.status_code == 200
    assert client.get("/api/product-tracking").json() == {}


def test_accounting_rows_are_hidden_from_analysis(db):
    supplier = Supplier(ragione_sociale="Fuel Test"); db.add(supplier); db.flush()
    inv = Invoice(supplier_id=supplier.id, numero="F2", data=date(2026, 1, 2), imponibile=50, iva=0, totale=50)
    db.add(inv); db.flush()
    row = InvoiceRow(invoice_id=inv.id, descrizione_originale="Carburante", descrizione_normalizzata="carburante", quantita=1, prezzo_unitario=50, totale_riga=50, confidence=1)
    db.add(row); db.flush(); db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="accounting_excluded", exclusion_reason="carburante")); db.commit()
    assert invoice_search(db, "carburante", limit=20) == []


def test_historical_report_tracks_price_direction_and_best_supplier(db):
    s1 = Supplier(ragione_sociale="Fornitore 1"); s2 = Supplier(ragione_sociale="MARR"); db.add_all([s1, s2]); db.flush()
    samples = [
        (s1, "A1", date(2024,1,1), Decimal("1.25")),
        (s1, "A2", date(2025,1,1), Decimal("1.30")),
        (s2, "B1", date(2024,2,1), Decimal("0.90")),
        (s2, "B2", date(2025,2,1), Decimal("0.85")),
    ]
    for supplier, number, when, price in samples:
        inv = Invoice(supplier_id=supplier.id, numero=number, data=when, imponibile=price, iva=0, totale=price); db.add(inv); db.flush()
        row = InvoiceRow(invoice_id=inv.id, descrizione_originale="Bombolone crema", descrizione_normalizzata="bombolone crema", quantita=1, unita_normalizzata="pz", prezzo_unitario=price, totale_riga=price, confidence=1); db.add(row); db.flush()
        db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="product"))
    db.commit()
    report = historical_product_report(db, "bombolone")
    assert report["summary"]["initial_price"] == 1.25
    assert report["summary"]["best_price"] == 0.85
    assert report["summary"]["best_supplier"] == "MARR"
    marr = next(x for x in report["suppliers"] if x["supplier"] == "MARR")
    assert marr["points"][-1]["trend"] == "down"
    assert marr["points"][-1]["delta"] == -0.05
    # Domanda in linguaggio naturale: non deve cercare letteralmente tutta la frase.
    nl_report = historical_product_report(db, "Chi mi vende meglio i bomboloni?")
    assert nl_report["summary"] is not None
    assert nl_report["summary"]["best_supplier"] == "MARR"


def test_historical_report_understands_invoice_abbreviation(db):
    supplier = Supplier(ragione_sociale="Fornitore carta"); db.add(supplier); db.flush()
    inv = Invoice(supplier_id=supplier.id, numero="C1", data=date(2026, 2, 1), imponibile=4, iva=0, totale=4)
    db.add(inv); db.flush()
    row = InvoiceRow(invoice_id=inv.id, descrizione_originale="Carta igienica  maxi", descrizione_normalizzata="carta igienica maxi", quantita=1, unita_normalizzata="pz", prezzo_unitario=4, totale_riga=4, confidence=1)
    db.add(row); db.flush(); db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="product")); db.commit()

    report = historical_product_report(db, "c igienica")

    assert report["summary"]["product"] == "c igienica"
    assert report["suppliers"][0]["supplier"] == "Fornitore carta"


def test_review_digest_splits_multiple_rooms():
    text = """Booking.com recensioni\nCAM: 217\nData recensione: 17/02/2026\nVoto: 9\nPositivo: staff gentile\nNegativo: camera piccola\nCAM: 305\nData recensione: 18/02/2026\nVoto: 7\nPositivo: colazione buona\nNegativo: letto scomodo"""
    items = split_review_blocks(text, "2026-02-19", "Outlook MSG", None, "sample.msg")
    assert len(items) == 2
    assert items[0]["room_code"] == "217"
    assert items[1]["room_code"] == "305"
    assert items[0]["source"] == "Booking"


def test_review_digest_splits_inline_room_markers_and_keeps_scores():
    text = """Booking.com recensioni
10
Mario Rossi in 01/03 out 02/03 camera 1104
Ottima camera e colazione
7,0
Luigi Bianchi in 02/03 out 03/03 cam:2209
Camera da rimodernare"""
    items = split_review_blocks(text, "2026-03-04", "Outlook MSG", None, "sample.msg")
    assert len(items) == 2
    assert [item["room_code"] for item in items] == ["1104", "2209"]
    assert [item["rating"] for item in items] == ["10", "7,0"]


def test_review_import_extracts_google_author_and_rejects_freeform_room():
    digest = "Google nessuna recensione Valter Hotel Gio Wine e Jazz Area reception@hotelgio.it"
    assert _author(digest, "reception@hotelgio.it") == "Valter"
    assert _room("Camera ok, letto e lenzuola rigide.") is None
    assert _room("CAM: 2219") == "2219"
    assert _room("camera\n10") is None


def test_room_parser_ignores_vista_dalla_camera_category_score():
    # Booking category line: the trailing 10 is a score, not room 10 (inesistente a Hotel Giò).
    assert _room("Categorie extra\nVista dalla camera 10\nWifi 9") is None
    assert _room("vista dalla camera 10") is None
    assert _room("camera 10") is None
    assert _room("CAM: 10") is None
    assert _room("CAM: 4411\nVista dalla camera 10") == "4411"
    blocks = split_review_blocks(
        """Booking.com recensioni
9,0
Mario, it in 14/07 out 15/07 cam. 4411
Numero di prenotazione 123
Categorie extra Vista dalla camera 10 Wifi 9
Ottima camera
8,0
Luca, it in 15/07 out 16/07 cam. 2208
Numero di prenotazione 456
Categorie extra Vista dalla camera 10
Camera comoda""",
        "2026-07-15",
        "Booking",
        None,
        "booking.txt",
    )
    assert [block["room_code"] for block in blocks] == ["4411", "2208"]
    assert all(block["room_code"] != "10" for block in blocks)


def test_tripadvisor_category_scores_count_as_review_vote():
    assert _rating("TripAdvisor Camere3,0 Servizio3,0 Posizione3,0") == "3.0"
    assert _rating("Camere5,0 Servizio5,0 Posizione5,0 Nessuna recensione Tripadvisor michele") == "5.0"
    assert _rating("Categorie base Staff 10 Pulizia 10 Posizione 7,5 Voto 9,0") == "9.0"
    assert _rating("Categorie base Staff 10\n9,0 Luca, it Luca Merlo") == "9.0"


def test_clean_review_text_removes_booking_metadata_and_keeps_guest_text():
    text = """cam. 2215
    Numero di prenotazione 123456
    __________________________________
    Categorie base
    Staff
    10
    Pulizia
    7,5
    __________________________________
    Quasi tutto!
    La moquette nella stanza
    <https://admin.booking.com/example>
    """
    assert clean_review_text(text) == "Quasi tutto!\nLa moquette nella stanza"
    assert clean_review_text("Ottimo soggiorno\nEugenio, it in 03/04/24 out 05/04/24") == "Ottimo soggiorno"


def test_clean_review_text_keeps_guest_text_from_multiple_digest_sections():
    text = """Booking.com recensioni
    ________________________________
    Prima recensione: camera pulita e staff gentile
    ________________________________
    Seconda recensione: colazione ottima e posizione comoda
    """
    cleaned = clean_review_text(text)
    assert "Prima recensione" in cleaned
    assert "Seconda recensione" in cleaned


def test_review_digest_supports_cam_dot_without_inventing_room_numbers():
    text = """Recensioni Hotel
    7,0
    Gina, it
    Gina Fiorino in 09/07 out 10/07 cam. 325
    Commento della recensione
    9,0
    Jordi, es
    Jordi in 24/04 out 25/04 cam. 3308
    Commento della seconda recensione
    9,0
    Leon, nl
    Leon in 07/07 out 09/07 cam. 1108
    Altro commento
    """
    blocks = split_review_blocks(text, "2026-07-15", "Booking", None, "archive.msg")
    assert [block["room_code"] for block in blocks] == ["325", "3308", "1108"]
    assert all(block["room_code"] != "10" for block in blocks)


def test_review_classifier_keeps_mixed_aspects_separate(db):
    text = "Camera ok, letto e lenzuola rigide. Colazione super, ristorante scarso. Croissant da migliorare."
    tags = classify_review_text(db, text)
    pairs = {(tag["category"], tag["polarity"]) for tag in tags}
    assert ("Camere / Arredi", "positive") in pairs
    assert ("Letti", "negative") in pairs
    assert ("Colazione", "positive") in pairs
    assert ("Ristorante", "negative") in pairs
    assert ("Colazione", "negative") in pairs


def test_review_classifier_interprets_comfort_words_and_negation_by_category(db):
    text = "Letto comodo, parcheggio scomodo, camera confortevole ma cuscino non comodo."
    tags = classify_review_text(db, text)
    pairs = {(tag["category"], tag["polarity"]) for tag in tags}
    assert ("Letti", "positive") in pairs
    assert ("Parcheggio", "negative") in pairs
    assert ("Camere / Arredi", "positive") in pairs
    assert ("Cuscini", "negative") in pairs


def test_review_classifier_separates_positive_breakfast_from_restaurant_criticism(db):
    text = "Colazione stratosferica eccellente, unico neo: nel ristorante non avevano molte proposte senza glutine nonostante a colazione ci fosse grande varietà."
    pairs = {(tag["category"], tag["polarity"]) for tag in classify_review_text(db, text)}
    assert ("Colazione", "positive") in pairs
    assert ("Ristorante", "negative") in pairs


def test_review_classifier_uses_smile_markers_for_following_aspects(db):
    text = "😊 Ristorante. La colazione. Cocktail. Massaggio per sedie in camera. ☹ Le camere sono un po' datate."
    pairs = {(tag["category"], tag["polarity"]) for tag in classify_review_text(db, text)}
    assert ("Ristorante", "positive") in pairs
    assert ("Colazione", "positive") in pairs
    assert ("Camere / Arredi", "negative") in pairs


def test_review_classifier_keeps_positive_outcome_after_but_clause(db):
    text = "☹ Mi aspettavo la cioccolata a colazione, comunque c'era molta scelta dolce e salata."
    pairs = {(tag["category"], tag["polarity"]) for tag in classify_review_text(db, text)}
    assert ("Colazione", "negative") in pairs
    assert ("Colazione", "positive") in pairs


def test_review_classifier_treats_negated_distance_as_positive(db):
    tags = classify_review_text(db, "La posizione non è lontana dal centro.")
    assert ("Posizione", "positive") in {(tag["category"], tag["polarity"]) for tag in tags}


def test_review_classifier_does_not_mark_negated_problems_as_negative(db):
    tags = classify_review_text(db, "La camera non ha avuto problemi durante il soggiorno.")
    assert ("Camere / Arredi", "negative") not in {(tag["category"], tag["polarity"]) for tag in tags}


def test_review_classifier_uses_distance_context_and_phrase_meaning(db):
    positive = classify_review_text(db, "La posizione non è lontana e si raggiunge in pochi passi.")
    negative = classify_review_text(db, "La posizione è lontana e serve molto tempo per arrivarci.")
    assert ("Posizione", "positive") in {(tag["category"], tag["polarity"]) for tag in positive}
    assert ("Posizione", "negative") in {(tag["category"], tag["polarity"]) for tag in negative}


def test_booking_digest_is_split_into_each_room_review(db):
    from app.review_importers import clean_review_text, split_review_blocks

    digest = """Recensioni Hotel Gio 15/08/26
9,0
jean-philippe
IN : 06/08/2026 OUT : 10/08/2026 CAM: 4411 Numero di prenotazione 5970610863
Tradotto dal francese da - Vedi l'originale
Benvenuto. Camera confortevole e pulita.
    10
    Darick
12/08/2026 - 13/08/2026 Matrimoniale Superior Jazz 4410 Numero di prenotazione 5716813973
Bellissimo hotel vicino al centro.
    9,0
    Matthias
10/08/2026 - 14/08/2026 Matrimoniale Superior Jazz 2208 Numero di prenotazione 5466683128
Hotel eccellente, colazione ricca.
    8,0
    Arturo
12/08/2026 - 14/08/2026 Matrimoniale Superior Jazz 4407 Numero di prenotazione 5987525889
Stanze grandi e comode."""
    blocks = split_review_blocks(digest, "2026-08-16", "Booking", None, "booking.txt")
    assert [block["room_code"] for block in blocks] == ["4411", "4410", "2208", "4407"]
    assert [block["rating"] for block in blocks] == ["9,0", "10", "9,0", "8,0"]
    texts = [clean_review_text(block["text"]) for block in blocks]
    assert "Camera confortevole" in texts[0]
    assert "Bellissimo hotel" in texts[1]
    assert all("Numero di prenotazione" not in text for text in texts)
    assert all("michele" not in text.lower() and "tel 075" not in text.lower() for text in texts)


def test_booking_digest_splits_even_when_one_room_code_is_invalid():
    text = """Booking recensioni
9,0
Paula, it in 03/05 out 05/05 camera ??? (non c'è nella lista clienti)
Numero di prenotazione 5012792605
Categorie base Staff 10
8,0
Marco, it in 04/05 out 05/05 camera 405
Numero di prenotazione 6234904895
Categorie base Staff 7,5"""
    blocks = split_review_blocks(text, "2026-05-08", "Booking", None, "booking.txt")
    assert len(blocks) == 2
    assert [block["rating"] for block in blocks] == ["9,0", "8,0"]


def test_booking_digest_splits_review_without_room_metadata():
    text = """Booking recensioni
9,0
Michele, it no name?
Numero di prenotazione 5266253512
Categorie base Staff 10
6,0
Filippo, it Filippo Birritella in 16/06 out 18/06 camera 404
Numero di prenotazione 6262516395
Categorie base Staff 10"""
    blocks = split_review_blocks(text, "2026-06-19", "Booking", None, "booking.txt")
    assert len(blocks) == 2
    assert [block["rating"] for block in blocks] == ["9,0", "6,0"]


def test_review_ranking_best_and_worst(db):
    hotel = db.scalar(select(Hotel).where(Hotel.code == "choco"))
    add_review(db, hotel_id=hotel.id, text="Camera 101 pulita, letto comodo e staff gentile", review_date=date(2026, 8, 1), rating=Decimal("9.5"), room_code="101")
    add_review(db, hotel_id=hotel.id, text="Camera 102 sporca, letto scomodo e pessimo odore", review_date=date(2026, 8, 2), rating=Decimal("4.0"), room_code="102")
    from app.eye_services import review_rankings
    ranking = review_rankings(db, hotel_id=hotel.id)
    assert ranking["best_rooms"][0]["room"] == "101"
    assert ranking["worst_rooms"][0]["room"] == "102"


def test_room_rating_timeline_keeps_the_good_period_before_a_drop(db):
    hotel = db.scalar(select(Hotel).where(Hotel.code == "choco"))
    add_review(db, hotel_id=hotel.id, text="Camera pulita e letto comodo", review_date=date(2026, 2, 10), rating=Decimal("9.5"), room_code="1101")
    add_review(db, hotel_id=hotel.id, text="Camera sporca e letto scomodo", review_date=date(2026, 4, 13), rating=Decimal("4"), room_code="1101")
    from app.eye_services import room_rating_timeline
    timeline = room_rating_timeline(db, hotel_id=hotel.id)
    room = next(item for item in timeline if item["room"] == "1101")
    assert room["periods"][0]["from"] == "2026-02-10"
    assert room["periods"][0]["to"] == "2026-04-12"
    assert room["periods"][0]["status"] == "ok"
    assert room["periods"][1]["from"] == "2026-04-13"
    assert room["periods"][1]["status"] == "attenzione"
    assert "Pulizia" in room["periods"][1]["causes"]


BOOKING_DIGEST = """recensioni 27-10-24
10

Ospite A, it   in 26/10/24  out 27/10/24  cam 4407

Numero di prenotazione 1000000001 <https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/booking.html?res_id=1000000001&lang=it&hotel_id=1>

27 ott 2024Nuovo!

________________________________

Categorie base

Staff

10

Pulizia

10

________________________________

una perfetta sinfonia

Personale ultragentile e colazione ricchissima.

10

Ospite B, it   in 26/10/24  out 27/10/24  cam 1108

Numero di prenotazione 1000000002 <https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/booking.html?res_id=1000000002&lang=it&hotel_id=1>

27 ott 2024Nuovo!

________________________________

Categorie base

Staff

10

Pulizia

10

________________________________

8,0

Ospite C, it   in 04/12/2024  out 06/12/24  cam 3306

Numero di prenotazione 1000000003 <https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/booking.html?res_id=1000000003&lang=it&hotel_id=1>

23 gen 2025Nuovo!

________________________________

Categorie base

Staff

7,5

Pulizia

10

________________________________

Letto scomodo e stanza rumorosa

Nulla
"""


def _import_digest(client, content: str = BOOKING_DIGEST):
    return client.post("/api/eye/reviews/import/gio", files=[("files", ("digest.txt", content.encode("utf-8"), "text/plain"))])


def test_import_accepts_comma_ratings_and_keeps_every_review_of_the_file(client, db):
    body = _import_digest(client).json()
    assert body["imported"] == 3
    assert not any("non importata" in e["error"] for e in body["errors"])
    stored = {r.room.code: float(r.rating) for r in db.scalars(select(Review)).all() if r.rating is not None}
    assert stored == {"4407": 10.0, "1108": 10.0, "3306": 8.0}


def test_import_skips_reviews_already_imported(client, db):
    assert _import_digest(client).json()["imported"] == 3
    second = _import_digest(client).json()
    assert second["imported"] == 0 and second["skipped_duplicates"] == 3
    assert len(db.scalars(select(Review)).all()) == 3


def test_import_discards_out_of_scale_ratings_without_losing_the_review():
    from app.routers.eye import _parse_rating
    assert _parse_rating("8,0", "Booking") == Decimal("8.0")
    assert _parse_rating("7,5", "Booking") == Decimal("7.5")
    assert _parse_rating("26", "Booking") is None
    assert _parse_rating("6", "Google") is None
    assert _parse_rating("4,5", "TripAdvisor") == Decimal("4.5")
    assert _parse_rating("abc", "Booking") is None and _parse_rating(None, "Booking") is None


def test_review_list_shows_the_stored_rating_of_imported_reviews(client):
    _import_digest(client)
    ratings = {r["room"]: r["rating"] for r in client.get("/api/eye/reviews", params={"hotel_code": "gio"}).json()}
    assert ratings["4407"] == 10.0 and ratings["3306"] == 8.0


def test_review_txt_import_endpoint(client):
    response = client.post("/api/eye/reviews/import/choco", files=[("files", ("review.txt", b"Recensione - Camera 101 pulita e staff gentile", "text/plain"))])
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    items = client.get("/api/eye/reviews", params={"hotel_code": "choco"}).json()
    assert len(items) == 1


def test_review_import_reports_central_sync_failure_without_losing_local_review(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.eye.central_review_upsert",
        AsyncMock(return_value={"enabled": True, "synced": False, "message": "offline"}),
    )
    response = client.post(
        "/api/eye/reviews/import/choco",
        files=[("files", ("review.txt", b"Recensione - Camera 102 pulita e staff gentile", "text/plain"))],
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["imported"] == 1
    assert payload["errors"][0]["review_id"] == payload["review_ids"][0]
    assert "offline" in payload["errors"][0]["error"]
    assert len(client.get("/api/eye/reviews", params={"hotel_code": "choco"}).json()) == 1


def test_reviews_sync_retries_all_local_reviews_before_pull(client, db, monkeypatch):
    hotel = db.scalar(select(Hotel).where(Hotel.code == "choco"))
    add_review(db, hotel_id=hotel.id, text="Camera 103 pulita", review_date=date(2026, 9, 1), room_code="103")
    monkeypatch.setattr("app.routers.eye.central_configured", lambda: True)
    push = AsyncMock(return_value={"enabled": True, "synced": True})
    monkeypatch.setattr("app.routers.eye.central_review_upsert", push)
    monkeypatch.setattr("app.routers.eye.refresh_review_cache", AsyncMock(return_value={"ok": True, "imported": 0}))
    response = client.post("/api/eye/reviews/sync")
    payload = response.json()
    assert response.status_code == 200
    assert payload["push"]["attempted"] >= 1
    assert payload["push"]["synced"] == payload["push"]["attempted"]
    assert push.await_count == payload["push"]["attempted"]
    assert payload["pull"]["ok"] is True


def test_created_profiles_share_full_access(client):
    developer_token = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"}).json()["session"]
    created = client.post("/api/eye/auth/users", json={"username":"operativo","display_name":"Operativo","role_name":"level1","pin":"654321"}, headers={"X-Eye-Session":developer_token})
    assert created.status_code == 200
    assert created.json()["role_name"] == "supremo"
    user_token = client.post("/api/eye/auth/login", json={"username":"operativo", "pin":"654321"}).json()["session"]
    response = client.get("/api/eye/users", headers={"X-Eye-Session":user_token})
    assert response.status_code == 200


def test_default_pin_unlocks_eye_api_and_session_unlocks_it(client):
    login = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"})
    assert login.status_code == 200
    token = login.json()["session"]
    blocked = client.get("/api/eye/hotels", headers={"X-Eye-Session":"invalid", "X-Eye-Role":"developer"})
    assert blocked.status_code == 401
    allowed = client.get("/api/eye/hotels", headers={"X-Eye-Session":token,"X-Eye-Role":"supremo"})
    assert allowed.status_code == 200
    assert len(allowed.json()) == 3


def test_created_user_has_same_access_level_after_login(client):
    developer_token = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"}).json()["session"]
    created = client.post("/api/eye/auth/users", json={"username":"utente1","display_name":"Utente 1","pin":"654321"}, headers={"X-Eye-Session":developer_token})
    assert created.status_code == 200
    assert created.json()["role_name"] == "supremo"
    login = client.post("/api/eye/auth/login", json={"username":"utente1","pin":"654321"})
    assert login.status_code == 200
    user_token = login.json()["session"]
    protected = client.get("/api/eye/users", headers={"X-Eye-Session":user_token})
    assert protected.status_code == 200


def test_create_user_defaults_to_standard_pin(client):
    developer_token = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"}).json()["session"]
    created = client.post("/api/eye/auth/users", json={"username":"reception","display_name":"Reception"}, headers={"X-Eye-Session":developer_token})
    assert created.status_code == 200
    login = client.post("/api/eye/auth/login", json={"username":"reception","pin":"000000"})
    assert login.status_code == 200
    hotels = client.get("/api/eye/hotels", headers={"X-Eye-Session":login.json()["session"]})
    assert hotels.status_code == 200
    assert len(hotels.json()) == 3



def test_mixed_digest_keeps_google_and_tripadvisor_out_of_booking():
    from app.review_importers import split_review_blocks

    mixed = BOOKING_DIGEST + """

<https://www.google.com/maps/contrib/109917461135353325196?hl=it> Mario Rossi <https://www.google.com/maps/contrib/109917461135353325196?hl=it> 16 ore fa su Google 5/5 Vacanza Hotel ottimo, personale gentile.

Camere economy non all'altezza <https://www.tripadvisor.it/Profile/Abc> Abc ha scritto una recensione 11 lug 2/5 Camera piccola.
"""
    blocks = split_review_blocks(mixed, "2024-10-27", "Booking", None, "x")
    assert [b["source"] for b in blocks] == ["Booking", "Booking", "Booking", "Google", "TripAdvisor"]
    assert [str(b["rating"]) for b in blocks][-2:] == ["5", "2"]
    # il footer che cita altre piattaforme non cambia la fonte di una recensione Booking
    assert blocks[2]["source"] == "Booking"


def test_import_ignores_the_same_file_selected_twice(client, db):
    content = BOOKING_DIGEST.encode("utf-8")
    files = [("files", ("a.txt", content, "text/plain")), ("files", ("b.txt", content, "text/plain"))]
    body = client.post("/api/eye/reviews/import/gio", files=files).json()
    assert body["imported"] == 3 and body["skipped_duplicate_files"] == 1
    assert len(db.scalars(select(Review)).all()) == 3


def test_import_skips_review_already_stored_inside_a_legacy_whole_email(client, db):
    # Archivio vecchio: tutta l'email salvata in un solo record.
    hotel = db.scalar(select(Hotel).where(Hotel.code == "gio"))
    add_review(db, hotel_id=hotel.id, text=BOOKING_DIGEST, review_date=date(2024, 10, 27), rating=None, source="Booking")
    body = _import_digest(client).json()
    assert body["imported"] == 0 and body["skipped_duplicates"] == 3


def _polarities(db, text):
    return {(tag["category"], tag["polarity"]) for tag in classify_review_text(db, text)}


def test_review_classifier_negated_negative_words_become_positive(db):
    # "non lontano" / "non è per nulla lontano": la negazione ribalta la parola negativa
    assert ("Posizione", "positive") in _polarities(db, "La posizione non è lontano dal centro.")
    assert ("Posizione", "positive") in _polarities(db, "Posizione non è per nulla lontana dal centro.")
    assert ("Posizione", "positive") in _polarities(db, "Posizione per niente lontana dal centro.")
    assert ("Posizione", "negative") not in _polarities(db, "Posizione non è per nulla lontana dal centro.")
    # senza negazione resta negativo
    assert ("Posizione", "negative") in _polarities(db, "Posizione lontana dal centro.")


def test_review_classifier_understands_empty_buffet_and_its_negation(db):
    assert ("Colazione", "negative") in _polarities(db, "Il buffet della colazione era vuoto.")
    assert ("Colazione", "positive") in _polarities(db, "Buffet della colazione non per nulla vuoto.")
    assert ("Colazione", "negative") not in _polarities(db, "Buffet della colazione non per nulla vuoto.")
    assert ("Colazione", "positive") in _polarities(db, "Il buffet della colazione non era vuoto, anzi ricco.")


def test_category_scores_are_read_per_tag_and_dates_are_not_votes():
    from app.review_importers import extract_category_scores
    booking = "Categorie base\n\nStaff\n\n10\n\nPulizia\n\n9,0\n\nComfort 8,0 Rapporto qualità/prezzo 7,5 Letti 10 7,0 Antonio, it in 25/10 out 26/10"
    assert extract_category_scores(booking, "Booking") == {"Qualità/prezzo": 7.5, "Staff": 10.0, "Pulizia": 9.0, "Comfort": 8.0, "Letti": 10.0}
    assert extract_category_scores("Camere5,0 Servizio5,0 Posizione4,0 Punti forti", "TripAdvisor") == {"Posizione": 4.0, "Servizi": 5.0, "Camere": 5.0}
    # fuori scala, orari/distanze e date non sono voti
    assert extract_category_scores("Staff 15 Posizione 5 minuti dal centro, Colazione 15/10", "Booking") == {}
    assert extract_category_scores("Staff 9", "Google") == {}


def test_overall_rating_ignores_stay_dates():
    assert _rating("8,0 Thomas, de in 15/10 out 16/10 camera 221") == "8.0"
    assert _rating("10 Luca, it in 26/10/24 out 27/10/24 cam 4407") == "10"


def test_review_list_exposes_category_scores_for_every_review(client):
    _import_digest(client)
    by_room = {r["room"]: r for r in client.get("/api/eye/reviews", params={"hotel_code": "gio"}).json()}
    assert by_room["4407"]["scores"].get("Staff") == 10.0 and by_room["4407"]["scores"].get("Pulizia") == 10.0
    assert all(isinstance(r["scores"], dict) for r in by_room.values())


def test_digest_blocks_without_room_do_not_inherit_the_wrong_room_of_the_whole_email(client, db):
    from app.models import Room
    hotel = db.scalar(select(Hotel).where(Hotel.code == "gio"))
    digest = BOOKING_DIGEST.replace("cam 1108", "cam.")  # un ospite senza numero camera
    # archivio vecchio: l'intera email salvata con una camera letta male
    add_review(db, hotel_id=hotel.id, text=digest, review_date=date(2024, 10, 28), rating=None, room_code="10", source="Booking")
    rooms = [r["room"] for r in client.get("/api/eye/reviews", params={"hotel_code": "gio"}).json()]
    assert "10" not in rooms
    assert rooms.count(None) >= 1


def test_rooms_that_are_words_are_not_exposed_as_rooms(client, db):
    from app.routers.eye import _valid_room
    assert [_valid_room(x) for x in ("325", "4407", "1108A", " 126 ")] == ["325", "4407", "1108A", "126"]
    assert [_valid_room(x) for x in ("pulita", "super", "ampia", "Superior", "e", "Numero", "", None)] == [None] * 8
    hotel = db.scalar(select(Hotel).where(Hotel.code == "gio"))
    add_review(db, hotel_id=hotel.id, text="Camera pulita e spaziosa, personale gentile. Voto 5/5 su Google", review_date=date(2026, 8, 23), rating=Decimal("5"), room_code="pulita", source="Google")
    rooms = [r["room"] for r in client.get("/api/eye/reviews", params={"hotel_code": "gio"}).json()]
    assert "pulita" not in rooms


def test_push_local_reviews_sends_only_unsynced_ones(client, db, monkeypatch):
    import asyncio
    from app import review_cache
    _import_digest(client)
    sent = []

    async def fake_upsert(review):
        sent.append(review["sync_uuid"])
        return {"enabled": True, "synced": True}

    monkeypatch.setattr(review_cache, "central_review_upsert", fake_upsert)
    first = asyncio.run(review_cache.push_local_reviews(db))
    assert first["pushed"] == 3 and len(sent) == 3 and not first["errors"]
    # le copie centrali (stesso testo/data/fonte) non vengono reinviate
    for r in db.scalars(select(Review)).all():
        db.add(CentralReviewCache(sync_uuid="c-" + r.sync_uuid, hotel_code="gio", review_date=r.date, source=r.source, author=r.author, rating=r.rating, room_code=None, text=r.text, payload_json="{}", synced_at=datetime.now()))
    db.commit()
    sent.clear()
    second = asyncio.run(review_cache.push_local_reviews(db))
    assert second["pushed"] == 0 and sent == [] and second["skipped_already_central"] == 3
