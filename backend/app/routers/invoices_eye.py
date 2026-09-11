import hashlib
import io
import json
import secrets
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..eye_services import apply_row_policies, create_price_alerts, ensure_invoice_metadata
from ..importers import parse_document
from ..models import ImportJob, Invoice, InvoiceRow, Supplier
from ..schemas import InvoiceIn
from ..services import audit, create_invoice, duplicate_candidates

router = APIRouter(prefix="/api/eye/invoices", tags=["Eye Supremo invoices"])
ALLOWED = {".xml", ".txt", ".pdf"}
MAX_BATCH_FILES = 100
MAX_BATCH_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _preview_bytes(filename: str, content: bytes, db: Session) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("Formato fattura supportato: XML, TXT o PDF")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(f"File troppo grande: massimo {settings.max_upload_mb} MB")
    digest = hashlib.sha256(content).hexdigest()
    safe_name = f"{secrets.token_hex(12)}{suffix}"
    path = settings.data_dir / "uploads" / safe_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    job = ImportJob(filename=Path(filename).name, stored_path=str(path), file_hash=digest, status="preview")
    db.add(job)
    db.flush()
    try:
        preview = parse_document(path)
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        audit(db, "import.error", f"{job.filename}: {exc}", "error")
        raise ValueError(str(exc)) from exc
    matches = duplicate_candidates(db, file_hash=digest)
    preview.update({"job_id": job.id, "file_hash": digest, "filename": job.filename, "duplicate_matches": [i.id for i in matches]})
    job.payload_json = json.dumps(preview, ensure_ascii=False)
    audit(db, "import.preview", f"Anteprima Eye Supremo per {job.filename}")
    return preview


async def _collect_uploads(files: list[UploadFile]) -> tuple[list[tuple[str, bytes]], list[dict]]:
    documents: list[tuple[str, bytes]] = []
    rejected: list[dict] = []
    total_uncompressed = 0
    for upload in files:
        source_name = Path(upload.filename or "documento").name
        suffix = Path(source_name).suffix.lower()
        max_input = max(settings.max_upload_mb * 1024 * 1024, 120 * 1024 * 1024 if suffix == ".zip" else 0)
        raw = await upload.read(max_input + 1)
        if len(raw) > max_input:
            rejected.append({"filename": source_name, "error": "File/ZIP troppo grande"})
            continue
        if suffix == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        member_name = Path(member.filename).name
                        member_suffix = Path(member_name).suffix.lower()
                        if member_suffix not in ALLOWED:
                            continue
                        if member.flag_bits & 0x1:
                            rejected.append({"filename": member_name, "error": "File ZIP cifrato non supportato"})
                            continue
                        if len(documents) >= MAX_BATCH_FILES:
                            rejected.append({"filename": member_name, "error": f"Limite lotto: {MAX_BATCH_FILES} fatture"})
                            continue
                        if member.file_size > settings.max_upload_mb * 1024 * 1024:
                            rejected.append({"filename": member_name, "error": f"File troppo grande: massimo {settings.max_upload_mb} MB"})
                            continue
                        total_uncompressed += member.file_size
                        if total_uncompressed > MAX_BATCH_UNCOMPRESSED_BYTES:
                            raise ValueError("Contenuto ZIP troppo grande dopo l'estrazione")
                        documents.append((member_name, archive.read(member)))
            except (zipfile.BadZipFile, ValueError) as exc:
                rejected.append({"filename": source_name, "error": str(exc) or "ZIP non valido"})
        elif suffix in ALLOWED:
            if len(documents) >= MAX_BATCH_FILES:
                rejected.append({"filename": source_name, "error": f"Limite lotto: {MAX_BATCH_FILES} fatture"})
            else:
                total_uncompressed += len(raw)
                if total_uncompressed > MAX_BATCH_UNCOMPRESSED_BYTES:
                    rejected.append({"filename": source_name, "error": "Lotto troppo grande"})
                else:
                    documents.append((source_name, raw))
        else:
            rejected.append({"filename": source_name, "error": "Formato supportato: XML, TXT, PDF o ZIP"})
    return documents, rejected


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, "Formato fattura supportato: XML, TXT o PDF")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        preview = _preview_bytes(file.filename or "documento", content, db)
        db.commit()
        return preview
    except ValueError as exc:
        db.commit()
        raise HTTPException(422, str(exc)) from exc


@router.post("/import/preview-batch")
async def import_preview_batch(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not files:
        raise HTTPException(400, "Seleziona almeno un file")
    documents, rejected = await _collect_uploads(files)
    items: list[dict] = [{"filename": item["filename"], "ok": False, "error": item["error"]} for item in rejected]
    for filename, content in documents:
        try:
            preview = _preview_bytes(filename, content, db)
            items.append({"filename": filename, "ok": True, "preview": preview})
        except ValueError as exc:
            items.append({"filename": filename, "ok": False, "error": str(exc)})
    db.commit()
    ready = sum(1 for item in items if item["ok"])
    failed = len(items) - ready
    return {"total": len(items), "ready": ready, "failed": failed, "limit": MAX_BATCH_FILES, "items": items}


@router.post("/import/{job_id}/confirm")
def import_confirm(job_id: int, payload: dict | None = None, force: bool = False, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if not job or not job.payload_json:
        raise HTTPException(404, "Anteprima non trovata")
    if job.status == "completed":
        raise HTTPException(409, "Importazione già confermata")
    preview = json.loads(job.payload_json)
    if payload:
        preview["supplier"].update(payload.get("supplier", {}))
        preview["invoice"].update(payload.get("invoice", {}))
        if payload.get("rows") is not None:
            preview["rows"] = payload["rows"]
    supplier_data = preview["supplier"]
    supplier = db.scalar(select(Supplier).where(Supplier.partita_iva == supplier_data.get("partita_iva"))) if supplier_data.get("partita_iva") else None
    if not supplier:
        supplier = db.scalar(select(Supplier).where(Supplier.ragione_sociale == supplier_data["ragione_sociale"]))
    if not supplier:
        supplier = Supplier(**{k: v for k, v in supplier_data.items() if k in {"ragione_sociale", "partita_iva", "codice_fiscale", "indirizzo", "email", "telefono", "note"}})
        db.add(supplier)
        db.flush()
    invoice_data = preview["invoice"]
    invoice_payload = InvoiceIn(supplier_id=supplier.id, numero=invoice_data["numero"], data=invoice_data["data"], imponibile=invoice_data["imponibile"], iva=invoice_data["iva"], totale=invoice_data["totale"], valuta=invoice_data.get("valuta", "EUR"), file_originale=job.filename, hash_file=job.file_hash, testo_estratto=preview.get("extracted_text"), rows=preview.get("rows", []))
    matches = duplicate_candidates(db, job.file_hash, invoice_payload.numero, invoice_payload.data, supplier.id, invoice_payload.totale)
    if matches and not force:
        raise HTTPException(409, {"message": "Possibile duplicato", "matches": [x.id for x in matches]})
    invoice = create_invoice(db, invoice_payload)
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.rows)).where(Invoice.id == invoice.id))
    ensure_invoice_metadata(db, invoice, None)
    apply_row_policies(db, invoice)
    job.status = "completed"
    db.commit()
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.rows).selectinload(InvoiceRow.policy)).where(Invoice.id == invoice.id))
    alerts = create_price_alerts(db, invoice)
    audit(db, "import.completed", f"Importata fattura {invoice.numero} nell'archivio centrale Apice", entity_type="invoice", entity_id=invoice.id)
    db.commit()
    return {"ok": True, "invoice_id": invoice.id, "alerts_created": len(alerts)}
