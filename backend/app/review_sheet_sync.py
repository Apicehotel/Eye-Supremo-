"""Payloads for the room-defect Google Sheet synchronisation.

The desktop app never talks to Google Sheets with a user credential.  When a
local webhook is configured, it sends one idempotent event per imported
review; the Google Apps Script receiver owns the spreadsheet merge.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .models import AppSetting, Review


SHEET_BY_HOTEL = {
    "choco": "Choco",
    "brigantino": "Brigantino",
}


def review_sheet_name(hotel_code: str, room_code: str | None) -> str | None:
    """Resolve the existing review-sheet tab without guessing a room."""
    code = (hotel_code or "").strip().lower()
    room = (room_code or "").strip()
    if code == "gio":
        if room.isdigit() and len(room) == 4:
            return "Gio Jazz"
        if room.isdigit() and len(room) == 3:
            return "Gio Wine"
        return None
    return SHEET_BY_HOTEL.get(code)


def review_defects(tags: Iterable[Any]) -> list[str]:
    """Return stable, unique negative categories for a single review."""
    seen: set[str] = set()
    defects: list[str] = []
    for tag in tags:
        polarity = getattr(tag, "polarity", None)
        category = getattr(getattr(tag, "category", None), "name", None)
        if polarity != "negative" or not category:
            continue
        key = " ".join(str(category).casefold().split())
        if key and key not in seen:
            seen.add(key)
            defects.append(str(category).strip())
    return defects


def review_sheet_event(review: Review) -> dict[str, Any] | None:
    """Create an idempotent merge event for one review with room defects."""
    hotel = review.hotel
    room = review.room
    if hotel is None or room is None:
        return None
    sheet = review_sheet_name(hotel.code, room.code)
    defects = review_defects(review.tags)
    if not sheet or not defects:
        return None
    return {
        "event_id": review.sync_uuid,
        "sheet": sheet,
        "room": room.code,
        "defects": defects,
        "review_date": review.date.isoformat(),
        "source": review.source or "",
        "rating": float(review.rating) if review.rating is not None else None,
        "text": review.text or "",
    }


async def sync_review_defects(db: Session, review: Review) -> dict[str, Any]:
    """Send one merge event to the configured Google Apps Script endpoint.

    A missing endpoint is deliberately a no-op: importing a review must never
    fail because the optional reporting sheet has not yet been connected.
    """
    event = review_sheet_event(review)
    if event is None:
        return {"enabled": False, "sent": False, "reason": "no_room_defect"}

    endpoint = db.get(AppSetting, "review_sheet_webhook_url")
    secret = db.get(AppSetting, "review_sheet_webhook_secret")
    if not endpoint or not endpoint.value.strip():
        return {"enabled": False, "sent": False, "reason": "not_configured"}

    payload = {"event": event}
    if secret and secret.value:
        payload["secret"] = secret.value
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(endpoint.value.strip(), json=payload)
            response.raise_for_status()
        return {"enabled": True, "sent": True, "sheet": event["sheet"], "room": event["room"]}
    except Exception as exc:  # The import remains local-first.
        return {"enabled": True, "sent": False, "message": str(exc)}
