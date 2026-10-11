import pytest


from scorer.db import SCHEMA_VERSION, connect


def test_connect_creates_schema_and_sets_version(tmp_path):
    conn = connect(tmp_path / "s.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"activities", "track_points"} <= tables


def test_connect_twice_is_idempotent(tmp_path):
    connect(tmp_path / "s.db").close()
    conn = connect(tmp_path / "s.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_failed_migration_leaves_no_partial_changes(tmp_path, monkeypatch):
    from scorer import db

    connect(tmp_path / "s.db").close()
    broken = "CREATE TABLE half_done (a INTEGER); THIS IS NOT SQL;"
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, broken])

    with pytest.raises(RuntimeError, match="migration 2"):
        connect(tmp_path / "s.db")

    import sqlite3

    raw = sqlite3.connect(tmp_path / "s.db")
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 1
    assert raw.execute("SELECT name FROM sqlite_master WHERE name = 'half_done'").fetchone() is None
