from datetime import UTC, datetime

import pytest

from scorer.geo import haversine_m, local_month


def test_haversine_one_degree_latitude_is_about_111_km():
    assert haversine_m(25.0, 121.5, 26.0, 121.5) == pytest.approx(111_195, rel=1e-3)


def test_haversine_same_point_is_zero():
    assert haversine_m(25.0, 121.5, 25.0, 121.5) == 0


def test_utc_late_evening_on_last_day_of_september_belongs_to_october():
    assert local_month(datetime(2026, 9, 30, 16, 30, tzinfo=UTC)) == "2026-10"


def test_utc_just_before_taipei_midnight_stays_in_september():
    assert local_month(datetime(2026, 9, 30, 15, 59, 59, tzinfo=UTC)) == "2026-09"
