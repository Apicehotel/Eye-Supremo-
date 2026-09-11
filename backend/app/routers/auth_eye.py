from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auth_models import LocalCredential
from ..auth_service import auth_configured, create_session, revoke_session, session_user, set_pin, verify_pin
from ..database import get_db
from ..models import UserProfile

router = APIRouter(prefix="/api/eye/auth", tags=["Eye Supremo auth"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    configured = auth_configured(db)
    return {"configured": configured, "bootstrap_required": not configured}


@router.post("/bootstrap")
def bootstrap(payload: dict, db: Session = Depends(get_db)):
    if auth_configured(db):
        raise HTTPException(409, "Configurazione iniziale già completata")
    pin = str(payload.get("pin", ""))
    developer = db.scalar(select(UserProfile).where(UserProfile.role_name == "developer"))
    if not developer:
        raise HTTPException(500, "Profilo Sviluppatore mancante")
    try:
        set_pin(db, developer, pin)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    token = create_session(db, developer)
    return {"session": token, "user": {"id": developer.id, "username": developer.username, "display_name": developer.display_name, "role_name": developer.role_name}}


@router.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    user = verify_pin(db, str(payload.get("username", "")), str(payload.get("pin", "")))
    if not user:
        raise HTTPException(401, "Utente o PIN non validi")
    token = create_session(db, user)
    return {"session": token, "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role_name": user.role_name}}


@router.get("/me")
def me(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    user = session_user(db, x_eye_session)
    if not user:
        raise HTTPException(401, "Sessione non valida")
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role_name": user.role_name, "can_manage_config": user.can_manage_config}


@router.post("/logout")
def logout(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    revoke_session(db, x_eye_session)
    return {"ok": True}


@router.put("/users/{user_id}/pin")
def change_pin(user_id: int, payload: dict, x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore può configurare i PIN")
    target = db.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    try:
        set_pin(db, target, str(payload.get("pin", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "user_id": user_id}


@router.get("/users")
def auth_users(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore gestisce gli utenti")
    credentials = set(db.scalars(select(LocalCredential.user_id)).all())
    users = db.scalars(select(UserProfile).order_by(UserProfile.id)).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name, "role_name": u.role_name, "pin_configured": u.id in credentials, "active": u.active} for u in users]
