"""SQLite 連線、schema migration 與資料存取。"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scorer.track import TrackPoint

# 每個元素是一次 migration；index + 1 即為套用後的 schema 版本（存在 PRAGMA user_version）。
# 之後要改 schema 只能在尾端新增，不可修改已發佈的 migration。
MIGRATIONS = [
    """
    CREATE TABLE activities (
        id              INTEGER PRIMARY KEY,
        runner_id       TEXT NOT NULL,
        source_file     TEXT NOT NULL,
        content_hash    TEXT NOT NULL UNIQUE,
        started_at      TEXT NOT NULL,   -- ISO 8601 UTC
        local_month     TEXT NOT NULL,   -- Asia/Taipei 當地日期所屬月份 YYYY-MM
        kept_points     INTEGER NOT NULL,
        dropped_no_time INTEGER NOT NULL,
        dropped_speed   INTEGER NOT NULL,
        imported_at     TEXT NOT NULL
    );
    CREATE INDEX idx_activities_runner ON activities (runner_id);
    CREATE INDEX idx_activities_month ON activities (local_month);
    CREATE TABLE track_points (
        activity_id INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
        seq         INTEGER NOT NULL,
        lat         REAL NOT NULL,
        lon         REAL NOT NULL,
        time        TEXT NOT NULL,       -- ISO 8601 UTC
        PRIMARY KEY (activity_id, seq)
    );
    """,
]
SCHEMA_VERSION = len(MIGRATIONS)


@dataclass(frozen=True)
class Activity:
    id: int
    runner_id: str
    source_file: str
    started_at: datetime
    local_month: str
    kept_points: int
    dropped_no_time: int
    dropped_speed: int


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(f"資料庫 schema 版本 {current} 比程式支援的 {SCHEMA_VERSION} 新，請更新程式")
    for version in range(current, SCHEMA_VERSION):
        with conn:
            conn.executescript(MIGRATIONS[version])
            conn.execute(f"PRAGMA user_version = {version + 1}")


def hash_exists(conn: sqlite3.Connection, content_hash: str) -> bool:
    return conn.execute("SELECT 1 FROM activities WHERE content_hash = ?", (content_hash,)).fetchone() is not None


def insert_activity(
    conn: sqlite3.Connection,
    *,
    runner_id: str,
    source_file: str,
    content_hash: str,
    local_month: str,
    points: list[TrackPoint],
    dropped_no_time: int,
    dropped_speed: int,
    imported_at: datetime,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO activities (runner_id, source_file, content_hash, started_at, local_month,
                   kept_points, dropped_no_time, dropped_speed, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                runner_id,
                source_file,
                content_hash,
                points[0].time.isoformat(),
                local_month,
                len(points),
                dropped_no_time,
                dropped_speed,
                imported_at.isoformat(),
            ),
        )
        activity_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO track_points (activity_id, seq, lat, lon, time) VALUES (?, ?, ?, ?, ?)",
            [(activity_id, i, p.lat, p.lon, p.time.isoformat()) for i, p in enumerate(points)],
        )
    return activity_id


def list_activities(
    conn: sqlite3.Connection, *, runner_id: str | None = None, local_month: str | None = None
) -> list[Activity]:
    sql = "SELECT * FROM activities WHERE 1 = 1"
    params: list[str] = []
    if runner_id is not None:
        sql += " AND runner_id = ?"
        params.append(runner_id)
    if local_month is not None:
        sql += " AND local_month = ?"
        params.append(local_month)
    sql += " ORDER BY started_at, id"
    return [
        Activity(
            id=r["id"],
            runner_id=r["runner_id"],
            source_file=r["source_file"],
            started_at=datetime.fromisoformat(r["started_at"]),
            local_month=r["local_month"],
            kept_points=r["kept_points"],
            dropped_no_time=r["dropped_no_time"],
            dropped_speed=r["dropped_speed"],
        )
        for r in conn.execute(sql, params)
    ]


def load_points(conn: sqlite3.Connection, activity_id: int) -> list[TrackPoint]:
    rows = conn.execute("SELECT lat, lon, time FROM track_points WHERE activity_id = ? ORDER BY seq", (activity_id,))
    return [TrackPoint(r["lat"], r["lon"], datetime.fromisoformat(r["time"])) for r in rows]
