"""距離計算與時區歸屬。"""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

EARTH_RADIUS_M = 6_371_000
LOCAL_TZ = ZoneInfo("Asia/Taipei")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """兩個經緯度之間的大圓距離（公尺）。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def to_local_offset_m(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """以 origin 為原點的局部平面座標（東向 x、北向 y，公尺）。

    只用於判定圈附近幾十公尺範圍的內插，等距圓柱近似的誤差可忽略。
    """
    x = math.radians(lon - origin_lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat))
    y = math.radians(lat - origin_lat) * EARTH_RADIUS_M
    return x, y


def local_month(utc_time: datetime) -> str:
    """UTC 時間轉成 Asia/Taipei 當地日期所屬的月份（YYYY-MM）。"""
    return utc_time.astimezone(LOCAL_TZ).strftime("%Y-%m")
