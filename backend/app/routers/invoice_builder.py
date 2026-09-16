import json, secrets
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from fastapi import Depends
from ..config import settings
from ..database import engine, get_db
from ..models import AppSetting, Invoice, InvoiceRow
from ..services import audit, ensure_invoice_snapshot, restore_backup, validate_backup

router = APIRouter(prefix="/api")

DEFAULT_PDF_LAYOUT = {
    "brand": "EYE SUPREMO",
    "document_title": "FATTURA",
    "show_unit": True,
    "show_tax": True,
    "show_notes": True,
    "paper_size": "A4",
    "font_scale": 1.0,
}


def _validate_layout(payload: dict) -> dict:
    allowed = set(DEFAULT_PDF_LAYOUT)
    unknown = set(payload) - allowed
    if unknown: raise HTTPException(422, f"Campi layout non supportati: {', '.join(sorted(unknown))}")
    result = {**DEFAULT_PDF_LAYOUT, **payload}
    if not isinstance(result["brand"], str) or not result["brand"].strip(): raise HTTPException(422, "Brand non valido")
    if not isinstance(result["document_title"], str) or not result["document_title"].strip(): raise HTTPException(422, "Titolo documento non valido")
    if result["paper_size"] not in {"A4", "Letter", "80mm"}: raise HTTPException(422, "Formato carta non supportato")
    try: result["font_scale"] = float(result["font_scale"])
    except (TypeError, ValueError): raise HTTPException(422, "Scala font non valida")
    if not .75 <= result["font_scale"] <= 1.5: raise HTTPException(422, "Scala font deve essere tra 0.75 e 1.5")
    for key in ("show_unit", "show_tax", "show_notes"):
        if not isinstance(result[key], bool): raise HTTPException(422, f"{key} deve essere booleano")
    return result


@router.get("/pdf-layout")
def get_pdf_layout(db: Session = Depends(get_db)):
    stored = db.get(AppSetting, "pdf_layout_json")
    if not stored: return DEFAULT_PDF_LAYOUT
    try: return _validate_layout(json.loads(stored.value))
    except Exception: return DEFAULT_PDF_LAYOUT


@router.put("/pdf-layout")
def put_pdf_layout(payload: dict, db: Session = Depends(get_db)):
    layout = _validate_layout(payload)
    db.merge(AppSetting(key="pdf_layout_json", value=json.dumps(layout, ensure_ascii=False)))
    audit(db, "pdf.layout.updated", "Layout PDF aggiornato")
    db.commit()
    return layout


@router.get("/invoices/{invoice_id}/snapshot")
def invoice_snapshot(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.scalar(select(Invoice).options(selectinload(Invoice.supplier), selectinload(Invoice.rows).selectinload(InvoiceRow.product)).where(Invoice.id == invoice_id))
    if not inv: raise HTTPException(404, "Fattura non trovata")
    snapshot = ensure_invoice_snapshot(db, inv)
    return {"id": snapshot.id, "invoice_id": invoice_id, "reason": snapshot.reason, "created_at": snapshot.created_at, "snapshot": json.loads(snapshot.snapshot_json)}


@router.post("/backups/validate")
async def backup_validate(file: UploadFile = File(...)):
    if Path(file.filename or "").suffix.lower() != ".zip": raise HTTPException(415, "Serve un backup ZIP")
    content = await file.read(512 * 1024 * 1024 + 1)
    if len(content) > 512 * 1024 * 1024: raise HTTPException(413, "Backup troppo grande")
    temp = settings.data_dir / "backups" / f"validate-{secrets.token_hex(8)}.zip"
    temp.write_bytes(content)
    try:
        return {"ok": True, **validate_backup(temp)}
    except Exception as exc:
        raise HTTPException(422, str(exc))
    finally:
        temp.unlink(missing_ok=True)


@router.post("/backups/restore")
async def backup_restore(file: UploadFile = File(...)):
    if Path(file.filename or "").suffix.lower() != ".zip": raise HTTPException(415, "Serve un backup ZIP")
    content = await file.read(512 * 1024 * 1024 + 1)
    if len(content) > 512 * 1024 * 1024: raise HTTPException(413, "Backup troppo grande")
    temp = settings.data_dir / "backups" / f"restore-upload-{secrets.token_hex(8)}.zip"
    temp.write_bytes(content)
    try:
        validate_backup(temp)
        engine.dispose()
        result = restore_backup(temp)
        return result
    except Exception as exc:
        raise HTTPException(422, str(exc))
    finally:
        temp.unlink(missing_ok=True)
