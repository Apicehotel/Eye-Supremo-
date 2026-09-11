import re
from rapidfuzz import fuzz
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload
from .models import Invoice, InvoiceRow, Supplier
from .normalization import normalize_text
from .eye_services import row_visible_to_role

STOPWORDS = {"quanto","quale","quali","cosa","come","ho","hai","abbiamo","speso","pagato","nel","nella","negli","da","di","il","la","le","i","un","una","fammi","vedere","mostra","per"}


def ensure_fts5(engine) -> bool:
    ddl = [
        "CREATE VIRTUAL TABLE IF NOT EXISTS invoice_rows_fts USING fts5(descrizione_originale, descrizione_normalizzata, content='invoice_rows', content_rowid='id', tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')",
        "CREATE TRIGGER IF NOT EXISTS invoice_rows_ai AFTER INSERT ON invoice_rows BEGIN INSERT INTO invoice_rows_fts(rowid,descrizione_originale,descrizione_normalizzata) VALUES(new.id,new.descrizione_originale,new.descrizione_normalizzata); END",
        "CREATE TRIGGER IF NOT EXISTS invoice_rows_ad AFTER DELETE ON invoice_rows BEGIN INSERT INTO invoice_rows_fts(invoice_rows_fts,rowid,descrizione_originale,descrizione_normalizzata) VALUES('delete',old.id,old.descrizione_originale,old.descrizione_normalizzata); END",
        "CREATE TRIGGER IF NOT EXISTS invoice_rows_au AFTER UPDATE ON invoice_rows BEGIN INSERT INTO invoice_rows_fts(invoice_rows_fts,rowid,descrizione_originale,descrizione_normalizzata) VALUES('delete',old.id,old.descrizione_originale,old.descrizione_normalizzata); INSERT INTO invoice_rows_fts(rowid,descrizione_originale,descrizione_normalizzata) VALUES(new.id,new.descrizione_originale,new.descrizione_normalizzata); END",
        "CREATE VIRTUAL TABLE IF NOT EXISTS reviews_fts USING fts5(text, content='reviews', content_rowid='id', tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')",
        "CREATE TRIGGER IF NOT EXISTS reviews_ai AFTER INSERT ON reviews BEGIN INSERT INTO reviews_fts(rowid,text) VALUES(new.id,new.text); END",
        "CREATE TRIGGER IF NOT EXISTS reviews_ad AFTER DELETE ON reviews BEGIN INSERT INTO reviews_fts(reviews_fts,rowid,text) VALUES('delete',old.id,old.text); END",
        "CREATE TRIGGER IF NOT EXISTS reviews_au AFTER UPDATE ON reviews BEGIN INSERT INTO reviews_fts(reviews_fts,rowid,text) VALUES('delete',old.id,old.text); INSERT INTO reviews_fts(rowid,text) VALUES(new.id,new.text); END",
    ]
    try:
        with engine.begin() as conn:
            for sql in ddl:
                conn.exec_driver_sql(sql)
            conn.exec_driver_sql("INSERT INTO invoice_rows_fts(invoice_rows_fts) VALUES('rebuild')")
            conn.exec_driver_sql("INSERT INTO reviews_fts(reviews_fts) VALUES('rebuild')")
        return True
    except Exception:
        return False


def _clean_query(query: str) -> tuple[str, str | None]:
    normalized = normalize_text(query)
    year_match = re.search(r"\b(19|20)\d{2}\b", normalized)
    year = year_match.group(0) if year_match else None
    if year:
        normalized = normalized.replace(year, " ")
    terms = [w for w in normalized.split() if w not in STOPWORDS]
    return " ".join(terms).strip(), year


def _fts_ids(db: Session, needle: str, limit: int) -> list[int]:
    if not needle:
        return []
    tokens = [re.sub(r"[^\w]", "", x) for x in needle.split() if x]
    tokens = [x for x in tokens if x]
    if not tokens:
        return []
    if len(tokens) == 1 and len(tokens[0]) == 1:
        return []
    match = " ".join([f'"{t}"*' for t in tokens])
    try:
        rows = db.execute(text("SELECT rowid FROM invoice_rows_fts WHERE invoice_rows_fts MATCH :match ORDER BY bm25(invoice_rows_fts) LIMIT :limit"), {"match": match, "limit": limit}).all()
        return [int(r[0]) for r in rows]
    except Exception:
        return []


def invoice_search(db: Session, query: str, role_name: str = "developer", limit: int = 50) -> list[dict]:
    needle, year = _clean_query(query)
    ids = _fts_ids(db, needle, max(limit * 4, 100))
    stmt = (select(InvoiceRow, Invoice, Supplier)
            .select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id).join(Supplier, Invoice.supplier_id == Supplier.id)
            .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product)))
    if ids:
        stmt = stmt.where(InvoiceRow.id.in_(ids))
    elif needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(or_(InvoiceRow.descrizione_originale.ilike(pattern), InvoiceRow.descrizione_normalizzata.ilike(pattern), Supplier.ragione_sociale.ilike(pattern)))
    if year:
        stmt = stmt.where(text("strftime('%Y', invoices.data) = :year")).params(year=year)
    rows = db.execute(stmt.order_by(Invoice.data.desc()).limit(max(limit * 4, 100))).all()
    if needle and not rows:
        candidates = db.execute((select(InvoiceRow, Invoice, Supplier)
            .select_from(InvoiceRow).join(Invoice, InvoiceRow.invoice_id == Invoice.id).join(Supplier, Invoice.supplier_id == Supplier.id)
            .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product)).order_by(Invoice.data.desc()).limit(1200))).all()
        ranked = [(fuzz.WRatio(needle, normalize_text(r.descrizione_originale)), (r, i, s)) for r, i, s in candidates]
        rows = [x for score, x in sorted(ranked, key=lambda z: z[0], reverse=True) if score >= 55][:limit * 2]
    result = []
    for row, inv, supplier in rows:
        if not row_visible_to_role(db, role_name, row, supplier):
            continue
        result.append({"row_id": row.id, "invoice_id": inv.id, "invoice": inv.numero, "date": inv.data.isoformat(), "supplier": supplier.ragione_sociale,
                       "description": row.descrizione_originale, "quantity": float(row.quantita), "unit_price": float(row.prezzo_unitario),
                       "row_total": float(row.totale_riga), "normalized_price": float(row.prezzo_normalizzato) if row.prezzo_normalizzato is not None else None,
                       "unit": row.unita_normalizzata, "analysis_status": row.policy.analysis_status if row.policy else "product"})
        if len(result) >= limit:
            break
    return result
