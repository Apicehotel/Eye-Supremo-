import hashlib, json, re, shutil, zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import httpx
from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from .config import settings
from .models import AuditLog, Invoice, InvoiceRow, InvoiceSnapshot, Product, Supplier
from .normalization import normalize_text, normalized_price


def audit(db: Session, event: str, message: str, severity="info", entity_type=None, entity_id=None):
    db.add(AuditLog(event_type=event, message=message, severity=severity, entity_type=entity_type, entity_id=entity_id))


def duplicate_candidates(db: Session, file_hash=None, numero=None, data=None, supplier_id=None, totale=None):
    query = select(Invoice).options(selectinload(Invoice.supplier))
    clauses = []
    if file_hash: clauses.append(Invoice.hash_file == file_hash)
    if numero and data and supplier_id: clauses.append((Invoice.numero == numero) & (Invoice.data == data) & (Invoice.supplier_id == supplier_id))
    if not clauses: return []
    return list(db.scalars(query.where(or_(*clauses))).all())


def snapshot_payload(inv: Invoice, supplier: Supplier, rows: list[dict]) -> dict:
    return {
        "invoice": {"id": inv.id, "numero": inv.numero, "data": inv.data.isoformat(), "imponibile": str(inv.imponibile), "iva": str(inv.iva), "totale": str(inv.totale), "valuta": inv.valuta, "file_originale": inv.file_originale, "hash_file": inv.hash_file, "stato_importazione": inv.stato_importazione},
        "supplier": {"id": supplier.id, "ragione_sociale": supplier.ragione_sociale, "partita_iva": supplier.partita_iva, "codice_fiscale": supplier.codice_fiscale, "indirizzo": supplier.indirizzo, "email": supplier.email, "telefono": supplier.telefono},
        "rows": rows,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "schema": 1,
    }


def create_invoice(db: Session, payload):
    data = payload.model_dump(exclude={"rows"})
    inv = Invoice(**data, stato_importazione="confermata")
    db.add(inv); db.flush()
    snapshot_rows = []
    for row in payload.rows:
        r = row.model_dump()
        r["descrizione_normalizzata"] = r["descrizione_normalizzata"] or normalize_text(r["descrizione_originale"])
        unit, price = normalized_price(Decimal(r["prezzo_unitario"]), Decimal(r["quantita"]), r["unita_originale"])
        db.add(InvoiceRow(invoice_id=inv.id, unita_normalizzata=unit, prezzo_normalizzato=price, **r))
        snapshot_rows.append({**{k:(str(v) if isinstance(v, Decimal) else v) for k,v in r.items()}, "unita_normalizzata": unit, "prezzo_normalizzato": str(price) if price is not None else None})
    db.add(InvoiceSnapshot(invoice_id=inv.id, reason="created", snapshot_json=json.dumps(snapshot_payload(inv, db.get(Supplier, inv.supplier_id), snapshot_rows), ensure_ascii=False)))
    audit(db, "invoice.created", f"Fattura {inv.numero} registrata", entity_type="invoice", entity_id=inv.id)
    db.commit(); db.refresh(inv); return inv


def ensure_invoice_snapshot(db: Session, inv: Invoice) -> InvoiceSnapshot:
    existing = db.scalar(select(InvoiceSnapshot).where(InvoiceSnapshot.invoice_id == inv.id).order_by(InvoiceSnapshot.created_at.desc()))
    if existing: return existing
    rows = [{"id": r.id, "descrizione_originale": r.descrizione_originale, "descrizione_normalizzata": r.descrizione_normalizzata, "product_id": r.product_id, "quantita": str(r.quantita), "unita_originale": r.unita_originale, "unita_normalizzata": r.unita_normalizzata, "prezzo_unitario": str(r.prezzo_unitario), "prezzo_normalizzato": str(r.prezzo_normalizzato) if r.prezzo_normalizzato is not None else None, "totale_riga": str(r.totale_riga), "aliquota_iva": str(r.aliquota_iva) if r.aliquota_iva is not None else None, "confidence": str(r.confidence)} for r in inv.rows]
    snap = InvoiceSnapshot(invoice_id=inv.id, reason="legacy_capture", snapshot_json=json.dumps(snapshot_payload(inv, inv.supplier, rows), ensure_ascii=False))
    db.add(snap); audit(db, "invoice.snapshot", f"Snapshot storico creato per fattura {inv.numero}", entity_type="invoice", entity_id=inv.id); db.commit(); db.refresh(snap); return snap


