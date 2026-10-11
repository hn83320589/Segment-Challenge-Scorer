from datetime import UTC, datetime, timedelta

import pytest

from scorer.track import GpxParseError, TrackPoint, clean_points, parse_gpx

T0 = datetime(2026, 10, 4, 22, 0, tzinfo=UTC)


def point(seconds, north_m, *, timed=True):
    return TrackPoint(25.0 + north_m / 111_195, 121.5, T0 + timedelta(seconds=seconds) if timed else None)


def test_points_without_timestamp_are_dropped_and_counted():
    points = [point(0, 0), point(0, 5, timed=False), point(3, 10), point(0, 15, timed=False)]
    result = clean_points(points)
    assert result.kept == [points[0], points[2]]
    assert result.dropped_no_time == 2
    assert result.dropped_speed == 0


def test_points_faster_than_30_kmh_from_previous_kept_point_are_dropped():
    points = [
        point(0, 0),
        point(3, 10),  # 12 km/h
        point(6, 500),  # 飄移：490 m / 3 s
        point(9, 20),  # 與上一個「保留點」比：10 m / 6 s → 保留
        point(12, 30),
    ]
    result = clean_points(points)
    assert result.kept == [points[0], points[1], points[3], points[4]]
    assert result.dropped_speed == 1
    assert result.dropped_no_time == 0


def test_consecutive_drift_points_are_all_dropped():
    points = [point(0, 0), point(1, 300), point(2, 310), point(3, 5)]
    result = clean_points(points)
    assert result.kept == [points[0], points[3]]
    assert result.dropped_speed == 2


def test_speed_just_under_30_kmh_is_kept_and_just_over_is_dropped():
    # 30 km/h = 8.333 m/s，3 秒約 25 m
    assert clean_points([point(0, 0), point(3, 24.9)]).dropped_speed == 0
    assert clean_points([point(0, 0), point(3, 25.1)]).dropped_speed == 1


def test_point_with_non_increasing_time_is_treated_as_drift():
    points = [point(0, 0), point(0, 1), point(3, 10)]
    result = clean_points(points)
    assert result.kept == [points[0], points[2]]
    assert result.dropped_speed == 1


def gpx(body):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">{body}</gpx>""".encode()


def test_parse_merges_tracks_and_segments_in_time_order():
    data = gpx("""
      <trk><trkseg>
        <trkpt lat="25.2" lon="121.5"><time>2026-10-04T22:10:00Z</time></trkpt>
      </trkseg></trk>
      <trk><trkseg>
        <trkpt lat="25.0" lon="121.5"><time>2026-10-04T22:00:00Z</time></trkpt>
      </trkseg><trkseg>
        <trkpt lat="25.1" lon="121.5"><time>2026-10-04T22:05:00Z</time></trkpt>
      </trkseg></trk>""")
    assert [p.lat for p in parse_gpx(data)] == [25.0, 25.1, 25.2]


def test_parse_treats_naive_time_as_utc_and_converts_offsets():
    data = gpx("""<trk><trkseg>
        <trkpt lat="25.0" lon="121.5"><time>2026-10-04T22:00:00</time></trkpt>
        <trkpt lat="25.0" lon="121.5"><time>2026-10-05T06:00:05+08:00</time></trkpt>
        <trkpt lat="25.0" lon="121.5"></trkpt>
      </trkseg></trk>""")
    times = [p.time for p in parse_gpx(data)]
    assert times == [T0, T0 + timedelta(seconds=5), None]


def test_parse_rejects_broken_xml():
    with pytest.raises(GpxParseError):
        parse_gpx(b"<gpx><trk><trkseg><trkpt lat=")


def test_parse_rejects_gpx_without_track_points():
    with pytest.raises(GpxParseError, match="沒有軌跡點"):
        parse_gpx(gpx(""))


def test_drifted_first_point_is_dropped_once_following_points_agree():
    # 第一點飄到 150 m 外，之後的點彼此一致：應剔除第一點，而不是後面一整串正常點
    drifted = TrackPoint(25.0 + 150 / 111_195, 121.5, T0)
    good = [point(3 * i, 10 * i) for i in range(1, 10)]
    result = clean_points([drifted, *good])
    assert result.kept == good
    assert result.dropped_speed == 1


def test_sustained_drift_mid_track_is_still_dropped():
    # 軌跡中段（已有足夠保留點）出現持續飄移，仍依「與前一個保留點比較」剔除
    before = [point(3 * i, 10 * i) for i in range(6)]
    drift = [TrackPoint(25.0 + (500 + 10 * i) / 111_195, 121.5, T0 + timedelta(seconds=18 + 3 * i)) for i in range(6)]
    after = point(36, 60)
    result = clean_points([*before, *drift, after])
    assert result.kept == [*before, after]
    assert result.dropped_speed == 6
