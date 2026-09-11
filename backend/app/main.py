from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, SessionLocal, engine
from .eye_services import seed_eye_supremo
from .routers.api import router as legacy_router
from .routers.eye import router as eye_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_eye_supremo(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Eye Supremo API", version="2.0.0", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(legacy_router)
app.include_router(eye_router)