def search_records(db: Session, query: str, limit=20):
    terms, filters = [], {}
    for token in query.split():
        if ":" in token:
            key, value = token.split(":", 1); filters[key.lower()] = value
        else: terms.append(token)
    text = " ".join(terms)
    natural_year = re.search(r"\b(19|20)\d{2}\b", text)
    if natural_year and "anno" not in filters:
        filters["anno"] = natural_year.group(0)
        text = text.replace(natural_year.group(0), " ")
    stopwords = {"quanto","quale","quali","cosa","come","ho","hai","abbiamo","speso","pagato","nel","nella","negli","da","di","il","la","le","i","un","una","fammi","vedere","mostra"}
    text = " ".join(word for word in normalize_text(text).split() if word not in stopwords)
    stmt = (select(InvoiceRow, Invoice, Supplier)
            .select_from(InvoiceRow)
            .join(Invoice, InvoiceRow.invoice_id == Invoice.id)
            .join(Supplier, Invoice.supplier_id == Supplier.id))
    if text:
        pattern = f"%{text}%"
        stmt = stmt.where(or_(InvoiceRow.descrizione_originale.ilike(pattern), InvoiceRow.descrizione_normalizzata.ilike(pattern), Supplier.ragione_sociale.ilike(pattern), Invoice.numero.ilike(pattern)))
    if "fornitore" in filters: stmt = stmt.where(Supplier.ragione_sociale.ilike(f"%{filters['fornitore']}%"))
    if "anno" in filters: stmt = stmt.where(func.strftime("%Y", Invoice.data) == filters["anno"])
    if "prodotto" in filters: stmt = stmt.where(InvoiceRow.descrizione_normalizzata.ilike(f"%{filters['prodotto']}%"))
    rows = db.execute(stmt.order_by(Invoice.data.desc()).limit(limit * 3)).all()
    if text and not rows:
        candidates = db.execute(select(InvoiceRow, Invoice, Supplier).select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id).join(Supplier, Invoice.supplier_id == Supplier.id).limit(500)).all()
        rows = sorted(candidates, key=lambda x: fuzz.token_set_ratio(text, x[0].descrizione_originale), reverse=True)[:limit]
    return [{"row_id": r.id, "descrizione": r.descrizione_originale, "quantita": float(r.quantita), "prezzo_unitario": float(r.prezzo_unitario), "prezzo_normalizzato": float(r.prezzo_normalizzato) if r.prezzo_normalizzato else None, "unita": r.unita_normalizzata, "fattura_id": i.id, "fattura": i.numero, "data": i.data.isoformat(), "fornitore": s.ragione_sociale, "totale_fattura": float(i.totale)} for r, i, s in rows[:limit]]


async def ollama_status():
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags"); response.raise_for_status()
            return {"available": True, "models": [m["name"] for m in response.json().get("models", [])]}
    except Exception:
        return {"available": False, "models": [], "message": "IA locale non disponibile"}


async def answer_with_ollama(question: str, records: list[dict]):
    status = await ollama_status()
    if not status["available"]:
        total = sum({r["fattura_id"]: r["totale_fattura"] for r in records}.values())
        year = re.search(r"\b(19|20)\d{2}\b", question)
        detail = f" per il {year.group(0)}" if year else ""
        formatted_total = f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        answer = f"Ho trovato {len(records)} righe pertinenti{detail}, relative a {len(set(r['fattura_id'] for r in records))} fatture, per un totale documenti di € {formatted_total}."
        return {"mode": "deterministic", "answer": answer + " Ollama non è disponibile: il risultato è calcolato direttamente dall'archivio.", "sources": records}
    prompt = "Rispondi in italiano usando esclusivamente i dati JSON forniti. Non inventare valori. Cita fattura, data e fornitore.\nDOMANDA: " + question + "\nDATI:\n" + json.dumps(records, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{settings.ollama_url}/api/generate", json={"model": settings.chat_model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}})
        res.raise_for_status()
        return {"mode": "ollama", "answer": res.json().get("response", ""), "sources": records}


def create_backup() -> Path:
    target = settings.data_dir / "backups" / f"randfatture-{datetime.now():%Y%m%d-%H%M%S}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in settings.data_dir.rglob("*"):
            if path.is_file() and path != target and "backups" not in path.parts:
                archive.write(path, path.relative_to(settings.data_dir))
    return target


def validate_backup(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "randfatture.db" not in names: raise ValueError("Backup non valido: database mancante")
        for name in names:
            resolved = (settings.data_dir / name).resolve()
            if settings.data_dir.resolve() not in resolved.parents and resolved != settings.data_dir.resolve(): raise ValueError("Backup non valido: percorso non sicuro")
        return {"files": len(names), "has_database": True, "names": names[:100]}


def restore_backup(path: Path) -> dict:
    info = validate_backup(path)
    safety = create_backup()
    staging = settings.data_dir / f"restore-{datetime.now():%Y%m%d-%H%M%S}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(path) as archive: archive.extractall(staging)
        restored_db = staging / "randfatture.db"
        if not restored_db.exists() or restored_db.stat().st_size == 0: raise ValueError("Backup non valido: database vuoto")
        for item in staging.iterdir():
            target = settings.data_dir / item.name
            if item.name == "backups": continue
            if target.exists():
                if target.is_dir(): shutil.rmtree(target)
                else: target.unlink()
            shutil.move(str(item), str(target))
        return {"ok": True, "safety_backup": safety.name, "files": info["files"], "restart_required": True}
    finally:
        if staging.exists(): shutil.rmtree(staging, ignore_errors=True)
