from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..eye_services import invoice_search_summary
from ..search_index import invoice_search

router = APIRouter(prefix="/api/eye/search", tags=["Eye Supremo search"])


def role_from_header(value: str) -> str:
    role = value.strip().lower()
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


@router.get("/live")
def live_search(
    q: str = Query(min_length=1, max_length=160),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_eye_role: str = Header(default="developer", alias="X-Eye-Role"),
    db: Session = Depends(get_db),
):
    """Ricerca locale su tutto l'indice FTS delle righe fattura (anche 20k+)."""
    role = role_from_header(x_eye_role)
    # Finestra ampia sull'indice completo, poi paginazione UI.
    fetch_limit = min(2000, max(limit + offset, limit * 4, 200))
    records = invoice_search(db, q, role_name=role, limit=fetch_limit)
    page = records[offset : offset + limit]
    summary = invoice_search_summary(records)
    return {
        "query": q,
        "summary": summary,
        "results": page,
        "count": len(page),
        "total": len(records),
        "offset": offset,
        "limit": limit,
        "engine": "fts5+rapidfuzz",
        "scope": "full-archive",
    }
