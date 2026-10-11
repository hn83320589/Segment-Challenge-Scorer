"""端對端：範例資料必須能重現 README 中的排行範例。"""

import importlib.util
from pathlib import Path

from scorer.cli import main

SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_sample_data.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_sample_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_data_reproduces_readme_leaderboard(tmp_path, capsys):
    load_generator().main(tmp_path)
    db = ["--db", str(tmp_path / "s.db")]
    config = ["--config", str(tmp_path / "segments.yaml")]

    assert main(["import", str(tmp_path / "gpx"), *db]) == 0
    assert main(["import", str(tmp_path / "broken"), *db]) == 2
    capsys.readouterr()

    assert main(["leaderboard", "RIVER-1K2", *db, *config]) == 0
    lines = capsys.readouterr().out.splitlines()[3:]
    ranking = [(line.split()[1], line.split()[3]) for line in lines]
    # zoe 來自 broken 資料夾中唯一正常的檔案；mei 與 kevin 同為 287 秒，mei 較早完成
    assert ranking == [
        ("hao", "272"),
        ("mei", "287"),
        ("kevin", "287"),
        ("jason", "299"),
        ("zoe", "308"),
        ("yuting", "315"),
        ("lin", "335"),
    ]
