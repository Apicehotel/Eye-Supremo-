from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..auth_models import LocalCredential, LocalSession
from ..auth_service import DEFAULT_PIN, auth_configured, create_session, revoke_session, session_user, set_pin, verify_pin
from ..database import get_db
from ..models import UserProfile
from .. import central_identity
from ..auth_models import CentralAccount

router = APIRouter(prefix="/api/eye/auth", tags=["Eye Supremo auth"])
ALLOWED_ROLES = {"developer", "supremo"}
FULL_ACCESS_ROLES = {"developer", "supremo"}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    configured = auth_configured(db)
    central = central_identity.enabled()
    return {"configured": central or configured, "bootstrap_required": not central and not configured,
            "central": central}


@router.get("/login-options")
def login_options(db: Session = Depends(get_db)):
    users = db.scalars(select(UserProfile).where(UserProfile.active.is_(True)).order_by(UserProfile.display_name)).all()
    return [{"username": u.username, "display_name": u.display_name, "role_name": u.role_name} for u in users]


@router.post("/bootstrap")
def bootstrap(payload: dict, db: Session = Depends(get_db)):
    if central_identity.enabled():
        raise HTTPException(403, "Il primo accesso richiede la verifica dell'utente centrale")
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
    return {"session": token, "user": {"id": user.id, "username": user.username, "display_name": user.display_name,
            "role_name": user.role_name, "can_view_reviews": user.can_view_reviews}}


@router.post("/login")
async def login(payload: dict, db: Session = Depends(get_db)):
    if central_identity.enabled():
        return await central_identity.login(db, str(payload.get("username", "")), str(payload.get("pin", "")))
    user = verify_pin(db, str(payload.get("username", "")), str(payload.get("pin", "")))
    if not user:
        raise HTTPException(401, "Utente o PIN non validi")
    token = create_session(db, user)
    return {"session": token, "user": {"id": user.id, "username": user.username, "display_name": user.display_name,
            "role_name": user.role_name, "can_view_reviews": user.can_view_reviews}}


@router.get("/me")
async def me(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    user = session_user(db, x_eye_session)
    if not user:
        raise HTTPException(401, "Sessione non valida")
    identity = await central_identity.identity_for_request(db, x_eye_session, user) if central_identity.enabled() else None
    account = db.get(CentralAccount, user.id) if central_identity.enabled() else None
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role_name": user.role_name, "can_manage_config": user.can_manage_config,
            "can_view_reviews": user.can_view_reviews,
            "central": central_identity.enabled(), "offline": central_identity.enabled() and identity is None,
            "offline_until": account.offline_until.isoformat(timespec="seconds") + "Z" if account and account.offline_until else None}


