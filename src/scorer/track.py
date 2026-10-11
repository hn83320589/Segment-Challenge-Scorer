"""GPX 解析與軌跡點清理。"""

from dataclasses import dataclass
from datetime import UTC, datetime

import gpxpy
import gpxpy.gpx

from scorer.geo import haversine_m

MAX_SPEED_MPS = 30 / 3.6


class GpxParseError(Exception):
    """GPX 損毀或格式錯誤。"""


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lon: float
    time: datetime | None  # 一律為 UTC aware；None 表示原始點沒有時間戳


@dataclass(frozen=True)
class CleanResult:
    kept: list[TrackPoint]
    dropped_no_time: int
    dropped_speed: int


def parse_gpx(data: bytes) -> list[TrackPoint]:
    """解析 GPX，所有 track/segment 依時間順序合併成一條軌跡。

    segment 之間依各自第一個有時間戳的點排序；segment 內維持原始順序，
    沒有時間戳的點保留下來交給清理步驟計數。
    """
    try:
        gpx = gpxpy.parse(data.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise GpxParseError(f"不是 UTF-8 編碼：{exc}") from exc
    except Exception as exc:  # gpxpy 對各種 XML/格式錯誤會拋出不同類型的例外
        raise GpxParseError(f"GPX 格式錯誤：{exc}") from exc

    segments = [
        [TrackPoint(p.latitude, p.longitude, _to_utc(p.time)) for p in segment.points]
        for track in gpx.tracks
        for segment in track.segments
        if segment.points
    ]
    if not segments:
        raise GpxParseError("檔案內沒有軌跡點")

    segments.sort(key=_first_time)
    return [p for segment in segments for p in segment]


def clean_points(points: list[TrackPoint]) -> CleanResult:
    """剔除沒有時間戳的點，以及與前一個保留點推算速度超過 30 km/h 的點。

    時間沒有前進（dt <= 0）的點無法推算速度，視同飄移剔除。
    """
    kept: list[TrackPoint] = []
    no_time = speed = 0
    for p in points:
        if p.time is None:
            no_time += 1
            continue
        if kept and _too_fast(kept[-1], p):
            speed += 1
            continue
        kept.append(p)
    return CleanResult(kept, no_time, speed)


def _too_fast(prev: TrackPoint, cur: TrackPoint) -> bool:
    dt = (cur.time - prev.time).total_seconds()
    if dt <= 0:
        return True
    return haversine_m(prev.lat, prev.lon, cur.lat, cur.lon) / dt > MAX_SPEED_MPS


def _to_utc(time: datetime | None) -> datetime | None:
    if time is None:
        return None
    if time.tzinfo is None:
        return time.replace(tzinfo=UTC)
    return time.astimezone(UTC)


def _first_time(segment: list[TrackPoint]) -> datetime:
    return next((p.time for p in segment if p.time is not None), datetime.max.replace(tzinfo=UTC))
