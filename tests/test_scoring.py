import csv
from datetime import UTC, datetime, timedelta

from scorer.config import Point, Segment
from scorer.db import Activity
from scorer.matching import Attempt
from scorer.scoring import build_leaderboard, format_duration, write_leaderboard_csv

SEGMENT = Segment("RIVER", "河堤直線", Point(25.0, 121.5), Point(25.01, 121.5), 25.0, 1200.0, "2026-10")
T0 = datetime(2026, 10, 4, 22, 0, tzinfo=UTC)


def activity(id, runner, month="2026-10"):
    return Activity(id, runner, f"{runner}_{id}.gpx", T0, month, 100, 0, 0)


def attempt(seconds, finished_minute, *, valid=True):
    end = T0 + timedelta(minutes=finished_minute)
    return Attempt("RIVER", end - timedelta(seconds=seconds), end, seconds, 1200.0, valid, None if valid else "x")


def test_each_runner_appears_once_with_best_time():
    results = [
        (activity(1, "amy"), attempt(310, 10)),
        (activity(1, "amy"), attempt(298, 40)),
        (activity(2, "amy"), attempt(305, 70)),
        (activity(3, "ben"), attempt(300, 10)),
    ]
    rows = build_leaderboard(results, SEGMENT)
    assert [(r.rank, r.runner_id, r.seconds) for r in rows] == [(1, "amy", 298), (2, "ben", 300)]


def test_same_seconds_ranks_earlier_finish_first():
    results = [
        (activity(1, "late"), attempt(300.2, 50)),
        (activity(2, "early"), attempt(299.6, 20)),
    ]
    rows = build_leaderboard(results, SEGMENT)
    assert [r.runner_id for r in rows] == ["early", "late"]
    assert rows[0].seconds == rows[1].seconds == 300


def test_runner_best_tie_prefers_earlier_attempt():
    results = [(activity(1, "amy"), attempt(300, 50)), (activity(1, "amy"), attempt(300, 20))]
    [row] = build_leaderboard(results, SEGMENT)
    assert row.finished_at == T0 + timedelta(minutes=20)


def test_invalid_attempts_and_other_months_are_excluded():
    results = [
        (activity(1, "amy"), attempt(200, 10, valid=False)),
        (activity(2, "ben", month="2026-09"), attempt(250, 10)),
        (activity(3, "cat"), attempt(320, 10)),
    ]
    assert [r.runner_id for r in build_leaderboard(results, SEGMENT)] == ["cat"]


def test_format_duration():
    assert format_duration(298) == "4:58"
    assert format_duration(3725) == "1:02:05"


def test_csv_is_utf8_with_bom_so_excel_shows_chinese(tmp_path):
    rows = build_leaderboard([(activity(1, "amy"), attempt(298, 10))], SEGMENT)
    path = tmp_path / "out.csv"
    write_leaderboard_csv(rows, path)

    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as f:
        header, first = list(csv.reader(f))
    assert header[:3] == ["名次", "跑者", "成績"]
    assert first[:4] == ["1", "amy", "4:58", "298"]
