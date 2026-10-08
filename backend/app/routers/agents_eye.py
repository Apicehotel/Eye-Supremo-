from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent_orchestrator import AGENTS, run_orchestrated_query
from ..database import get_db
from ..models import Hotel

router = APIRouter(prefix="/api/eye/agents", tags=["Eye Supremo agents"])


def current_role(x_eye_role: str = Header(default="developer", alias="X-Eye-Role")) -> str:
    role = x_eye_role.strip().lower()
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


def current_username(x_eye_user: str = Header(default="", alias="X-Eye-User")) -> str:
    return x_eye_user.strip().lower()


@router.get("/registry")
def registry():
    return [{"name": x.name, "purpose": x.purpose, "tools": list(x.tools)} for x in AGENTS.values()]


@router.post("/ask")
async def ask_agents(payload: dict, role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(422, "Domanda vuota")

    area = str(payload.get("area") or "all").strip().lower()
    if area not in {"all", "invoices", "reviews"}:
        # Compatibilità: review_only / include_reviews dal client.
        if payload.get("review_only") or payload.get("prefer_reviews"):
            area = "reviews"
        elif payload.get("include_reviews") is False:
            area = "invoices"
        else:
            area = "all"

    hotel_id = None
    hotel_code = str(payload.get("hotel_code") or "").strip().lower()
    if hotel_code:
        hotel = db.scalar(select(Hotel).where(Hotel.code == hotel_code, Hotel.active.is_(True)))
        if not hotel:
            raise HTTPException(404, "Hotel non trovato")
        hotel_id = hotel.id

    return await run_orchestrated_query(db, question, role_name=role, hotel_id=hotel_id, area=area)
