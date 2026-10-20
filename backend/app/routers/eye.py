import json
import re
import hashlib
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from ..ai_service import eye_ai_answer
from ..config import settings
from ..central_service import central_invoice_detail, central_invoice_search, central_product_detail, central_supplier_detail, central_supplier_page, configured as central_configured
from ..central_cache import cache_status, cached_row_search, cached_search, refresh_central_cache
from ..central_service import central_review_upsert
from ..local_cache_bootstrap import bootstrap_status, run_local_cache_bootstrap, schedule_bootstrap
from ..review_cache import cached_review_search, refresh_review_cache, review_cache_status
from ..review_sheet_sync import sync_review_defects
from ..review_sync import review_sync_summary, set_review_state
from ..database import SessionLocal, get_db
from ..eye_services import (
    add_review, ensure_invoice_metadata,
    review_rankings, room_rating_timeline, seed_eye_supremo, classify_review_text,
)
from ..models import (
    Alert, AppSetting, AuditLog, EmergingTheme, Hotel, Invoice, InvoiceMeta, InvoiceRow, Product, Review, ReviewCategory,
    ReviewTag, Room, Supplier, CentralInvoiceCache, CentralReviewCache, RoleExclusion, UserProfile,
)
from ..normalization import normalize_text
from ..review_importers import (clean_review_text, extract_category_scores, normalized_review_rating,
                                normalized_source, parse_review_document, review_identity, split_review_blocks)
from ..sync_service import push_to_supabase, sync_configuration
from ..services import audit

router = APIRouter(prefix="/api/eye", tags=["Eye Supremo"])


def _valid_room(code: str | None) -> str | None:
    """Un numero camera è fatto di cifre (es. 325, 4407, 1108A): parole come «pulita» o «super» non lo sono."""
    value = (code or "").strip()
    return value if re.fullmatch(r"\d{1,4}[A-Za-z]?", value) else None


def _review_payload(review: Review, *, review_id=None, text: str | None = None, date_value: str | None = None,
                    room_code: str | None = None, author: str | None = None, source: str | None = None,
                    rating: float | None = None, tags: list[dict] | None = None, inherit_room: bool = True) -> dict:
    return {
        "id": review.id if review_id is None else review_id,
        "hotel": review.hotel.name,
        "hotel_code": review.hotel.code,
        "room": _valid_room(room_code if room_code is not None else (review.room.code if review.room and inherit_room else None)),
        "author": author if author is not None else review.author,
        "source": source if source is not None else review.source,
        "rating": rating if rating is not None else (float(review.rating) if review.rating is not None else None),
        "date": date_value or review.date.isoformat(),
        "text": clean_review_text(text if text is not None else review.text),
        "scores": extract_category_scores(text if text is not None else review.text, source if source is not None else review.source),
        "tags": tags if tags is not None else [{"category": t.category.name, "polarity": t.polarity, "confidence": float(t.confidence)} for t in review.tags],
    }


def _expanded_review_payloads(review: Review) -> list[dict]:
    """Expose legacy digest emails as separate review rows without losing originals."""
    blocks = split_review_blocks(review.text, review.date.isoformat(), review.source or "email", review.author, review.raw_file or "")
    if len(blocks) <= 1:
        block = blocks[0] if blocks else {}
        try:
            block_rating = float(str(block["rating"]).replace(",", ".")) if block.get("rating") is not None else None
        except (TypeError, ValueError):
            block_rating = None
        payload = _review_payload(
            review,
            room_code=block.get("room_code"),
            author=block.get("author"),
            source=block.get("source"),
            rating=block_rating,
            date_value=block.get("date") or review.date.isoformat(),
        )
        # Il voto nel testo ha la precedenza; se manca (recensione già separata) vale quello salvato.
        payload["rating"] = block_rating if block_rating is not None else (float(review.rating) if review.rating is not None else None)
        return [_finalize_review_payload(payload, review.id)]
    expanded = []
    for index, block in enumerate(blocks, start=1):
        try:
            block_rating = float(str(block["rating"]).replace(",", ".")) if block.get("rating") is not None else None
        except (TypeError, ValueError):
            block_rating = None
        payload = _review_payload(
            review,
            review_id=f"{review.id}:part:{index}",
            text=block.get("text") or "",
            date_value=block.get("date") or review.date.isoformat(),
            room_code=block.get("room_code"),
            author=block.get("author"),
            source=block.get("source"),
            rating=block_rating,
            tags=[],
            inherit_room=False,  # la camera salvata sull'intera email non vale per le singole recensioni
        )
        # ``None`` means the individual block has no recognized score; do not
        # inherit the digest-level score from the parent email.
        payload["rating"] = block_rating
        expanded.append(_finalize_review_payload(payload, review.id))
    return expanded


