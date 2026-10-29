"""Identità centrale personale e autorizzazione offline limitata nel tempo.

I token remoti sono mantenuti solo in memoria e non sono esposti al browser.
Il PIN viene trasmesso via HTTPS al login, mai memorizzato in chiaro.
"""
from __future__ import annotations

import hashlib
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_models import CentralAccount, LocalCredential, LocalSession
from .auth_service import create_session, set_pin, verify_pin, validate_pin_format
from .config import settings
from .models import UserProfile


@dataclass
class Identity:
    username: str
    token: str
    user_id: int
    expires_at: datetime
    checked_at: float


# La chiave è l'hash della sessione locale; ogni richiesta usa il proprio contesto.
_IDENTITIES: dict[str, Identity] = {}
_LOCAL_LOGINS: dict[str, datetime] = {}
_OFFLINE_PROBES: dict[str, float] = {}
current_identity: ContextVar[Identity | None] = ContextVar("eye_identity", default=None)


class CentralUnavailable(Exception):
    pass


def enabled() -> bool:
    return settings.central_identity_enabled


def session_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def remote(action: str, *, token: str | None = None, **payload) -> dict:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Configura Supabase per usare gli utenti centrali")
    if not settings.supabase_url.startswith("https://"):
        raise HTTPException(503, "Il login centrale richiede HTTPS")
    url = settings.supabase_url.rstrip("/") + "/functions/v1/" + settings.central_identity_function
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(url, json={"action": action, **payload}, headers={
                "apikey": settings.supabase_publishable_key,
                **({"Authorization": f"Bearer {token}"} if token else {}),
            })
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        raise CentralUnavailable() from exc
    if response.status_code in {502, 503, 504}:
        raise CentralUnavailable()
    messages = {401: "Credenziali o sessione centrale non valide", 403: "Operazione centrale non autorizzata",
                409: "Username già esistente", 422: "Dati del profilo o PIN non validi",
                429: "Troppi tentativi: attendi alcuni minuti prima di riprovare"}
    if not response.is_success:
        raise HTTPException(response.status_code if response.status_code in messages else 503,
                            messages.get(response.status_code, "Servizio utenti centrali da aggiornare o non disponibile"))
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(503, "Risposta del servizio utenti centrali non valida") from exc
    if not isinstance(data, dict):
        raise HTTPException(503, "Risposta del servizio utenti centrali non valida")
    return data


def invalidate(db: Session, user: UserProfile) -> None:
    account = db.get(CentralAccount, user.id)
    if account:
        account.offline_until = None
    for key in db.scalars(select(LocalSession.token_hash).where(LocalSession.user_id == user.id)):
        _LOCAL_LOGINS.pop(key, None)
        _OFFLINE_PROBES.pop(key, None)
    db.query(LocalSession).filter(LocalSession.user_id == user.id).delete(synchronize_session=False)
    for key, identity in list(_IDENTITIES.items()):
        if identity.user_id == user.id:
            _IDENTITIES.pop(key, None)
    db.commit()


def mirror(db: Session, item: dict) -> UserProfile:
    """Aggiorna il profilo ma non copia mai un hash PIN da un altro PC."""
    username = str(item["username"])
    user = db.scalar(select(UserProfile).where(UserProfile.username == username))
    if user is None:
        user = UserProfile(username=username, display_name=item["display_name"], role_name=item["role"])
        db.add(user); db.flush()
    account = db.get(CentralAccount, user.id)
    version = int(item["auth_version"])
    if account is not None and (account.auth_version != version or not item["active"]):
        invalidate(db, user)
        credential = db.get(LocalCredential, user.id)
        if credential:
            db.delete(credential)
    if account is None:
        account = CentralAccount(user_id=user.id, username=username, auth_version=version)
        db.add(account)
    account.auth_version = version
    user.display_name = item["display_name"]
    user.role_name = item["role"]
    user.can_manage_config = item["role"] in {"supremo", "developer"}
    user.can_view_reviews = bool(item.get("can_view_reviews", True))
    user.active = bool(item["active"])
    db.commit()
    return user


