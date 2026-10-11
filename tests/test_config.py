import pytest

from scorer.config import ConfigError, load_segments

VALID = """
segments:
  - code: RIVER
    name: 河堤直線
    start: {lat: 25.02, lon: 121.50}
    end: {lat: 25.03, lon: 121.50}
    reference_length_m: 1200
    month: "2026-10"
"""


def write(tmp_path, text):
    path = tmp_path / "segments.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_segment_with_default_radius(tmp_path):
    [segment] = load_segments(write(tmp_path, VALID))
    assert segment.code == "RIVER"
    assert segment.name == "河堤直線"
    assert segment.radius_m == 25
    assert segment.reference_length_m == 1200
    assert segment.month == "2026-10"


def test_missing_required_field_names_the_field(tmp_path):
    text = VALID.replace("    reference_length_m: 1200\n", "")
    with pytest.raises(ConfigError, match=r"segments\[0\]\.reference_length_m"):
        load_segments(write(tmp_path, text))


def test_latitude_out_of_range_names_the_field(tmp_path):
    text = VALID.replace("end: {lat: 25.03", "end: {lat: 95.03")
    with pytest.raises(ConfigError, match=r"segments\[0\]\.end\.lat"):
        load_segments(write(tmp_path, text))


def test_longitude_out_of_range_names_the_field(tmp_path):
    text = VALID.replace("start: {lat: 25.02, lon: 121.50}", "start: {lat: 25.02, lon: 221.50}")
    with pytest.raises(ConfigError, match=r"segments\[0\]\.start\.lon"):
        load_segments(write(tmp_path, text))


def test_invalid_month_names_the_field(tmp_path):
    text = VALID.replace('"2026-10"', '"2026-13"')
    with pytest.raises(ConfigError, match=r"segments\[0\]\.month"):
        load_segments(write(tmp_path, text))


def test_duplicate_code_is_rejected(tmp_path):
    body = VALID.split("segments:\n")[1]
    with pytest.raises(ConfigError, match=r"segments\[1\]\.code"):
        load_segments(write(tmp_path, "segments:\n" + body + body))


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="找不到設定檔"):
        load_segments(tmp_path / "nope.yaml")
