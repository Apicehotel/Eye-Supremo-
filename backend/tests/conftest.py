import os, tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="eye-supremo-tests-"))
os.environ["EYESUPREMO_DATA_DIR"] = str(TEST_DIR)

import pytest
from fastapi.testclient import TestClient
from app.database import Base, SessionLocal, engine
from app.eye_services import seed_eye_supremo
from app.search_index import ensure_fts5
from app.main import app

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
    return TestClient(app)
