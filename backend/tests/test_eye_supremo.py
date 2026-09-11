from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.eye_services import add_review, invoice_search_summary
from app.search_index import invoice_search
from app.models import Hotel, Invoice, InvoiceRow, InvoiceRowPolicy, Supplier, UserProfile


def test_core_seed(db):
    hotels = db.scalars(select(Hotel).order_by(Hotel.code)).all()
    assert {h.code for h in hotels} == {"gio", "choco", "brigantino"}
    roles = {u.role_name for u in db.scalars(select(UserProfile)).all()}
    assert roles == {"developer", "supremo", "level1", "level2", "level3"}


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


def test_accounting_rows_are_hidden_from_analysis(db):
    supplier = Supplier(ragione_sociale="Fuel Test"); db.add(supplier); db.flush()
    inv = Invoice(supplier_id=supplier.id, numero="F2", data=date(2026, 1, 2), imponibile=50, iva=0, totale=50)
    db.add(inv); db.flush()
    row = InvoiceRow(invoice_id=inv.id, descrizione_originale="Carburante", descrizione_normalizzata="carburante", quantita=1, prezzo_unitario=50, totale_riga=50, confidence=1)
    db.add(row); db.flush(); db.add(InvoiceRowPolicy(row_id=row.id, analysis_status="accounting_excluded", exclusion_reason="carburante")); db.commit()
    assert invoice_search(db, "carburante", limit=20) == []


def test_review_ranking_best_and_worst(db):
    hotel = db.scalar(select(Hotel).where(Hotel.code == "choco"))
    add_review(db, hotel_id=hotel.id, text="Camera 101 pulita, letto comodo e staff gentile", review_date=date(2026, 8, 1), rating=Decimal("9.5"), room_code="101")
    add_review(db, hotel_id=hotel.id, text="Camera 102 sporca, letto scomodo e pessimo odore", review_date=date(2026, 8, 2), rating=Decimal("4.0"), room_code="102")
    from app.eye_services import review_rankings
    ranking = review_rankings(db, hotel_id=hotel.id)
    assert ranking["best_rooms"][0]["room"] == "101"
    assert ranking["worst_rooms"][0]["room"] == "102"


def test_review_txt_import_endpoint(client):
    response = client.post("/api/eye/reviews/import/choco", files=[("files", ("review.txt", b"Camera pulita e staff gentile", "text/plain"))])
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    items = client.get("/api/eye/reviews", params={"hotel_code": "choco"}).json()
    assert len(items) == 1


def test_non_developer_cannot_manage_users(client):
    response = client.get("/api/eye/users", headers={"X-Eye-Role": "level1"})
    assert response.status_code == 403


def test_bootstrap_locks_eye_api_and_session_unlocks_it(client):
    bootstrap = client.post("/api/eye/auth/bootstrap", json={"pin":"123456"})
    assert bootstrap.status_code == 200
    token = bootstrap.json()["session"]
    blocked = client.get("/api/eye/hotels", headers={"X-Eye-Role":"developer"})
    assert blocked.status_code == 401
    allowed = client.get("/api/eye/hotels", headers={"X-Eye-Session":token,"X-Eye-Role":"level1"})
    assert allowed.status_code == 200


def test_level_user_cannot_spoof_developer_after_login(client):
    bootstrap = client.post("/api/eye/auth/bootstrap", json={"pin":"123456"}).json()
    developer_token = bootstrap["session"]
    users = client.get("/api/eye/auth/users", headers={"X-Eye-Session":developer_token}).json()
    level1 = next(u for u in users if u["role_name"] == "level1")
    changed = client.put(f"/api/eye/auth/users/{level1['id']}/pin", json={"pin":"654321"}, headers={"X-Eye-Session":developer_token})
    assert changed.status_code == 200
    login = client.post("/api/eye/auth/login", json={"username":"livello1","pin":"654321"})
    assert login.status_code == 200
    level_token = login.json()["session"]
    protected = client.get("/api/eye/users", headers={"X-Eye-Session":level_token,"X-Eye-Role":"developer"})
    assert protected.status_code == 403
