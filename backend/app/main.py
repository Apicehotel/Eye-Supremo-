import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import Base, SessionLocal, engine
from .eye_services import seed_eye_supremo
from .search_index import ensure_fts5
from .routers.search_eye import router as search_router
from .routers.api import router as legacy_router
from .routers.eye import router as eye_router
from .routers.invoices_eye import router as eye_invoice_router
from .routers.sync_eye import router as sync_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_eye_supremo(db)
    finally:
        db.close()
    ensure_fts5(engine)
    yield


app = FastAPI(title="Eye Supremo API", version="2.0.0", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(search_router)
app.include_router(legacy_router)
app.include_router(eye_router)
app.include_router(eye_invoice_router)
app.include_router(sync_router)


def frontend_dist() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend_dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


_dist = frontend_dist()
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
