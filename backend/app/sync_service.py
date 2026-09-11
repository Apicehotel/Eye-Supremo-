import httpx
from .config import settings


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.supabase_access_token}",
        "apikey": settings.supabase_publishable_key or "",
        "Content-Type": "application/json",
    }


def _ready() -> tuple[bool, str | None]:
    if not settings.sync_enabled:
        return False, "Sincronizzazione disattivata"
    if not settings.supabase_url or not settings.supabase_publishable_key:
        return False, "Supabase non configurato"
    if not settings.supabase_access_token:
        return False, "Sessione Supabase autenticata mancante"
    return True, None


async def _call(payload: dict) -> dict:
    ready, message = _ready()
    if not ready:
        return {"enabled": settings.sync_enabled, "synced": False, "message": message}
    url = settings.supabase_url.rstrip("/") + "/functions/v1/eye-supremo-sync"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            res = await client.post(url, json=payload, headers=_headers())
            res.raise_for_status()
            data = res.json() if res.content else {}
        return {"enabled": True, "synced": True, "remote": data}
    except Exception as exc:
        return {"enabled": True, "synced": False, "message": str(exc)}


async def push_to_supabase(payload: dict) -> dict:
    body = dict(payload)
    body["action"] = "push"
    if "objects" not in body:
        body = {"action": "push", "objects": [payload]}
    return await _call(body)


async def pull_from_supabase(hotel_codes: list[str] | None = None, since: str | None = None) -> dict:
    body: dict = {"action": "pull", "hotel_codes": hotel_codes or []}
    if since:
        body["since"] = since
    return await _call(body)


def sync_configuration() -> dict:
    return {
        "enabled": settings.sync_enabled,
        "configured": bool(settings.supabase_url and settings.supabase_publishable_key),
        "authenticated": bool(settings.supabase_access_token),
        "mode": "local-first",
        "remote": "Supabase bridge",
        "direction": "push-pull",
    }
