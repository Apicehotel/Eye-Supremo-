from datetime import date
from decimal import Decimal

from app.models import CentralReviewCache, Hotel
from app.review_cache import cached_review_search


def _seed_review_cache(db):
    hotel = db.query(Hotel).filter(Hotel.code == "gio").one()
    db.add(
        CentralReviewCache(
            sync_uuid="rev-cache-1",
            hotel_code="gio",
            review_date=date(2026, 4, 1),
            source="Booking",
            author="Mario",
            rating=Decimal("8.5"),
            room_code="101",
            text="Camera pulita ma colazione scarsa",
            payload_json='{"sync_uuid":"rev-cache-1"}',
        )
    )
    db.commit()
    return hotel


def test_cached_review_search_finds_local_rows(db):
    _seed_review_cache(db)
    rows = cached_review_search(db, "colazione", hotel_code="gio", limit=10)
    assert len(rows) == 1
    assert rows[0]["local_cache"] is True
    assert rows[0]["room"] == "101"
    assert "colazione" in rows[0]["text"].lower()


def test_reviews_endpoint_uses_sqlite_cache_without_blocking_on_supabase(client, db, monkeypatch):
    _seed_review_cache(db)
    called = {"refresh": 0}

    async def fake_refresh():
        called["refresh"] += 1
        return {"ok": True, "imported": 0}

    monkeypatch.setattr("app.routers.eye.refresh_review_cache", fake_refresh)
    response = client.get("/api/eye/reviews", params={"q": "colazione", "hotel_code": "gio", "limit": 20})
    assert response.status_code == 200
    payload = response.json()
    assert any(item.get("origin") == "sqlite-cache" for item in payload)
    assert any("colazione" in str(item.get("text") or "").lower() for item in payload)
