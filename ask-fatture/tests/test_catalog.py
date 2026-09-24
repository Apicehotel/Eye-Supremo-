import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.catalog import upsert_supplier
from app.db import db, init_db
from app.import_xml import parse_fatturapa
from app.main import app

FIXTURE = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures" / "fattura.xml"


def test_parse_supplier_details():
    parsed = parse_fatturapa(FIXTURE)
    s = parsed["supplier"]
    assert "EDUF" in s["ragione_sociale"]
    assert s.get("partita_iva")  # IdCodice in fixture


def test_import_builds_supplier_and_product_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("ASKFATTURE_DATA_DIR", str(tmp_path))
    from app import config

    config.settings.data_dir = tmp_path
    (tmp_path / "uploads").mkdir(exist_ok=True)
    # Force db path under tmp
    monkeypatch.setattr(type(config.settings), "database_path", property(lambda self: tmp_path / "ask.db"))
    init_db()
    with TestClient(app) as client:
        with FIXTURE.open("rb") as f:
            r = client.post("/api/import", files={"file": ("fattura.xml", f, "application/xml")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["supplier_id"]
        assert body["supplier"]["partita_iva"]
        suppliers = client.get("/api/suppliers").json()
        assert len(suppliers) >= 1
        products = client.get("/api/products").json()
        assert len(products) >= 1
        detail = client.get(f"/api/suppliers/{body['supplier_id']}").json()
        assert detail["prodotti"]
        updated = client.put(
            f"/api/suppliers/{body['supplier_id']}",
            json={"sconti": [{"label": "Hotel", "percentuale": 5, "note": "secca"}]},
        )
        assert updated.status_code == 200
        assert updated.json()["sconti"][0]["percentuale"] == 5


def test_upsert_supplier_by_piva(tmp_path, monkeypatch):
    monkeypatch.setenv("ASKFATTURE_DATA_DIR", str(tmp_path))
    from app import config

    config.settings.data_dir = tmp_path
    monkeypatch.setattr(type(config.settings), "database_path", property(lambda self: tmp_path / "ask.db"))
    init_db()
    with db() as conn:
        a = upsert_supplier(conn, {"ragione_sociale": "Alpha", "partita_iva": "123"})
        b = upsert_supplier(conn, {"ragione_sociale": "Alpha Spa", "partita_iva": "123", "citta": "Roma"})
        assert a == b
        row = conn.execute("SELECT * FROM suppliers WHERE id=?", (a,)).fetchone()
        assert row["citta"] == "Roma"
        assert row["ragione_sociale"] == "Alpha Spa"
