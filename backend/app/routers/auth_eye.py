from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..auth_models import LocalCredential, LocalSession
from ..auth_service import auth_configured, create_session, revoke_session, session_user, set_pin, verify_pin
from ..database import get_db
from ..models import UserProfile

router = APIRouter(prefix="/api/eye/auth", tags=["Eye Supremo auth"])
ALLOWED_ROLES = {"developer", "supremo", "level1", "level2", "level3"}
FULL_ACCESS_ROLES = {"developer", "supremo"}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    configured = auth_configured(db)
    return {"configured": configured, "bootstrap_required": not configured}


@router.get("/login-options")
def login_options(db: Session = Depends(get_db)):
    users = db.scalars(select(UserProfile).where(UserProfile.active.is_(True)).order_by(UserProfile.display_name)).all()
    return [{"username": u.username, "display_name": u.display_name, "role_name": u.role_name} for u in users]


@router.post("/bootstrap")
def bootstrap(payload: dict, db: Session = Depends(get_db)):
    if auth_configured(db):
        raise HTTPException(409, "Configurazione iniziale già completata")
    pin = str(payload.get("pin", ""))
    username = str(payload.get("username", "")).strip().lower()
    user = db.scalar(select(UserProfile).where(UserProfile.username == username, UserProfile.active.is_(True))) if username else None
    if not user:
        user = db.scalar(select(UserProfile).where(UserProfile.role_name == "developer", UserProfile.active.is_(True)))
    if not user:
        raise HTTPException(500, "Nessun profilo utente disponibile")
    try:
        set_pin(db, user, pin)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    token = create_session(db, user)
    return {"session": token, "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role_name": user.role_name}}


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
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    target = db.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    try:
        set_pin(db, target, str(payload.get("pin", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "user_id": user_id}


@router.patch("/users/{user_id}")
def set_user_status(user_id: int, payload: dict, x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    target = db.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    active = bool(payload.get("active"))
    if not active and target.id == actor.id:
        raise HTTPException(400, "Non puoi disattivare l'utente attualmente collegato")
    if not active and (db.scalar(select(UserProfile.id).where(UserProfile.active.is_(True), UserProfile.id != target.id)) is None):
        raise HTTPException(400, "Deve rimanere almeno un utente attivo")
    target.active = active
    if not active:
        db.query(LocalSession).filter(LocalSession.user_id == target.id).delete(synchronize_session=False)
    db.commit()
    return {"id": target.id, "active": target.active}


@router.get("/users")
def auth_users(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    credentials = set(db.scalars(select(LocalCredential.user_id)).all())
    users = db.scalars(select(UserProfile).order_by(UserProfile.id)).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name, "role_name": u.role_name, "pin_configured": u.id in credentials, "active": u.active} for u in users]


@router.post("/users")
def create_user(payload: dict, x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    username = str(payload.get("username", "")).strip().lower()
    display_name = str(payload.get("display_name", "")).strip()
    # I livelli sono temporaneamente disattivati: ogni nuovo profilo ha
    # lo stesso comportamento operativo del profilo Supremo.
    role_name = "supremo"
    pin = str(payload.get("pin", ""))
    if not username or not username.replace("_", "").replace("-", "").isalnum() or len(username) > 80:
        raise HTTPException(422, "Username non valido")
    if not display_name or len(display_name) > 160:
        raise HTTPException(422, "Nome visualizzato non valido")
    try:
        from ..auth_service import validate_pin_format
        validate_pin_format(pin)
        user = UserProfile(username=username, display_name=display_name, role_name=role_name, can_manage_config=True)
        db.add(user); db.flush(); set_pin(db, user, pin)
    except ValueError as exc:
        db.rollback(); raise HTTPException(422, str(exc))
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Username già esistente")
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role_name": user.role_name, "pin_configured": True, "active": True}
