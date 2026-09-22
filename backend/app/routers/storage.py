import hashlib
import json
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth_models import RemoteUpload, UserProfile
from ..auth_service import require_role
from ..config import settings
from ..database import get_db
from ..importers import parse_document
from ..models import ImportJob, Invoice
from ..routers.auth import current_user
from ..services import audit, duplicate_candidates
from .. import storage_service

router = APIRouter(prefix="/api/storage", tags=["Storage"])

ALLOWED = {".pdf", ".xml", ".docx", ".xlsx", ".pptx", ".jpg", ".jpeg", ".png", ".csv"}
OPERATOR_ROLES = {"developer", "supremo", "level1", "level2", "level3"}
UPLOAD_ROLES = OPERATOR_ROLES | {"uploader"}


def _guard(user: UserProfile, allowed: set[str]) -> None:
    try:
        require_role(user, allowed)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _serialize(item: RemoteUpload) -> dict:
    duplicates = []
    if item.duplicate_invoice_ids:
        try:
            duplicates = json.loads(item.duplicate_invoice_ids)
        except json.JSONDecodeError:
            duplicates = []
    return {
        "id": item.id,
        "original_name": item.original_name,
        "storage_path": item.storage_path,
        "file_hash": item.file_hash,
        "size_bytes": item.size_bytes,
        "content_type": item.content_type,
        "status": item.status,
        "duplicate_invoice_ids": duplicates,
        "uploaded_by": item.uploaded_by,
        "uploader_name": item.uploader.display_name if item.uploader else None,
        "note": item.note,
        "created_at": item.created_at.isoformat(timespec="seconds"),
        "updated_at": item.updated_at.isoformat(timespec="seconds") if item.updated_at else None,
    }


@router.get("/status")
def status(user: UserProfile = Depends(current_user)):
    _guard(user, UPLOAD_ROLES)
    return storage_service.storage_status()


@router.get("/central")
def central_catalog(
    limit: int = 50,
    offset: int = 0,
    user: UserProfile = Depends(current_user),
):
    """Catalogo metadati MultiHotel (~20k) via RPC eye_central_invoice_page."""
    _guard(user, OPERATOR_ROLES)
    if not settings.central_configured:
        raise HTTPException(
            503,
            "Catalogo centrale non configurato: imposta RANDFATTURE_SUPABASE_URL, "
            "chiave (service o anon) e RANDFATTURE_SUPABASE_CENTRAL_PIN",
        )
    try:
        return storage_service.central_invoice_page(limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(502, f"Catalogo centrale non raggiungibile: {exc}") from exc


@router.post("/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    user: UserProfile = Depends(current_user),
    db: Session = Depends(get_db),
):
    _guard(user, UPLOAD_ROLES)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, "Formato file non supportato")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File troppo grande")

    digest = hashlib.sha256(content).hexdigest()
    matches = duplicate_candidates(db, file_hash=digest)
    status = "possible_duplicate" if matches else "pending_review"
    original = Path(file.filename or "documento").name
    storage_path = storage_service.build_storage_path(original, digest)

    try:
        backend = storage_service.upload_bytes(
            storage_path,
            content,
            file.content_type,
            file_hash=digest,
            original_name=original,
            uploaded_by=user.username,
        )
    except Exception as exc:
        raise HTTPException(502, f"Upload Storage fallito: {exc}") from exc

    item = RemoteUpload(
        original_name=original,
        storage_path=storage_path,
        file_hash=digest,
        size_bytes=len(content),
        content_type=file.content_type or backend.get("content_type"),
        status=status,
        duplicate_invoice_ids=json.dumps([i.id for i in matches]) if matches else "[]",
        uploaded_by=user.id,
        note="Possibile duplicato per hash file" if matches else None,
    )
    db.add(item)
    audit(
        db,
        "storage.upload",
        f"{user.username} ha caricato {original} ({status})",
        entity_type="remote_upload",
    )
    db.commit()
    db.refresh(item)
    item = db.scalar(select(RemoteUpload).options(selectinload(RemoteUpload.uploader)).where(RemoteUpload.id == item.id))
    return {
        "ok": True,
        "backend": backend.get("backend"),
        "indexed": backend.get("indexed"),
        "index_error": backend.get("index_error"),
        "upload": _serialize(item),
        "duplicate_matches": [i.id for i in matches],
    }


