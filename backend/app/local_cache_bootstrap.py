"""Bootstrap cache locale all'installazione / primo avvio.

Scarica da Supabase (quando raggiungibile) le fatture e le recensioni
nella cache SQLite del PC, così Ask e le liste restano usabili offline.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from .central_cache import cache_status, refresh_central_cache
from .central_service import configured as central_configured
from .config import settings
from .database import SessionLocal
from .models import AppSetting
from .review_cache import refresh_review_cache, review_cache_status

STATE_KEY = "local_cache_bootstrap_state"
DETAIL_KEY = "local_cache_bootstrap_detail"
AT_KEY = "local_cache_bootstrap_at"
RESULT_KEY = "local_cache_bootstrap_result"

_LOCK = asyncio.Lock()
_TASK: asyncio.Task | None = None


def _get(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key) or AppSetting(key=key, value=value)
    row.value = value
    db.add(row)


def bootstrap_enabled() -> bool:
    """Se True, al primo avvio scarica automaticamente la cache offline."""
    return bool(settings.cache_bootstrap_on_start)


def bootstrap_status(db: Session | None = None) -> dict[str, Any]:
    owns = db is None
    if owns:
        db = SessionLocal()
    try:
        state = _get(db, STATE_KEY) or "never"
        detail = _get(db, DETAIL_KEY) or ""
        at = _get(db, AT_KEY)
        raw = _get(db, RESULT_KEY) or "{}"
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            result = {}
        invoices = cache_status(db)
        reviews = review_cache_status(db)
        ready = bool(invoices.get("count") or reviews.get("count")) and state in {"ok", "partial"}
        return {
            "enabled": central_configured(),
            "configured": central_configured(),
            "state": state,
            "detail": detail,
            "completed_at": at,
            "ready_offline": ready,
            "running": state == "running" or (_TASK is not None and not _TASK.done()),
            "invoices": invoices,
            "reviews": reviews,
            "result": result,
            "auto_on_start": bootstrap_enabled(),
            "desktop": bool(getattr(sys, "frozen", False)),
        }
    finally:
        if owns:
            db.close()


def needs_bootstrap(db: Session | None = None) -> bool:
    if not central_configured():
        return False
    owns = db is None
    if owns:
        db = SessionLocal()
    try:
        state = _get(db, STATE_KEY) or "never"
        if state == "running":
            return False
        invoices = cache_status(db).get("count") or 0
        reviews = review_cache_status(db).get("count") or 0
        if state == "never":
            return True
        if state in {"error", "skipped"} and (invoices == 0 or reviews == 0):
            return True
        if invoices == 0 and reviews == 0:
            return True
        return False
    finally:
        if owns:
            db.close()


def _clear_incremental_checkpoints(db: Session) -> None:
    for key in ("central_sync_at", "central_review_sync_at"):
        row = db.get(AppSetting, key)
        if row:
            row.value = ""
            db.add(row)
    db.commit()


async def run_local_cache_bootstrap(*, force: bool = False, full: bool = False) -> dict[str, Any]:
    """Scarica fatture + recensioni nella cache SQLite locale."""
    async with _LOCK:
        db = SessionLocal()
        try:
            if not central_configured():
                _set(db, STATE_KEY, "skipped")
                _set(db, DETAIL_KEY, "Supabase centrale non configurato")
                _set(db, AT_KEY, datetime.now(UTC).isoformat())
                db.commit()
                return bootstrap_status(db)

            current = _get(db, STATE_KEY) or "never"
            if current == "running" and not force:
                return bootstrap_status(db)

            if not force and not needs_bootstrap(db) and current == "ok":
                return bootstrap_status(db)

            _set(db, STATE_KEY, "running")
            _set(db, DETAIL_KEY, "Download cache fatture e recensioni in corso…")
            db.commit()
            if full:
                _clear_incremental_checkpoints(db)
        finally:
            db.close()

        invoice_result: dict[str, Any]
        review_result: dict[str, Any]
        try:
            invoice_result = await refresh_central_cache()
        except Exception as exc:  # noqa: BLE001
            invoice_result = {"ok": False, "message": str(exc), "imported": 0}

        try:
            review_result = await refresh_review_cache()
        except Exception as exc:  # noqa: BLE001
            review_result = {"ok": False, "message": str(exc), "imported": 0}

        db = SessionLocal()
        try:
            invoices = cache_status(db)
            reviews = review_cache_status(db)
            inv_ok = bool(invoice_result.get("ok"))
            rev_ok = bool(review_result.get("ok"))
            if inv_ok and rev_ok:
                state = "ok"
                detail = (
                    f"Cache pronta: {invoices.get('count', 0)} fatture, "
                    f"{reviews.get('count', 0)} recensioni"
                )
            elif inv_ok or rev_ok or invoices.get("count") or reviews.get("count"):
                state = "partial"
                detail = (
                    f"Cache parziale. Fatture: {'ok' if inv_ok else invoice_result.get('message', 'errore')}; "
                    f"Recensioni: {'ok' if rev_ok else review_result.get('message', 'errore')}"
                )
            else:
                state = "error"
                detail = (
                    f"Download non riuscito. Fatture: {invoice_result.get('message', 'errore')}; "
                    f"Recensioni: {review_result.get('message', 'errore')}"
                )
            result = {
                "invoices": invoice_result,
                "reviews": review_result,
                "invoice_count": invoices.get("count", 0),
                "review_count": reviews.get("count", 0),
            }
            _set(db, STATE_KEY, state)
            _set(db, DETAIL_KEY, detail)
            _set(db, AT_KEY, datetime.now(UTC).isoformat())
            _set(db, RESULT_KEY, json.dumps(result, default=str))
            db.commit()
            return bootstrap_status(db)
        finally:
            db.close()


def schedule_bootstrap(*, force: bool = False, full: bool = False) -> dict[str, Any]:
    """Avvia il bootstrap in background (non blocca l'UI)."""
    global _TASK
    status = bootstrap_status()
    if status.get("running") and not force:
        return status
    if not central_configured() and not force:
        return status

    async def _runner():
        await run_local_cache_bootstrap(force=force, full=full)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return status

    _TASK = loop.create_task(_runner())
    db = SessionLocal()
    try:
        _set(db, STATE_KEY, "running")
        _set(db, DETAIL_KEY, "Download cache avviato in background…")
        db.commit()
        return bootstrap_status(db)
    finally:
        db.close()


def maybe_schedule_on_startup() -> None:
    """Chiamato dal lifespan: scarica la cache al primo avvio / installazione."""
    if not bootstrap_enabled():
        return
    if not central_configured():
        return
    if not needs_bootstrap():
        return
    schedule_bootstrap(force=False, full=False)
