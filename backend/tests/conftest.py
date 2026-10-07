import os, tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="eye-supremo-tests-"))
os.environ["EYESUPREMO_DATA_DIR"] = str(TEST_DIR)
# Evita download rete durante i test automatici.
os.environ["EYESUPREMO_CACHE_BOOTSTRAP_ON_START"] = "false"

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
