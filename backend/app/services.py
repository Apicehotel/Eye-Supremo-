import hashlib, json, re, shutil, sqlite3, tempfile, uuid, zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import httpx
from rapidfuzz import fuzz
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload
from .config import settings
from .models import AuditLog, Invoice, InvoiceRow, Product, Supplier
from .normalization import normalize_text, normalized_price_with_content
from .product_taxonomy import search_terms


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
        unit, price = normalized_price_with_content(
            Decimal(r["prezzo_unitario"]),
            Decimal(r["quantita"]),
            r["unita_originale"],
            r["descrizione_originale"],
        )
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
        fields = (InvoiceRow.descrizione_originale, InvoiceRow.descrizione_normalizzata, Supplier.ragione_sociale, Invoice.numero)
        clauses = []
        for term in tuple(dict.fromkeys(search_terms(text) + (text,))):
            clauses.append(and_(*[or_(*[field.ilike(f"%{token}%") for field in fields]) for token in normalize_text(term).split()]))
        stmt = stmt.where(or_(*clauses))
    if "fornitore" in filters: stmt = stmt.where(Supplier.ragione_sociale.ilike(f"%{filters['fornitore']}%"))
    if "anno" in filters: stmt = stmt.where(func.strftime("%Y", Invoice.data) == filters["anno"])
    if "prodotto" in filters: stmt = stmt.where(InvoiceRow.descrizione_normalizzata.ilike(f"%{filters['prodotto']}%"))
    rows = db.execute(stmt.order_by(Invoice.data.desc()).limit(limit * 3)).all()
    if text and not rows:
        candidates = db.execute(select(InvoiceRow, Invoice, Supplier).select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id).join(Supplier, Invoice.supplier_id == Supplier.id).limit(500)).all()
        rows = sorted(candidates, key=lambda x: fuzz.token_set_ratio(text, x[0].descrizione_originale), reverse=True)[:limit]
    return [{"row_id": r.id, "descrizione": r.descrizione_originale, "quantita": float(r.quantita), "prezzo_unitario": float(r.prezzo_unitario), "prezzo_normalizzato": float(r.prezzo_normalizzato) if r.prezzo_normalizzato else None, "unita": r.unita_normalizzata, "totale_riga": float(r.totale_riga), "fattura_id": i.id, "fattura": i.numero, "data": i.data.isoformat(), "fornitore": s.ragione_sociale, "totale_fattura": float(i.totale)} for r, i, s in rows[:limit]]


async def ollama_status(db=None):
    from .model_layers import fetch_installed_models, layer_status_payload, resolve_ai_runtime
    runtime = resolve_ai_runtime(db)
    try:
        models = await fetch_installed_models(runtime.ollama_url)
        layers = layer_status_payload(models, runtime)
        return {"available": True, "models": models, "layers": layers}
    except Exception:
        return {
            "available": False,
            "models": [],
            "message": "IA locale non disponibile",
            "layers": layer_status_payload([], runtime),
        }


async def answer_with_ollama(question: str, records: list[dict], db=None):
    from .model_layers import generate_with_layers, resolve_ai_runtime
    runtime = resolve_ai_runtime(db)
    status = await ollama_status(db)
    if not status["available"]:
        # Somma solo le righe trovate (non il totale intero delle fatture che le contengono).
        row_total = sum(float(r.get("totale_riga") or 0) for r in records)
        year = re.search(r"\b(19|20)\d{2}\b", question)
        detail = f" per il {year.group(0)}" if year else ""
        formatted_total = f"{row_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        invoice_count = len({r["fattura_id"] for r in records})
        answer = (
            f"Ho trovato {len(records)} righe pertinenti{detail}, relative a {invoice_count} fatture, "
            f"per un totale righe di € {formatted_total}."
        )
        return {
            "mode": "deterministic",
            "answer": answer + " Ollama non è disponibile: il risultato è calcolato direttamente dall'archivio.",
            "sources": records,
            "ai_layer": "deterministic",
            "ai_model": None,
            "ai_policy": runtime.policy,
        }
    prompt = "Rispondi in italiano usando esclusivamente i dati JSON forniti. Non inventare valori. Cita fattura, data e fornitore.\nDOMANDA: " + question + "\nDATI:\n" + json.dumps(records, ensure_ascii=False)
    result = await generate_with_layers(
        prompt=prompt,
        runtime=runtime,
        temperature=0.1,
        num_predict=650,
    )
    return {
        "mode": "ollama",
        "answer": result.get("answer", ""),
        "sources": records,
        "ai_layer": result.get("_layer"),
        "ai_model": result.get("_model"),
        "ai_policy": runtime.policy,
    }


def create_backup() -> Path:
    """Snapshot SQLite coerente anche con WAL e scritture concorrenti."""
    data_dir = settings.data_dir.resolve()
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"eyesupremo-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.zip"
    partial = target.with_suffix(".zip.partial")
    source = data_dir / "eye-supremo.db"
    if not source.is_file():
        raise RuntimeError("Database locale non disponibile per il backup")
    try:
        with tempfile.TemporaryDirectory(prefix="eye-backup-") as scratch:
            snapshot = Path(scratch) / source.name
            # Il context manager di sqlite3 gestisce commit/rollback, ma non
            # chiude la connessione. Su Windows il file snapshot resterebbe
            # quindi bloccato e TemporaryDirectory fallirebbe con WinError 32.
            src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            dst = sqlite3.connect(snapshot)
            try:
                src.backup(dst, pages=256)
                result = dst.execute("PRAGMA integrity_check").fetchone()
                if result != ("ok",):
                    raise RuntimeError("La verifica del database di backup non è riuscita")
            finally:
                dst.close()
                src.close()
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, source.name)
                for path in data_dir.rglob("*"):
                    if path.is_symlink() or not path.is_file():
                        continue
                    relative = path.relative_to(data_dir)
                    if relative.parts[0] in {"backups", "updates"} or path.name in {source.name, source.name+'-wal', source.name+'-shm', source.name+'-journal'}:
                        continue
                    archive.write(path, relative)
                archive.writestr("backup-manifest.json", json.dumps({"app": "Eye Supremo", "database": source.name,
                                  "created_at": datetime.now().isoformat(), "integrity_check": "ok"}))
            with zipfile.ZipFile(partial) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("Archivio di backup non valido")
            partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target
