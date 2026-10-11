"""區段比對：從清理後的軌跡找出每一次嘗試。"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from scorer.config import Point, Segment
from scorer.geo import haversine_m, to_local_offset_m
from scorer.track import TrackPoint

DISTANCE_TOLERANCE = 0.10
REASON_NOT_FINISHED = "進入起點後未到終點"


@dataclass(frozen=True)
class Attempt:
    segment_code: str
    start_time: datetime
    end_time: datetime | None
    elapsed_s: float | None
    distance_m: float | None
    valid: bool
    reason: str | None = None

    @property
    def seconds(self) -> int | None:
        """官方成績：四捨五入到整數秒。"""
        return None if self.elapsed_s is None else math.floor(self.elapsed_s + 0.5)


def match_segment(points: list[TrackPoint], segment: Segment) -> list[Attempt]:
    """找出所有「先進入起點圈、再進入終點圈」的嘗試。

    - 「進入」是指從圈外移動到圈內（第一個點就在圈內也算進入）。
    - 進入時間以相鄰兩點線性內插到判定圈邊界，降低取樣間隔造成的誤差。
    - 嘗試進行中又重新進入起點圈時，以最後一次進入為準重新計時。
    - 軌跡結束時仍未進入終點圈，記為無效嘗試。
    """
    attempts: list[Attempt] = []
    start_cross: TrackPoint | None = None
    path: list[TrackPoint] = []
    was_in_start = was_in_end = False

    for i, p in enumerate(points):
        prev = points[i - 1] if i > 0 else None
        in_start = _inside(p, segment.start, segment.radius_m)
        in_end = _inside(p, segment.end, segment.radius_m)

        if start_cross is not None:
            if in_end and not was_in_end:
                end_cross = _boundary_crossing(prev, p, segment.end, segment.radius_m)
                attempts.append(_finish(segment, start_cross, end_cross, path + [end_cross]))
                start_cross = None
            else:
                path.append(p)

        if in_start and not was_in_start:
            start_cross = _boundary_crossing(prev, p, segment.start, segment.radius_m)
            path = [start_cross, p]

        was_in_start, was_in_end = in_start, in_end

    if start_cross is not None:
        attempts.append(
            Attempt(segment.code, start_cross.time, None, None, None, valid=False, reason=REASON_NOT_FINISHED)
        )
    return attempts


def _finish(segment: Segment, start: TrackPoint, end: TrackPoint, path: list[TrackPoint]) -> Attempt:
    elapsed = (end.time - start.time).total_seconds()
    distance = sum(haversine_m(a.lat, a.lon, b.lat, b.lon) for a, b in zip(path, path[1:]))
    low = segment.reference_length_m * (1 - DISTANCE_TOLERANCE)
    high = segment.reference_length_m * (1 + DISTANCE_TOLERANCE)
    reason = None
    if not low <= distance <= high:
        reason = (
            f"距離不符：實際 {distance:.0f} m，參考 {segment.reference_length_m:.0f} m"
            f"（容許 {low:.0f}–{high:.0f} m）"
        )
    return Attempt(segment.code, start.time, end.time, elapsed, distance, valid=reason is None, reason=reason)


def _inside(p: TrackPoint, center: Point, radius_m: float) -> bool:
    return haversine_m(p.lat, p.lon, center.lat, center.lon) <= radius_m


def _boundary_crossing(outside: TrackPoint | None, inside: TrackPoint, center: Point, radius_m: float) -> TrackPoint:
    """在 outside→inside 線段上找出與判定圈邊界的交點，時間與位置皆線性內插。"""
    if outside is None:
        return inside
    ox, oy = to_local_offset_m(outside.lat, outside.lon, center.lat, center.lon)
    ix, iy = to_local_offset_m(inside.lat, inside.lon, center.lat, center.lon)
    dx, dy = ix - ox, iy - oy
    # 解 |O + t·D|² = r²，取 [0, 1] 內較小的根（從圈外進入的那一點）
    a = dx * dx + dy * dy
    b = 2 * (ox * dx + oy * dy)
    c = ox * ox + oy * oy - radius_m * radius_m
    disc = b * b - 4 * a * c
    if a == 0 or disc < 0:
        return inside
    t = min(max((-b - math.sqrt(disc)) / (2 * a), 0.0), 1.0)
    seconds = (inside.time - outside.time).total_seconds() * t
    return TrackPoint(
        outside.lat + (inside.lat - outside.lat) * t,
        outside.lon + (inside.lon - outside.lon) * t,
        outside.time + timedelta(seconds=seconds),
    )
