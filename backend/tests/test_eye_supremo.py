from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.eye_services import add_review, classify_review_text, invoice_search_summary
from app.search_index import invoice_search
from app.models import AppSetting, CentralInvoiceCache, Hotel, Invoice, InvoiceRow, InvoiceRowPolicy, Supplier, UserProfile
from app.agent_orchestrator import _max_invoice_context
from app.report_service import historical_product_report
from app.review_importers import _author, _room, split_review_blocks
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
    assert "lamp" not in search_terms("lampadine")
    assert is_family_match("lampadina LED E27", "lampadine")
    assert not is_family_match("lamponi surgelati", "lampadine")
    assert is_family_match("carta fotoc A4 risma 500ff", "a4")
    assert not is_family_match("plastificatrice formato A4", "a4")
    assert is_family_match("acqua naturale 0,5 lt", "acqua")
    assert not is_family_match("acquedotto tariffa base", "acqua")
    assert "bombolino" in search_terms("bomboloni")


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
    group = next(row for row in rows if row["nome_canonico"] == "Acqua 0,75 l")
    assert group["purchases"] == 3


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
    half_litre = next(row for row in rows if row["nome_canonico"] == "Acqua 0,5 l")
    assert half_litre["purchases"] == 5
    assert set(half_litre["canonical_names"]) == {"acqua naturale 0 5 l", "acqua frizzante 500 ml"}
    assert any(row["nome_canonico"] == "Acqua naturale 0,75 l" for row in rows)


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


def test_review_import_extracts_google_author_and_rejects_freeform_room():
    digest = "Google nessuna recensione Valter Hotel Gio Wine e Jazz Area reception@hotelgio.it"
    assert _author(digest, "reception@hotelgio.it") == "Valter"
    assert _room("Camera ok, letto e lenzuola rigide.") is None
    assert _room("CAM: 2219") == "2219"


def test_review_classifier_keeps_mixed_aspects_separate(db):
    text = "Camera ok, letto e lenzuola rigide. Colazione super, ristorante scarso. Croissant da migliorare."
    tags = classify_review_text(db, text)
    pairs = {(tag["category"], tag["polarity"]) for tag in tags}
    assert ("Camere / Arredi", "positive") in pairs
    assert ("Letti", "negative") in pairs
    assert ("Colazione", "positive") in pairs
    assert ("Ristorante", "negative") in pairs
    assert ("Colazione", "negative") in pairs


def test_review_ranking_best_and_worst(db):
    hotel = db.scalar(select(Hotel).where(Hotel.code == "choco"))
    add_review(db, hotel_id=hotel.id, text="Camera 101 pulita, letto comodo e staff gentile", review_date=date(2026, 8, 1), rating=Decimal("9.5"), room_code="101")
    add_review(db, hotel_id=hotel.id, text="Camera 102 sporca, letto scomodo e pessimo odore", review_date=date(2026, 8, 2), rating=Decimal("4.0"), room_code="102")
    from app.eye_services import review_rankings
    ranking = review_rankings(db, hotel_id=hotel.id)
    assert ranking["best_rooms"][0]["room"] == "101"
    assert ranking["worst_rooms"][0]["room"] == "102"


def test_review_txt_import_endpoint(client):
    response = client.post("/api/eye/reviews/import/choco", files=[("files", ("review.txt", b"Recensione - Camera 101 pulita e staff gentile", "text/plain"))])
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    items = client.get("/api/eye/reviews", params={"hotel_code": "choco"}).json()
    assert len(items) == 1


def test_created_profiles_share_full_access(client):
    developer_token = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"}).json()["session"]
    created = client.post("/api/eye/auth/users", json={"username":"levelcheck","display_name":"Level Check","role_name":"level1","pin":"654321"}, headers={"X-Eye-Session":developer_token})
    assert created.status_code == 200
    level_token = client.post("/api/eye/auth/login", json={"username":"levelcheck", "pin":"654321"}).json()["session"]
    response = client.get("/api/eye/users", headers={"X-Eye-Session":level_token, "X-Eye-Role": "developer"})
    assert response.status_code == 200


def test_default_pin_unlocks_eye_api_and_session_unlocks_it(client):
    login = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"})
    assert login.status_code == 200
    token = login.json()["session"]
    blocked = client.get("/api/eye/hotels", headers={"X-Eye-Session":"invalid", "X-Eye-Role":"developer"})
    assert blocked.status_code == 401
    allowed = client.get("/api/eye/hotels", headers={"X-Eye-Session":token,"X-Eye-Role":"level1"})
    assert allowed.status_code == 200
    assert len(allowed.json()) == 3


def test_created_user_has_same_access_level_after_login(client):
    developer_token = client.post("/api/eye/auth/login", json={"username":"sviluppatore", "pin":"000000"}).json()["session"]
    users = client.get("/api/eye/auth/users", headers={"X-Eye-Session":developer_token}).json()
    created = client.post("/api/eye/auth/users", json={"username":"utente1","display_name":"Utente 1","role_name":"level1","pin":"654321"}, headers={"X-Eye-Session":developer_token})
    assert created.status_code == 200
    login = client.post("/api/eye/auth/login", json={"username":"utente1","pin":"654321"})
    assert login.status_code == 200
    level_token = login.json()["session"]
    protected = client.get("/api/eye/users", headers={"X-Eye-Session":level_token,"X-Eye-Role":"developer"})
    assert protected.status_code == 200