async def login(db: Session, username: str, pin: str) -> dict:
    try:
        validate_pin_format(pin)
    except ValueError:
        raise HTTPException(401, "Utente o PIN non validi")
    username = username.strip().lower()
    try:
        result = await remote("login", username=username, pin=pin)
    except CentralUnavailable:
        user = verify_pin(db, username, pin)
        account = db.get(CentralAccount, user.id) if user else None
        if not user or not account or not account.offline_until or account.offline_until <= datetime.now(UTC).replace(tzinfo=None):
            raise HTTPException(503, "Primo accesso o autorizzazione scaduta: collega il PC a Internet")
        return auth_payload(create_session(db, user), user, account, offline=True)
    except HTTPException as exc:
        if exc.status_code == 401:
            user = db.scalar(select(UserProfile).where(UserProfile.username == username))
            if user:
                invalidate(db, user)
        raise
    user = mirror(db, result["user"])
    if not user.active:
        invalidate(db, user)
        raise HTTPException(401, "Profilo disattivato")
    set_pin(db, user, pin)
    account = db.get(CentralAccount, user.id)
    account.verified_at = datetime.now(UTC).replace(tzinfo=None)
    # La lease non si rinnova usando il solo token: richiede un nuovo login con PIN.
    account.offline_until = account.verified_at + timedelta(days=settings.offline_access_days)
    db.commit()
    local_token = create_session(db, user)
    expires_at = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    # Rimuove token di sessioni scadute; nessun accumulo illimitato.
    for key, identity in list(_IDENTITIES.items()):
        if identity.expires_at <= datetime.now(UTC).replace(tzinfo=None):
            _IDENTITIES.pop(key, None)
    _IDENTITIES[session_key(local_token)] = Identity(username, result["token"], user.id, expires_at, time.monotonic())
    if settings.cache_bootstrap_on_start:
        context = current_identity.set(_IDENTITIES[session_key(local_token)])
        try:
            from .local_cache_bootstrap import maybe_schedule_on_startup
            maybe_schedule_on_startup()
        finally:
            current_identity.reset(context)
    return auth_payload(local_token, user, account, offline=False)


def auth_payload(token: str, user: UserProfile, account: CentralAccount, *, offline: bool) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    for key, expires_at in list(_LOCAL_LOGINS.items()):
        if expires_at <= now:
            _LOCAL_LOGINS.pop(key, None)
            _OFFLINE_PROBES.pop(key, None)
    _LOCAL_LOGINS[session_key(token)] = now + timedelta(hours=12)
    if offline:
        _OFFLINE_PROBES[session_key(token)] = time.monotonic()
    return {"session": token, "user": {"id": user.id, "username": user.username,
            "display_name": user.display_name, "role_name": user.role_name,
            "can_view_reviews": user.can_view_reviews},
            "offline": offline, "offline_until": account.offline_until.isoformat(timespec="seconds") + "Z" if account.offline_until else None}


async def identity_for_request(db: Session, local_token: str, user: UserProfile) -> Identity | None:
    key = session_key(local_token)
    identity = _IDENTITIES.get(key)
    if identity is None:
        # Dopo un accesso offline, rileva il ritorno del servizio senza inviare
        # il PIN: richiede un nuovo login, che verifica revoche e cambi PIN.
        if time.monotonic() - _OFFLINE_PROBES.get(key, 0) >= 60:
            _OFFLINE_PROBES[key] = time.monotonic()
            try:
                result = await remote("availability")
            except (CentralUnavailable, HTTPException):
                return None
            if result.get("available") is True:
                _LOCAL_LOGINS.pop(key, None)
                raise HTTPException(401, "Connessione ripristinata: accedi per verificare il profilo centrale")
        return None
    if identity.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        _IDENTITIES.pop(key, None)
        return None
    if time.monotonic() - identity.checked_at >= 60:
        try:
            result = await remote("me", token=identity.token)
        except CentralUnavailable:
            # La richiesta può usare SQLite, ma nessuna credenziale condivisa.
            return None
        except HTTPException as exc:
            if exc.status_code in {401, 403}:
                invalidate(db, user)
            raise
        mirror(db, result["user"])
        if not user.active or session_key(local_token) not in _IDENTITIES:
            raise HTTPException(401, "Sessione revocata: accedi nuovamente")
        identity.checked_at = time.monotonic()
    return identity


def require_identity(local_token: str) -> Identity:
    identity = _IDENTITIES.get(session_key(local_token))
    if identity is None or identity.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(503, "Gestione utenti disponibile online: accedi nuovamente con il PIN")
    return identity


async def manage(db: Session, local_token: str, action: str, **payload) -> dict:
    identity = require_identity(local_token)
    try:
        return await remote(action, token=identity.token, **payload)
    except CentralUnavailable:
        raise HTTPException(503, "Gestione utenti disponibile solo con connessione al centrale")
    except HTTPException as exc:
        if exc.status_code in {401, 403}:
            user = db.get(UserProfile, identity.user_id)
            if user:
                invalidate(db, user)
        raise


async def logout(local_token: str) -> None:
    _LOCAL_LOGINS.pop(session_key(local_token), None)
    _OFFLINE_PROBES.pop(session_key(local_token), None)
    identity = _IDENTITIES.pop(session_key(local_token), None)
    if identity:
        try:
            await remote("logout", token=identity.token)
        except (CentralUnavailable, HTTPException):
            pass  # Il token remoto scade comunque; quello locale viene sempre revocato.
