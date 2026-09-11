import httpx
from .config import settings


async def push_to_supabase(payload: dict) -> dict:
    if not settings.sync_enabled:
        return {"enabled": False, "synced": False, "message": "Sincronizzazione disattivata"}
    if not settings.supabase_url or not settings.supabase_publishable_key:
        return {"enabled": True, "synced": False, "message": "Supabase non configurato"}
    url = settings.supabase_url.rstrip("/") + "/functions/v1/eye-supremo-sync"
    headers = {
        "Authorization": f"Bearer {settings.supabase_publishable_key}",
        "apikey": settings.supabase_publishable_key,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json() if res.content else {}
        return {"enabled": True, "synced": True, "remote": data}
    except Exception as exc:
        return {"enabled": True, "synced": False, "message": str(exc)}


def sync_configuration() -> dict:
    return {
        "enabled": settings.sync_enabled,
        "configured": bool(settings.supabase_url and settings.supabase_publishable_key),
        "mode": "local-first",
        "remote": "Supabase bridge",
    }
