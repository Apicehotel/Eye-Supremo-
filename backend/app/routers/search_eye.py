from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy.orm import Session
from fastapi import Depends

from ..database import get_db
from ..search_index import invoice_search_page

router = APIRouter(prefix="/api/eye/search", tags=["Eye Supremo search"])


def role_from_header(value: str) -> str:
    role = value.strip().lower()
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


@router.get("/live")
def live_search(
    q: str = Query(min_length=1, max_length=160),
    limit: int = Query(50, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    x_eye_role: str = Header(default="developer", alias="X-Eye-Role"),
    db: Session = Depends(get_db),
):
    """Ricerca estesa a TUTTE le fatture/righe dell'archivio locale.

    Nessun tetto sulla ricerca: `limit`/`offset` servono solo a paginare
    la risposta UI. `total` e `summary` coprono l'intero match set.
    """
    role = role_from_header(x_eye_role)
    return invoice_search_page(db, q, role_name=role, limit=limit, offset=offset)
