import os
from pathlib import Path

# Deve stare prima degli import app.*
TEST_DATA = Path(__file__).resolve().parent / "_tmp_data"
TEST_DATA.mkdir(exist_ok=True)
os.environ["ASKFATTURE_DATA_DIR"] = str(TEST_DATA)

from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.import_xml import parse_fatturapa
from app.main import app

FIXTURE = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures" / "fattura.xml"


def setup_function():
    settings.data_dir = TEST_DATA
    (TEST_DATA / "uploads").mkdir(exist_ok=True)
    if settings.database_path.exists():
        settings.database_path.unlink()
    init_db()


def test_parse_fixture():
    assert FIXTURE.exists()
    parsed = parse_fatturapa(FIXTURE)
    assert parsed["numero"] == "42/A"
    assert "EDUF" in parsed["fornitore"]
    assert len(parsed["rows"]) >= 1


def test_import_and_ask_without_ollama(monkeypatch):
    async def no_ollama():
        return {"available": False, "model": "qwen3:1.7b", "model_present": False}

    monkeypatch.setattr("app.ask.ollama_ready", no_ollama)
    with TestClient(app) as client:
        with FIXTURE.open("rb") as f:
            r = client.post("/api/import", files={"file": ("fattura.xml", f, "application/xml")})
        assert r.status_code == 200, r.text
        assert r.json()["rows"] >= 1
        ask = client.post("/api/ask", json={"question": "quanto pago la lampadina?"})
        assert ask.status_code == 200
        body = ask.json()
        assert body["mode"] == "local"
        assert body["sources"]
        assert "answer" in body
