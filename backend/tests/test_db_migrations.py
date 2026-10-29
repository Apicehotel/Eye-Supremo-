import sqlite3

from sqlalchemy import create_engine


def test_safe_migrations_are_idempotent_and_create_a_verified_snapshot(tmp_path, monkeypatch):
    from app import db_migrations
    from app.config import settings

    database = tmp_path / "eye-supremo.db"
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, created_at TEXT)")
        connection.execute("CREATE TABLE sync_state (id INTEGER PRIMARY KEY, status TEXT)")
        connection.execute("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
        connection.commit()
    engine = create_engine(f"sqlite:///{database}")

    first = db_migrations.run_safe_migrations(engine)
    second = db_migrations.run_safe_migrations(engine)

    assert first["applied"] == [version for version, _ in db_migrations.MIGRATIONS]
    assert first["backup"]
    assert second["applied"] == []
    with sqlite3.connect(database) as connection:
        versions = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        assert len(versions) == len(db_migrations.MIGRATIONS)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(user_profiles)")}
        assert "can_view_reviews" in columns
