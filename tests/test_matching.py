from datetime import UTC, datetime, timedelta

import pytest

from scorer.config import Point, Segment
from scorer.matching import match_segment
from scorer.track import TrackPoint

T0 = datetime(2026, 10, 4, 22, 0, tzinfo=UTC)
M_PER_DEG_LAT = 111_194.93
START = Point(25.0, 121.5)
END = Point(25.0 + 1200 / M_PER_DEG_LAT, 121.5)
SEGMENT = Segment("RIVER", "河堤直線", START, END, 25.0, 1200.0, "2026-10")


def run(path_m, *, speed=4.0, interval=3, t0=T0):
    """沿著北向直線，依序經過 path_m 中的各個位置（相對起點的公尺數），以等速前進並每 interval 秒取樣。"""
    points, t, pos = [], 0.0, path_m[0]
    for target in path_m[1:]:
        direction = 1 if target > pos else -1
        while (target - pos) * direction > 0:
            points.append(TrackPoint(START.lat + pos / M_PER_DEG_LAT, START.lon, t0 + timedelta(seconds=t)))
            pos += direction * min(speed * interval, abs(target - pos))
            t += interval
    points.append(TrackPoint(START.lat + pos / M_PER_DEG_LAT, START.lon, t0 + timedelta(seconds=t)))
    return points


def test_full_run_through_segment_has_correct_elapsed_seconds():
    # 進起點圈（-25 m）到進終點圈（1175 m）共 1200 m，以 4 m/s 前進應為 300 秒
    [attempt] = match_segment(run([-202, 1400]), SEGMENT)
    assert attempt.valid
    assert attempt.elapsed_s == pytest.approx(300, abs=1)
    assert attempt.seconds == 300
    assert attempt.distance_m == pytest.approx(1200, abs=2)


def test_elapsed_is_accurate_even_with_sparse_sampling():
    [attempt] = match_segment(run([-202, 1400], speed=3.7, interval=5), SEGMENT)
    assert attempt.elapsed_s == pytest.approx(1200 / 3.7, abs=1)


def test_each_lap_produces_its_own_attempt():
    # 來回跑：起點→終點→回到起點南方→再跑一次
    [first, second] = match_segment(run([-200, 1300, -200, 1300]), SEGMENT)
    assert first.valid and second.valid
    assert second.start_time > first.end_time


def test_attempt_with_detour_beyond_ten_percent_is_invalid_with_reason():
    # 中途折返 150 m，實際距離約 1500 m（> 1320 m 上限）
    [attempt] = match_segment(run([-200, 600, 450, 1300]), SEGMENT)
    assert not attempt.valid
    assert attempt.distance_m == pytest.approx(1500, abs=3)
    assert "距離不符" in attempt.reason
    assert attempt.elapsed_s is not None


def test_attempt_within_ten_percent_is_valid():
    # 折返 50 m，實際約 1300 m（< 1320 m）
    [attempt] = match_segment(run([-200, 600, 550, 1300]), SEGMENT)
    assert attempt.valid


def test_entering_start_but_never_reaching_end_is_recorded_as_invalid():
    [attempt] = match_segment(run([-200, 800]), SEGMENT)
    assert not attempt.valid
    assert attempt.reason == "進入起點後未到終點"
    assert attempt.end_time is None


def test_entering_end_before_start_does_not_complete_an_attempt():
    # 反方向：先經過終點再經過起點；終點在起點之前，不能算完成
    [attempt] = match_segment(run([1400, -200]), SEGMENT)
    assert not attempt.valid
    assert attempt.reason == "進入起點後未到終點"


def test_track_never_near_segment_has_no_attempts():
    assert match_segment(run([3000, 5000]), SEGMENT) == []