def _finalize_review_payload(payload: dict, raw_review_id: int) -> dict:
    source = normalized_source(payload.get("source"))
    raw_rating = payload.get("rating")
    rating = normalized_review_rating(raw_rating, source)
    payload["source"] = source
    payload["rating"] = rating
    payload["raw_review_id"] = raw_review_id
    payload["normalized_key"] = review_identity(
        hotel_code=payload.get("hotel_code"), review_date=payload.get("date"),
        room_code=payload.get("room"), source=source, rating=rating,
        text=payload.get("text") or "",
    )
    payload["valid"] = bool(clean_review_text(payload.get("text") or "")) and source is not None
    payload["excluded_reason"] = None if payload["valid"] else "testo o fonte non riconosciuti"
    if raw_rating is not None and rating is None:
        payload["valid"] = False
        payload["excluded_reason"] = "voto fuori scala o non leggibile"
    return payload


def _review_stats(db: Session, hotel_code: str | None = None) -> dict:
    stmt = select(Review).options(selectinload(Review.hotel), selectinload(Review.room))
    if hotel_code:
        stmt = stmt.join(Hotel, Review.hotel_id == Hotel.id).where(Hotel.code == hotel_code)
    raw_reviews = db.scalars(stmt).all()
    seen: set[str] = set()
    expanded = normalized = duplicates = excluded = valid_votes = without_room = without_rating = 0
    for review in raw_reviews:
        for payload in _expanded_review_payloads(review):
            expanded += 1
            if not payload.get("valid"):
                excluded += 1
                continue
            key = payload["normalized_key"]
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            normalized += 1
            if payload.get("rating") is not None:
                valid_votes += 1
            else:
                without_rating += 1
            if not payload.get("room"):
                without_room += 1
    return {"raw": len(raw_reviews), "expanded": expanded, "normalized": normalized,
            "valid": normalized, "excluded": excluded, "duplicates": duplicates,
            "valid_votes": valid_votes, "without_room": without_room,
            "without_rating": without_rating}


def current_role(x_eye_role: str = Header(default="developer", alias="X-Eye-Role")) -> str:
    role = x_eye_role.strip().lower()
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Ruolo non valido")
    return role


def current_username(x_eye_user: str = Header(default="", alias="X-Eye-User")) -> str:
    return x_eye_user.strip().lower()


def allowed_hotel_ids(db: Session, role: str, username: str) -> set[int] | None:
    # Permessi unificati: ogni profilo attivo vede tutti gli hotel.
    return None


def hotel_from_code(db: Session, code: str) -> Hotel:
    hotel = db.scalar(select(Hotel).where(Hotel.code == code))
    if not hotel:
        raise HTTPException(404, "Hotel non trovato")
    return hotel


def require_hotel_access(db: Session, hotel: Hotel, role: str, username: str):
    allowed = allowed_hotel_ids(db, role, username)
    if allowed is not None and hotel.id not in allowed:
        raise HTTPException(403, "Hotel non assegnato a questo utente")


