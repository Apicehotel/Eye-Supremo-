from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..eye_services import invoice_search_summary
from ..search_index import invoice_search

router = APIRouter(prefix="/api/eye/search", tags=["Eye Supremo search"])


def role_from_header(value: str) -> str:
    role = value.strip().lower()
    if role not in {"developer", "supremo", "level1", "level2", "level3"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


@router.get("/live")
def live_search(q: str = Query(min_length=1, max_length=160), limit: int = Query(30, le=100), x_eye_role: str = Header(default="developer", alias="X-Eye-Role"), db: Session = Depends(get_db)):
    role = role_from_header(x_eye_role)
    records = invoice_search(db, q, role_name=role, limit=limit)
    return {"query": q, "summary": invoice_search_summary(records), "results": records, "engine": "fts5+rapidfuzz"}