@router.get("/inbox")
def inbox(user: UserProfile = Depends(current_user), db: Session = Depends(get_db)):
    _guard(user, UPLOAD_ROLES)
    stmt = select(RemoteUpload).options(selectinload(RemoteUpload.uploader)).order_by(RemoteUpload.created_at.desc())
    if user.role_name == "uploader":
        stmt = stmt.where(RemoteUpload.uploaded_by == user.id)
    else:
        stmt = stmt.where(RemoteUpload.status.in_(("pending_review", "possible_duplicate")))
    items = db.scalars(stmt.limit(200)).all()
    return [_serialize(x) for x in items]


@router.post("/{upload_id}/reject")
def reject(upload_id: int, user: UserProfile = Depends(current_user), db: Session = Depends(get_db)):
    _guard(user, OPERATOR_ROLES)
    item = db.get(RemoteUpload, upload_id)
    if not item:
        raise HTTPException(404, "Upload non trovato")
    item.status = "rejected"
    item.updated_at = datetime.now()
    audit(db, "storage.rejected", f"Upload {item.original_name} scartato", entity_type="remote_upload", entity_id=item.id)
    db.commit()
    return {"ok": True}


@router.post("/{upload_id}/import-preview")
def import_preview_from_storage(
    upload_id: int,
    user: UserProfile = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Scarica il file dallo Storage e crea un'anteprima import locale (senza salvare la fattura)."""
    _guard(user, OPERATOR_ROLES)
    item = db.get(RemoteUpload, upload_id)
    if not item:
        raise HTTPException(404, "Upload non trovato")
    if item.status == "rejected":
        raise HTTPException(409, "Upload già scartato")

    try:
        content = storage_service.download_bytes(item.storage_path)
    except Exception as exc:
        raise HTTPException(502, f"Download Storage fallito: {exc}") from exc

    suffix = Path(item.original_name).suffix.lower() or Path(item.storage_path).suffix.lower()
    safe_name = f"{secrets.token_hex(12)}{suffix}"
    path = settings.data_dir / "uploads" / safe_name
    path.write_bytes(content)

    job = ImportJob(filename=item.original_name, stored_path=str(path), file_hash=item.file_hash, status="preview")
    db.add(job)
    db.flush()
    try:
        preview = parse_document(path)
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        audit(db, "import.error", str(exc), "error")
        db.commit()
        raise HTTPException(422, str(exc)) from exc

    matches = list(duplicate_candidates(db, file_hash=item.file_hash))
    inv = preview.get("invoice") or {}
    numero, data = inv.get("numero"), inv.get("data")
    if numero and data:
        from datetime import date as date_cls
        parsed_date = data if hasattr(data, "year") else date_cls.fromisoformat(str(data)[:10])
        extra = db.scalars(
            select(Invoice).where(Invoice.numero == str(numero), Invoice.data == parsed_date)
        ).all()
        matches.extend(extra)
    all_ids = sorted({i.id for i in matches})
    preview.update({
        "job_id": job.id,
        "file_hash": item.file_hash,
        "stored_path": str(path),
        "duplicate_matches": all_ids,
        "remote_upload_id": item.id,
    })
    job.payload_json = json.dumps(preview, ensure_ascii=False, default=str)
    item.status = "possible_duplicate" if all_ids else "in_preview"
    item.duplicate_invoice_ids = json.dumps(all_ids)
    item.updated_at = datetime.now()
    audit(db, "storage.import_preview", f"Anteprima da Storage per {item.original_name}", entity_type="remote_upload", entity_id=item.id)
    db.commit()
    return preview


@router.post("/{upload_id}/mark-imported")
def mark_imported(upload_id: int, payload: dict | None = None, user: UserProfile = Depends(current_user), db: Session = Depends(get_db)):
    _guard(user, OPERATOR_ROLES)
    item = db.get(RemoteUpload, upload_id)
    if not item:
        raise HTTPException(404, "Upload non trovato")
    invoice_id = (payload or {}).get("invoice_id")
    item.status = "imported"
    item.note = f"Importata fattura #{invoice_id}" if invoice_id else "Importata"
    item.updated_at = datetime.now()
    if invoice_id and not db.get(Invoice, invoice_id):
        raise HTTPException(404, "Fattura non trovata")
    audit(db, "storage.imported", item.note, entity_type="remote_upload", entity_id=item.id)
    db.commit()
    return {"ok": True}
