import json
import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from .models import (
    Alert, EmergingTheme, Hotel, Invoice, InvoiceMeta, InvoiceRow, InvoiceRowPolicy,
    Review, ReviewCategory, ReviewTag, RoleExclusion, Room, Supplier, UserProfile,
)
from .normalization import normalize_text

HOTEL_SEEDS = [
    ("gio", "Hotel Giò"),
    ("choco", "Chocohotel"),
    ("brigantino", "Hotel Il Brigantino"),
]
ROLE_SEEDS = [
    ("sviluppatore", "Sviluppatore", "developer", True),
    ("supremo", "Supremo", "supremo", False),
    ("livello1", "Utente Livello 1", "level1", False),
    ("livello2", "Utente Livello 2", "level2", False),
    ("livello3", "Utente Livello 3", "level3", False),
]
REVIEW_CATEGORY_SEEDS = [
    "Camere / Arredi", "Ristorante", "Colazione", "Staff", "Letti", "Pulizia",
    "Altro", "Parcheggio", "Posizione", "Cuscini",
]
ACCOUNTING_EXCLUSION_KEYWORDS = {
    "carburante", "gasolio", "benzina", "diesel", "sconto", "abbuono", "arrotondamento",
    "trasporto", "spese trasporto", "spese bancarie", "bollo", "cauzione", "interessi",
    "contributo conai", "ritenuta", "acconto",
}
CATEGORY_KEYWORDS = {
    "Camere / Arredi": ["camera", "arredo", "mobili", "mobilio", "armadio", "comodino"],
    "Ristorante": ["ristorante", "cena", "pranzo", "menu", "menù", "cucina"],
    "Colazione": ["colazione", "breakfast", "buffet", "cornetto", "cappuccino"],
    "Staff": ["staff", "personale", "reception", "receptionist", "gentile", "cortese"],
    "Letti": ["letto", "letti", "materasso", "materassi"],
    "Pulizia": ["pulizia", "pulito", "pulita", "sporco", "sporca", "igiene"],
    "Parcheggio": ["parcheggio", "garage", "posto auto"],
    "Posizione": ["posizione", "zona", "centro", "vicino", "distanza"],
    "Cuscini": ["cuscino", "cuscini"],
}
POSITIVE_WORDS = {"ottimo", "ottima", "eccellente", "pulito", "pulita", "gentile", "comodo", "comoda", "buono", "buona", "perfetto", "perfetta", "fantastico", "fantastica"}
NEGATIVE_WORDS = {"pessimo", "pessima", "sporco", "sporca", "rumore", "rumoroso", "rotto", "rotta", "scomodo", "scomoda", "cattivo", "cattiva", "odore", "freddo", "caldo", "lento", "lenta"}


def seed_eye_supremo(db: Session) -> None:
    for code, name in HOTEL_SEEDS:
        if not db.scalar(select(Hotel).where(Hotel.code == code)):
            db.add(Hotel(code=code, name=name))
    db.flush()
    for username, display, role, can_manage in ROLE_SEEDS:
        if not db.scalar(select(UserProfile).where(UserProfile.username == username)):
            db.add(UserProfile(username=username, display_name=display, role_name=role, can_manage_config=can_manage))
    for name in REVIEW_CATEGORY_SEEDS:
        if not db.scalar(select(ReviewCategory).where(ReviewCategory.name == name)):
            db.add(ReviewCategory(name=name, auto_learned=False))
    db.commit()


def classify_invoice_row(description: str) -> tuple[str, str | None]:
    text = normalize_text(description)
    for keyword in ACCOUNTING_EXCLUSION_KEYWORDS:
        if keyword in text:
            return "accounting_excluded", keyword
    if len(text) < 2:
        return "review", "descrizione insufficiente"
    return "product", None


def ensure_invoice_metadata(db: Session, invoice: Invoice, hotel_id: int | None = None) -> InvoiceMeta:
    meta = db.get(InvoiceMeta, invoice.id)
    if not meta:
        meta = InvoiceMeta(invoice_id=invoice.id, hotel_id=hotel_id, sync_uuid=str(uuid.uuid4()), sync_status="local")
        db.add(meta)
    elif hotel_id is not None:
        meta.hotel_id = hotel_id
    return meta


def apply_row_policies(db: Session, invoice: Invoice) -> None:
    for row in invoice.rows:
        status, reason = classify_invoice_row(row.descrizione_originale)
        policy = db.get(InvoiceRowPolicy, row.id)
        if not policy:
            db.add(InvoiceRowPolicy(row_id=row.id, analysis_status=status, exclusion_reason=reason))


def role_exclusions(db: Session, role_name: str) -> list[RoleExclusion]:
    if role_name in {"developer", "supremo"}:
        return []
    return list(db.scalars(select(RoleExclusion).where(RoleExclusion.role_name == role_name, RoleExclusion.enabled.is_(True))).all())


