"""Test lettura recensioni centrali (eye_central_reviews)."""


def test_central_reviews_catalog_maps_hotels(monkeypatch):
    from app import storage_service

    pages = {
        0: {
            "items": [
                {
                    "sync_uuid": "a1",
                    "hotel_code": "gio",
                    "author": "<ospite@example.com>",
                    "source": "Booking",
                    "rating": 5,
                    "review_date": "2026-09-01",
                    "text": "Ottimo soggiorno",
                    "room_code": "101",
                    "updated_at": "2026-09-02T00:00:00Z",
                },
                {
                    "sync_uuid": "a2",
                    "hotel_code": "choco",
                    "author": None,
                    "source": "TripAdvisor",
                    "rating": 4,
                    "review_date": "2026-09-03",
                    "text": "Colazione buona",
                    "room_code": None,
                    "updated_at": "2026-09-03T00:00:00Z",
                },
                {
                    "sync_uuid": "a3",
                    "hotel_code": "gio",
                    "author": "Bob",
                    "source": "Booking",
                    "rating": 8.0,
                    "review_date": "2026-09-04",
                    "text": "Scala 10",
                    "room_code": None,
                    "updated_at": "2026-09-04T00:00:00Z",
                },
            ],
            "total": 3,
            "limit": 200,
            "offset": 0,
        }
    }

    def fake_page(*, limit=200, offset=0, **_kwargs):
        return pages.get(offset, {"items": [], "total": 3, "limit": limit, "offset": offset})

    monkeypatch.setattr(storage_service, "central_review_page", fake_page)
    catalog = storage_service.central_reviews_catalog()
    assert catalog["total"] == 3
    assert catalog["returned"] == 3
    assert catalog["items"][0]["hotelId"] == "hotelgio"
    assert catalog["items"][0]["author"] == "ospite@example.com"
    assert catalog["items"][1]["hotelId"] == "chocohotel"
    assert catalog["items"][1]["author"] == "Ospite"
    assert catalog["items"][2]["rating"] == 4.0  # 8/10 → 4 stelle
    by_id = {h["id"]: h for h in catalog["hotels"]}
    assert by_id["all"]["count"] == 3
    assert by_id["hotelgio"]["count"] == 2
    assert by_id["chocohotel"]["count"] == 1
    assert by_id["brigantino"]["count"] == 0


def test_reviews_api_endpoint(client, monkeypatch):
    from app.config import settings
    from app import storage_service

    boot = client.post("/api/auth/bootstrap", json={"pin": "123456"}).json()
    headers = {"X-Eye-Session": boot["session"]}

    monkeypatch.setattr(settings, "supabase_url", "https://ooqlfldcrnkudhgjnied.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-test")
    monkeypatch.setattr(settings, "supabase_central_pin", "pin-test")

    def fake_catalog(**_kwargs):
        return {
            "configured": True,
            "total": 654,
            "returned": 1,
            "items": [
                {
                    "id": "u1",
                    "hotelId": "hotelgio",
                    "author": "Anna",
                    "source": "Booking",
                    "rating": 5,
                    "date": "2026-09-01",
                    "text": "Perfetto",
                    "status": "Importata",
                }
            ],
            "hotels": [
                {"id": "all", "name": "Tutti", "short": "Tutti", "count": 654, "score": "4.50"},
            ],
            "sources": ["Booking"],
        }

    monkeypatch.setattr(storage_service, "central_reviews_catalog", fake_catalog)
    res = client.get("/api/storage/central/reviews", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 654
    assert body["items"][0]["author"] == "Anna"


def test_reviews_api_requires_config(client, monkeypatch):
    from app.config import settings

    boot = client.post("/api/auth/bootstrap", json={"pin": "123456"}).json()
    headers = {"X-Eye-Session": boot["session"]}
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_anon_key", None)
    monkeypatch.setattr(settings, "supabase_service_key", None)
    monkeypatch.setattr(settings, "supabase_central_pin", None)
    res = client.get("/api/storage/central/reviews", headers=headers)
    assert res.status_code == 503
