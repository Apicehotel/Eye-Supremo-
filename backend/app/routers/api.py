import hashlib, json, secrets
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from ..config import settings
from ..database import get_db
from ..importers import parse_document
from ..models import AppSetting, AuditLog, ImportJob, Invoice, InvoiceRow, Product, Supplier
from ..schemas import InvoiceIn, ProductIn, ProductOut, SupplierIn, SupplierOut
from ..services import answer_with_ollama, audit, create_backup, create_invoice, duplicate_candidates, ollama_status, search_records
from ..unified_invoices import list_unified_invoices

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    from ..version import APP_VERSION

    return {"status": "ok", "app": "RandFatture", "version": APP_VERSION}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    invoices = db.scalar(select(func.count(Invoice.id))) or 0
    spent = float(db.scalar(select(func.coalesce(func.sum(Invoice.totale), 0))) or 0)
    now = date.today()
    month_spent = float(db.scalar(select(func.coalesce(func.sum(Invoice.totale), 0)).where(func.strftime("%Y-%m", Invoice.data) == now.strftime("%Y-%m"))) or 0)
    supplier_count = db.scalar(select(func.count(Supplier.id))) or 0
    product_count = db.scalar(select(func.count(Product.id))) or 0
    monthly = db.execute(select(func.strftime("%Y-%m", Invoice.data), func.sum(Invoice.totale)).group_by(func.strftime("%Y-%m", Invoice.data)).order_by(func.strftime("%Y-%m", Invoice.data)).limit(24)).all()
    recent = db.scalars(select(Invoice).options(selectinload(Invoice.supplier), selectinload(Invoice.rows)).order_by(Invoice.created_at.desc()).limit(6)).all()
    central_total = None
    if settings.central_configured:
        try:
            from .. import storage_service

            page = storage_service.central_invoice_page(limit=1, offset=0)
            if isinstance(page, dict):
                central_total = page.get("total")
        except Exception:
            central_total = None
    return {
        "kpis": {
            "invoices": invoices,
            "central_invoices": central_total,
            "total_spent": spent,
            "month_spent": month_spent,
            "suppliers": supplier_count,
            "products": product_count,
        },
        "monthly": [{"month": m, "total": float(v)} for m, v in monthly],
        "recent": [serialize_invoice(x) for x in recent],
        "anomalies": detect_anomalies(db)[:5],
        "central_configured": settings.central_configured,
    }


def serialize_invoice(i):
    return {
        "id": i.id,
        "source": "local",
        "numero": i.numero,
        "data": i.data.isoformat(),
        "imponibile": float(i.imponibile),
        "iva": float(i.iva),
        "totale": float(i.totale),
        "valuta": i.valuta,
        "stato_importazione": i.stato_importazione,
        "file_originale": i.file_originale,
        "hash_file": i.hash_file,
        "supplier": {"id": i.supplier.id, "ragione_sociale": i.supplier.ragione_sociale},
        "row_count": len(i.rows),
        "openable": True,
    }


