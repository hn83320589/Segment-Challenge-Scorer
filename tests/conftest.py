from datetime import UTC, datetime, timedelta

import pytest

T0 = datetime(2026, 10, 4, 22, 0, tzinfo=UTC)
M_PER_DEG_LAT = 111_194.93


def make_gpx(start_lat=25.0, lon=121.5, *, meters=(-200, 1400), speed=4.0, interval=3, t0=T0, extra=""):
    """產生一條沿北向直線等速前進的 GPX（位置為相對 start_lat 的公尺數）。"""
    pts, t, pos = [], 0, meters[0]
    while pos <= meters[1]:
        time = (t0 + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pts.append(f'<trkpt lat="{start_lat + pos / M_PER_DEG_LAT:.7f}" lon="{lon}"><time>{time}</time></trkpt>')
        pos += speed * interval
        t += interval
    body = "".join(pts) + extra
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><trkseg>{body}</trkseg></trk></gpx>"
    ).encode()


@pytest.fixture
def gpx_bytes():
    return make_gpx
