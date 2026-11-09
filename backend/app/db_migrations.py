"""Idempotent, local-first SQLite migrations for the desktop app."""
from __future__ import annotations

import logging
import sqlite3
import tempfile
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.engine import Engine

from .config import settings
from .normalization import normalize_row_price

log = logging.getLogger(__name__)


MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("2026-10-20-01", "CREATE INDEX IF NOT EXISTS ix_audit_log_created_at ON audit_log(created_at)"),
    ("2026-10-20-02", "CREATE INDEX IF NOT EXISTS ix_sync_state_status ON sync_state(status)"),
    ("2026-10-29-01", "ALTER TABLE user_profiles ADD COLUMN can_view_reviews BOOLEAN NOT NULL DEFAULT 1"),
    # Passo in Python (nessun SQL): ricalcola unità e prezzo normalizzato di ogni riga con il nuovo normalizzatore.
    ("2026-11-09-01", "RECOMPUTE invoice_rows.prezzo_normalizzato"),
)

_NORMALIZED_PRICE_COLUMNS = {
    "id", "prezzo_unitario", "quantita", "unita_originale", "descrizione_originale",
    "unita_normalizzata", "prezzo_normalizzato",
}


def _recompute_normalized_prices(connection: sqlite3.Connection) -> int:
    """Ricalcola ``prezzo_normalizzato``/``unita_normalizzata`` con le regole attuali. Le descrizioni restano intatte."""
    table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='invoice_rows'").fetchone()
    if not table:
        return 0
    columns = {row[1] for row in connection.execute("PRAGMA table_info(invoice_rows)")}
    if not _NORMALIZED_PRICE_COLUMNS <= columns:
        return 0
    updates: list[tuple[str | None, float | None, int]] = []
    rows = connection.execute(
        "SELECT id, prezzo_unitario, quantita, unita_originale, descrizione_originale FROM invoice_rows"
    ).fetchall()
    for row_id, price, quantity, unit, description in rows:
        try:
            result = normalize_row_price(Decimal(str(price or 0)), Decimal(str(quantity or 0)), unit, description)
        except (InvalidOperation, ValueError):
            log.warning("Riga %s: prezzo normalizzato non ricalcolato (valori non numerici)", row_id)
            continue
        updates.append((result.unit, float(result.price) if result.price is not None else None, row_id))
    connection.executemany(
        "UPDATE invoice_rows SET unita_normalizzata = ?, prezzo_normalizzato = ? WHERE id = ?", updates
    )
    return len(updates)


def _sqlite_path(engine: Engine) -> Path | None:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        return None
    if engine.url.database == ":memory:":
        return None
    return Path(engine.url.database).resolve()


def _backup_database(path: Path) -> Path | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    target_dir = settings.data_dir / "backups" / "migrations"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"pre-migration-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.db"
    with tempfile.NamedTemporaryFile(suffix=".db", dir=target_dir, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        source = sqlite3.connect(path)
        destination = sqlite3.connect(temporary_path)
        try:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("Il backup pre-migrazione non ha superato il controllo integrità")
        finally:
            destination.close()
            source.close()
        temporary_path.replace(target)
        return target
    finally:
        temporary_path.unlink(missing_ok=True)


def run_safe_migrations(engine: Engine) -> dict[str, object]:
    """Apply pending migrations only after a verified SQLite snapshot."""
    path = _sqlite_path(engine)
    if path is None:
        return {"backend": engine.url.get_backend_name(), "applied": [], "backup": None}

    with sqlite3.connect(path) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        } if table else set()
        pending = [(version, sql) for version, sql in MIGRATIONS if version not in applied]

    backup = _backup_database(path) if pending else None
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for version, sql in pending:
            # Base.metadata.create_all runs before these migrations. On a new
            # installation the ORM may therefore have already created a newly
            # introduced column, while existing databases still need ALTER.
            if version == "2026-10-29-01":
                columns = {row[1] for row in connection.execute("PRAGMA table_info(user_profiles)")}
                if columns and "can_view_reviews" not in columns:
                    connection.execute(sql)
            elif version == "2026-11-09-01":
                log.info("Migrazione %s: ricalcolate %s righe", version, _recompute_normalized_prices(connection))
            else:
                connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now().isoformat(timespec="seconds")),
            )
        connection.commit()
    return {"backend": "sqlite", "applied": [version for version, _ in pending], "backup": str(backup) if backup else None}
