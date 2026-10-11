"""讀取並驗證區段設定檔（YAML）。"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scorer.geo import haversine_m

DEFAULT_RADIUS_M = 25.0
DISTANCE_TOLERANCE = 0.10  # 嘗試的實際距離須落在參考長度 ±10% 內
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ConfigError(Exception):
    """設定檔錯誤，訊息會指出出錯的欄位路徑。"""


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float


@dataclass(frozen=True)
class Segment:
    code: str
    name: str
    start: Point
    end: Point
    radius_m: float
    reference_length_m: float
    month: str


def load_segments(path: Path) -> list[Segment]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"找不到設定檔：{path}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"設定檔不是合法的 YAML：{exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("segments"), list) or not data["segments"]:
        raise ConfigError("segments：必須是至少包含一個區段的清單")

    segments: list[Segment] = []
    seen_codes: set[str] = set()
    for i, raw in enumerate(data["segments"]):
        where = f"segments[{i}]"
        segment = _parse_segment(raw, where)
        if segment.code in seen_codes:
            raise ConfigError(f"{where}.code：區段代碼 {segment.code!r} 重複")
        seen_codes.add(segment.code)
        segments.append(segment)
    return segments


def _parse_segment(raw: Any, where: str) -> Segment:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}：必須是物件")

    month = _required_str(raw, "month", where)
    if not MONTH_PATTERN.match(month):
        raise ConfigError(f"{where}.month：格式必須是 YYYY-MM，收到 {month!r}")

    radius = raw.get("radius_m", DEFAULT_RADIUS_M)
    segment = Segment(
        code=_required_str(raw, "code", where),
        name=_required_str(raw, "name", where),
        start=_parse_point(raw, "start", where),
        end=_parse_point(raw, "end", where),
        radius_m=_positive_number(radius, f"{where}.radius_m"),
        reference_length_m=_positive_number(_required(raw, "reference_length_m", where), f"{where}.reference_length_m"),
        month=month,
    )
    _check_geometry(segment, where)
    return segment


def _check_geometry(segment: Segment, where: str) -> None:
    straight = haversine_m(segment.start.lat, segment.start.lon, segment.end.lat, segment.end.lon)
    if straight <= 2 * segment.radius_m:
        raise ConfigError(
            f"{where}.radius_m：起點與終點判定圈重疊（起終點相距 {straight:.0f} m，"
            f"必須大於 2 × 判定半徑 = {2 * segment.radius_m:.0f} m）"
        )
    # 嘗試距離從「進起點圈」量到「進終點圈」，至少約等於起終點直線距離
    upper = segment.reference_length_m * (1 + DISTANCE_TOLERANCE)
    if straight > upper:
        raise ConfigError(
            f"{where}.reference_length_m：起終點直線距離 {straight:.0f} m 已超過參考長度上限 {upper:.0f} m，"
            "任何嘗試都不可能有效，請檢查座標或參考長度"
        )


def _parse_point(raw: dict, key: str, where: str) -> Point:
    value = _required(raw, key, where)
    field = f"{where}.{key}"
    if not isinstance(value, dict):
        raise ConfigError(f"{field}：必須包含 lat 與 lon")
    lat = _number(_required(value, "lat", field), f"{field}.lat")
    lon = _number(_required(value, "lon", field), f"{field}.lon")
    if not -90 <= lat <= 90:
        raise ConfigError(f"{field}.lat：緯度必須介於 -90 到 90，收到 {lat}")
    if not -180 <= lon <= 180:
        raise ConfigError(f"{field}.lon：經度必須介於 -180 到 180，收到 {lon}")
    return Point(lat, lon)


def _required(raw: dict, key: str, where: str) -> Any:
    if raw.get(key) is None:
        raise ConfigError(f"{where}.{key}：缺少必要欄位")
    return raw[key]


def _required_str(raw: dict, key: str, where: str) -> str:
    value = _required(raw, key, where)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}.{key}：必須是非空字串")
    return value.strip()


def _number(value: Any, field: str) -> float:
    # bool 是 int 的子類別，YAML 的 yes/no 不應被當成數字
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{field}：必須是數字，收到 {value!r}")
    return float(value)


def _positive_number(value: Any, field: str) -> float:
    number = _number(value, field)
    if number <= 0:
        raise ConfigError(f"{field}：必須大於 0，收到 {number}")
    return number
