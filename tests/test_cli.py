import csv

import pytest

from scorer.cli import main

CONFIG = """
segments:
  - code: RIVER
    name: 河堤直線
    start: {lat: 25.0, lon: 121.5}
    end: {lat: 25.0107918, lon: 121.5}
    reference_length_m: 1200
    month: "2026-10"
"""


@pytest.fixture
def workspace(tmp_path, gpx_bytes):
    folder = tmp_path / "gpx"
    folder.mkdir()
    (folder / "amy_a.gpx").write_bytes(gpx_bytes(speed=4.0))
    (folder / "ben_a.gpx").write_bytes(gpx_bytes(speed=3.0))
    config = tmp_path / "segments.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return tmp_path, folder, ["--db", str(tmp_path / "s.db")], ["--config", str(config)]


def test_import_success_exits_0(workspace, capsys):
    _, folder, db, _ = workspace
    assert main(["import", str(folder), *db]) == 0
    assert "新增活動：2" in capsys.readouterr().out


def test_import_with_broken_file_exits_2_and_lists_it(workspace, capsys):
    _, folder, db, _ = workspace
    (folder / "cat_bad.gpx").write_text("not xml at all")
    assert main(["import", str(folder), *db]) == 2
    out = capsys.readouterr().out
    assert "新增活動：2" in out
    assert "cat_bad.gpx" in out and "GPX 格式錯誤" in out


def test_import_missing_folder_exits_1(tmp_path):
    assert main(["import", str(tmp_path / "nope"), "--db", str(tmp_path / "s.db")]) == 1


def test_unknown_option_exits_1(workspace):
    assert main(["leaderboard", "RIVER", "--bogus"]) == 1


def test_leaderboard_prints_table_and_writes_csv(workspace, capsys):
    tmp_path, folder, db, config = workspace
    main(["import", str(folder), *db])
    out_csv = tmp_path / "board.csv"

    assert main(["leaderboard", "RIVER", *db, *config, "--csv", str(out_csv)]) == 0

    out = capsys.readouterr().out
    assert out.index("amy") < out.index("ben")
    assert "5:00" in out
    with out_csv.open(encoding="utf-8-sig", newline="") as f:
        assert [row[1] for row in list(csv.reader(f))[1:]] == ["amy", "ben"]


def test_leaderboard_unknown_segment_exits_1(workspace, capsys):
    _, _, db, config = workspace
    assert main(["leaderboard", "NOPE", *db, *config]) == 1
    assert "NOPE" in capsys.readouterr().err


def test_bad_config_exits_1_and_names_field(workspace, capsys):
    tmp_path, _, db, _ = workspace
    bad = tmp_path / "bad.yaml"
    bad.write_text(CONFIG.replace("lat: 25.0,", "lat: 125.0,"), encoding="utf-8")
    assert main(["leaderboard", "RIVER", *db, "--config", str(bad)]) == 1
    assert "segments[0].start.lat" in capsys.readouterr().err


def test_report_lists_attempts_with_reasons(workspace, gpx_bytes, capsys):
    tmp_path, folder, db, config = workspace
    # amy 另一個活動：進入起點後在 800 m 停止
    (folder / "amy_short.gpx").write_bytes(gpx_bytes(meters=(-200, 800)))
    main(["import", str(folder), *db])

    assert main(["report", "amy", *db, *config]) == 0
    out = capsys.readouterr().out
    assert "amy_a.gpx" in out and "amy_short.gpx" in out
    assert "5:00" in out
    assert "進入起點後未到終點" in out


def test_report_unknown_runner_exits_1(workspace, capsys):
    _, _, db, config = workspace
    assert main(["report", "nobody", *db, *config]) == 1
