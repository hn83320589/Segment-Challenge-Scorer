"""區段比對：從清理後的軌跡找出每一次嘗試。"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from scorer.config import DISTANCE_TOLERANCE, Point, Segment
from scorer.geo import haversine_m, to_local_offset_m
from scorer.track import TrackPoint

REASON_NOT_FINISHED = "進入起點後未到終點"
# 相鄰兩點時間差超過此值時不做邊界內插：其中一點可能是飄移點，內插結果不可信
MAX_INTERPOLATION_GAP_S = 10


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

    - 「進入」是指從圈外移動到圈內；第一個點就在圈內也算進入。
      兩個相鄰點都在圈外、但連線穿過判定圈（取樣稀疏時）也算進入。
    - 進入時間以相鄰兩點線性內插到判定圈邊界，降低取樣間隔造成的誤差；
      兩點相隔超過 MAX_INTERPOLATION_GAP_S 秒時不內插（見 _entry_crossing）。
    - 嘗試進行中又重新進入起點圈時，以最後一次進入為準重新計時。
    - 軌跡結束時仍未進入終點圈，記為無效嘗試。
    """
    attempts: list[Attempt] = []
    start_cross: TrackPoint | None = None
    path: list[TrackPoint] = []

    for i, p in enumerate(points):
        prev = points[i - 1] if i > 0 else None

        if start_cross is not None:
            end_cross = _entry_crossing(prev, p, segment.end, segment.radius_m)
            if end_cross is not None:
                attempts.append(_finish(segment, start_cross, end_cross, path + [end_cross]))
                start_cross = None
            else:
                path.append(p)

        entry = _entry_crossing(prev, p, segment.start, segment.radius_m)
        if entry is not None:
            start_cross = entry
            path = [entry] if entry is p else [entry, p]

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


def _entry_crossing(prev: TrackPoint | None, cur: TrackPoint, center: Point, radius_m: float) -> TrackPoint | None:
    """prev→cur 這一步是否進入判定圈；是的話回傳進圈的那一點（時間與位置皆線性內插），否則 None。"""
    cur_inside = _inside(cur, center, radius_m)
    if prev is None:
        return cur if cur_inside else None
    if _inside(prev, center, radius_m):
        return None

    t = _first_intersection(prev, cur, center, radius_m)
    gap_too_long = (cur.time - prev.time).total_seconds() > MAX_INTERPOLATION_GAP_S
    if cur_inside:
        # 確定已進圈；時間差太大時退回使用圈內點本身，不相信內插
        return cur if t is None or gap_too_long else _interpolate(prev, cur, t)
    # 兩點都在圈外：只有連線穿過圓、且時間差不大時才算進圈
    if t is None or gap_too_long:
        return None
    return _interpolate(prev, cur, t)


def _first_intersection(a: TrackPoint, b: TrackPoint, center: Point, radius_m: float) -> float | None:
    """線段 a→b 第一次碰到圓周的位置比例 t ∈ [0, 1]；沒有交點則為 None。

    以圓心為原點的局部平面座標解 |A + t·D|² = r²，取較小的根（從圈外進入的那一點）。
    """
    ax, ay = to_local_offset_m(a.lat, a.lon, center.lat, center.lon)
    bx, by = to_local_offset_m(b.lat, b.lon, center.lat, center.lon)
    dx, dy = bx - ax, by - ay
    qa = dx * dx + dy * dy
    qb = 2 * (ax * dx + ay * dy)
    qc = ax * ax + ay * ay - radius_m * radius_m
    disc = qb * qb - 4 * qa * qc
    if qa == 0 or disc < 0:
        return None
    t = (-qb - math.sqrt(disc)) / (2 * qa)
    # 圈內判定用 haversine、這裡用平面近似，邊界上可能有極小誤差，容許少量超出後夾回 [0, 1]
    if t < -1e-6 or t > 1 + 1e-6:
        return None
    return min(max(t, 0.0), 1.0)


def _interpolate(a: TrackPoint, b: TrackPoint, t: float) -> TrackPoint:
    seconds = (b.time - a.time).total_seconds() * t
    return TrackPoint(a.lat + (b.lat - a.lat) * t, a.lon + (b.lon - a.lon) * t, a.time + timedelta(seconds=seconds))
