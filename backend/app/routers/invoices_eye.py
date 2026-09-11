import hashlib
import json
import secrets
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..config import settings
from ..database import get_db
from ..eye_services import apply_row_policies, create_price_alerts, ensure_invoice_metadata
from ..importers import parse_document
from ..models import Hotel, ImportJob, Invoice, InvoiceRow, Supplier
from ..schemas import InvoiceIn
from ..services import audit, create_invoice, duplicate_candidates

router = APIRouter(prefix="/api/eye/invoices", tags=["Eye Supremo invoices"])
ALLOWED = {".xml", ".txt", ".pdf"}


def resolve_hotel(db: Session, hotel_code: str | None):
    if not hotel_code:
        return None
    hotel = db.scalar(select(Hotel).where(Hotel.code == hotel_code))
    if not hotel:
        raise HTTPException(404, "Hotel non trovato")
    return hotel


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), hotel_code: str | None = None, db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, "Formato fattura supportato: XML, TXT o PDF")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File troppo grande")
    hotel = resolve_hotel(db, hotel_code)
    digest = hashlib.sha256(content).hexdigest()
    safe_name = f"{secrets.token_hex(12)}{suffix}"
    path = settings.data_dir / "uploads" / safe_name
    path.write_bytes(content)
    job = ImportJob(filename=Path(file.filename or "documento").name, stored_path=str(path), file_hash=digest, status="preview")
    db.add(job); db.flush()
    try:
        preview = parse_document(path)
    except Exception as exc:
        job.status = "error"; job.error = str(exc); audit(db, "import.error", str(exc), "error"); db.commit()
        raise HTTPException(422, str(exc))
    matches = duplicate_candidates(db, file_hash=digest)
    preview.update({"job_id": job.id, "file_hash": digest, "duplicate_matches": [i.id for i in matches], "hotel": hotel.name if hotel else None, "hotel_code": hotel.code if hotel else None})
    job.payload_json = json.dumps(preview, ensure_ascii=False)
    audit(db, "import.preview", f"Anteprima Eye Supremo per {job.filename}")
    db.commit()
    return preview


@router.post("/import/{job_id}/confirm")
def import_confirm(job_id: int, payload: dict | None = None, hotel_code: str | None = None, force: bool = False, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if not job or not job.payload_json:
        raise HTTPException(404, "Anteprima non trovata")
    if job.status == "completed":
        raise HTTPException(409, "Importazione già confermata")
    hotel = resolve_hotel(db, hotel_code)
    preview = json.loads(job.payload_json)
    if payload:
        preview["supplier"].update(payload.get("supplier", {})); preview["invoice"].update(payload.get("invoice", {}))
        if payload.get("rows") is not None:
            preview["rows"] = payload["rows"]
    supplier_data = preview["supplier"]
    supplier = db.scalar(select(Supplier).where(Supplier.partita_iva == supplier_data.get("partita_iva"))) if supplier_data.get("partita_iva") else None
    if not supplier:
        supplier = db.scalar(select(Supplier).where(Supplier.ragione_sociale == supplier_data["ragione_sociale"]))
    if not supplier:
        supplier = Supplier(**{k: v for k, v in supplier_data.items() if k in {"ragione_sociale", "partita_iva", "codice_fiscale", "indirizzo", "email", "telefono", "note"}})
        db.add(supplier); db.flush()
    invoice_data = preview["invoice"]
    invoice_payload = InvoiceIn(supplier_id=supplier.id, numero=invoice_data["numero"], data=invoice_data["data"], imponibile=invoice_data["imponibile"], iva=invoice_data["iva"], totale=invoice_data["totale"], valuta=invoice_data.get("valuta", "EUR"), file_originale=job.filename, hash_file=job.file_hash, testo_estratto=preview.get("extracted_text"), rows=preview.get("rows", []))
    matches = duplicate_candidates(db, job.file_hash, invoice_payload.numero, invoice_payload.data, supplier.id, invoice_payload.totale)
    if matches and not force:
        raise HTTPException(409, {"message": "Possibile duplicato", "matches": [x.id for x in matches]})
    invoice = create_invoice(db, invoice_payload)
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.rows)).where(Invoice.id == invoice.id))
    ensure_invoice_metadata(db, invoice, hotel.id if hotel else None)
    apply_row_policies(db, invoice)
    job.status = "completed"
    db.commit()
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.rows).selectinload(InvoiceRow.policy)).where(Invoice.id == invoice.id))
    alerts = create_price_alerts(db, invoice)
    audit(db, "import.completed", f"Importata fattura {invoice.numero} in Eye Supremo", entity_type="invoice", entity_id=invoice.id)
    db.commit()
    return {"ok": True, "invoice_id": invoice.id, "hotel": hotel.name if hotel else None, "alerts_created": len(alerts)}
