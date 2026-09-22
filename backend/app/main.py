from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, SessionLocal, engine
from .auth_service import seed_users
from .routers.api import router
from .routers.auth import router as auth_router
from .routers.invoice_builder import router as invoice_builder_router
from .routers.storage import router as storage_router
from .routers.warehouse import router as warehouse_router
# Ensure auth/storage tables are registered on Base.metadata
from . import auth_models  # noqa: F401


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_users(db)
    finally:
        db.close()
    yield


app = FastAPI(title="RandFatture API", version="1.3.0", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(storage_router)
app.include_router(invoice_builder_router)
app.include_router(warehouse_router)
