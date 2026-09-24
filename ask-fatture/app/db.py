import json
import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ragione_sociale TEXT NOT NULL,
  nome_commerciale TEXT,
  partita_iva TEXT,
  codice_fiscale TEXT,
  indirizzo TEXT,
  cap TEXT,
  citta TEXT,
  provincia TEXT,
  nazione TEXT DEFAULT 'IT',
  email TEXT,
  telefono TEXT,
  pec TEXT,
  sconti_json TEXT DEFAULT '[]',
  note TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_piva ON suppliers(partita_iva) WHERE partita_iva IS NOT NULL AND partita_iva != '';
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(ragione_sociale);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  nome_norm TEXT NOT NULL UNIQUE,
  unita_base TEXT,
  pack_contenuto REAL,
  pack_unita TEXT,
  pack_note TEXT,
  pack_updated_by TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_products_nome ON products(nome);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER REFERENCES suppliers(id),
  numero TEXT,
  data TEXT,
  fornitore TEXT,
  totale REAL,
  file_name TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  product_id INTEGER REFERENCES products(id),
  descrizione TEXT NOT NULL,
  descrizione_norm TEXT,
  quantita REAL,
  unita TEXT,
  unita_normalizzata TEXT,
  prezzo_unitario REAL,
  prezzo_normalizzato REAL,
  contenuto_base REAL,
  totale_riga REAL
);
CREATE INDEX IF NOT EXISTS idx_lines_desc ON lines(descrizione);
CREATE INDEX IF NOT EXISTS idx_lines_desc_norm ON lines(descrizione_norm);
CREATE INDEX IF NOT EXISTS idx_lines_product ON lines(product_id);
CREATE INDEX IF NOT EXISTS idx_invoices_supplier ON invoices(supplier_id);
"""

_LINE_EXTRA = {
    "descrizione_norm": "TEXT",
    "unita_normalizzata": "TEXT",
    "prezzo_normalizzato": "REAL",
    "contenuto_base": "REAL",
    "product_id": "INTEGER",
}
_INV_EXTRA = {"supplier_id": "INTEGER"}
_PRODUCT_EXTRA = {
    "pack_contenuto": "REAL",
    "pack_unita": "TEXT",
    "pack_note": "TEXT",
    "pack_updated_by": "TEXT",
}


def connect() -> sqlite3.Connection:
    path = settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "lines" in tables:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(lines)").fetchall()}
        for col, typ in _LINE_EXTRA.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE lines ADD COLUMN {col} {typ}")
    if "invoices" in tables:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(invoices)").fetchall()}
        for col, typ in _INV_EXTRA.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {col} {typ}")
    if "products" in tables:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
        for col, typ in _PRODUCT_EXTRA.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col} {typ}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def parse_sconti(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def dump_sconti(items: list | None) -> str:
    clean = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("nome") or "").strip()
        if not label:
            continue
        entry = {"label": label}
        if item.get("percentuale") is not None:
            try:
                entry["percentuale"] = float(item["percentuale"])
            except (TypeError, ValueError):
                pass
        if item.get("note"):
            entry["note"] = str(item["note"])[:500]
        if item.get("prodotto"):
            entry["prodotto"] = str(item["prodotto"])[:200]
        clean.append(entry)
    return json.dumps(clean, ensure_ascii=False)
