import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .central_service import central_review_page, central_review_upsert
from .database import SessionLocal
from .eye_services import classify_review_text
from .models import AppSetting, CentralReviewCache, Hotel, Review, ReviewTag, Room
from .review_sync import ensure_review_state, set_review_state

_STOP = {
    "quanto", "quale", "quali", "cosa", "come", "nel", "nella", "da", "di", "il", "la", "le", "i",
    "un", "una", "fammi", "vedere", "mostra", "per", "recension", "recensione", "recensioni",
    "camere", "camera", "hotel", "meglio", "peggio", "quali",
}


def review_cache_status(db: Session) -> dict:
    count = db.scalar(select(func.count()).select_from(CentralReviewCache)) or 0
    state = db.get(AppSetting, "central_review_sync_state")
    return {
        "count": count,
        "state": state.value if state else "never",
        "local": True,
    }


def _review_tokens(query: str) -> list[str]:
    return [t for t in re.findall(r"[a-zàèéìòù0-9]+", (query or "").lower()) if len(t) >= 4 and t not in _STOP]


def cached_review_search(
    db: Session,
    query: str = "",
    *,
    hotel_code: str | None = None,
    hotel_id: int | None = None,
    limit: int = 50,
    exclude_sync_uuids: set[str] | None = None,
) -> list[dict]:
    """Cerca recensioni nella cache SQLite locale (niente rete Supabase)."""
    limit = max(1, min(int(limit or 50), 500))
    exclude = exclude_sync_uuids or set()
    tokens = _review_tokens(query)
    needle = (query or "").strip().lower()

    resolved_code = hotel_code
    if hotel_id and not resolved_code:
        hotel = db.get(Hotel, hotel_id)
        resolved_code = hotel.code if hotel else None

    stmt = select(CentralReviewCache).order_by(CentralReviewCache.review_date.desc())
    if resolved_code:
        stmt = stmt.where(CentralReviewCache.hotel_code == resolved_code)
    if tokens:
        clauses = [CentralReviewCache.text.ilike(f"%{term}%") for term in tokens[-3:]]
        clauses.append(CentralReviewCache.room_code.ilike(f"%{tokens[-1]}%"))
        clauses.append(CentralReviewCache.author.ilike(f"%{tokens[-1]}%"))
        stmt = stmt.where(or_(*clauses))
    elif needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                CentralReviewCache.text.ilike(pattern),
                CentralReviewCache.room_code.ilike(pattern),
                CentralReviewCache.author.ilike(pattern),
                CentralReviewCache.source.ilike(pattern),
            )
        )

    records = list(db.scalars(stmt.limit(limit * 3)).all())
    if not records:
        return []
    codes = {r.hotel_code for r in records}
    hotel_names = {
        h.code: h.name
        for h in db.scalars(select(Hotel).where(Hotel.code.in_(codes))).all()
    }

    results: list[dict] = []
    for record in records:
        if record.sync_uuid in exclude:
            continue
        text = record.text or ""
        if tokens and not any(t in text.lower() or t in (record.room_code or "").lower() for t in tokens):
            continue
        results.append({
            "review_id": f"cache:{record.sync_uuid}",
            "sync_uuid": record.sync_uuid,
            "hotel": hotel_names.get(record.hotel_code, record.hotel_code),
            "hotel_code": record.hotel_code,
            "room": record.room_code,
            "date": record.review_date.isoformat() if record.review_date else None,
            "rating": float(record.rating) if record.rating is not None else None,
            "text": text,
            "source": record.source,
            "author": record.author,
            "local_cache": True,
        })
        if len(results) >= limit:
            break
    return results


def _upsert_review_mirror(db: Session, values: dict) -> Review | None:
    """Keep the normal review model aligned with the central cache.

    The normal model powers room rankings and aspect summaries. A cache-only
    copy is therefore not enough: rooms, changed fields and classifier tags
    must be mirrored as well.
    """
    hotel = db.scalar(select(Hotel).where(Hotel.code == values["hotel_code"]))
    if not hotel:
        return None

    room = None
    if values.get("room_code"):
        room = db.scalar(
            select(Room).where(Room.hotel_id == hotel.id, Room.code == values["room_code"])
        )
        if room is None:
            room = Room(hotel_id=hotel.id, code=values["room_code"])
            db.add(room)
            db.flush()

    review = db.scalar(select(Review).where(Review.sync_uuid == values["sync_uuid"]))
    created = review is None
    if review is None:
        review = Review(
            sync_uuid=values["sync_uuid"],
            hotel_id=hotel.id,
            date=values["review_date"],
            text=values["text"],
        )
        db.add(review)
        db.flush()

    state = ensure_review_state(db, review)
    remote_differs = review.text != values["text"] or review.date != values["review_date"] or review.source != values["source"] or review.rating != values["rating"]
    if not created and remote_differs and state.status in {"local", "inviato"}:
        set_review_state(db, review, "conflitto", error="Versione locale e versione Supabase divergono")
        return review
    text_changed = review.text != values["text"]
    review.hotel_id = hotel.id
    review.room_id = room.id if room else None
    review.source = values["source"]
    review.author = values["author"]
    review.rating = values["rating"]
    review.date = values["review_date"]
    review.text = values["text"]
    set_review_state(db, review, "sincronizzato")

    if created or text_changed or not review.tags:
        review.tags.clear()
        db.flush()
        for tag in classify_review_text(db, review.text, hotel.id):
            review.tags.append(
                ReviewTag(
                    category_id=tag["category_id"],
                    polarity=tag["polarity"],
                    confidence=tag["confidence"],
                    excerpt=tag.get("excerpt"),
                )
            )
    return review


