"""排行榜與跑者報告。"""

import csv
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scorer import db
from scorer.config import Segment
from scorer.db import Activity
from scorer.geo import LOCAL_TZ
from scorer.matching import Attempt, match_segment

CSV_HEADER = ["名次", "跑者", "成績", "秒數", "完成時間（台北）", "活動檔案"]


@dataclass(frozen=True)
class LeaderboardRow:
    rank: int
    runner_id: str
    seconds: int
    finished_at: datetime
    source_file: str


@dataclass(frozen=True)
class ActivityReport:
    activity: Activity
    attempts: list[tuple[Segment, Attempt]]


def build_leaderboard(results: Iterable[tuple[Activity, Attempt]], segment: Segment) -> list[LeaderboardRow]:
    """每位跑者只取最佳成績；同秒時完成時間較早者在前。

    只採計有效、且活動歸屬月份等於區段挑戰月份的嘗試。
    """
    best: dict[str, tuple[Activity, Attempt]] = {}
    for activity, attempt in results:
        if not attempt.valid or attempt.segment_code != segment.code or activity.local_month != segment.month:
            continue
        current = best.get(activity.runner_id)
        if current is None or _sort_key(attempt) < _sort_key(current[1]):
            best[activity.runner_id] = (activity, attempt)

    ordered = sorted(best.values(), key=lambda item: (*_sort_key(item[1]), item[0].runner_id))
    return [
        LeaderboardRow(rank, activity.runner_id, attempt.seconds, attempt.end_time, activity.source_file)
        for rank, (activity, attempt) in enumerate(ordered, start=1)
    ]


def _sort_key(attempt: Attempt) -> tuple[int, datetime]:
    return attempt.seconds, attempt.end_time


def segment_leaderboard(conn: sqlite3.Connection, segment: Segment) -> list[LeaderboardRow]:
    activities = db.list_activities(conn, local_month=segment.month)
    results = [
        (activity, attempt)
        for activity in activities
        for attempt in match_segment(db.load_points(conn, activity.id), segment)
    ]
    return build_leaderboard(results, segment)


def runner_report(conn: sqlite3.Connection, runner_id: str, segments: list[Segment]) -> list[ActivityReport]:
    reports = []
    for activity in db.list_activities(conn, runner_id=runner_id):
        points = db.load_points(conn, activity.id)
        attempts = [(segment, attempt) for segment in segments for attempt in match_segment(points, segment)]
        reports.append(ActivityReport(activity, attempts))
    return reports


def format_duration(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_local(time: datetime) -> str:
    return time.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def leaderboard_table_rows(rows: list[LeaderboardRow]) -> list[list]:
    return [
        [r.rank, r.runner_id, format_duration(r.seconds), r.seconds, format_local(r.finished_at), r.source_file]
        for r in rows
    ]


def write_leaderboard_csv(rows: list[LeaderboardRow], path: Path) -> None:
    # utf-8-sig 會寫入 BOM，Excel 才會以 UTF-8 開啟而不是用系統編碼（Big5）造成中文亂碼
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(leaderboard_table_rows(rows))
