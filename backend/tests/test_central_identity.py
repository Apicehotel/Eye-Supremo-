import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import central_identity as identity
from app.auth_models import CentralAccount, LocalCredential
from app.auth_service import session_user, verify_pin
from app.config import settings
from app.database import Base
from app.main import app
from app.models import UserProfile


@pytest.fixture
def central(monkeypatch):
    monkeypatch.setattr(settings, 'central_identity_enabled', True)
    identity._IDENTITIES.clear()
    identity._LOCAL_LOGINS.clear()
    identity._OFFLINE_PROBES.clear()
    users = {'alice': {'username': 'alice', 'display_name': 'Alice', 'role': 'supremo',
                       'active': True, 'auth_version': 1, 'pin': '654321'}}
    tokens = {}
    async def remote(action, token=None, **payload):
        if action == 'availability': return {'available':True}
        if action == 'login':
            user = users.get(payload['username'])
            if not user or not user['active'] or user['pin'] != payload['pin']:
                raise HTTPException(401, 'Credenziali non valide')
            token = 'eye1_' + str(len(tokens)+1).zfill(64)
            tokens[token] = (user['username'], user['auth_version'])
            return {'user': {k:v for k,v in user.items() if k!='pin'}, 'token': token,
                    'expires_at': (datetime.now(UTC).replace(tzinfo=None)+timedelta(hours=12)).isoformat()+'Z'}
        principal = tokens.get(token)
        user = users.get(principal[0]) if principal else None
        if not user or not user['active'] or principal[1] != user['auth_version']:
            raise HTTPException(401, 'Sessione revocata')
        if action == 'me': return {'user': {k:v for k,v in user.items() if k!='pin'}}
        if action == 'logout': tokens.pop(token, None); return {'ok':True}
        if action == 'list_users': return {'users':[{k:v for k,v in u.items() if k!='pin'} for u in users.values()]}
        username = payload['username']
        if action == 'create_user':
            if username in users: raise HTTPException(409, 'Username esistente')
            users[username] = {'username':username,'display_name':payload['display_name'],'pin':payload['pin'],
                               'role':'supremo','active':True,'auth_version':1}
        elif action == 'set_pin':
            users[username]['pin'] = payload['pin']; users[username]['auth_version'] += 1
        elif action == 'set_active':
            users[username]['active'] = payload['active']; users[username]['auth_version'] += 1
        return {'user':{k:v for k,v in users[username].items() if k!='pin'}}
    monkeypatch.setattr(identity, 'remote', remote)
    yield users
    identity._IDENTITIES.clear()
    identity._LOCAL_LOGINS.clear()
    identity._OFFLINE_PROBES.clear()


@pytest.fixture
def central_client(central):
    return TestClient(app)


def login(client, username='alice', pin='654321'):
    response = client.post('/api/eye/auth/login', json={'username':username,'pin':pin})
    assert response.status_code == 200, response.text
    client.headers['X-Eye-Session'] = response.json()['session']
    return response.json()


async def unavailable(*args, **kwargs):
    raise identity.CentralUnavailable()


def test_first_login_requires_online_even_with_old_local_default(central_client, monkeypatch):
    monkeypatch.setattr(identity, 'remote', unavailable)
    response = central_client.post('/api/eye/auth/login', json={'username':'supremo','pin':'000000'})
    assert response.status_code == 503
    assert central_client.post('/api/eye/auth/bootstrap', json={'pin':'654321'}).status_code == 403


def test_online_login_caches_only_personal_verifier(central_client, db):
    payload = login(central_client)
    user = db.scalar(select(UserProfile).where(UserProfile.username=='alice'))
    credential = db.get(LocalCredential, user.id)
    assert verify_pin(db, 'alice', '654321').id == user.id
    assert credential.pin_hash != '654321'
    assert 'token' not in payload and 'pin' not in str(payload)
    account = db.get(CentralAccount, user.id)
    assert timedelta(days=6) < account.offline_until-datetime.now(UTC).replace(tzinfo=None) <= timedelta(days=7)
    assert central_client.get('/api/eye/hotels').status_code == 200


def test_offline_login_does_not_renew_lease(central_client, db, monkeypatch):
    online = login(central_client)
    user = db.scalar(select(UserProfile).where(UserProfile.username=='alice'))
    until = db.get(CentralAccount, user.id).offline_until
    monkeypatch.setattr(identity, 'remote', unavailable)
    offline = login(central_client)
    assert offline['offline'] is True
    db.expire_all()
    assert db.get(CentralAccount, user.id).offline_until == until
    account = db.get(CentralAccount, user.id)
    account.offline_until = datetime.now(UTC).replace(tzinfo=None)-timedelta(seconds=1); db.commit()
    assert session_user(db, online['session']) is None
    assert central_client.get('/api/eye/hotels').status_code == 401
    assert central_client.post('/api/eye/auth/login', json={'username':'alice','pin':'654321'}).status_code == 503


def test_remote_rejection_never_falls_back_to_cached_pin(central_client, central, db):
    payload = login(central_client)
    central['alice']['pin'] = '789654'
    response = central_client.post('/api/eye/auth/login', json={'username':'alice','pin':'654321'})
    assert response.status_code == 401
    assert session_user(db, payload['session']) is None


