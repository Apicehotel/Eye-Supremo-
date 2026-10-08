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
        normalized = normalize_text(query)
        if year:
            normalized = normalized.replace(year, " ")
        terms = [w for w in normalized.split() if w not in STOPWORDS and len(w) >= 3]
        needle = " ".join(terms).strip()
    return needle, year


def _fts_match_expr(needle: str) -> str | None:
    """Espressione FTS: varianti prodotto in OR. Nessun LIMIT implicito."""
    if not needle:
        return None
    variants = [normalize_text(t) for t in search_terms(needle)]
    variants = [v for v in dict.fromkeys(variants + [needle]) if v]
    or_parts: list[str] = []
    for variant in variants:
        tokens = [re.sub(r"[^\w]", "", x) for x in variant.split() if x]
        tokens = [x for x in tokens if x and len(x) > 1]
        if not tokens:
            continue
        and_match = " ".join([f'"{t}"*' for t in tokens])
        or_parts.append(f"({and_match})" if len(tokens) > 1 else and_match)
    if not or_parts:
        return None
    return " OR ".join(or_parts)


def _base_stmt():
    return (
        select(InvoiceRow, Invoice, Supplier)
        .select_from(InvoiceRow)
        .join(Invoice, InvoiceRow.invoice_id == Invoice.id)
        .join(Supplier, Invoice.supplier_id == Supplier.id)
        .options(selectinload(InvoiceRow.policy), selectinload(InvoiceRow.product))
    )


def _serialize_row(row: InvoiceRow, inv: Invoice, supplier: Supplier) -> dict:
    return {
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
    }


def _collect_all_matches(
    db: Session,
    query: str,
    role_name: str = "developer",
) -> list[dict]:
    """Restituisce TUTTE le righe pertinenti nell'archivio. Nessun tetto artificiale."""
    needle, year = _clean_query(query)
    stmt = _base_stmt()
    match = _fts_match_expr(needle)
    used_fts = False
    if match:
        try:
            # Subquery FTS senza LIMIT: interroga l'intero indice.
            stmt = stmt.where(
                text(
                    "invoice_rows.id IN ("
                    "SELECT rowid FROM invoice_rows_fts "
                    "WHERE invoice_rows_fts MATCH :fts_match"
                    ")"
                )
            ).params(fts_match=match)
            used_fts = True
        except Exception:
            used_fts = False
    if needle and not used_fts:
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

    # Nessun .limit(): tutte le fatture/righe che matchano.
    rows = db.execute(stmt.order_by(Invoice.data.desc(), InvoiceRow.id.desc())).all()

    if needle and not rows:
        # Fallback fuzzy su TUTTE le righe che contengono almeno un token prodotto.
        tokens = [t for t in normalize_text(needle).split() if len(t) >= 3]
        candidate_stmt = _base_stmt().order_by(Invoice.data.desc(), InvoiceRow.id.desc())
        if tokens:
            candidate_stmt = candidate_stmt.where(
                or_(*[
                    or_(
                        InvoiceRow.descrizione_originale.ilike(f"%{t}%"),
                        InvoiceRow.descrizione_normalizzata.ilike(f"%{t}%"),
                    )
                    for t in tokens
                ])
            )
        if year:
            candidate_stmt = candidate_stmt.where(text("strftime('%Y', invoices.data) = :year")).params(year=year)
        candidates = db.execute(candidate_stmt).all()
        ranked = [
            (fuzz.WRatio(needle, normalize_text(r.descrizione_originale)), (r, i, s))
            for r, i, s in candidates
        ]
        rows = [x for score, x in sorted(ranked, key=lambda z: z[0], reverse=True) if score >= 55]

    result: list[dict] = []
    for row, inv, supplier in rows:
        if not row_visible_to_role(db, role_name, row, supplier):
            continue
        result.append(_serialize_row(row, inv, supplier))
    return result


def invoice_search(
    db: Session,
    query: str,
    role_name: str = "developer",
    limit: int | None = None,
) -> list[dict]:
    """Ricerca estesa a tutto l'archivio. `limit` è solo un taglio opzionale in coda."""
    records = _collect_all_matches(db, query, role_name=role_name)
    if limit is None or limit <= 0:
        return records
    return records[:limit]


def invoice_search_page(
    db: Session,
    query: str,
    role_name: str = "developer",
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Cerca su tutto l'archivio; paginazione solo per la risposta UI."""
    from .eye_services import invoice_search_summary

    records = _collect_all_matches(db, query, role_name=role_name)
    offset = max(0, int(offset or 0))
    limit = max(1, int(limit or 50))
    page = records[offset: offset + limit]
    return {
        "query": query,
        "summary": invoice_search_summary(records),
        "results": page,
        "count": len(page),
        "total": len(records),
        "offset": offset,
        "limit": limit,
        "engine": "fts5+rapidfuzz",
        "scope": "full-archive-unlimited",
    }
