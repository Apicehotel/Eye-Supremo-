"""Regressioni del seed ripetuto a ogni avvio dell'applicazione."""
from sqlalchemy import select

from app.auth_models import LocalCredential
from app.auth_service import DEFAULT_PIN, create_session, session_user, set_pin, verify_pin
from app.eye_services import seed_eye_supremo
from app.models import UserProfile


def test_startup_preserves_changed_pin_and_session(db):
    user = db.scalar(select(UserProfile).where(UserProfile.username == "supremo"))
    set_pin(db, user, "654321")
    credential = db.get(LocalCredential, user.id)
    original = (credential.salt, credential.pin_hash, credential.updated_at)
    token = create_session(db, user)

    seed_eye_supremo(db)
    seed_eye_supremo(db)
    db.expire_all()

    credential = db.get(LocalCredential, user.id)
    assert (credential.salt, credential.pin_hash, credential.updated_at) == original
    assert verify_pin(db, user.username, "654321").id == user.id
    assert verify_pin(db, user.username, DEFAULT_PIN) is None
    assert session_user(db, token).id == user.id


def test_startup_preserves_created_inactive_user_pin(db):
    user = UserProfile(username="reception", display_name="Reception", role_name="supremo", active=False)
    db.add(user)
    db.flush()
    set_pin(db, user, "987654")
    credential = db.get(LocalCredential, user.id)
    original = (credential.salt, credential.pin_hash)

    seed_eye_supremo(db)
    db.expire_all()

    credential = db.get(LocalCredential, user.id)
    assert (credential.salt, credential.pin_hash) == original
    assert db.get(UserProfile, user.id).active is False


def test_startup_initializes_only_missing_credentials(db):
    user = db.scalar(select(UserProfile).where(UserProfile.username == "supremo"))
    developer = db.scalar(select(UserProfile).where(UserProfile.username == "sviluppatore"))
    set_pin(db, developer, "654321")
    db.delete(db.get(LocalCredential, user.id))
    db.commit()

    seed_eye_supremo(db)

    assert verify_pin(db, user.username, DEFAULT_PIN).id == user.id
    assert verify_pin(db, developer.username, "654321").id == developer.id
