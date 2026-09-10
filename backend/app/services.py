import hashlib, json, re, shutil, zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import httpx
from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from .config import settings
from .models import AuditLog, Invoice, InvoiceRow, Product, Supplier
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


def create_invoice(db: Session, payload):
    data = payload.model_dump(exclude={"rows"})
    inv = Invoice(**data, stato_importazione="confermata")
    db.add(inv); db.flush()
    for row in payload.rows:
        r = row.model_dump()
        r["descrizione_normalizzata"] = r["descrizione_normalizzata"] or normalize_text(r["descrizione_originale"])
        unit, price = normalized_price(Decimal(r["prezzo_unitario"]), Decimal(r["quantita"]), r["unita_originale"])
        db.add(InvoiceRow(invoice_id=inv.id, unita_normalizzata=unit, prezzo_normalizzato=price, **r))
    audit(db, "invoice.created", f"Fattura {inv.numero} registrata", entity_type="invoice", entity_id=inv.id)
    db.commit(); db.refresh(inv); return inv


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
