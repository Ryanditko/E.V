"""Weather-provider i18n: the dashboard/rain paths must follow the language,
using the shared wx.code.* keys instead of a hardcoded Portuguese map."""

import httpx

from ev.providers.tools.weather import (
    _weather_desc, rain_tomorrow, weather_full,
)


def test_weather_desc_switches_language():
    assert _weather_desc(63, "en") == "rain"
    assert _weather_desc(63, "pt") == "chuva"
    assert _weather_desc(999, "en") == ""  # unknown code -> ""


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fake_get(geo, forecast):
    def _get(url, *args, **kwargs):
        return _Resp(geo if "geocoding" in url else forecast)
    return _get


def test_rain_tomorrow_switches_language(monkeypatch):
    geo = {"results": [{"name": "Sampa", "latitude": 1, "longitude": 2}]}
    forecast = {"daily": {"precipitation_probability_max": [10, 80],
                          "weather_code": [1, 63]}}
    monkeypatch.setattr(httpx, "get", _fake_get(geo, forecast))

    en = rain_tomorrow("Sampa", "en")
    pt = rain_tomorrow("Sampa", "pt")
    assert en and "rain" in en.lower() and "umbrella" in en.lower()
    assert pt and "chuva" in pt.lower() and "guarda-chuva" in pt.lower()


def test_weather_full_switches_language(monkeypatch):
    geo = {"results": [{"name": "Sampa", "latitude": 1, "longitude": 2,
                        "admin1": "SP"}]}
    forecast = {
        "current": {
            "time": "2026-08-20T10:00", "temperature_2m": 20,
            "apparent_temperature": 19, "weather_code": 63, "is_day": 1,
            "relative_humidity_2m": 70, "wind_speed_10m": 5,
            "wind_direction_10m": 90, "wind_gusts_10m": 8,
            "surface_pressure": 1012, "cloud_cover": 40,
        },
        "hourly": {
            "time": ["2026-08-20T10:00"], "temperature_2m": [20],
            "weather_code": [63], "precipitation_probability": [40],
            "uv_index": [3],
        },
        "daily": {
            "time": ["2026-08-20"], "temperature_2m_max": [25],
            "temperature_2m_min": [15], "weather_code": [63],
            "sunrise": ["2026-08-20T06:00"], "sunset": ["2026-08-20T18:00"],
            "uv_index_max": [5], "precipitation_probability_max": [40],
        },
    }
    monkeypatch.setattr(httpx, "get", _fake_get(geo, forecast))

    en = weather_full("Sampa", "en")
    pt = weather_full("Sampa", "pt")
    assert en["current"]["desc"] == "rain"
    assert pt["current"]["desc"] == "chuva"
    # today label + wind direction (90deg -> East) also localize
    assert en["daily"][0]["day"] == "Today"
    assert pt["daily"][0]["day"] == "Hoje"
    assert en["current"]["wind_dir"] == "E"
    assert pt["current"]["wind_dir"] == "L"
