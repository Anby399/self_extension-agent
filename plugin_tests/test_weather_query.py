"""weather_query 插件的离线测试 (不访问网络)。"""

from unittest import mock

import weather_query as wq


SAMPLE_FORECAST = {
    "current": {
        "time": "2025-01-01T12:00",
        "temperature_2m": 8.46,
        "apparent_temperature": 6.14,
        "relative_humidity_2m": 62,
        "weather_code": 3,
        "wind_speed_10m": 11.23,
    },
    "daily": {
        "time": ["2025-01-01"],
        "temperature_2m_max": [11.02],
        "temperature_2m_min": [3.17],
        "precipitation_probability_max": [10],
    },
}

SAMPLE_GEOCODE = {
    "results": [
        {
            "name": "上海",
            "latitude": 31.22222,
            "longitude": 121.45806,
            "country": "中国",
            "admin1": "上海市",
        }
    ]
}


def test_plugin_meta():
    assert wq.PLUGIN_META["name"] == "weather_query"
    assert wq.PLUGIN_META["version"]
    assert wq.PLUGIN_META["description"]


def test_describe_weather_code_known():
    assert wq.describe_weather_code(0) == "晴"
    assert wq.describe_weather_code(2) == "多云"
    assert wq.describe_weather_code(3) == "阴"
    assert wq.describe_weather_code(61) == "小雨"
    assert wq.describe_weather_code(95) == "雷阵雨"


def test_describe_weather_code_unknown():
    assert wq.describe_weather_code(1234) == "未知"
    assert wq.describe_weather_code(None) == "未知"
    assert wq.describe_weather_code("abc") == "未知"


def test_parse_forecast_fields():
    parsed = wq.parse_forecast(SAMPLE_FORECAST)
    assert parsed["weather"] == "阴"
    assert parsed["temperature"] == 8.5
    assert parsed["feels_like"] == 6.1
    assert parsed["humidity"] == 62
    assert parsed["wind_speed"] == 11.2
    assert parsed["temp_max"] == 11.0
    assert parsed["temp_min"] == 3.2
    assert parsed["precipitation_probability"] == 10


def test_parse_forecast_tolerates_missing_data():
    parsed = wq.parse_forecast({})
    assert parsed["weather"] == "未知"
    assert parsed["temperature"] is None
    assert parsed["temp_max"] is None


def test_build_summary_contains_key_facts():
    parsed = wq.parse_forecast(SAMPLE_FORECAST)
    text = wq.build_summary("上海", parsed)
    assert "上海" in text
    assert "阴" in text
    assert "8.5°C" in text
    assert "3.2~11.0°C" in text


def test_geocode_parses_first_result():
    with mock.patch.object(wq, "http_get_json", return_value=SAMPLE_GEOCODE) as mocked:
        place = wq.geocode("上海")
    assert mocked.call_count == 1
    assert place["name"] == "上海"
    assert place["latitude"] == 31.22222
    assert place["longitude"] == 121.45806


def test_geocode_raises_when_no_result():
    with mock.patch.object(wq, "http_get_json", return_value={"results": []}):
        try:
            wq.geocode("不存在的城市")
        except LookupError:
            pass
        else:
            raise AssertionError("应当抛出 LookupError")


def test_run_success_with_mocked_network():
    with mock.patch.object(wq, "geocode", return_value=SAMPLE_GEOCODE["results"][0]):
        with mock.patch.object(wq, "fetch_forecast", return_value=SAMPLE_FORECAST):
            result = wq.run("上海")
    assert result["success"] is True
    assert result["city"] == "上海"
    assert result["temperature"] == 8.5
    assert "阴" in result["summary"]


def test_run_reports_failure_without_raising():
    with mock.patch.object(wq, "geocode", side_effect=RuntimeError("网络不可用")):
        result = wq.run("上海")
    assert result["success"] is False
    assert "网络不可用" in result["error"]
    assert "上海" in result["summary"]


def test_run_rejects_empty_city():
    result = wq.run("   ")
    assert result["success"] is False
    assert result["error"] == "城市名不能为空"
