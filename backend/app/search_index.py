import re
from rapidfuzz import fuzz
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session, selectinload
from .models import Invoice, InvoiceRow, Supplier
from .normalization import normalize_text
from .eye_services import row_visible_to_role
from .product_taxonomy import QUESTION_FILLERS, extract_product_query, search_terms

STOPWORDS = set(QUESTION_FILLERS) | {
    "quanto", "quale", "quali", "cosa", "come", "ho", "hai", "abbiamo", "speso", "pagato",
    "nel", "nella", "negli", "da", "di", "il", "la", "le", "i", "un", "una", "fammi",
    "vedere", "mostra", "per",
}


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
    """Ritorna (needle prodotto, anno opzionale) per la ricerca su tutto l'indice."""
    year_match = re.search(r"\b(19|20)\d{2}\b", normalize_text(query))
    year = year_match.group(0) if year_match else None
    needle = extract_product_query(query)
    if year and year in needle.split():
        needle = " ".join(t for t in needle.split() if t != year).strip()
    if not needle:
        # Fallback: strip stopword dalla frase intera.
        normalized = normalize_text(query)
        if year:
            normalized = normalized.replace(year, " ")
        terms = [w for w in normalized.split() if w not in STOPWORDS and len(w) >= 3]
        needle = " ".join(terms).strip()
    return needle, year


def _fts_ids(db: Session, needle: str, limit: int) -> list[int]:
    """Cerca su tutto invoice_rows_fts. Varianti prodotto in OR, non AND della frase."""
    if not needle:
        return []
    variants = [normalize_text(t) for t in search_terms(needle)]
    variants = [v for v in dict.fromkeys(variants + [needle]) if v]
    or_parts: list[str] = []
    for variant in variants:
        tokens = [re.sub(r"[^\w]", "", x) for x in variant.split() if x]
        tokens = [x for x in tokens if x and not (len(x) == 1)]
        if not tokens:
            continue
        # Dentro una variante: AND dei token («carta» AND «igienica»).
        # Tra varianti (bomboloni/bombolone/…): OR.
        and_match = " ".join([f'"{t}"*' for t in tokens])
        or_parts.append(f"({and_match})" if len(tokens) > 1 else and_match)
    if not or_parts:
        return []
    match = " OR ".join(or_parts)
    try:
        rows = db.execute(
            text(
                "SELECT rowid FROM invoice_rows_fts "
                "WHERE invoice_rows_fts MATCH :match "
                "ORDER BY bm25(invoice_rows_fts) LIMIT :limit"
            ),
            {"match": match, "limit": limit},
        ).all()
        return [int(r[0]) for r in rows]
    except Exception:
        return []


def invoice_search(db: Session, query: str, role_name: str = "developer", limit: int = 50) -> list[dict]:
    needle, year = _clean_query(query)
    # L'indice FTS copre tutte le righe (anche 20k+); non è uno scan parziale.
    ids = _fts_ids(db, needle, max(limit * 20, 500))
    stmt = (
        select(InvoiceRow, Invoice, Supplier)
        .select_from(InvoiceRow)
        .join(Invoice, InvoiceRow.invoice_id == Invoice.id)
        .join(Supplier, Invoice.supplier_id == Supplier.id)
        .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product))
    )
    if ids:
        stmt = stmt.where(InvoiceRow.id.in_(ids))
    elif needle:
        fields = (
            InvoiceRow.descrizione_originale,
            InvoiceRow.descrizione_normalizzata,
            Supplier.ragione_sociale,
        )
        clauses = []
        for term in search_terms(needle):
            tokens = normalize_text(term).split()
            if not tokens:
                continue
            clauses.append(and_(*[or_(*[field.ilike(f"%{token}%") for field in fields]) for token in tokens]))
        if clauses:
            stmt = stmt.where(or_(*clauses))
        else:
            pattern = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    InvoiceRow.descrizione_originale.ilike(pattern),
                    InvoiceRow.descrizione_normalizzata.ilike(pattern),
                    Supplier.ragione_sociale.ilike(pattern),
                )
            )
    if year:
        stmt = stmt.where(text("strftime('%Y', invoices.data) = :year")).params(year=year)
    rows = db.execute(stmt.order_by(Invoice.data.desc()).limit(max(limit * 8, 200))).all()
    if needle and not rows:
        # Ultimo fallback: fuzzy solo sulle descrizioni che contengono almeno un token prodotto.
        tokens = [t for t in normalize_text(needle).split() if len(t) >= 4]
        candidate_stmt = (
            select(InvoiceRow, Invoice, Supplier)
            .select_from(InvoiceRow)
            .join(Invoice, InvoiceRow.invoice_id == Invoice.id)
            .join(Supplier, Invoice.supplier_id == Supplier.id)
            .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product))
            .order_by(Invoice.data.desc())
        )
        if tokens:
            candidate_stmt = candidate_stmt.where(
                or_(*[
                    or_(
                        InvoiceRow.descrizione_originale.ilike(f"%{t}%"),
                        InvoiceRow.descrizione_normalizzata.ilike(f"%{t}%"),
                    )
                    for t in tokens
                ])
            ).limit(4000)
        else:
            candidate_stmt = candidate_stmt.limit(2000)
        candidates = db.execute(candidate_stmt).all()
        ranked = [
            (fuzz.WRatio(needle, normalize_text(r.descrizione_originale)), (r, i, s))
            for r, i, s in candidates
        ]
        rows = [x for score, x in sorted(ranked, key=lambda z: z[0], reverse=True) if score >= 55][: limit * 2]
    result = []
    for row, inv, supplier in rows:
        if not row_visible_to_role(db, role_name, row, supplier):
            continue
        result.append({
            "row_id": row.id,
            "invoice_id": inv.id,
            "invoice": inv.numero,
            "date": inv.data.isoformat(),
            "supplier": supplier.ragione_sociale,
            "description": row.descrizione_originale,
            "quantity": float(row.quantita),
            "unit_price": float(row.prezzo_unitario),
            "row_total": float(row.totale_riga),
            "normalized_price": float(row.prezzo_normalizzato) if row.prezzo_normalizzato is not None else None,
            "unit": row.unita_normalizzata,
            "analysis_status": row.policy.analysis_status if row.policy else "product",
        })
        if len(result) >= limit:
            break
    return result
