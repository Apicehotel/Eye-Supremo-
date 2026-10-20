"""Idempotent, local-first SQLite migrations for the desktop app."""
from __future__ import annotations

import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from .config import settings


MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("2026-10-20-01", "CREATE INDEX IF NOT EXISTS ix_audit_log_created_at ON audit_log(created_at)"),
    ("2026-10-20-02", "CREATE INDEX IF NOT EXISTS ix_sync_state_status ON sync_state(status)"),
)


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
            connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now().isoformat(timespec="seconds")),
            )
        connection.commit()
    return {"backend": "sqlite", "applied": [version for version, _ in pending], "backup": str(backup) if backup else None}