async def refresh_review_cache() -> dict:
    db = SessionLocal()
    offset = 0
    imported = 0
    total = 0
    checkpoint = db.get(AppSetting, "central_review_sync_at")
    try:
        while True:
            page = await central_review_page(offset, 500, (checkpoint.value if checkpoint and checkpoint.value else None))
            items = page.get("items", [])
            total = page.get("total", 0)
            if not items:
                break
            for item in items:
                values = dict(
                    sync_uuid=str(item["sync_uuid"]),
                    hotel_code=str(item["hotel_code"]),
                    review_date=date.fromisoformat(str(item["review_date"])[:10]),
                    source=item.get("source"),
                    author=item.get("author"),
                    rating=Decimal(str(item["rating"])) if item.get("rating") is not None else None,
                    room_code=item.get("room_code"),
                    text=str(item.get("text") or ""),
                    payload_json=json.dumps(item, default=str),
                    synced_at=datetime.now(),
                )
                existing = db.get(CentralReviewCache, values["sync_uuid"])
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    db.add(CentralReviewCache(**values))
                _upsert_review_mirror(db, values)
                imported += 1
            db.commit()
            offset += len(items)
            if len(items) < 500 or offset >= total:
                break
        # Also repair the local Review mirror when a prior cache existed before
        # mirror support was enabled.
        for cached_review in db.scalars(select(CentralReviewCache)).all():
            if db.scalar(select(Review).where(Review.sync_uuid == cached_review.sync_uuid)):
                continue
            _upsert_review_mirror(
                db,
                {
                    "sync_uuid": cached_review.sync_uuid,
                    "hotel_code": cached_review.hotel_code,
                    "review_date": cached_review.review_date,
                    "source": cached_review.source,
                    "author": cached_review.author,
                    "rating": cached_review.rating,
                    "room_code": cached_review.room_code,
                    "text": cached_review.text,
                },
            )
        state = db.get(AppSetting, "central_review_sync_state") or AppSetting(key="central_review_sync_state", value="")
        state.value = f"ok:{imported}"
        db.add(state)
        checkpoint = db.get(AppSetting, "central_review_sync_at") or AppSetting(key="central_review_sync_at", value="")
        checkpoint.value = datetime.now(UTC).isoformat()
        db.add(checkpoint)
        db.commit()
        return {"ok": True, "imported": imported, "total": total}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        db.close()



async def push_local_reviews(db: Session) -> dict:
    """Invia a Supabase le recensioni presenti solo in locale (mai sincronizzate).

    L'upsert centrale e' idempotente su sync_uuid; in piu' saltiamo le recensioni
    che hanno gia' una copia centrale con stessa data, fonte e testo, per non
    creare doppioni.
    """
    cached_uuids = set(db.scalars(select(CentralReviewCache.sync_uuid)).all())
    central_keys = {(c.hotel_code, c.review_date, (c.source or "").lower(), re.sub(r"\s+", " ", c.text or "").strip().lower()[:300])
                    for c in db.scalars(select(CentralReviewCache)).all()}
    pending = pushed = skipped = conflicts = 0
    errors: list[str] = []
    for review in db.scalars(select(Review).order_by(Review.id)).all():
        state = ensure_review_state(db, review)
        if state.status == "conflitto":
            conflicts += 1
            continue
        if review.sync_uuid in cached_uuids:
            set_review_state(db, review, "sincronizzato")
            continue
        hotel = db.get(Hotel, review.hotel_id)
        if hotel is None:
            continue
        key = (hotel.code, review.date, (review.source or "").lower(), re.sub(r"\s+", " ", review.text or "").strip().lower()[:300])
        if key in central_keys:
            skipped += 1
            set_review_state(db, review, "sincronizzato")
            continue
        pending += 1
        set_review_state(db, review, "inviato")
        db.commit()
        room = db.get(Room, review.room_id) if review.room_id else None
        try:
            result = await central_review_upsert({
                "sync_uuid": review.sync_uuid, "hotel_code": hotel.code, "review_date": review.date.isoformat(),
                "source": review.source, "author": review.author,
                "rating": float(review.rating) if review.rating is not None else None,
                "room_code": getattr(room, "code", None) if room else None, "text": review.text,
            })
            if not result.get("synced"):
                message = result.get("message") or "Supabase centrale non configurato o sessione scaduta"
                set_review_state(db, review, "inviato", error=message)
                db.commit()
                errors.append(message)
                continue
            pushed += 1
            central_keys.add(key)
            set_review_state(db, review, "sincronizzato")
            db.commit()
        except Exception as exc:  # noqa: BLE001
            message = str(exc)[:160]
            set_review_state(db, review, "inviato", error=message)
            db.commit()
            errors.append(message)
            if len(errors) >= 3:
                break
    db.commit()
    return {"pending": pending, "pushed": pushed, "skipped_already_central": skipped, "conflicts": conflicts, "errors": errors}
