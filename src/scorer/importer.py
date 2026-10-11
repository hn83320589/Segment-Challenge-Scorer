"""批次匯入資料夾中的 GPX。"""

import hashlib
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from scorer import db
from scorer.geo import local_month
from scorer.track import GpxParseError, clean_points, parse_gpx

FILENAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_.+\.gpx$", re.IGNORECASE)


class ImportFileError(Exception):
    """單一檔案無法匯入；不會中斷整批匯入。"""


@dataclass(frozen=True)
class Duplicate:
    name: str
    runner_id: str
    existing_file: str
    existing_runner: str

    @property
    def runner_mismatch(self) -> bool:
        """內容相同但 runner_id 不同，通常代表有人上傳錯檔。"""
        return self.runner_id != self.existing_runner


@dataclass
class ImportSummary:
    imported: list[str] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)  # (檔名, 錯誤原因)


def import_folder(conn: sqlite3.Connection, folder: Path) -> ImportSummary:
    """匯入資料夾（不含子資料夾）內所有 .gpx。以內容雜湊去重，與檔名無關。"""
    summary = ImportSummary()
    files = sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == ".gpx")
    for path in files:
        try:
            duplicate = _import_file(conn, path)
        except (ImportFileError, GpxParseError, OSError) as exc:
            summary.failures.append((path.name, str(exc)))
            continue
        if duplicate is None:
            summary.imported.append(path.name)
        else:
            summary.duplicates.append(duplicate)
    return summary


def _import_file(conn: sqlite3.Connection, path: Path) -> Duplicate | None:
    """匯入單一檔案；內容已匯入過時不寫入，回傳重複資訊。"""
    match = FILENAME_PATTERN.match(path.name)
    if not match:
        raise ImportFileError("檔名格式錯誤，應為 <runner_id>_<任意>.gpx，runner_id 只能是英數字")

    data = path.read_bytes()
    content_hash = hashlib.sha256(data).hexdigest()
    runner_id = match.group(1)
    existing = db.find_by_hash(conn, content_hash)
    if existing is not None:
        return Duplicate(path.name, runner_id, existing["source_file"], existing["runner_id"])

    cleaned = clean_points(parse_gpx(data))
    if not cleaned.kept:
        raise ImportFileError(
            f"清理後沒有可用的軌跡點（無時間戳 {cleaned.dropped_no_time} 點、飄移 {cleaned.dropped_speed} 點）"
        )

    db.insert_activity(
        conn,
        runner_id=runner_id,
        source_file=path.name,
        content_hash=content_hash,
        local_month=local_month(cleaned.kept[0].time),
        points=cleaned.kept,
        dropped_no_time=cleaned.dropped_no_time,
        dropped_speed=cleaned.dropped_speed,
        imported_at=datetime.now(UTC),
    )
    return None
