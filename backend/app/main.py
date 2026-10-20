import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .auth_service import auth_configured, session_user
from .database import Base, SessionLocal, engine
from .eye_services import seed_eye_supremo
from .local_cache_bootstrap import maybe_schedule_on_startup
from .search_index import ensure_fts5
from .routers.auth_eye import router as auth_router
from .routers.search_eye import router as search_router
from .routers.api import router as legacy_router
from .routers.eye import router as eye_router
from .routers.invoices_eye import router as eye_invoice_router
from .routers.reports_eye import router as reports_router
from .routers.agents_eye import router as agents_router
from .routers.sync_eye import router as sync_router
from .routers.updates_eye import router as updates_router
from . import central_identity


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_eye_supremo(db)
        from .models import AppSetting
        from .product_recognition import set_user_groups
        import json as _json
        row = db.get(AppSetting, "product_groups")
        if row:
            set_user_groups(_json.loads(row.value))
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()
    ensure_fts5(engine)
    # Primo avvio / installazione: scarica fatture e recensioni in cache PC.
    maybe_schedule_on_startup()
    yield


app = FastAPI(title="Eye Supremo API", version="2.0.23", docs_url="/api/docs", lifespan=lifespan)
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
    public_auth = path in {"/api/eye/auth/status", "/api/eye/auth/login-options", "/api/eye/auth/login",
                           "/api/eye/auth/bootstrap", "/api/eye/auth/me", "/api/eye/auth/logout"}
    eye_protected = path.startswith("/api/eye/") and not public_auth
    legacy_admin = path.startswith(DEVELOPER_ONLY_PREFIXES)
    central_protected = central_identity.enabled() and path.startswith("/api/") and not public_auth and path not in {"/api/health", "/api/docs", "/api/openapi.json"}
    identity_context = None
    if eye_protected or legacy_admin or central_protected:
        db = SessionLocal()
        try:
            if central_identity.enabled() or auth_configured(db):
                token = request.headers.get("X-Eye-Session")
                user = session_user(db, token)
                if not user or not user.active:
                    return JSONResponse({"detail": "Sessione Eye Supremo richiesta"}, status_code=401)
                if legacy_admin and user.role_name not in {"developer", "supremo"}:
                    return JSONResponse({"detail": "Profilo non autorizzato"}, status_code=403)
                if central_identity.enabled():
                    try:
                        identity = await central_identity.identity_for_request(db, token, user)
                    except HTTPException as exc:
                        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                    identity_context = central_identity.current_identity.set(identity)
                headers = list(request.scope.get("headers", []))
                headers = [(k, v) for k, v in headers if k.lower() not in {b"x-eye-role", b"x-eye-user"}]
                headers.append((b"x-eye-role", user.role_name.encode("utf-8")))
                headers.append((b"x-eye-user", user.username.encode("utf-8")))
                request.scope["headers"] = headers
        finally:
            db.close()
    try:
        return await call_next(request)
    finally:
        if identity_context is not None:
            central_identity.current_identity.reset(identity_context)


app.include_router(auth_router)
app.include_router(search_router)
app.include_router(reports_router)
app.include_router(agents_router)
app.include_router(legacy_router)
app.include_router(eye_router)
app.include_router(eye_invoice_router)
app.include_router(sync_router)
app.include_router(updates_router)


def frontend_dist() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend_dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


_dist = frontend_dist()
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")