def test_rate_limit_does_not_enable_offline_bypass(central_client, monkeypatch):
    login(central_client)
    async def limited(*args, **kwargs): raise HTTPException(429, 'Troppi tentativi')
    monkeypatch.setattr(identity, 'remote', limited)
    assert central_client.post('/api/eye/auth/login', json={'username':'alice','pin':'654321'}).status_code == 429


def test_create_user_is_central_and_another_pc_can_login(central_client, central, db):
    login(central_client)
    response = central_client.post('/api/eye/auth/users', json={'username':'bob','display_name':'Bob','pin':'789654'})
    assert response.status_code == 200
    assert 'bob' in central
    user = db.get(UserProfile, response.json()['id'])
    assert db.get(LocalCredential, user.id) is None
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as pc2:
        result = asyncio.run(identity.login(pc2, 'bob', '789654'))
        assert result['user']['username'] == 'bob'
        assert verify_pin(pc2,'bob','789654')
    engine.dispose()


def test_create_failure_never_creates_local_only_user(central_client, db, monkeypatch):
    login(central_client)
    monkeypatch.setattr(identity, 'remote', unavailable)
    response = central_client.post('/api/eye/auth/users', json={'username':'bob','display_name':'Bob','pin':'789654'})
    assert response.status_code == 503
    assert db.scalar(select(UserProfile).where(UserProfile.username=='bob')) is None


def test_directory_contains_metadata_not_offline_credentials(central_client, db, central):
    central['bob'] = {'username':'bob','display_name':'Bob','role':'supremo','active':True,'auth_version':1,'pin':'789654'}
    login(central_client)
    response = central_client.get('/api/eye/auth/users')
    assert response.status_code == 200
    bob = next(u for u in response.json() if u['username']=='bob')
    assert db.get(LocalCredential,bob['id']) is None
    assert '789654' not in response.text and 'pin_hash' not in response.text


def test_change_own_pin_revokes_session_and_requires_new_login(central_client, db):
    payload = login(central_client)
    response = central_client.put(f"/api/eye/auth/users/{payload['user']['id']}/pin", json={'pin':'789654'})
    assert response.status_code == 200 and response.json()['reauthenticate']
    assert session_user(db, payload['session']) is None
    assert central_client.get('/api/eye/hotels').status_code == 401
    assert login(central_client, pin='789654')['offline'] is False


def test_revalidation_detects_remote_disable(central_client, central, db):
    payload = login(central_client)
    central['alice']['active'] = False
    identity._IDENTITIES[identity.session_key(payload['session'])].checked_at = -1000
    assert central_client.get('/api/eye/hotels').status_code == 401
    assert session_user(db, payload['session']) is None


def test_offline_admin_requires_online_login(central_client, monkeypatch):
    login(central_client)
    monkeypatch.setattr(identity,'remote',unavailable)
    login(central_client)
    assert central_client.post('/api/eye/auth/users',json={'username':'bob','display_name':'Bob','pin':'789654'}).status_code == 503


def test_legacy_api_requires_session_in_central_mode(central_client):
    assert central_client.get('/api/invoices').status_code == 401
    assert central_client.get('/api/products').status_code == 401
    login(central_client)
    assert central_client.get('/api/invoices').status_code == 200


def test_context_uses_personal_token_and_never_shared_credentials(central, monkeypatch):
    from app.central_service import _credentials, configured
    monkeypatch.setattr(settings,'central_username','shared')
    monkeypatch.setattr(settings,'central_pin','111111')
    assert _credentials() == ('','') and configured() is False
    alice = identity.Identity('alice','personal-a',1,datetime.now(UTC).replace(tzinfo=None)+timedelta(hours=1),0)
    bob = identity.Identity('bob','personal-b',2,datetime.now(UTC).replace(tzinfo=None)+timedelta(hours=1),0)
    async def run(who):
        context = identity.current_identity.set(who)
        try:
            await asyncio.sleep(0)
            return _credentials()
        finally: identity.current_identity.reset(context)
    async def parallel(): return await asyncio.gather(run(alice),run(bob))
    assert asyncio.run(parallel()) == [('alice','personal-a'),('bob','personal-b')]
    assert _credentials() == ('','')


def test_restart_keeps_local_session_and_offline_access(central_client, db, monkeypatch):
    payload = login(central_client)
    identity._IDENTITIES.clear()
    identity._LOCAL_LOGINS.clear()
    assert session_user(db, payload['session']).username == 'alice'
    assert verify_pin(db, 'alice', '654321')
    monkeypatch.setattr(identity, 'remote', unavailable)
    assert central_client.get('/api/eye/hotels', headers={'X-Eye-Session': payload['session']}).status_code == 200


def test_reconnection_requests_fresh_online_login(central_client, central, monkeypatch):
    login(central_client)
    original_remote = identity.remote
    monkeypatch.setattr(identity, 'remote', unavailable)
    payload = login(central_client)
    monkeypatch.setattr(identity, 'remote', original_remote)
    identity._OFFLINE_PROBES[identity.session_key(payload['session'])] = -1000
    assert central_client.get('/api/eye/hotels').status_code == 401
    assert login(central_client)['offline'] is False