def row_visible_to_role(db: Session, role_name: str, row: InvoiceRow, supplier: Supplier | None = None) -> bool:
    policy = row.policy
    if policy and policy.analysis_status == "accounting_excluded":
        return False
    text = normalize_text(row.descrizione_originale)
    product = normalize_text(row.product.nome_canonico) if row.product else ""
    supplier_name = normalize_text(supplier.ragione_sociale) if supplier else ""
    for rule in role_exclusions(db, role_name):
        needle = normalize_text(rule.value)
        if rule.exclusion_type == "keyword" and needle in text:
            return False
        if rule.exclusion_type == "product" and needle in product:
            return False
        if rule.exclusion_type == "supplier" and needle in supplier_name:
            return False
        if rule.exclusion_type == "category" and row.product and normalize_text(row.product.categoria or "") == needle:
            return False
    return True


def invoice_search(db: Session, query: str, role_name: str = "developer", limit: int = 50) -> list[dict]:
    q = normalize_text(query).strip()
    terms = [x for x in q.split() if x not in {"quanto", "speso", "pagato", "abbiamo", "ho", "per", "il", "la", "le", "i", "un", "una", "di", "da"}]
    needle = " ".join(terms).strip()
    year = re.search(r"\b(19|20)\d{2}\b", q)
    stmt = (select(InvoiceRow, Invoice, Supplier)
            .select_from(InvoiceRow)
            .join(Invoice, InvoiceRow.invoice_id == Invoice.id)
            .join(Supplier, Invoice.supplier_id == Supplier.id)
            .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product)))
    if year:
        stmt = stmt.where(func.strftime("%Y", Invoice.data) == year.group(0))
        needle = needle.replace(year.group(0), " ").strip()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(or_(InvoiceRow.descrizione_originale.ilike(pattern), InvoiceRow.descrizione_normalizzata.ilike(pattern), Supplier.ragione_sociale.ilike(pattern)))
    rows = db.execute(stmt.order_by(Invoice.data.desc()).limit(max(limit * 4, 100))).all()
    if needle and not rows:
        candidates = db.execute((select(InvoiceRow, Invoice, Supplier)
            .select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id)
            .join(Supplier, Invoice.supplier_id == Supplier.id)
            .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product))
            .order_by(Invoice.data.desc()).limit(1500))).all()
        scored = [(fuzz.WRatio(needle, normalize_text(r.descrizione_originale)), (r, i, s)) for r, i, s in candidates]
        rows = [item for score, item in sorted(scored, key=lambda x: x[0], reverse=True) if score >= 55][:limit * 2]
    result = []
    for row, inv, supplier in rows:
        if not row_visible_to_role(db, role_name, row, supplier):
            continue
        result.append({
            "row_id": row.id, "invoice_id": inv.id, "invoice": inv.numero,
            "date": inv.data.isoformat(), "supplier": supplier.ragione_sociale,
            "description": row.descrizione_originale, "quantity": float(row.quantita),
            "unit_price": float(row.prezzo_unitario), "row_total": float(row.totale_riga),
            "normalized_price": float(row.prezzo_normalizzato) if row.prezzo_normalizzato is not None else None,
            "unit": row.unita_normalizzata, "analysis_status": row.policy.analysis_status if row.policy else "product",
        })
        if len(result) >= limit:
            break
    return result


def invoice_search_summary(records: list[dict]) -> dict:
    return {
        "rows": len(records),
        "invoices": len({r["invoice_id"] for r in records}),
        "row_total": round(sum(r["row_total"] for r in records), 2),
        "quantity": round(sum(r["quantity"] for r in records), 4),
    }


def classify_review_text(db: Session, text: str, hotel_id: int | None = None) -> list[dict]:
    norm = normalize_text(text)
    tokens = set(norm.split())
    polarity = "negative" if len(tokens & NEGATIVE_WORDS) > len(tokens & POSITIVE_WORDS) else "positive"
    matches = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = [k for k in keywords if normalize_text(k) in norm]
        if hits:
            cat = db.scalar(select(ReviewCategory).where(ReviewCategory.name == category))
            if cat:
                matches.append({"category_id": cat.id, "category": cat.name, "polarity": polarity, "confidence": min(1.0, .65 + .08 * len(hits))})
    return matches


def register_emerging_theme(db: Session, hotel_id: int | None, name: str) -> EmergingTheme:
    normalized = normalize_text(name)[:120]
    theme = db.scalar(select(EmergingTheme).where(EmergingTheme.hotel_id == hotel_id, EmergingTheme.normalized == normalized))
    if theme:
        theme.occurrences += 1
        theme.last_seen = datetime.now()
        return theme
    theme = EmergingTheme(hotel_id=hotel_id, name=name[:120], normalized=normalized, occurrences=1)
    db.add(theme)
    return theme


