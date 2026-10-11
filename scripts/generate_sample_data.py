"""產生範例 GPX 資料與區段設定檔。

模擬跑團最常用的 5 公里河堤環狀路線（1600 m × 900 m 的矩形），
挑戰區段是東側長邊上 1.2 公里的直線。輸出完全可重現（固定亂數種子、不含產生時間），
README 中的排行範例即由這份資料產生。

用法：uv run python scripts/generate_sample_data.py [輸出資料夾，預設 sample_data]
"""

import math
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ORIGIN_LAT, ORIGIN_LON = 25.0215, 121.5095  # 區段起點（河堤東側）
M_PER_DEG_LAT = 111_194.93
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
INTERVAL_S = 3
LATERAL_NOISE_M = 1.5
TAIPEI = ZoneInfo("Asia/Taipei")

# 局部座標（x 東、y 北，公尺）；區段起點為 (0, 0)、終點為 (0, 1200)
LOOP = [(0, -200), (0, 1400), (-900, 1400), (-900, -200), (0, -200)]  # 周長 5000 m


@dataclass
class Run:
    runner: str
    local_start: str  # Asia/Taipei 當地時間 "YYYY-MM-DD HH:MM"
    segment_seconds: list[float]  # 每圈在區段上的目標秒數（決定該圈配速）
    detour_lap: int | None = None  # 該圈在區段中途折返 120 m（距離超出 ±10%）
    stop_at_m: float | None = None  # 最後一圈跑到區段 y 公尺處就停止（手錶沒電）
    drift: bool = False  # 注入 GPS 飄移點與缺時間戳的點
    split: bool = False  # 中途暫停，拆成兩個 track
    tags: list[str] = field(default_factory=list)


RUNS = [
    Run("kevin", "2026-10-03 06:00", [296.4, 293.1]),
    Run("kevin", "2026-10-10 05:50", [291.8, 289.5, 294.0]),
    Run("kevin", "2026-10-17 06:10", [290.2, 287.3]),
    Run("kevin", "2026-10-25 06:00", [292.6]),
    Run("mei", "2026-10-04 06:30", [289.9, 286.8]),
    Run("mei", "2026-10-11 06:20", [288.4, 290.7]),
    Run("mei", "2026-10-18 06:30", [291.0], stop_at_m=700),
    Run("mei", "2026-10-24 06:15", [289.2, 288.8]),
    Run("jason", "2026-10-03 05:40", [305.5, 301.2, 303.9], drift=True),
    Run("jason", "2026-10-10 05:45", [302.7, 299.8]),
    Run("jason", "2026-10-18 05:40", [300.4, 298.6]),
    Run("jason", "2026-10-25 05:50", [301.1]),
    Run("yuting", "2026-10-04 07:00", [318.0, 322.4], detour_lap=0),
    Run("yuting", "2026-10-11 07:10", [321.5, 316.9]),
    Run("yuting", "2026-10-17 07:05", [319.3]),
    Run("yuting", "2026-10-24 07:00", [315.2, 317.7]),
    Run("hao", "2026-10-01 00:30", [276.3, 274.9]),  # UTC 2026-09-30T16:30Z，歸屬 10 月
    Run("hao", "2026-10-10 06:00", [273.8, 275.5, 272.4], split=True),
    Run("hao", "2026-10-17 06:00", [274.6, 271.9]),
    Run("hao", "2026-10-24 06:05", [272.8]),
    Run("lin", "2026-09-27 06:00", [330.0, 332.5]),  # 9 月活動：不列入 10 月排行
    Run("lin", "2026-10-04 06:00", [342.1, 339.6]),
    Run("lin", "2026-10-11 06:00", [338.4]),
    Run("lin", "2026-10-18 06:00", [336.9, 340.2]),
    Run("lin", "2026-10-25 06:00", [335.5, 337.0]),
]


def lap_waypoints(detour: bool) -> list[tuple[float, float]]:
    if not detour:
        return LOOP
    return [LOOP[0], (0, 600), (0, 480), *LOOP[1:]]


