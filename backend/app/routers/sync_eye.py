from fastapi import APIRouter, Header, HTTPException
from ..sync_service import pull_from_supabase

router = APIRouter(prefix="/api/eye/sync", tags=["Eye Supremo sync"])


def _role(value: str) -> str:
    role = value.strip().lower()
    if role not in {"developer", "supremo", "level1", "level2", "level3"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


@router.post("/pull")
async def pull(payload: dict, x_eye_role: str = Header(default="developer", alias="X-Eye-Role")):
    role = _role(x_eye_role)
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Il pull multi-hotel richiede Supremo o Sviluppatore")
    hotels = payload.get("hotel_codes") if isinstance(payload.get("hotel_codes"), list) else []
    since = payload.get("since")
    return await pull_from_supabase([str(x) for x in hotels], str(since) if since else None)
