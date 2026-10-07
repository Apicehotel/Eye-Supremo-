import asyncio
from datetime import date
from decimal import Decimal

from app.local_cache_bootstrap import (
    bootstrap_status,
    needs_bootstrap,
    run_local_cache_bootstrap,
)
from app.models import AppSetting, CentralInvoiceCache, CentralReviewCache


def test_needs_bootstrap_when_caches_empty(db):
    assert needs_bootstrap(db) is True


def test_bootstrap_status_endpoint(client):
    response = client.get("/api/eye/cache/bootstrap/status")
    assert response.status_code == 200
    payload = response.json()
    assert "state" in payload
    assert "invoices" in payload
    assert "reviews" in payload


def test_run_bootstrap_downloads_invoices_and_reviews(db, monkeypatch):
    async def fake_invoices():
        db.add(
            CentralInvoiceCache(
                source_hash="boot-inv-1",
                invoice_number="BOOT-1",
                invoice_date=date(2026, 1, 1),
                supplier_name="Boot Spa",
                total=Decimal("10"),
                search_text="boot",
                payload_json='{"rows":[]}',
            )
        )
        db.commit()
        return {"ok": True, "imported": 1, "total": 1}

    async def fake_reviews():
        db.add(
            CentralReviewCache(
                sync_uuid="boot-rev-1",
                hotel_code="gio",
                review_date=date(2026, 1, 2),
                source="Booking",
                author="Test",
                rating=Decimal("9"),
                room_code="1",
                text="Ottima colazione",
                payload_json="{}",
            )
        )
        db.commit()
        return {"ok": True, "imported": 1, "total": 1}

    monkeypatch.setattr("app.local_cache_bootstrap.refresh_central_cache", fake_invoices)
    monkeypatch.setattr("app.local_cache_bootstrap.refresh_review_cache", fake_reviews)
    monkeypatch.setattr("app.local_cache_bootstrap.central_configured", lambda: True)

    result = asyncio.run(run_local_cache_bootstrap(force=True, full=False))
    assert result["state"] == "ok"
    assert result["ready_offline"] is True
    assert result["invoices"]["count"] >= 1
    assert result["reviews"]["count"] >= 1
    assert needs_bootstrap(db) is False


def test_bootstrap_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.local_cache_bootstrap.central_configured", lambda: False)
    result = asyncio.run(run_local_cache_bootstrap(force=True))
    assert result["state"] == "skipped"


def test_bootstrap_post_starts_background(client, monkeypatch):
    called = {"n": 0}

    async def fake_run(*, force=False, full=False):
        called["n"] += 1
        return {"state": "running", "running": True}

    monkeypatch.setattr("app.routers.eye.run_local_cache_bootstrap", fake_run)
    monkeypatch.setattr("app.routers.eye.schedule_bootstrap", lambda **kwargs: {"state": "running", "running": True, "configured": True})
    response = client.post("/api/eye/cache/bootstrap", json={"background": True, "full": True})
    assert response.status_code == 200
    assert response.json()["running"] is True


def test_bootstrap_status_reads_persisted_state(db):
    db.add(AppSetting(key="local_cache_bootstrap_state", value="ok"))
    db.add(AppSetting(key="local_cache_bootstrap_detail", value="Cache pronta"))
    db.commit()
    status = bootstrap_status(db)
    assert status["state"] == "ok"
    assert status["detail"] == "Cache pronta"