def simulate(run: Run, rng: random.Random) -> list[tuple[float, float, float]]:
    """回傳 (x, y, 秒數) 取樣點。每圈以固定配速前進，使區段（入圈到入圈 1200 m）時間等於目標秒數。"""
    samples, t, next_sample = [], 0.0, 0.0
    for lap, target in enumerate(run.segment_seconds):
        speed = 1200 / target
        waypoints = lap_waypoints(run.detour_lap == lap)
        last_lap = lap == len(run.segment_seconds) - 1
        if last_lap and run.stop_at_m is not None:
            waypoints = [LOOP[0], (0, run.stop_at_m)]
        for (x0, y0), (x1, y1) in zip(waypoints, waypoints[1:]):
            leg = math.hypot(x1 - x0, y1 - y0)
            leg_time = leg / speed
            while next_sample <= t + leg_time:
                f = (next_sample - t) / leg_time
                samples.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, next_sample))
                next_sample += INTERVAL_S
            t += leg_time

    # 只加垂直於行進方向的小幅雜訊：看起來像真實 GPS，又不影響進圈時間
    noisy = []
    for i, (x, y, s) in enumerate(samples):
        nx, ny = samples[min(i + 1, len(samples) - 1)][:2]
        px, py = samples[max(i - 1, 0)][:2]
        dx, dy = nx - px, ny - py
        norm = math.hypot(dx, dy) or 1
        n = rng.uniform(-LATERAL_NOISE_M, LATERAL_NOISE_M)
        noisy.append((x - dy / norm * n, y + dx / norm * n, s))
    return noisy


def to_trkpts(run: Run, samples, rng: random.Random) -> list[str]:
    start = datetime.strptime(run.local_start, "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI).astimezone(UTC)
    lines = []
    for i, (x, y, s) in enumerate(samples):
        lat, lon = ORIGIN_LAT + y / M_PER_DEG_LAT, ORIGIN_LON + x / M_PER_DEG_LON
        time = (start + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if run.drift and i > 0 and i % 97 == 0:
            # 飄移：位置突然跳到 300–600 m 外
            jump = rng.uniform(300, 600)
            lines.append(f'<trkpt lat="{lat + jump / M_PER_DEG_LAT:.7f}" lon="{lon:.7f}"><time>{time}</time></trkpt>')
            continue
        lines.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"><time>{time}</time></trkpt>')
        if run.drift and i % 131 == 0:
            lines.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"/>')  # 沒有時間戳
    return lines


def to_gpx(run: Run, trkpts: list[str]) -> str:
    groups = [trkpts[: len(trkpts) // 2], trkpts[len(trkpts) // 2 :]] if run.split else [trkpts]
    tracks = "".join(
        f"  <trk><name>河堤晨跑</name><trkseg>\n    " + "\n    ".join(group) + "\n  </trkseg></trk>\n"
        for group in groups
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="segment-challenge-scorer sample generator" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"{tracks}</gpx>\n"
    )


def write_config(path: Path) -> None:
    def lat(y: float) -> str:
        return f"{ORIGIN_LAT + y / M_PER_DEG_LAT:.7f}"

    def lon(x: float) -> str:
        return f"{ORIGIN_LON + x / M_PER_DEG_LON:.7f}"

    path.write_text(
        f"""# 區段設定檔：同一份檔案可定義多個區段
segments:
  - code: RIVER-1K2
    name: 河堤直線 1.2K
    start: {{lat: {lat(0)}, lon: {lon(0)}}}
    end: {{lat: {lat(1200)}, lon: {lon(0)}}}
    radius_m: 25            # 判定半徑（公尺），省略時預設 25
    reference_length_m: 1200
    month: "2026-10"

  - code: WEST-1K4
    name: 西岸回程 1.4K
    start: {{lat: {lat(1300)}, lon: {lon(-900)}}}
    end: {{lat: {lat(-100)}, lon: {lon(-900)}}}
    reference_length_m: 1400
    month: "2026-10"
""",
        encoding="utf-8",
    )


def main(out_dir: Path) -> None:
    rng = random.Random(20261011)
    gpx_dir, broken_dir = out_dir / "gpx", out_dir / "broken"
    gpx_dir.mkdir(parents=True, exist_ok=True)
    broken_dir.mkdir(parents=True, exist_ok=True)

    for run in RUNS:
        content = to_gpx(run, to_trkpts(run, simulate(run, rng), rng))
        (gpx_dir / f"{run.runner}_{run.local_start[:10]}.gpx").write_text(content, encoding="utf-8")

    # 示範錯誤處理：一個截斷的損毀檔、一個檔名格式錯誤的檔案、一個正常檔
    good = Run("zoe", "2026-10-12 06:30", [310.4, 308.1])
    (broken_dir / "zoe_2026-10-12.gpx").write_text(to_gpx(good, to_trkpts(good, simulate(good, rng), rng)))
    truncated = to_gpx(good, to_trkpts(good, simulate(good, rng), rng))[:1500]
    (broken_dir / "zoe_2026-10-19.gpx").write_text(truncated, encoding="utf-8")
    (broken_dir / "morning-run.gpx").write_text(to_gpx(good, []), encoding="utf-8")

    write_config(out_dir / "segments.yaml")
    print(f"已產生 {len(RUNS)} 個活動到 {gpx_dir}，錯誤示範檔到 {broken_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_data"))
