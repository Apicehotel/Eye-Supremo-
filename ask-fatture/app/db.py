import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
"""

_EXTRA_COLS = {
    "descrizione_norm": "TEXT",
    "unita_normalizzata": "TEXT",
    "prezzo_normalizzato": "REAL",
    "contenuto_base": "REAL",
}


def connect() -> sqlite3.Connection:
    path = settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(lines)").fetchall()}
    for col, typ in _EXTRA_COLS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE lines ADD COLUMN {col} {typ}")


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
