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


# ---- completezza cache, percorso alternativo, ripresa automatica, stato sintetico ----

def _fake_pages(total, page_size=500, fallback=False):
    """Simula central_invoice_page con `total` fatture sul server."""
    async def fake(offset=0, limit=500, since=None):
        n = max(0, min(limit, total - offset))
        items = [
            {"source_hash": f"p{offset + i:06d}", "invoice_number": str(offset + i), "invoice_date": "2026-01-01",
             "supplier_name": "Forn", "total": 1, "rows": []}
            for i in range(n)
        ]
        out = {"items": items, "offset": offset, "limit": limit, "total": total}
        if fallback:
            out["fallback"] = True
            out["total"] = len(items)
        return out
    return fake


def _configure(monkeypatch):
    monkeypatch.setattr("app.local_cache_bootstrap.central_configured", lambda: True)


def test_full_download_is_verified_complete(db, monkeypatch):
    from app.central_cache import refresh_central_cache
    _configure(monkeypatch)
    monkeypatch.setattr("app.central_cache.central_invoice_page", _fake_pages(1200))
    result = asyncio.run(refresh_central_cache())
    assert result["ok"] and result["complete"] is True and result["local_count"] == 1200
    status = bootstrap_status(db)
    assert status["health"] == "ok" and status["ready_offline"] is True
    assert status["invoices"]["remote_total"] == 1200 and status["invoices"]["percent"] == 100
    assert "1.200" in status["headline"]


def test_fallback_path_is_flagged_incomplete_and_retried(db, monkeypatch):
    from app.central_cache import refresh_central_cache
    _configure(monkeypatch)
    db.merge(AppSetting(key="local_cache_bootstrap_state", value="ok")); db.commit()
    monkeypatch.setattr("app.central_cache.central_invoice_page", _fake_pages(20000, fallback=True))
    result = asyncio.run(refresh_central_cache())
    assert result["ok"] and result["complete"] is False and result["fallback"] is True
    assert "Percorso alternativo" in result["message"]
    assert db.get(AppSetting, "central_sync_at") is None or not db.get(AppSetting, "central_sync_at").value
    status = bootstrap_status(db)
    assert status["health"] == "incomplete" and status["ready_offline"] is False
    assert needs_bootstrap(db) is True


def test_missing_invoices_are_detected_and_resumed(db, monkeypatch):
    from app.central_cache import refresh_central_cache
    _configure(monkeypatch)
    monkeypatch.setattr("app.central_cache.central_invoice_page", _fake_pages(1000))
    asyncio.run(refresh_central_cache())
    db.merge(AppSetting(key="local_cache_bootstrap_state", value="ok")); db.commit()
    assert bootstrap_status(db)["health"] == "ok"
    assert needs_bootstrap(db) is False
    # il server ora ha 1300 fatture: la cache (1000) e' incompleta
    monkeypatch.setattr("app.central_cache.central_invoice_page", _fake_pages(1300))
    db.merge(AppSetting(key="central_remote_total", value="1300")); db.commit()
    status = bootstrap_status(db)
    assert status["health"] == "incomplete" and status["invoices"]["missing"] == 300
    assert needs_bootstrap(db) is True
    asyncio.run(refresh_central_cache())
    assert bootstrap_status(db)["health"] == "ok"
    assert needs_bootstrap(db) is False


def test_interrupted_download_keeps_progress_and_reports_error(db, monkeypatch):
    from app.central_cache import refresh_central_cache
    _configure(monkeypatch)
    ok_pages = _fake_pages(5000)

    async def flaky(offset=0, limit=500, since=None):
        if offset >= 1000:
            raise RuntimeError("rete caduta")
        return await ok_pages(offset, limit, since)

    monkeypatch.setattr("app.central_cache.central_invoice_page", flaky)
    db.merge(AppSetting(key="local_cache_bootstrap_state", value="ok")); db.commit()
    result = asyncio.run(refresh_central_cache())
    assert result["ok"] is False
    status = bootstrap_status(db)
    assert status["invoices"]["count"] == 1000
    assert status["health"] == "incomplete"
    assert needs_bootstrap(db) is True


def test_health_when_empty_and_not_configured(db):
    status = bootstrap_status(db)
    assert status["health"] in {"empty", "not_configured"}
    assert status["ready_offline"] is False
