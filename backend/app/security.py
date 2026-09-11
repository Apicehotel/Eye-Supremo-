from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from .auth_service import auth_configured, session_user
from .database import get_db

VALID_ROLES = {"developer", "supremo", "level1", "level2", "level3"}


def current_role(
    x_eye_session: str | None = Header(default=None, alias="X-Eye-Session"),
    x_eye_role: str = Header(default="developer", alias="X-Eye-Role"),
    db: Session = Depends(get_db),
) -> str:
    if auth_configured(db):
        user = session_user(db, x_eye_session)
        if not user or not user.active:
            raise HTTPException(401, "Sessione Eye Supremo richiesta")
        return user.role_name
    # First-run/dev mode only, before any local PIN exists.
    role = x_eye_role.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(403, "Ruolo non valido")
    return role
