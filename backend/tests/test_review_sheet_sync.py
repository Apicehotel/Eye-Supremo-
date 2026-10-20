from datetime import date
from decimal import Decimal

from app.models import Hotel, Review, ReviewCategory, ReviewTag, Room
from app.review_sheet_sync import review_defects, review_sheet_event, review_sheet_name


def test_review_sheet_name_uses_the_established_room_split():
    assert review_sheet_name("gio", "2215") == "Gio Jazz"
    assert review_sheet_name("gio", "221") == "Gio Wine"
    assert review_sheet_name("choco", "201") == "Choco"
    assert review_sheet_name("brigantino", "A-Ma") == "Brigantino"
    assert review_sheet_name("gio", "camera") is None


def test_review_defects_keeps_each_negative_category_once():
    class Category:
        name = "Pulizia"

    class Tag:
        polarity = "negative"
        category = Category()

    assert review_defects([Tag(), Tag()]) == ["Pulizia"]


def test_review_sheet_event_is_idempotent_and_skips_positive_only_reviews(db):
    hotel = db.query(Hotel).filter(Hotel.code == "choco").one()
    room = Room(hotel_id=hotel.id, code="201")
    category = db.query(ReviewCategory).filter(ReviewCategory.name == "Pulizia").one()
    db.add(room)
    db.flush()
    review = Review(hotel_id=hotel.id, room_id=room.id, date=date(2026, 10, 20), text="Camera sporca", rating=Decimal("4"), sync_uuid="event-201")
    db.add(review)
    db.flush()
    db.add(ReviewTag(
        review_id=review.id,
        category_id=category.id,
        polarity="negative",
        confidence=Decimal("1"),
    ))
    db.commit()
    db.refresh(review)
    event = review_sheet_event(review)
    assert event == {
        "event_id": "event-201", "sheet": "Choco", "room": "201", "defects": ["Pulizia"],
        "review_date": "2026-10-20", "source": "", "rating": 4.0, "text": "Camera sporca",
    }