@router.post("/logout")
async def logout(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    if central_identity.enabled() and x_eye_session:
        await central_identity.logout(x_eye_session)
    revoke_session(db, x_eye_session)
    return {"ok": True}


@router.put("/users/{user_id}/pin")
async def change_pin(user_id: int, payload: dict, x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    target = db.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    try:
        if central_identity.enabled():
            from ..auth_service import validate_pin_format
            validate_pin_format(str(payload.get("pin", "")))
            result = await central_identity.manage(db, x_eye_session, "set_pin", username=target.username, pin=str(payload.get("pin", "")))
            central_identity.mirror(db, result["user"])
            central_identity.invalidate(db, target)
            return {"ok": True, "user_id": user_id, "reauthenticate": target.id == actor.id}
        set_pin(db, target, str(payload.get("pin", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "user_id": user_id}


@router.patch("/users/{user_id}")
async def set_user_status(user_id: int, payload: dict, x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    target = db.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    changing_active = isinstance(payload.get("active"), bool)
    changing_reviews = isinstance(payload.get("can_view_reviews"), bool)
    if changing_active == changing_reviews:
        raise HTTPException(422, "Indica un solo permesso da modificare")
    if changing_reviews:
        can_view_reviews = payload["can_view_reviews"]
        if central_identity.enabled():
            result = await central_identity.manage(
                db, x_eye_session, "set_reviews_access",
                username=target.username, can_view_reviews=can_view_reviews,
            )
            central_identity.mirror(db, result["user"])
        else:
            target.can_view_reviews = can_view_reviews
            db.query(LocalSession).filter(LocalSession.user_id == target.id).delete(synchronize_session=False)
            db.commit()
        return {"id": target.id, "can_view_reviews": target.can_view_reviews}
    active = payload["active"]
    if not active and target.id == actor.id:
        raise HTTPException(400, "Non puoi disattivare l'utente attualmente collegato")
    if central_identity.enabled():
        result = await central_identity.manage(db, x_eye_session, "set_active", username=target.username, active=active)
        central_identity.mirror(db, result["user"])
        return {"id": target.id, "active": target.active}
    if not active and (db.scalar(select(UserProfile.id).where(UserProfile.active.is_(True), UserProfile.id != target.id)) is None):
        raise HTTPException(400, "Deve rimanere almeno un utente attivo")
    target.active = active
    if not active:
        db.query(LocalSession).filter(LocalSession.user_id == target.id).delete(synchronize_session=False)
    db.commit()
    return {"id": target.id, "active": target.active}


@router.get("/users")
async def auth_users(x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    if central_identity.enabled():
        result = await central_identity.manage(db, x_eye_session, "list_users")
        users = []
        for item in result["users"]:
            user = central_identity.mirror(db, item)
            users.append({"id": user.id, "username": user.username, "display_name": user.display_name,
                          "role_name": user.role_name, "active": user.active, "pin_configured": True,
                          "can_view_reviews": user.can_view_reviews, "central": True})
        return users
    credentials = set(db.scalars(select(LocalCredential.user_id)).all())
    users = db.scalars(select(UserProfile).order_by(UserProfile.id)).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name, "role_name": u.role_name,
             "pin_configured": u.id in credentials, "active": u.active,
             "can_view_reviews": u.can_view_reviews} for u in users]


@router.post("/users")
async def create_user(payload: dict, x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"), db: Session = Depends(get_db)):
    actor = session_user(db, x_eye_session)
    if not actor or actor.role_name not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "Profilo non autorizzato")
    username = str(payload.get("username", "")).strip().lower()
    display_name = str(payload.get("display_name", "")).strip()
    # Livelli utente eliminati: ogni nuovo profilo ha gli stessi permessi operativi.
    role_name = "supremo"
    pin = str(payload.get("pin") or DEFAULT_PIN)
    can_view_reviews = payload.get("can_view_reviews", True)
    if not isinstance(can_view_reviews, bool):
        raise HTTPException(422, "Permesso recensioni non valido")
    if not username or not username.replace("_", "").replace("-", "").isalnum() or len(username) > 80:
        raise HTTPException(422, "Username non valido")
    if not display_name or len(display_name) > 160:
        raise HTTPException(422, "Nome visualizzato non valido")
    try:
        from ..auth_service import validate_pin_format
        validate_pin_format(pin)
        if central_identity.enabled():
            if "pin" not in payload or not payload["pin"]:
                raise HTTPException(422, "Scegli un PIN iniziale personale")
            result = await central_identity.manage(
                db, x_eye_session, "create_user", username=username,
                display_name=display_name, pin=pin, can_view_reviews=can_view_reviews,
            )
            user = central_identity.mirror(db, result["user"])
            return {"id": user.id, "username": user.username, "display_name": user.display_name,
                    "role_name": user.role_name, "pin_configured": True, "active": user.active,
                    "can_view_reviews": user.can_view_reviews, "central": True}
        user = UserProfile(username=username, display_name=display_name, role_name=role_name,
                           can_manage_config=True, can_view_reviews=can_view_reviews)
        db.add(user); db.flush(); set_pin(db, user, pin)
    except ValueError as exc:
        db.rollback(); raise HTTPException(422, str(exc))
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Username già esistente")
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "role_name": user.role_name, "pin_configured": True, "active": True,
            "can_view_reviews": user.can_view_reviews}