@router.get("/suppliers")
def suppliers(q: str = "", skip: int = 0, limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    stmt = select(Supplier)
    if q: stmt = stmt.where(Supplier.ragione_sociale.ilike(f"%{q}%"))
    return db.scalars(stmt.order_by(Supplier.ragione_sociale).offset(skip).limit(limit)).all()


@router.post("/suppliers", response_model=SupplierOut)
def add_supplier(payload: SupplierIn, db: Session = Depends(get_db)):
    item = Supplier(**payload.model_dump()); db.add(item); audit(db, "supplier.created", f"Fornitore {item.ragione_sociale} creato"); db.commit(); db.refresh(item); return item


@router.get("/products")
def products(q: str = "", skip: int = 0, limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    stmt = select(Product)
    if q: stmt = stmt.where(Product.nome_canonico.ilike(f"%{q}%"))
    items = db.scalars(stmt.order_by(Product.nome_canonico).offset(skip).limit(limit)).all()
    result = []
    for p in items:
        stats = db.execute(select(func.min(InvoiceRow.prezzo_normalizzato), func.max(InvoiceRow.prezzo_normalizzato), func.avg(InvoiceRow.prezzo_normalizzato), func.count(InvoiceRow.id)).where(InvoiceRow.product_id == p.id)).one()
        result.append({**ProductOut.model_validate(p).model_dump(), "min_price": float(stats[0]) if stats[0] else None, "max_price": float(stats[1]) if stats[1] else None, "avg_price": float(stats[2]) if stats[2] else None, "purchases": stats[3]})
    return result


@router.post("/products", response_model=ProductOut)
def add_product(payload: ProductIn, db: Session = Depends(get_db)):
    item = Product(**payload.model_dump()); db.add(item); audit(db, "product.created", f"Prodotto {item.nome_canonico} creato"); db.commit(); db.refresh(item); return item


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product: raise HTTPException(404, "Prodotto non trovato")
    history = db.execute(select(InvoiceRow, Invoice, Supplier).select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id).join(Supplier, Invoice.supplier_id == Supplier.id).where(InvoiceRow.product_id == product_id).order_by(Invoice.data)).all()
    return {"product": ProductOut.model_validate(product), "history": [{"date": i.data, "supplier": s.ragione_sociale, "quantity": r.quantita, "price": r.prezzo_unitario, "normalized_price": r.prezzo_normalizzato, "unit": r.unita_normalizzata, "invoice": i.numero, "invoice_id": i.id} for r, i, s in history]}


@router.get("/invoices")
def invoices(
    q: str = "",
    year: int | None = None,
    supplier_id: int | None = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    include_central: bool = True,
    db: Session = Depends(get_db),
):
    """Lista unificata: PC locale + catalogo Supabase MultiHotel (se .env configurato)."""
    return list_unified_invoices(
        db,
        q=q,
        year=year,
        supplier_id=supplier_id,
        skip=skip,
        limit=limit,
        include_central=include_central,
    )


@router.post("/invoices")
def add_invoice(payload: InvoiceIn, force: bool = False, db: Session = Depends(get_db)):
    duplicates = duplicate_candidates(db, payload.hash_file, payload.numero, payload.data, payload.supplier_id, payload.totale)
    if duplicates and not force: raise HTTPException(409, {"message": "Possibile duplicato", "matches": [x.id for x in duplicates]})
    return {"id": create_invoice(db, payload).id}


@router.get("/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.scalar(select(Invoice).options(selectinload(Invoice.supplier), selectinload(Invoice.rows).selectinload(InvoiceRow.product)).where(Invoice.id == invoice_id))
    if not inv: raise HTTPException(404, "Fattura non trovata")
    return {**serialize_invoice(inv), "testo_estratto": inv.testo_estratto, "rows": [{"id": r.id, "descrizione_originale": r.descrizione_originale, "descrizione_normalizzata": r.descrizione_normalizzata, "product": r.product.nome_canonico if r.product else None, "quantita": float(r.quantita), "unita_originale": r.unita_originale, "unita_normalizzata": r.unita_normalizzata, "prezzo_unitario": float(r.prezzo_unitario), "prezzo_normalizzato": float(r.prezzo_normalizzato) if r.prezzo_normalizzato else None, "totale_riga": float(r.totale_riga), "aliquota_iva": float(r.aliquota_iva) if r.aliquota_iva else None, "confidence": float(r.confidence)} for r in inv.rows]}


ALLOWED = {".pdf", ".xml", ".docx", ".xlsx", ".pptx", ".jpg", ".jpeg", ".png", ".csv"}


@router.post("/imports/preview")
async def import_preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED: raise HTTPException(415, "Formato file non supportato")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, "File troppo grande")
    digest = hashlib.sha256(content).hexdigest(); safe_name = f"{secrets.token_hex(12)}{suffix}"
    path = settings.data_dir / "uploads" / safe_name; path.write_bytes(content)
    job = ImportJob(filename=Path(file.filename or "documento").name, stored_path=str(path), file_hash=digest, status="preview")
    db.add(job); db.flush()
    try: preview = parse_document(path)
    except Exception as exc:
        job.status = "error"; job.error = str(exc); audit(db, "import.error", str(exc), "error"); db.commit(); raise HTTPException(422, str(exc))
    matches = duplicate_candidates(db, file_hash=digest)
    preview.update({"job_id": job.id, "file_hash": digest, "stored_path": str(path), "duplicate_matches": [i.id for i in matches]})
    job.payload_json = json.dumps(preview, ensure_ascii=False); audit(db, "import.preview", f"Anteprima creata per {job.filename}"); db.commit(); return preview


@router.post("/imports/{job_id}/confirm")
def import_confirm(job_id: int, payload: dict | None = None, force: bool = False, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if not job or not job.payload_json: raise HTTPException(404, "Anteprima non trovata")
    if job.status == "completed": raise HTTPException(409, "Importazione già confermata")
    preview = json.loads(job.payload_json)
    if payload:
        preview["supplier"].update(payload.get("supplier", {})); preview["invoice"].update(payload.get("invoice", {}))
        if payload.get("rows") is not None: preview["rows"] = payload["rows"]
    supplier_data = preview["supplier"]
    supplier = None
    if supplier_data.get("partita_iva"):
        supplier = db.scalar(select(Supplier).where(Supplier.partita_iva == supplier_data["partita_iva"]))
    if not supplier:
        supplier = db.scalar(select(Supplier).where(Supplier.ragione_sociale == supplier_data["ragione_sociale"]))
    if not supplier:
        supplier = Supplier(**{k:v for k,v in supplier_data.items() if k in {"ragione_sociale","partita_iva","codice_fiscale","indirizzo","email","telefono","note"}}); db.add(supplier); db.flush()
    invoice_data = preview["invoice"]
    invoice_payload = InvoiceIn(supplier_id=supplier.id, numero=invoice_data["numero"], data=invoice_data["data"], imponibile=invoice_data["imponibile"], iva=invoice_data["iva"], totale=invoice_data["totale"], valuta=invoice_data.get("valuta", "EUR"), file_originale=job.filename, hash_file=job.file_hash, testo_estratto=preview.get("extracted_text"), rows=preview.get("rows", []))
    matches = duplicate_candidates(db, job.file_hash, invoice_payload.numero, invoice_payload.data, supplier.id, invoice_payload.totale)
    if matches and not force: raise HTTPException(409, {"message":"Possibile duplicato","matches":[x.id for x in matches]})
    invoice = create_invoice(db, invoice_payload); job.status = "completed"; audit(db, "import.completed", f"Importata fattura {invoice.numero}", entity_type="invoice", entity_id=invoice.id); db.commit()
    return {"ok": True, "invoice_id": invoice.id}


@router.get("/search")
def search(q: str, limit: int = Query(20, le=100), db: Session = Depends(get_db)): return {"query": q, "results": search_records(db, q, limit)}


@router.post("/ai/ask")
async def ask(payload: dict, db: Session = Depends(get_db)):
    question = str(payload.get("question", "")).strip()
    if not question: raise HTTPException(422, "Domanda vuota")
    records = search_records(db, question, 20)
    return await answer_with_ollama(question, records)


@router.get("/ollama/status")
async def ollama(): return await ollama_status()


def detect_anomalies(db: Session):
    anomalies = []
    for inv in db.scalars(select(Invoice).options(selectinload(Invoice.rows), selectinload(Invoice.supplier)).order_by(Invoice.data.desc()).limit(200)).all():
        row_total = sum(float(r.totale_riga) for r in inv.rows)
        if inv.rows and abs(row_total - float(inv.imponibile)) > .05:
            anomalies.append({"id": f"total-{inv.id}", "severity": "high", "title": "Totale righe incoerente", "description": f"Fattura {inv.numero}: righe € {row_total:.2f}, imponibile € {float(inv.imponibile):.2f}", "invoice_id": inv.id})
        for r in inv.rows:
            if float(r.confidence) < .6: anomalies.append({"id": f"confidence-{r.id}", "severity": "medium", "title": "Campo da verificare", "description": r.descrizione_originale, "invoice_id": inv.id})
    return anomalies


@router.get("/anomalies")
def anomalies(db: Session = Depends(get_db)): return detect_anomalies(db)


@router.get("/history")
def history(db: Session = Depends(get_db)):
    rows = db.execute(select(func.strftime("%Y", Invoice.data), func.count(Invoice.id), func.sum(Invoice.totale), func.count(func.distinct(Invoice.supplier_id))).group_by(func.strftime("%Y", Invoice.data)).order_by(func.strftime("%Y", Invoice.data).desc())).all()
    return [{"year": y, "invoices": c, "total": float(t or 0), "suppliers": s} for y, c, t, s in rows]


@router.get("/logs")
def logs(limit: int = Query(100, le=500), db: Session = Depends(get_db)): return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    stored = {x.key: x.value for x in db.scalars(select(AppSetting)).all()}
    return {"ollama_url": stored.get("ollama_url", settings.ollama_url), "chat_model": stored.get("chat_model", settings.chat_model), "embedding_model": stored.get("embedding_model", settings.embedding_model), "max_upload_mb": settings.max_upload_mb}


@router.put("/settings")
def put_settings(payload: dict, db: Session = Depends(get_db)):
    allowed = {"ollama_url", "chat_model", "embedding_model", "theme"}
    for key, value in payload.items():
        if key in allowed: db.merge(AppSetting(key=key, value=str(value)))
    audit(db, "settings.updated", "Impostazioni aggiornate"); db.commit(); return {"ok": True}


@router.post("/backups")
def backup(db: Session = Depends(get_db)):
    path = create_backup(); audit(db, "backup.created", f"Backup creato: {path.name}"); db.commit(); return {"filename": path.name, "path": str(path)}


@router.get("/backups/{filename}")
def download_backup(filename: str):
    safe = Path(filename).name; path = settings.data_dir / "backups" / safe
    if not path.exists(): raise HTTPException(404, "Backup non trovato")
    return FileResponse(path, filename=safe)


@router.get("/reports/spending.csv")
def spending_csv(db: Session = Depends(get_db)):
    from fastapi.responses import Response
    rows = db.execute(select(func.strftime("%Y-%m", Invoice.data), func.sum(Invoice.totale)).group_by(func.strftime("%Y-%m", Invoice.data))).all()
    body = "mese;totale\n" + "\n".join(f"{m};{float(v):.2f}" for m, v in rows)
    return Response(body, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=spesa-mensile.csv"})
