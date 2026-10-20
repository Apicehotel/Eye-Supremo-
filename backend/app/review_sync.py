"""Local-first sync state for review records.

The SQLite database is the source of truth for the desktop app.  SyncState is
the durable outbox: Supabase can be enabled later without making imports or
the review archive depend on a network connection.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Review, SyncState

REVIEW_ENTITY = "review"
REVIEW_STATES = {"local", "inviato", "sincronizzato", "conflitto"}


def get_review_state(db: Session, sync_uuid: str) -> SyncState | None:
    return db.scalar(select(SyncState).where(SyncState.entity_type == REVIEW_ENTITY, SyncState.entity_uuid == sync_uuid))


def ensure_review_state(db: Session, review: Review, status: str = "local") -> SyncState:
    if status not in REVIEW_STATES:
        raise ValueError(f"Stato recensione non valido: {status}")
    state = get_review_state(db, review.sync_uuid)
    if state is None:
        state = SyncState(entity_type=REVIEW_ENTITY, entity_uuid=review.sync_uuid, status=status)
        db.add(state)
        db.flush()
    return state


def set_review_state(db: Session, review: Review, status: str, *, error: str | None = None) -> SyncState:
    state = ensure_review_state(db, review, status)
    state.status = status
    state.last_error = error
    if status == "sincronizzato":
        state.remote_updated_at = datetime.now()
    return state


def ensure_all_review_states(db: Session) -> None:
    for review in db.scalars(select(Review)).all():
        ensure_review_state(db, review)


def review_sync_summary(db: Session) -> dict:
    ensure_all_review_states(db)
    db.flush()
    states = db.scalars(select(SyncState).where(SyncState.entity_type == REVIEW_ENTITY)).all()
    counts = Counter(state.status for state in states)
    queue = [
        {
            "sync_uuid": state.entity_uuid,
            "status": state.status,
            "last_error": state.last_error,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
        for state in sorted(states, key=lambda item: item.updated_at or datetime.min, reverse=True)
        if state.status in {"local", "inviato", "conflitto"}
    ]
    return {
        "entity": REVIEW_ENTITY,
        "counts": {status: counts.get(status, 0) for status in sorted(REVIEW_STATES)},
        "queue_size": len(queue),
        "queue": queue[:100],
        "supabase_optional": True,
    }
