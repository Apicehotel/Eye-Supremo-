import os, tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="randfatture-tests-"))
os.environ["RANDFATTURE_DATA_DIR"] = str(TEST_DIR)

import pytest
from fastapi.testclient import TestClient
from app.database import Base, SessionLocal, engine
from app.main import app

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
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
