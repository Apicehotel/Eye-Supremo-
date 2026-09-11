import hashlib
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from ..ai_service import eye_ai_answer
from ..config import settings
from ..database import get_db
from ..eye_services import (
    add_review, ensure_invoice_metadata, invoice_search, invoice_search_summary,
    review_rankings, seed_eye_supremo,
)
from ..importers import parse_review_email
from ..models import (
    Alert, EmergingTheme, Hotel, Invoice, Review, ReviewCategory, ReviewTag,
    RoleExclusion, Room, UserProfile,
)
from ..normalization import normalize_text
from ..sync_service import push_to_supabase, sync_configuration

router = APIRouter(prefix="/api/eye", tags=["Eye Supremo"])


def current_role(x_eye_role: str = Header(default="developer", alias="X-Eye-Role")) -> str:
    role = x_eye_role.strip().lower()
    if role not in {"developer", "supremo", "level1", "level2", "level3"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


def hotel_from_code(db: Session, code: str) -> Hotel:
    hotel = db.scalar(select(Hotel).where(Hotel.code == code))
    if not hotel:
        raise HTTPException(404, "Hotel non trovato")
    return hotel


@router.get("/hotels")
def hotels(db: Session = Depends(get_db)):
    return db.scalars(select(Hotel).where(Hotel.active.is_(True)).order_by(Hotel.name)).all()


@router.get("/users")
def users(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore gestisce utenti e configurazione")
    return db.scalars(select(UserProfile).order_by(UserProfile.id)).all()


@router.get("/role-exclusions")
def exclusions(role_name: str | None = None, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        role_name = role
    stmt = select(RoleExclusion)
    if role_name:
        stmt = stmt.where(RoleExclusion.role_name == role_name)
    return db.scalars(stmt.order_by(RoleExclusion.role_name, RoleExclusion.exclusion_type, RoleExclusion.value)).all()


@router.post("/role-exclusions")
def add_exclusion(payload: dict, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore modifica le esclusioni")
    role_name = str(payload.get("role_name", "")).strip()
    exclusion_type = str(payload.get("exclusion_type", "")).strip()
    value = normalize_text(str(payload.get("value", "")))
    if role_name not in {"level1", "level2", "level3"} or exclusion_type not in {"category", "product", "supplier", "keyword"} or not value:
        raise HTTPException(422, "Esclusione non valida")
    existing = db.scalar(select(RoleExclusion).where(RoleExclusion.role_name == role_name, RoleExclusion.exclusion_type == exclusion_type, RoleExclusion.value == value))
    if existing:
        existing.enabled = True
        item = existing
    else:
        item = RoleExclusion(role_name=role_name, exclusion_type=exclusion_type, value=value, note=payload.get("note")); db.add(item)
    db.commit(); db.refresh(item); return item


@router.get("/search/live")
def live_search(q: str = Query(min_length=1, max_length=160), limit: int = Query(30, le=100), role: str = Depends(current_role), db: Session = Depends(get_db)):
    records = invoice_search(db, q, role_name=role, limit=limit)
    return {"query": q, "summary": invoice_search_summary(records), "results": records}


@router.post("/ai/ask")
async def ask_eye(payload: dict, role: str = Depends(current_role), db: Session = Depends(get_db)):
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(422, "Domanda vuota")
    hotel_id = None
    if payload.get("hotel_code"):
        hotel_id = hotel_from_code(db, str(payload["hotel_code"])).id
    return await eye_ai_answer(db, question, role_name=role, hotel_id=hotel_id)


@router.post("/invoices/{invoice_id}/hotel/{hotel_code}")
def assign_invoice_hotel(invoice_id: int, hotel_code: str, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Fattura non trovata")
    hotel = hotel_from_code(db, hotel_code)
    meta = ensure_invoice_metadata(db, inv, hotel.id); db.commit(); db.refresh(meta)
    return {"ok": True, "invoice_id": invoice_id, "hotel": hotel.name, "sync_uuid": meta.sync_uuid}


@router.post("/reviews/import/{hotel_code}")
async def import_reviews(hotel_code: str, files: list[UploadFile] = File(...), role: str = Depends(current_role), db: Session = Depends(get_db)):
    hotel = hotel_from_code(db, hotel_code)
    imported, errors = [], []
    for file in files[:200]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".eml", ".txt"}:
            errors.append({"file": file.filename, "error": "Formato recensione supportato: EML o TXT"}); continue
        content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            errors.append({"file": file.filename, "error": "File troppo grande"}); continue
        safe = settings.data_dir / "reviews" / f"{secrets.token_hex(12)}{suffix}"
        safe.write_bytes(content)
        try:
            if suffix == ".eml":
                parsed = parse_review_email(safe)
            else:
                text = content.decode("utf-8", errors="replace")
                parsed = {"date": date.today().isoformat(), "author": None, "source": "txt", "text": text, "rating": None, "room_code": None, "raw_file": safe.name}
            review = add_review(db, hotel_id=hotel.id, text=parsed["text"], review_date=date.fromisoformat(parsed["date"]),
                                rating=Decimal(parsed["rating"]) if parsed.get("rating") else None,
                                room_code=parsed.get("room_code"), source=parsed.get("source"), author=parsed.get("author"), raw_file=parsed.get("raw_file"))
            imported.append(review.id)
        except Exception as exc:
            errors.append({"file": file.filename, "error": str(exc)})
    return {"hotel": hotel.name, "imported": len(imported), "review_ids": imported, "errors": errors}


@router.get("/reviews")
def reviews(hotel_code: str | None = None, q: str = "", limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(Review).options(selectinload(Review.hotel), selectinload(Review.room), selectinload(Review.tags).selectinload(ReviewTag.category))
    if hotel_code:
        stmt = stmt.where(Review.hotel_id == hotel_from_code(db, hotel_code).id)
    if q:
        stmt = stmt.where(Review.text.ilike(f"%{q}%"))
    items = db.scalars(stmt.order_by(Review.date.desc()).limit(limit)).unique().all()
    return [{
        "id": r.id, "hotel": r.hotel.name, "hotel_code": r.hotel.code, "room": r.room.code if r.room else None,
        "author": r.author, "source": r.source, "rating": float(r.rating) if r.rating is not None else None,
        "date": r.date.isoformat(), "text": r.text,
        "tags": [{"category": t.category.name, "polarity": t.polarity, "confidence": float(t.confidence)} for t in r.tags],
    } for r in items]


@router.get("/rankings")
def rankings(hotel_code: str | None = None, limit: int = Query(5, ge=1, le=25), db: Session = Depends(get_db)):
    hotel_id = hotel_from_code(db, hotel_code).id if hotel_code else None
    return review_rankings(db, hotel_id=hotel_id, limit=limit)


@router.get("/rankings/by-hotel")
def rankings_by_hotel(limit: int = Query(5, ge=1, le=25), db: Session = Depends(get_db)):
    result = {}
    for hotel in db.scalars(select(Hotel).where(Hotel.active.is_(True))).all():
        result[hotel.code] = {"hotel": hotel.name, **review_rankings(db, hotel_id=hotel.id, limit=limit)}
    return result


@router.get("/emerging-themes")
def emerging_themes(status: str = "candidate", db: Session = Depends(get_db)):
    stmt = select(EmergingTheme).where(EmergingTheme.status == status).order_by(EmergingTheme.occurrences.desc(), EmergingTheme.last_seen.desc())
    return db.scalars(stmt.limit(200)).all()


@router.post("/emerging-themes/{theme_id}/approve")
def approve_theme(theme_id: int, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role != "developer":
        raise HTTPException(403, "Solo lo Sviluppatore approva nuove categorie")
    theme = db.get(EmergingTheme, theme_id)
    if not theme:
        raise HTTPException(404, "Tema non trovato")
    category = db.scalar(select(ReviewCategory).where(ReviewCategory.name == theme.name))
    if not category:
        category = ReviewCategory(name=theme.name, auto_learned=True); db.add(category); db.flush()
    theme.status = "approved"; theme.merged_into_id = category.id; db.commit()
    return {"ok": True, "category_id": category.id, "name": category.name}


@router.get("/alerts")
def alerts(unread_only: bool = False, limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(Alert)
    if unread_only:
        stmt = stmt.where(Alert.is_read.is_(False), Alert.resolved.is_(False))
    return db.scalars(stmt.order_by(Alert.created_at.desc()).limit(limit)).all()


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int, db: Session = Depends(get_db)):
    item = db.get(Alert, alert_id)
    if not item:
        raise HTTPException(404, "Alert non trovato")
    item.is_read = True; db.commit(); return {"ok": True}


@router.get("/sync/status")
def sync_status():
    return sync_configuration()


@router.post("/sync/push")
async def sync_push(payload: dict, role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    return await push_to_supabase(payload)
