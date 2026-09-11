import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .auth_models import LocalCredential, LocalSession
from .models import UserProfile

PBKDF2_ITERATIONS = 310_000
SESSION_HOURS = 12


def auth_configured(db: Session) -> bool:
    return (db.scalar(select(func.count(LocalCredential.user_id))) or 0) > 0


def hash_pin(pin: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS).hex()


def validate_pin_format(pin: str) -> None:
    if not pin.isdigit() or not (6 <= len(pin) <= 12):
        raise ValueError("Il PIN deve contenere da 6 a 12 cifre")


def set_pin(db: Session, user: UserProfile, pin: str) -> None:
    validate_pin_format(pin)
    salt = secrets.token_hex(16)
    digest = hash_pin(pin, salt)
    item = db.get(LocalCredential, user.id)
    if item:
        item.salt = salt
        item.pin_hash = digest
    else:
        db.add(LocalCredential(user_id=user.id, salt=salt, pin_hash=digest))
    db.query(LocalSession).filter(LocalSession.user_id == user.id).delete(synchronize_session=False)
    db.commit()


def verify_pin(db: Session, username: str, pin: str) -> UserProfile | None:
    user = db.scalar(select(UserProfile).where(UserProfile.username == username, UserProfile.active.is_(True)))
    if not user:
        return None
    credential = db.get(LocalCredential, user.id)
    if not credential:
        return None
    candidate = hash_pin(pin, credential.salt)
    return user if hmac.compare_digest(candidate, credential.pin_hash) else None


def create_session(db: Session, user: UserProfile) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now() + timedelta(hours=SESSION_HOURS)
    db.add(LocalSession(token_hash=token_hash, user_id=user.id, expires_at=expires))
    db.commit()
    return raw


def session_user(db: Session, raw_token: str | None) -> UserProfile | None:
    if not raw_token:
        return None
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    session = db.get(LocalSession, digest)
    if not session:
        return None
    if session.expires_at < datetime.now():
        db.delete(session); db.commit(); return None
    return db.get(UserProfile, session.user_id)


def revoke_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    session = db.get(LocalSession, digest)
    if session:
        db.delete(session); db.commit()
