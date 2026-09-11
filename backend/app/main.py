import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .auth_service import auth_configured, session_user
from .database import Base, SessionLocal, engine
from .eye_services import seed_eye_supremo
from .search_index import ensure_fts5
from .routers.auth_eye import router as auth_router
from .routers.search_eye import router as search_router
from .routers.api import router as legacy_router
from .routers.eye import router as eye_router
from .routers.invoices_eye import router as eye_invoice_router
from .routers.reports_eye import router as reports_router
from .routers.agents_eye import router as agents_router
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


app = FastAPI(title="Eye Supremo API", version="2.1.0", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEVELOPER_ONLY_PREFIXES = ("/api/settings", "/api/backups", "/api/logs")


@app.middleware("http")
async def local_auth_guard(request: Request, call_next):
    path = request.url.path
    public_auth = path.startswith("/api/eye/auth/")
    eye_protected = path.startswith("/api/eye/") and not public_auth
    legacy_admin = path.startswith(DEVELOPER_ONLY_PREFIXES)
    if eye_protected or legacy_admin:
        db = SessionLocal()
        try:
            if auth_configured(db):
                token = request.headers.get("X-Eye-Session")
                user = session_user(db, token)
                if not user or not user.active:
                    return JSONResponse({"detail": "Sessione Eye Supremo richiesta"}, status_code=401)
                if legacy_admin and user.role_name != "developer":
                    return JSONResponse({"detail": "Solo lo Sviluppatore può usare questa funzione"}, status_code=403)
                headers = list(request.scope.get("headers", []))
                headers = [(k, v) for k, v in headers if k.lower() not in {b"x-eye-role", b"x-eye-user"}]
                headers.append((b"x-eye-role", user.role_name.encode("utf-8")))
                headers.append((b"x-eye-user", user.username.encode("utf-8")))
                request.scope["headers"] = headers
        finally:
            db.close()
    return await call_next(request)


app.include_router(auth_router)
app.include_router(search_router)
app.include_router(reports_router)
app.include_router(agents_router)
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
