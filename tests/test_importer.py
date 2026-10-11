from scorer.db import connect
from scorer.importer import import_folder


def activity_count(conn):
    return conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]


def test_imports_all_gpx_and_takes_runner_id_from_filename(tmp_path, gpx_bytes):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "amy_morning.gpx").write_bytes(gpx_bytes(speed=4.0))
    (folder / "ben_2026_10_04.gpx").write_bytes(gpx_bytes(speed=3.5))
    conn = connect(tmp_path / "s.db")

    summary = import_folder(conn, folder)

    assert summary.imported == ["amy_morning.gpx", "ben_2026_10_04.gpx"]
    assert summary.failures == []
    runners = [r[0] for r in conn.execute("SELECT runner_id FROM activities ORDER BY runner_id")]
    assert runners == ["amy", "ben"]


def test_importing_same_folder_twice_does_not_duplicate(tmp_path, gpx_bytes):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "amy_a.gpx").write_bytes(gpx_bytes())
    conn = connect(tmp_path / "s.db")

    import_folder(conn, folder)
    second = import_folder(conn, folder)

    assert activity_count(conn) == 1
    assert second.imported == []
    assert [d.name for d in second.duplicates] == ["amy_a.gpx"]


def test_renamed_copy_is_detected_by_content_hash(tmp_path, gpx_bytes):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "amy_a.gpx").write_bytes(gpx_bytes())
    conn = connect(tmp_path / "s.db")
    import_folder(conn, folder)

    (folder / "amy_a.gpx").rename(folder / "amy_renamed.gpx")
    summary = import_folder(conn, folder)

    assert activity_count(conn) == 1
    [dup] = summary.duplicates
    assert (dup.name, dup.existing_file) == ("amy_renamed.gpx", "amy_a.gpx")


def test_broken_file_does_not_stop_the_batch(tmp_path, gpx_bytes):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "amy_a.gpx").write_bytes(gpx_bytes())
    (folder / "ben_broken.gpx").write_bytes(b"<gpx><trk><trkseg><trkpt lat=")
    (folder / "nounderscore.gpx").write_bytes(gpx_bytes(speed=3.0))
    (folder / "cat_b.gpx").write_bytes(gpx_bytes(speed=3.3))
    conn = connect(tmp_path / "s.db")

    summary = import_folder(conn, folder)

    assert summary.imported == ["amy_a.gpx", "cat_b.gpx"]
    failed = dict(summary.failures)
    assert set(failed) == {"ben_broken.gpx", "nounderscore.gpx"}
    assert "GPX 格式錯誤" in failed["ben_broken.gpx"]
    assert "檔名" in failed["nounderscore.gpx"]
    assert activity_count(conn) == 2


def test_dropped_point_counts_are_recorded_per_activity(tmp_path, gpx_bytes):
    folder = tmp_path / "in"
    folder.mkdir()
    extra = (
        '<trkpt lat="25.5" lon="121.5"><time>2026-10-04T22:10:00Z</time></trkpt>'  # 飄移
        '<trkpt lat="25.0" lon="121.5"></trkpt>'  # 無時間
    )
    (folder / "amy_a.gpx").write_bytes(gpx_bytes(meters=(0, 100), extra=extra))
    conn = connect(tmp_path / "s.db")
    import_folder(conn, folder)

    row = conn.execute("SELECT dropped_no_time, dropped_speed, kept_points FROM activities").fetchone()
    assert tuple(row) == (1, 1, 9)
    assert conn.execute("SELECT COUNT(*) FROM track_points").fetchone()[0] == 9


def test_activity_month_follows_taipei_local_date(tmp_path, gpx_bytes):
    from datetime import UTC, datetime

    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "amy_a.gpx").write_bytes(gpx_bytes(t0=datetime(2026, 9, 30, 16, 30, tzinfo=UTC)))
    conn = connect(tmp_path / "s.db")
    import_folder(conn, folder)

    assert conn.execute("SELECT local_month FROM activities").fetchone()[0] == "2026-10"


def test_duplicate_under_another_runner_id_is_flagged(tmp_path, gpx_bytes):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "hao_a.gpx").write_bytes(gpx_bytes())
    (folder / "mei_a.gpx").write_bytes(gpx_bytes())  # mei 誤傳了 hao 的檔案
    conn = connect(tmp_path / "s.db")

    [dup] = import_folder(conn, folder).duplicates

    assert dup.name == "mei_a.gpx"
    assert dup.existing_runner == "hao"
    assert dup.runner_mismatch