@router.get("/reviews/stats")
def review_stats(hotel_code: str | None = None, role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    if hotel_code:
        require_hotel_access(db, hotel_from_code(db, hotel_code), role, username)
    return _review_stats(db, hotel_code)


@router.get("/hotels")
def hotels(role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    stmt = select(Hotel).where(Hotel.active.is_(True))
    allowed = allowed_hotel_ids(db, role, username)
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(Hotel.id.in_(allowed))
    return db.scalars(stmt.order_by(Hotel.name)).all()


@router.get("/users")
def users(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Profilo non autorizzato")
    return db.scalars(select(UserProfile).order_by(UserProfile.id)).all()


@router.get("/role-exclusions")
def exclusions(role_name: str | None = None, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        role_name = role
    stmt = select(RoleExclusion)
    if role_name:
        stmt = stmt.where(RoleExclusion.role_name == role_name)
    return db.scalars(stmt.order_by(RoleExclusion.role_name, RoleExclusion.exclusion_type, RoleExclusion.value)).all()


@router.post("/role-exclusions")
def add_exclusion(payload: dict, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Profilo non autorizzato")
    raise HTTPException(410, "I livelli utente sono stati eliminati: le esclusioni per livello non sono più utilizzate")


@router.post("/ai/ask")
async def ask_eye(payload: dict, role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(422, "Domanda vuota")
    hotel_id = None
    if payload.get("hotel_code"):
        hotel = hotel_from_code(db, str(payload["hotel_code"])); require_hotel_access(db, hotel, role, username); hotel_id = hotel.id
    return await eye_ai_answer(db, question, role_name=role, hotel_id=hotel_id)


@router.post("/invoices/{invoice_id}/hotel/{hotel_code}")
def assign_invoice_hotel(invoice_id: int, hotel_code: str, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Fattura non trovata")
    hotel = hotel_from_code(db, hotel_code)
    meta = ensure_invoice_metadata(db, inv, hotel.id); db.commit(); db.refresh(meta)
    return {"ok": True, "invoice_id": invoice_id, "destination": hotel.name, "sync_uuid": meta.sync_uuid}


RATING_SCALE = {"booking": 10, "google": 5, "tripadvisor": 5}


def _parse_rating(value, source: str | None) -> Decimal | None:
    """Voto da testo: accetta la virgola decimale e scarta valori illeggibili o fuori scala."""
    if value is None or str(value).strip() == "":
        return None
    try:
        rating = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    scale = RATING_SCALE.get((source or "").strip().lower(), 10)
    return rating if rating.is_finite() and 0 <= rating <= scale else None


def _already_imported(db: Session, hotel_id: int, review_date: date, room_code: str | None, source: str | None, text: str) -> bool:
    """Una recensione identica (hotel, data, camera, fonte e testo) non viene importata due volte."""
    stmt = select(Review.id).where(
        Review.hotel_id == hotel_id, Review.date == review_date, Review.text == text,
        (Review.source == source) if source else Review.source.is_(None),
    )
    if room_code:
        stmt = stmt.join(Room, Review.room_id == Room.id).where(Room.code == room_code)
    else:
        stmt = stmt.where(Review.room_id.is_(None))
    if db.scalar(stmt.limit(1)) is not None:
        return True
    # Le email importate con le versioni vecchie sono salvate intere in un solo record:
    # una recensione già contenuta in un record dello stesso hotel conta come già presente.
    clean = text.strip()
    if len(clean) >= 60:
        contained = select(Review.id).where(Review.hotel_id == hotel_id, Review.text.contains(clean, autoescape=True)).limit(1)
        return db.scalar(contained) is not None
    return False


@router.post("/reviews/import/{hotel_code}")
async def import_reviews(hotel_code: str, files: list[UploadFile] = File(...), role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    hotel = hotel_from_code(db, hotel_code); require_hotel_access(db, hotel, role, username)
    imported, errors, skipped, skipped_files = [], [], 0, 0
    seen_files: set[str] = set()
    existing_keys = {
        payload["normalized_key"]
        for review in db.scalars(select(Review).where(Review.hotel_id == hotel.id)).all()
        for payload in _expanded_review_payloads(review)
        if payload.get("valid")
    }
    if len(files) > 200:
        errors.append({"file": None, "error": f"Caricati al massimo 200 file per volta: {len(files) - 200} non elaborati, ricaricali separatamente"})
    for file in files[:200]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".msg", ".eml", ".txt"}:
            errors.append({"file": file.filename, "error": "Formato recensione supportato: MSG, EML o TXT"}); continue
        content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            errors.append({"file": file.filename, "error": "File troppo grande"}); continue
        digest = hashlib.sha256(content).hexdigest()
        if digest in seen_files:
            skipped_files += 1  # stesso file selezionato due volte nello stesso caricamento
            continue
        seen_files.add(digest)
        safe = settings.data_dir / "reviews" / f"{secrets.token_hex(12)}{suffix}"
        safe.write_bytes(content)
        try:
            parsed_reviews = parse_review_document(safe)
            if not parsed_reviews:
                errors.append({"file": file.filename, "error": "Nessuna recensione riconosciuta nel messaggio"}); continue
            file_count = 0
            for index, parsed in enumerate(parsed_reviews, start=1):
                # Un blocco difettoso non deve far perdere le altre recensioni dello stesso file.
                try:
                    review_date = date.fromisoformat(parsed["date"])
                    rating = _parse_rating(parsed.get("rating"), parsed.get("source"))
                    if parsed.get("rating") and rating is None:
                        errors.append({"file": file.filename, "error": f"Recensione {index}: voto «{parsed['rating']}» non valido, salvata senza voto"})
                    key = review_identity(hotel_code=hotel.code, review_date=review_date.isoformat(),
                                          room_code=parsed.get("room_code"), source=parsed.get("source"),
                                          rating=rating, text=parsed["text"])
                    if key in existing_keys or _already_imported(db, hotel.id, review_date, parsed.get("room_code"), parsed.get("source"), parsed["text"]):
                        skipped += 1
                        continue
                    review = add_review(db, hotel_id=hotel.id, text=parsed["text"], review_date=review_date, rating=rating,
                                        room_code=parsed.get("room_code"), source=parsed.get("source"), author=parsed.get("author"), raw_file=parsed.get("raw_file"))
                    imported.append(review.id); file_count += 1; existing_keys.add(key)
                    sheet_result = await sync_review_defects(db, review)
                    if sheet_result.get("enabled") and not sheet_result.get("sent"):
                        errors.append({"file": file.filename, "error": f"Recensione locale salvata, foglio difetti: {sheet_result.get('message', 'sync non riuscita')}"})
                    if central_configured():
                        try:
                            sync_result = await central_review_upsert({"sync_uuid": review.sync_uuid, "hotel_code": hotel.code, "review_date": review.date.isoformat(), "source": review.source, "author": review.author, "rating": float(review.rating) if review.rating is not None else None, "room_code": parsed.get("room_code"), "text": review.text})
                            if not sync_result.get("synced"):
                                errors.append({"file": file.filename, "review_id": review.id, "error": f"Recensione locale salvata, sync centrale non completato: {sync_result.get('message') or 'Supabase non disponibile; resta in coda locale'}"})
                            else:
                                set_review_state(db, review, "sincronizzato")
                                db.commit()
                        except Exception as sync_exc:
                            errors.append({"file": file.filename, "review_id": review.id, "error": f"Recensione locale salvata, sync centrale: {sync_exc}"})
                except Exception as block_exc:
                    db.rollback()
                    errors.append({"file": file.filename, "error": f"Recensione {index} non importata: {block_exc}"})
        except Exception as exc:
            errors.append({"file": file.filename, "error": str(exc)})
    for error in errors:
        audit(db, "import.error", f"Recensioni {hotel.name}: {error.get('error', 'errore import')}", "error")
    if errors:
        db.commit()
    return {"hotel": hotel.name, "imported": len(imported), "skipped_duplicates": skipped, "skipped_duplicate_files": skipped_files, "review_ids": imported, "errors": errors}


@router.get("/reviews")
def reviews(hotel_code: str | None = None, q: str = "", limit: int | None = Query(None, ge=1), background_tasks: BackgroundTasks = None, role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    stmt = select(Review).options(selectinload(Review.hotel), selectinload(Review.room), selectinload(Review.tags).selectinload(ReviewTag.category))
    if hotel_code:
        hotel = hotel_from_code(db, hotel_code); require_hotel_access(db, hotel, role, username); stmt = stmt.where(Review.hotel_id == hotel.id)
    else:
        allowed = allowed_hotel_ids(db, role, username)
        if allowed is not None:
            if not allowed: return []
            stmt = stmt.where(Review.hotel_id.in_(allowed))
    if q:
        stmt = stmt.where(Review.text.ilike(f"%{q}%"))
    ordered = stmt.order_by(Review.date.desc())
    # Do not apply the database limit before expansion: one legacy email can
    # contain many reviews and would otherwise hide them from the archive.
    items = db.scalars(ordered).unique().all()
    result = []
    seen_expanded: set[str] = set()
    for review in items:
        for payload in _expanded_review_payloads(review):
            # Legacy archives may not have persisted ReviewTag rows yet. Keep
            # the historical view useful by applying the same deterministic
            # classifier to the cleaned review text on read.
            if not payload.get("tags") and payload.get("text"):
                payload["tags"] = [
                    {"category": tag["category"], "polarity": tag["polarity"], "confidence": float(tag["confidence"])}
                    for tag in classify_review_text(db, payload["text"], review.hotel_id)
                ]
            if q:
                haystack = f"{payload['text']} {payload.get('room') or ''} {payload['hotel']}".lower()
                if q.lower() not in haystack:
                    continue
            if not payload.get("valid"):
                continue
            identity = payload["normalized_key"]
            if identity in seen_expanded:
                continue
            seen_expanded.add(identity)
            result.append(payload)
    cached = db.scalars(select(CentralReviewCache)).all()
    fetch_limit = limit if limit is not None else 500
    status = review_cache_status(db)
    # Cache PC first; sync Supabase solo in background. Legacy digest emails
    # are expanded before the limit so individual reviews are not hidden.
    if background_tasks is not None and central_configured():
        background_tasks.add_task(refresh_review_cache)
    if status["count"] and len(result) < fetch_limit:
        local_ids = {r.sync_uuid for r in items if r.sync_uuid}
        allowed_codes = None
        if hotel_code:
            allowed_codes = {hotel_code}
        else:
            allowed = allowed_hotel_ids(db, role, username)
            if allowed is not None:
                allowed_codes = {h.code for h in db.scalars(select(Hotel).where(Hotel.id.in_(allowed))).all()} if allowed else set()
        cached_items = cached_review_search(
            db,
            q,
            hotel_code=hotel_code,
            limit=fetch_limit - len(result),
            exclude_sync_uuids=local_ids,
        )
        for item in cached_items:
            if allowed_codes is not None and item.get("hotel_code") not in allowed_codes:
                continue
            cache_payload = _finalize_review_payload({
                "id": f"cache:{item['sync_uuid']}",
                "hotel": item.get("hotel") or item.get("hotel_code"),
                "hotel_code": item.get("hotel_code"),
                "room": item.get("room"),
                "author": item.get("author"),
                "source": item.get("source"),
                "rating": item.get("rating"),
                "date": item.get("date"),
                "text": item.get("text"),
                "tags": [],
                "origin": "sqlite-cache",
            }, 0)
            if not cache_payload["valid"] or cache_payload["normalized_key"] in seen_expanded:
                continue
            seen_expanded.add(cache_payload["normalized_key"])
            result.append(cache_payload)
    return result[:limit] if limit is not None else result


@router.post("/reviews/sync")
async def reviews_sync(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}: raise HTTPException(403, "Permesso insufficiente")
    push = {"configured": central_configured(), "attempted": 0, "synced": 0, "errors": []}
    if central_configured():
        reviews = db.scalars(select(Review).options(selectinload(Review.hotel), selectinload(Review.room))).all()
        for review in reviews:
            push["attempted"] += 1
            try:
                result = await central_review_upsert({
                    "sync_uuid": review.sync_uuid,
                    "hotel_code": review.hotel.code,
                    "review_date": review.date.isoformat(),
                    "source": review.source,
                    "author": review.author,
                    "rating": float(review.rating) if review.rating is not None else None,
                    "room_code": review.room.code if review.room else None,
                    "text": review.text,
                })
                if result.get("synced"):
                    push["synced"] += 1
                else:
                    push["errors"].append({"review_id": review.id, "error": result.get("message") or "Supabase centrale non configurato"})
            except Exception as exc:
                push["errors"].append({"review_id": review.id, "error": str(exc)})
    pull = await refresh_review_cache()
    return {"push": push, "pull": pull}


@router.post("/reviews/sync/push")
async def reviews_sync_push(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}: raise HTTPException(403, "Permesso insufficiente")
    from ..review_cache import push_local_reviews
    result = await push_local_reviews(db)
    if result["pushed"]:
        try: await refresh_review_cache()
        except Exception: pass
    return result


@router.get("/reviews/sync/status")
def reviews_sync_status(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}: raise HTTPException(403, "Permesso insufficiente")
    summary = review_sync_summary(db)
    db.commit()
    return {"configured": central_configured(), **review_cache_status(db), "review_sync": summary}


@router.get("/data-health")
def data_health(role: str = Depends(current_role), db: Session = Depends(get_db)):
    """Riepilogo leggibile della qualità e della disponibilità dei dati locali."""
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    review_stats = _review_stats(db)
    review_sync = review_sync_summary(db)
    invoice_meta = db.scalars(select(InvoiceMeta)).all()
    invoice_sync_counts = {status: sum(1 for item in invoice_meta if item.sync_status == status)
                           for status in {"local", "inviato", "sincronizzato", "conflitto"}}
    local = {
        "invoices": db.scalar(select(func.count()).select_from(Invoice)) or 0,
        "invoice_rows": db.scalar(select(func.count()).select_from(InvoiceRow)) or 0,
        "suppliers": db.scalar(select(func.count()).select_from(Supplier)) or 0,
        "products": db.scalar(select(func.count()).select_from(Product)) or 0,
        "reviews_raw": review_stats["raw"],
        "reviews_valid": review_stats["valid"],
    }
    synchronized = (review_sync["counts"].get("sincronizzato", 0) + invoice_sync_counts.get("sincronizzato", 0))
    queued = (review_sync["queue_size"] + invoice_sync_counts.get("local", 0) + invoice_sync_counts.get("inviato", 0))
    conflicts = review_sync["counts"].get("conflitto", 0) + invoice_sync_counts.get("conflitto", 0)
    error_logs = db.scalars(select(AuditLog).where(AuditLog.event_type == "import.error").order_by(AuditLog.created_at.desc()).limit(10)).all()
    backup_logs = db.scalars(select(AuditLog).where(AuditLog.event_type == "backup.created").order_by(AuditLog.created_at.desc()).limit(5)).all()
    settings_map = {key: db.get(AppSetting, key) for key in ("central_sync_at", "central_review_sync_at")}
    db.commit()
    return {
        "generated_at": datetime.now().isoformat(),
        "local_records": {**local, "total": local["invoices"] + local["invoice_rows"] + local["suppliers"] + local["products"] + local["reviews_raw"]},
        "synchronized": {"total": synchronized, "reviews": review_sync["counts"].get("sincronizzato", 0), "invoices": invoice_sync_counts.get("sincronizzato", 0)},
        "sync": {"queued": queued, "conflicts": conflicts, "supabase_configured": central_configured(), "reviews": review_sync, "invoices": invoice_sync_counts},
        "imports": {"errors": len(error_logs), "latest_errors": [{"message": item.message, "created_at": item.created_at.isoformat() if item.created_at else None} for item in error_logs]},
        "reviews": {"without_room": review_stats["without_room"], "without_rating": review_stats["without_rating"]},
        "last_sync": {"invoices": settings_map["central_sync_at"].value if settings_map["central_sync_at"] else None, "reviews": settings_map["central_review_sync_at"].value if settings_map["central_review_sync_at"] else None},
        "backups": {"count": len(backup_logs), "latest": [{"message": item.message, "created_at": item.created_at.isoformat() if item.created_at else None} for item in backup_logs]},
    }


@router.get("/rankings")
def rankings(hotel_code: str | None = None, limit: int = Query(5, ge=1, le=25), role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    hotel_id = None
    if hotel_code:
        hotel = hotel_from_code(db, hotel_code); require_hotel_access(db, hotel, role, username); hotel_id = hotel.id
    return review_rankings(db, hotel_id=hotel_id, limit=limit)


@router.get("/rankings/by-hotel")
def rankings_by_hotel(limit: int = Query(5, ge=1, le=25), role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    allowed = allowed_hotel_ids(db, role, username)
    stmt = select(Hotel).where(Hotel.active.is_(True))
    if allowed is not None:
        if not allowed: return {}
        stmt = stmt.where(Hotel.id.in_(allowed))
    result = {}
    for hotel in db.scalars(stmt).all():
        result[hotel.code] = {"hotel": hotel.name, **review_rankings(db, hotel_id=hotel.id, limit=limit)}
    return result


@router.get("/rankings/timeline")
def rankings_timeline(hotel_code: str | None = None, role: str = Depends(current_role), username: str = Depends(current_username), db: Session = Depends(get_db)):
    hotel_id = None
    if hotel_code:
        hotel = hotel_from_code(db, hotel_code); require_hotel_access(db, hotel, role, username); hotel_id = hotel.id
    return {"rooms": room_rating_timeline(db, hotel_id=hotel_id)}


@router.get("/emerging-themes")
def emerging_themes(status: str = "candidate", db: Session = Depends(get_db)):
    stmt = select(EmergingTheme).where(EmergingTheme.status == status).order_by(EmergingTheme.occurrences.desc(), EmergingTheme.last_seen.desc())
    return db.scalars(stmt.limit(200)).all()


@router.post("/emerging-themes/{theme_id}/approve")
def approve_theme(theme_id: int, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Profilo non autorizzato")
    theme = db.get(EmergingTheme, theme_id)
    if not theme:
        raise HTTPException(404, "Tema non trovato")
    category = db.scalar(select(ReviewCategory).where(ReviewCategory.name == theme.name))
    if not category:
        category = ReviewCategory(name=theme.name, auto_learned=True); db.add(category); db.flush()
    theme.status = "approved"; theme.merged_into_id = category.id; db.commit()
    return {"ok": True, "category_id": category.id, "name": category.name}


@router.get("/alerts")
def alerts(unread_only: bool = False, limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(Alert)
    if unread_only:
        stmt = stmt.where(Alert.is_read.is_(False), Alert.resolved.is_(False))
    items = db.scalars(stmt.order_by(Alert.created_at.desc()).limit(limit)).all()
    if items:
        return items
    # Central imports do not create local Alert rows. Expose a factual,
    # non-actionable notice so the tab reflects the shared archive too.
    central = list(db.scalars(select(CentralInvoiceCache)).all())
    credits = [x for x in central if float(x.total or 0) < 0]
    if credits and not unread_only:
        amount = sum(float(x.total or 0) for x in credits)
        return [{"id": "central-credit-notes", "hotel_id": None, "kind": "accounting", "severity": "info", "title": "Note di accredito escluse dai totali", "description": f"{len(credits)} documenti per {abs(amount):.2f} € sono esclusi dalla spesa.", "is_read": True, "resolved": True, "created_at": max(x.invoice_date for x in credits).isoformat()}]
    return []


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int, db: Session = Depends(get_db)):
    item = db.get(Alert, alert_id)
    if not item:
        raise HTTPException(404, "Alert non trovato")
    item.is_read = True; db.commit(); return {"ok": True}


@router.get("/sync/status")
def sync_status():
    return sync_configuration()


@router.get("/central/status")
def central_status():
    return {"configured": central_configured(), "remote": "Supabase", "dataset": "eye_central_invoice_search"}


@router.get("/central/invoices")
async def central_invoices(q: str = "", limit: int = Query(50, ge=1, le=5000), offset: int = Query(0, ge=0), background_tasks: BackgroundTasks = None, role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        status = cache_status(db)
        if status["count"]:
            # Cache PC first: più veloce di Supabase; sync solo in background.
            if background_tasks is not None and central_configured():
                background_tasks.add_task(refresh_central_cache)
            if q.strip():
                row_page = cached_row_search(db, q, limit=limit, offset=offset)
                if row_page.get("total"):
                    return {
                        "enabled": True,
                        "local": True,
                        "items": row_page["items"],
                        "count": row_page["count"],
                        "total": row_page["total"],
                        "offset": row_page["offset"],
                        "limit": row_page["limit"],
                        "suppliers": row_page.get("suppliers") or [],
                        "supplier_count": row_page.get("supplier_count") or 0,
                        "source": "sqlite-cache",
                        "scope": "full-cache",
                        "sync": status,
                    }
                # Cache piena ma 0 match per questa query → prova Supabase
                # (la cache può essere parziale/stale; non bloccare la ricerca).
            else:
                cached = cached_search(db, q, limit, offset)
                return cached | {"source": "sqlite-cache", "sync": status}
    finally:
        db.close()
    # Cache vuota, oppure query senza match in cache: prova Supabase.
    if background_tasks is not None and central_configured():
        background_tasks.add_task(refresh_central_cache)
    central = await central_invoice_search(q, limit)
    if central.get("items") or not central.get("message"):
        return central | {"source": "supabase"}
    db = SessionLocal()
    try:
        cached = cached_search(db, q, limit, offset)
        return cached | {"source": "sqlite-cache-offline", "offline": True, "remote_message": central.get("message")}
    finally:
        db.close()


@router.get("/central/invoices/{source_hash}")
async def central_invoice_detail_route(source_hash: str, role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    try:
        remote = await central_invoice_detail(source_hash)
        if remote and remote.get("invoice_number"):
            return remote
    except Exception:
        pass
    item = db.get(CentralInvoiceCache, source_hash)
    if not item:
        raise HTTPException(404, "Fattura centrale non trovata")
    return json.loads(item.payload_json or "{}")


def _local_invoice_ref(db: Session, invoice: Invoice) -> dict:
    """Fattura locale nello stesso formato del dettaglio centrale (per l'anteprima unica in app)."""
    rows = db.scalars(select(InvoiceRow).where(InvoiceRow.invoice_id == invoice.id).order_by(InvoiceRow.id)).all()
    return {
        "source": "local",
        "id": invoice.id,
        "source_hash": invoice.hash_file,
        "invoice_number": invoice.numero,
        "invoice_date": invoice.data.isoformat(),
        "supplier_name": invoice.supplier.ragione_sociale if invoice.supplier else None,
        "taxable": float(invoice.imponibile or 0),
        "vat": float(invoice.iva or 0),
        "total": float(invoice.totale or 0),
        "currency": invoice.valuta,
        "source_filename": invoice.file_originale,
        "rows": [{
            "original_description": r.descrizione_originale,
            "normalized_description": r.descrizione_normalizzata,
            "quantity": float(r.quantita or 0),
            "original_unit": r.unita_originale,
            "normalized_unit": r.unita_normalizzata,
            "unit_price": float(r.prezzo_unitario or 0),
            "line_total": float(r.totale_riga or 0),
            "normalized_price": float(r.prezzo_normalizzato) if r.prezzo_normalizzato is not None else None,
        } for r in rows],
    }


@router.get("/invoice-ref/{ref}")
async def invoice_reference(ref: str, role: str = Depends(current_role), db: Session = Depends(get_db)):
    """Fattura di riferimento di una riga prodotto.

    `ref` e' l'id numerico di una fattura locale oppure lo source_hash centrale. Prova in ordine:
    fattura locale, cache del PC, archivio centrale.
    """
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    ref = ref.strip()
    if ref.isdigit() and len(ref) <= 9:
        invoice = db.scalar(select(Invoice).options(selectinload(Invoice.supplier)).where(Invoice.id == int(ref)))
        if invoice:
            return _local_invoice_ref(db, invoice)
    else:
        invoice = db.scalar(select(Invoice).options(selectinload(Invoice.supplier)).where(Invoice.hash_file == ref))
        if invoice:
            return _local_invoice_ref(db, invoice)
        cached = db.get(CentralInvoiceCache, ref)
        if cached:
            data = json.loads(cached.payload_json or "{}")
            if data.get("rows"):
                return {**data, "source": "cache"}
        try:
            remote = await central_invoice_detail(ref)
            if remote and remote.get("invoice_number"):
                return {**remote, "source": "central"}
        except Exception:  # noqa: BLE001
            pass
        if cached:
            return {**json.loads(cached.payload_json or "{}"), "source": "cache", "rows_available": False}
    raise HTTPException(404, "Fattura di riferimento non trovata")


@router.get("/central/products/{canonical_name:path}")
async def central_product_detail_route(canonical_name: str, role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    try:
        detail = await central_product_detail(canonical_name)
        if detail.get("product"):
            return detail
    except Exception:
        pass
    db = SessionLocal()
    try:
        product = db.scalar(select(Product).where(Product.nome_canonico.ilike(canonical_name)))
        if not product:
            raise HTTPException(404, "Prodotto non trovato nella cache locale")
        history = db.execute(select(InvoiceRow, Invoice, Supplier).select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id).join(Supplier, Invoice.supplier_id == Supplier.id).where(InvoiceRow.product_id == product.id).order_by(Invoice.data)).all()
        return {"offline": True, "product": {"nome_canonico": product.nome_canonico, "categoria": product.categoria, "marca": product.marca, "unita_base": product.unita_base}, "history": [{"date": i.data.isoformat(), "supplier": s.ragione_sociale, "quantity": float(r.quantita), "price": float(r.prezzo_unitario), "normalized_price": float(r.prezzo_normalizzato) if r.prezzo_normalizzato else None, "unit": r.unita_normalizzata, "invoice": i.numero, "invoice_id": i.id} for r, i, s in history]}
    finally:
        db.close()


@router.get("/central/suppliers")
async def central_suppliers(q: str = "", limit: int = Query(2000, ge=1, le=2000), role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    try:
        page = await central_supplier_page(q, limit)
    except Exception as exc:
        page = {"enabled": False, "items": [], "total": 0, "message": str(exc)}
    if not page.get("items") and (not page.get("enabled") or page.get("message")):
        db = SessionLocal()
        try:
            term = f"%{q.strip()}%" if q.strip() else None
            stmt = select(Supplier).order_by(Supplier.ragione_sociale).limit(limit)
            if term:
                stmt = select(Supplier).where(Supplier.ragione_sociale.ilike(term) | Supplier.partita_iva.ilike(term)).order_by(Supplier.ragione_sociale).limit(limit)
            local_items = []
            for supplier in db.scalars(stmt).all():
                invoices = db.scalars(select(Invoice).where(Invoice.supplier_id == supplier.id).order_by(Invoice.data.desc())).all()
                local_items.append({"id": str(supplier.id), "ragione_sociale": supplier.ragione_sociale, "partita_iva": supplier.partita_iva, "codice_fiscale": supplier.codice_fiscale, "invoice_count": len(invoices), "total_spent": float(sum((i.totale or 0) for i in invoices)), "last_invoice_date": invoices[0].data.isoformat() if invoices else None})
            return {"enabled": False, "local": True, "offline": True, "items": local_items, "total": len(local_items), "message": page.get("message") or "Supabase non disponibile"}
        finally:
            db.close()
    if not q.strip() or not page.get("enabled"):
        return page

    # Supplier search also covers invoice-line descriptions. This keeps
    # delivery, gifts and other non-product charges out of Products while
    # still making their suppliers discoverable here.
    try:
        invoice_matches = await central_invoice_search(q, min(limit, 500))
        supplier_names = {
            normalize_text(str(item.get("supplier_name") or "")).strip()
            for item in invoice_matches.get("items", [])
            if item.get("supplier_name")
        }
        if supplier_names:
            all_suppliers = page.get("items", [])
            if not all_suppliers or len(all_suppliers) < min(limit, 2000):
                full_page = await central_supplier_page("", min(limit, 2000))
                all_suppliers = full_page.get("items", all_suppliers)
            items = [
                item for item in all_suppliers
                if normalize_text(str(item.get("ragione_sociale") or "")).strip() in supplier_names
            ]
            return {**page, "items": items, "total": len(items)}
    except Exception:
        pass
    return page


@router.get("/central/suppliers/{supplier_id}")
async def central_supplier_detail_route(supplier_id: str, role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    detail = await central_supplier_detail(supplier_id)
    if not detail.get("supplier"):
        raise HTTPException(404, "Fornitore centrale non trovato")
    return detail


@router.get("/central/sync/status")
def central_sync_status(role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}: raise HTTPException(403, "Permesso insufficiente")
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        checkpoint = db.get(AppSetting, "central_sync_at")
        return {"configured": central_configured(), "last_sync_at": checkpoint.value if checkpoint else None, **cache_status(db)}
    finally: db.close()


@router.get("/central/summary")
def central_summary(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    from ..dashboard_service import dashboard_snapshot
    return {"offline": not central_configured(), **dashboard_snapshot(db), "anomalies": []}


@router.get("/cache/bootstrap/status")
def cache_bootstrap_status(role: str = Depends(current_role), db: Session = Depends(get_db)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    return bootstrap_status(db)


@router.post("/cache/bootstrap")
async def cache_bootstrap(payload: dict | None = None, role: str = Depends(current_role)):
    """Scarica fatture e recensioni nella cache SQLite per uso offline."""
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    body = payload or {}
    background = bool(body.get("background", True))
    full = bool(body.get("full", False))
    if background:
        return schedule_bootstrap(force=True, full=full)
    return await run_local_cache_bootstrap(force=True, full=full)


@router.post("/central/sync")
async def central_sync(role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}: raise HTTPException(403, "Permesso insufficiente")
    return await refresh_central_cache()


@router.post("/sync/push")
async def sync_push(payload: dict, role: str = Depends(current_role)):
    if role not in {"developer", "supremo"}:
        raise HTTPException(403, "Permesso insufficiente")
    return await push_to_supabase(payload)
