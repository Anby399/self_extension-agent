"""天气查询插件: 基于 Open-Meteo 免费接口, 查询指定城市的实时天气与当日预报。

仅使用标准库 (urllib + json), 无需 API Key, 无导入期副作用。
"""

import json
import urllib.parse
import urllib.request

PLUGIN_META = {
    "name": "weather_query",
    "description": "查询指定城市的实时天气与当日预报 (基于 Open-Meteo 免费接口)",
    "version": "1.0.0",
}

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_TIMEOUT = 10
USER_AGENT = "self-extension-agent/1.0 (weather_query plugin)"

# WMO Weather interpretation codes -> 中文描述
WMO_CODE_TEXT = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "冻雾",
    51: "毛毛雨(弱)",
    53: "毛毛雨(中)",
    55: "毛毛雨(强)",
    56: "冻毛毛雨(弱)",
    57: "冻毛毛雨(强)",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨(弱)",
    67: "冻雨(强)",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴小冰雹",
    99: "雷阵雨伴大冰雹",
}


def describe_weather_code(code):
    """把 WMO 天气代码转成中文描述, 无法识别时返回 '未知'。"""
    try:
        key = int(code)
    except (TypeError, ValueError):
        return "未知"
    return WMO_CODE_TEXT.get(key, "未知")


def http_get_json(url, params=None, timeout=DEFAULT_TIMEOUT):
    """发起 GET 请求并解析 JSON 响应。"""
    if params:
        query = urllib.parse.urlencode(params)
        full_url = url + ("&" if "?" in url else "?") + query
    else:
        full_url = url
    request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def geocode(city, timeout=DEFAULT_TIMEOUT):
    """把城市名解析为带经纬度的地点信息。"""
    payload = http_get_json(
        GEOCODE_URL,
        {
            "name": city,
            "count": 1,
            "language": "zh",
            "format": "json",
        },
        timeout=timeout,
    )
    results = payload.get("results") or []
    if not results:
        raise LookupError("未找到城市: %s" % city)
    item = results[0]
    return {
        "name": item.get("name") or city,
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "country": item.get("country"),
        "admin1": item.get("admin1"),
    }


def fetch_forecast(latitude, longitude, timeout=DEFAULT_TIMEOUT):
    """获取指定经纬度的实时天气与当日预报原始数据。"""
    return http_get_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "weather_code",
                    "wind_speed_10m",
                ]
            ),
            "daily": ",".join(
                [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                ]
            ),
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=timeout,
    )


def _first(seq):
    if isinstance(seq, (list, tuple)) and seq:
        return seq[0]
    return None


def _round(value, digits=1):
    if isinstance(value, (int, float)):
        return round(value, digits)
    return value


def parse_forecast(payload):
    """从接口原始响应中提取关注的天气字段。"""
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    return {
        "time": current.get("time"),
        "weather": describe_weather_code(current.get("weather_code")),
        "weather_code": current.get("weather_code"),
        "temperature": _round(current.get("temperature_2m")),
        "feels_like": _round(current.get("apparent_temperature")),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": _round(current.get("wind_speed_10m")),
        "temp_max": _round(_first(daily.get("temperature_2m_max"))),
        "temp_min": _round(_first(daily.get("temperature_2m_min"))),
        "precipitation_probability": _first(daily.get("precipitation_probability_max")),
    }


def build_summary(name, parsed):
    """把解析后的天气字段拼成一句中文描述。"""
    parts = ["%s当前%s" % (name, parsed.get("weather") or "未知")]
    if parsed.get("temperature") is not None:
        parts.append("气温 %s°C" % parsed["temperature"])
    if parsed.get("feels_like") is not None:
        parts.append("体感 %s°C" % parsed["feels_like"])
    if parsed.get("humidity") is not None:
        parts.append("湿度 %s%%" % parsed["humidity"])
    if parsed.get("wind_speed") is not None:
        parts.append("风速 %s km/h" % parsed["wind_speed"])
    text = ", ".join(parts) + "。"
    if parsed.get("temp_min") is not None and parsed.get("temp_max") is not None:
        text += " 今日气温 %s~%s°C。" % (parsed["temp_min"], parsed["temp_max"])
    if parsed.get("precipitation_probability") is not None:
        text += " 降水概率 %s%%。" % parsed["precipitation_probability"]
    return text


def run(city="上海", timeout=DEFAULT_TIMEOUT):
    """查询城市天气。

    返回 dict, 失败时 success 为 False 并附带 error 字段, 不抛异常。
    """
    if not isinstance(city, str) or not city.strip():
        return {
            "success": False,
            "city": city,
            "error": "城市名不能为空",
            "summary": "请提供要查询的城市名。",
        }
    city = city.strip()
    try:
        place = geocode(city, timeout=timeout)
        payload = fetch_forecast(place["latitude"], place["longitude"], timeout=timeout)
    except Exception as exc:  # 网络/解析/查找失败统一转成结构化错误
        return {
            "success": False,
            "city": city,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "summary": "无法获取 %s 的天气数据: %s" % (city, exc),
        }

    parsed = parse_forecast(payload)
    label = place.get("name") or city
    result = {
        "success": True,
        "city": label,
        "country": place.get("country"),
        "admin1": place.get("admin1"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
    }
    result.update(parsed)
    result["summary"] = build_summary(label, parsed)
    return result
