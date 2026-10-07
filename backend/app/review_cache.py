import json
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlalchemy import func, select
from .central_service import central_review_page
from .database import SessionLocal
from .models import AppSetting, CentralReviewCache, Hotel, Review, Room


def review_cache_status(db):
    return {"count": db.scalar(select(func.count()).select_from(CentralReviewCache)) or 0}


async def refresh_review_cache() -> dict:
    db = SessionLocal(); offset = 0; imported = 0; total = 0
    checkpoint = db.get(AppSetting, "central_review_sync_at")
    try:
        while True:
            page = await central_review_page(offset, 500, checkpoint.value if checkpoint else None); items = page.get("items", []); total = page.get("total", 0)
            if not items: break
            for item in items:
                values = dict(sync_uuid=str(item["sync_uuid"]), hotel_code=str(item["hotel_code"]), review_date=date.fromisoformat(str(item["review_date"])[:10]), source=item.get("source"), author=item.get("author"), rating=Decimal(str(item["rating"])) if item.get("rating") is not None else None, room_code=item.get("room_code"), text=str(item.get("text") or ""), payload_json=json.dumps(item, default=str), synced_at=datetime.now())
                existing = db.get(CentralReviewCache, values["sync_uuid"])
                if existing:
                    for key, value in values.items(): setattr(existing, key, value)
                else: db.add(CentralReviewCache(**values))
                # Mirror the record into the normal local model so rankings and
                # the existing analysis pipeline see remote reviews too.
                if not db.scalar(select(Review).where(Review.sync_uuid == values["sync_uuid"])):
                    hotel = db.scalar(select(Hotel).where(Hotel.code == values["hotel_code"]))
                    if hotel:
                        room = db.scalar(select(Room).where(Room.hotel_id == hotel.id, Room.code == values["room_code"])) if values["room_code"] else None
                        db.add(Review(sync_uuid=values["sync_uuid"], hotel_id=hotel.id, room_id=room.id if room else None, source=values["source"], author=values["author"], rating=values["rating"], date=values["review_date"], text=values["text"]))
                imported += 1
            db.commit(); offset += len(items)
            if len(items) < 500 or offset >= total: break
        # Also repair the local Review mirror when a prior cache existed before
        # mirror support was enabled.
        for cached_review in db.scalars(select(CentralReviewCache)).all():
            if db.scalar(select(Review).where(Review.sync_uuid == cached_review.sync_uuid)): continue
            hotel = db.scalar(select(Hotel).where(Hotel.code == cached_review.hotel_code))
            if hotel:
                room = db.scalar(select(Room).where(Room.hotel_id == hotel.id, Room.code == cached_review.room_code)) if cached_review.room_code else None
                db.add(Review(sync_uuid=cached_review.sync_uuid, hotel_id=hotel.id, room_id=room.id if room else None, source=cached_review.source, author=cached_review.author, rating=cached_review.rating, date=cached_review.review_date, text=cached_review.text))
        state = db.get(AppSetting, "central_review_sync_state") or AppSetting(key="central_review_sync_state", value="")
        state.value = f"ok:{imported}"; db.add(state)
        checkpoint = db.get(AppSetting, "central_review_sync_at") or AppSetting(key="central_review_sync_at", value="")
        checkpoint.value = datetime.now(UTC).isoformat(); db.add(checkpoint); db.commit()
        return {"ok": True, "imported": imported, "total": total}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    finally: db.close()
