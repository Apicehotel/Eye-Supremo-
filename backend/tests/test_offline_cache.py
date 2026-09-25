from pathlib import Path


def test_offline_sync_paginates_full_catalog(tmp_path, monkeypatch):
    from app.config import settings
    from app import offline_cache, storage_service

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "supabase_central_pin", "123456")
    monkeypatch.setattr(settings, "supabase_central_gateway", "https://example.test/gateway")

    rows = [
        {
            "id": f"inv-{i}",
            "invoice_number": f"N-{i}",
            "invoice_date": "2026-09-01",
            "supplier_name": "Fornitore",
            "total": float(i),
            "currency": "EUR",
            "source_hash": f"{i:064x}",
            "source_filename": f"{i}.xml",
        }
        for i in range(250)
    ]

    def fake_page(*, limit=200, offset=0, **_kwargs):
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }

    monkeypatch.setattr(storage_service, "central_invoice_page", fake_page)
    result = offline_cache.sync_catalog()

    assert result["ok"] is True
    assert result["cached_invoices"] == 250
    assert result["reported_total"] == 250
    assert result["complete"] is True
    assert offline_cache.catalog_path().exists()
    assert len(offline_cache.cached_items()) == 250
    assert offline_cache.status()["cached_invoices"] == 250


def test_offline_sync_keeps_previous_cache_on_network_failure(tmp_path, monkeypatch):
    from app.config import settings
    from app import offline_cache, storage_service

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "supabase_central_pin", "123456")
    monkeypatch.setattr(settings, "supabase_central_gateway", "https://example.test/gateway")

    offline_cache._atomic_write_json(
        offline_cache.catalog_path(),
        {
            "version": 1,
            "synced_at": "2026-09-25T00:00:00+00:00",
            "complete": True,
            "total": 1,
            "items": [{"id": "old", "invoice_number": "OLD"}],
        },
    )

    def fail_page(**_kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(storage_service, "central_invoice_page", fail_page)

    try:
        offline_cache.sync_catalog()
        assert False, "sync_catalog should fail"
    except RuntimeError:
        pass

    data = offline_cache.load_catalog()
    assert data["total"] == 1
    assert data["items"][0]["invoice_number"] == "OLD"


def test_local_document_lookup(tmp_path, monkeypatch):
    from app.config import settings
    from app import offline_cache

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    digest = "a" * 64
    target = offline_cache.documents_dir() / digest[:2] / f"{digest}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"pdf")

    found = offline_cache.local_document_for(digest, "fattura.pdf")
    assert found == target
    assert Path(found).read_bytes() == b"pdf"
