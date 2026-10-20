import os, tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="eye-supremo-tests-"))
os.environ["EYESUPREMO_DATA_DIR"] = str(TEST_DIR)
# Evita download rete durante i test automatici.
os.environ["EYESUPREMO_CACHE_BOOTSTRAP_ON_START"] = "false"
os.environ["EYESUPREMO_CENTRAL_IDENTITY_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient
from app.database import Base, SessionLocal, engine
from app.eye_services import seed_eye_supremo
from app.search_index import ensure_fts5
from app.main import app
from app.auth_service import create_session
from app.models import UserProfile

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ensure_fts5(engine)
    session = SessionLocal()
    try:
        seed_eye_supremo(session)
    finally:
        session.close()
    yield

@pytest.fixture(autouse=True)
def no_real_supabase(monkeypatch):
    """I test non devono mai raggiungere la Supabase reale (in CI la rete c'è): chi serve la simula."""
    monkeypatch.setattr("app.agent_orchestrator.central_configured", lambda: False)
    # Blocca anche i percorsi RPC/import, non soltanto Ask. Un test deve
    # simulare esplicitamente HTTP: mai leggere o scrivere il centrale reale.
    import httpx
    original_init = httpx.AsyncClient.__init__

    def offline_request(request):
        raise httpx.ConnectError("Rete disabilitata nei test", request=request)

    def isolated_init(self, *args, **kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(offline_request))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", isolated_init)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client():
    test_client = TestClient(app)
    session = SessionLocal()
    try:
        developer = session.query(UserProfile).filter(UserProfile.role_name == "developer").first()
        test_client.headers.update({"X-Eye-Session": create_session(session, developer)})
    finally:
        session.close()
    return test_client

