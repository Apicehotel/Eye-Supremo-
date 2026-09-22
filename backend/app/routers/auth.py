from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_models import LocalCredential, UserProfile
from ..auth_service import (
    auth_configured,
    create_session,
    revoke_session,
    seed_users,
    serialize_user,
    session_user,
    set_pin,
    verify_pin,
)
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def current_user(
    x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"),
    db: Session = Depends(get_db),
) -> UserProfile:
    user = session_user(db, x_eye_session)
    if not user or not user.active:
        raise HTTPException(401, "Sessione non valida")
    return user


@router.get("/status")
def status(db: Session = Depends(get_db)):
    seed_users(db)
    return {"configured": auth_configured(db), "bootstrap_required": not auth_configured(db)}


@router.post("/bootstrap")
def bootstrap(payload: dict, db: Session = Depends(get_db)):
    seed_users(db)
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
    return {"session": token, "user": serialize_user(developer)}


@router.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    seed_users(db)
    user = verify_pin(db, str(payload.get("username", "")), str(payload.get("pin", "")))
    if not user:
        raise HTTPException(401, "Utente o PIN non validi")
    token = create_session(db, user)
    return {"session": token, "user": serialize_user(user)}


@router.get("/me")
def me(user: UserProfile = Depends(current_user)):
    return serialize_user(user)


@router.post("/logout")
def logout(
    x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"),
    db: Session = Depends(get_db),
):
    revoke_session(db, x_eye_session)
    return {"ok": True}


@router.get("/users")
def auth_users(user: UserProfile = Depends(current_user), db: Session = Depends(get_db)):
    if user.role_name != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore gestisce gli utenti")
    credentials = set(db.scalars(select(LocalCredential.user_id)).all())
    users = db.scalars(select(UserProfile).order_by(UserProfile.id)).all()
    return [
        {
            **serialize_user(u),
            "pin_configured": u.id in credentials,
            "active": u.active,
        }
        for u in users
    ]


@router.put("/users/{user_id}/pin")
def change_pin(user_id: int, payload: dict, user: UserProfile = Depends(current_user), db: Session = Depends(get_db)):
    if user.role_name != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore può configurare i PIN")
    target = db.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    try:
        set_pin(db, target, str(payload.get("pin", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "user_id": user_id}