def add_review(db: Session, *, hotel_id: int, text: str, review_date: date, rating: Decimal | None = None,
               room_code: str | None = None, source: str | None = None, author: str | None = None,
               raw_file: str | None = None) -> Review:
    room = None
    if room_code:
        room = db.scalar(select(Room).where(Room.hotel_id == hotel_id, Room.code == room_code))
        if not room:
            room = Room(hotel_id=hotel_id, code=room_code); db.add(room); db.flush()
    review = Review(hotel_id=hotel_id, room_id=room.id if room else None, source=source, author=author,
                    rating=rating, date=review_date, text=text, raw_file=raw_file, sync_uuid=str(uuid.uuid4()))
    db.add(review); db.flush()
    tags = classify_review_text(db, text, hotel_id)
    for tag in tags:
        db.add(ReviewTag(review_id=review.id, category_id=tag["category_id"], polarity=tag["polarity"], confidence=tag["confidence"]))
    # Unknown noun-like tokens become candidates only after recurrence; avoids category explosion.
    known = {normalize_text(x) for values in CATEGORY_KEYWORDS.values() for x in values}
    for token in [t for t in normalize_text(text).split() if len(t) >= 6 and t not in known][:8]:
        if token not in POSITIVE_WORDS and token not in NEGATIVE_WORDS:
            register_emerging_theme(db, hotel_id, token)
    db.commit(); db.refresh(review)
    return review


def review_rankings(db: Session, hotel_id: int | None = None, limit: int = 5) -> dict:
    room_rows = db.execute(
        select(Room.code, Hotel.name, func.count(Review.id), func.avg(Review.rating), func.avg(Review.sentiment_score))
        .select_from(Review).join(Hotel, Review.hotel_id == Hotel.id).join(Room, Review.room_id == Room.id)
        .where(*( [Review.hotel_id == hotel_id] if hotel_id else [] ))
        .group_by(Room.id, Room.code, Hotel.name)
    ).all()
    scored_rooms = []
    for code, hotel, count, avg_rating, sentiment in room_rows:
        rating = float(avg_rating or 0)
        confidence = min(1.0, (count or 0) / 10)
        score = rating * (0.6 + 0.4 * confidence) + float(sentiment or 0) * .5
        scored_rooms.append({"room": code, "hotel": hotel, "reviews": count, "rating": round(rating, 2), "score": round(score, 3)})
    scored_rooms.sort(key=lambda x: x["score"], reverse=True)

    service_rows = db.execute(
        select(ReviewCategory.name, ReviewTag.polarity, func.count(ReviewTag.id))
        .select_from(ReviewTag).join(Review, ReviewTag.review_id == Review.id).join(ReviewCategory, ReviewTag.category_id == ReviewCategory.id)
        .where(*( [Review.hotel_id == hotel_id] if hotel_id else [] ))
        .group_by(ReviewCategory.name, ReviewTag.polarity)
    ).all()
    service_counts = defaultdict(lambda: {"positive": 0, "negative": 0})
    for name, polarity, count in service_rows:
        service_counts[name][polarity] += count
    services = []
    for name, counts in service_counts.items():
        total = counts["positive"] + counts["negative"]
        score = (counts["positive"] - counts["negative"]) / total if total else 0
        services.append({"service": name, **counts, "mentions": total, "score": round(score, 3)})
    services.sort(key=lambda x: x["score"], reverse=True)
    return {
        "best_rooms": scored_rooms[:limit],
        "worst_rooms": list(reversed(scored_rooms[-limit:])),
        "best_services": services[:limit],
        "worst_services": list(reversed(services[-limit:])),
    }


def create_price_alerts(db: Session, invoice: Invoice, threshold_pct: float = 20.0) -> list[Alert]:
    created = []
    for row in invoice.rows:
        if row.policy and row.policy.analysis_status != "product":
            continue
        if not row.descrizione_normalizzata:
            continue
        history = db.scalars(
            select(InvoiceRow).join(Invoice).where(
                InvoiceRow.id != row.id,
                InvoiceRow.descrizione_normalizzata == row.descrizione_normalizzata,
                Invoice.data < invoice.data,
            ).order_by(Invoice.data.desc()).limit(10)
        ).all()
        prices = [float(x.prezzo_normalizzato or x.prezzo_unitario) for x in history if float(x.prezzo_normalizzato or x.prezzo_unitario) > 0]
        current = float(row.prezzo_normalizzato or row.prezzo_unitario)
        if not prices or current <= 0:
            continue
        avg = sum(prices) / len(prices)
        change = ((current - avg) / avg) * 100 if avg else 0
        if change >= threshold_pct:
            meta = db.get(InvoiceMeta, invoice.id)
            alert = Alert(hotel_id=meta.hotel_id if meta else None, kind="price_increase", severity="high" if change >= 35 else "warning",
                          title=f"Aumento prezzo {change:.1f}%", description=f"{row.descrizione_originale}: {current:.2f} contro media {avg:.2f}",
                          entity_type="invoice_row", entity_id=row.id)
            db.add(alert); created.append(alert)
    return created
