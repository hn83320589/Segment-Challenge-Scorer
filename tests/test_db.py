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
