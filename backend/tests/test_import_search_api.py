from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import date
from app.importers import parse_xml
from app.models import Invoice, Supplier
from app.services import duplicate_candidates

FIXTURE = Path(__file__).parent / "fixtures" / "fattura.xml"

def test_xml_structured_parser():
    result = parse_xml(FIXTURE)
    assert result["supplier"]["ragione_sociale"] == "EDUF S.r.l."
    assert result["invoice"]["numero"] == "42/A"
    assert result["rows"][0]["descrizione_normalizzata"] == "lamp led e27 10w"

def test_health_and_empty_search(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/search", params={"q":"lampadina"}).json()["results"] == []

def test_database_and_duplicates(db):
    supplier = Supplier(ragione_sociale="Test"); db.add(supplier); db.flush()
    invoice = Invoice(supplier_id=supplier.id, numero="A1", data=date(2024,1,1), totale=10, imponibile=8, iva=2, hash_file="abc")
    db.add(invoice); db.commit()
    assert duplicate_candidates(db, file_hash="abc")[0].numero == "A1"

def test_ollama_fallback(client):
    with patch("app.routers.api.answer_with_ollama", new=AsyncMock(return_value={"mode":"deterministic","answer":"ok","sources":[]})):
        response = client.post("/api/ai/ask", json={"question":"Quanto ho speso?"})
        assert response.status_code == 200
        assert response.json()["mode"] == "deterministic"

def test_import_preview(client):
    with FIXTURE.open("rb") as f:
        response = client.post("/api/imports/preview", files={"file":("fattura.xml", f, "application/xml")})
    assert response.status_code == 200
    assert response.json()["invoice"]["numero"] == "42/A"

def test_import_confirm(client):
    with FIXTURE.open("rb") as f:
        preview = client.post("/api/imports/preview", files={"file":("fattura.xml", f, "application/xml")}).json()
    confirmed = client.post(f"/api/imports/{preview['job_id']}/confirm", json={})
    assert confirmed.status_code == 200
    detail = client.get(f"/api/invoices/{confirmed.json()['invoice_id']}").json()
    assert detail["numero"] == "42/A" and len(detail["rows"]) == 1
