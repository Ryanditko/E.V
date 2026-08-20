"""Weather tools (open-meteo, no API key)."""

from __future__ import annotations

import logging

from ...core.i18n import t

log = logging.getLogger("ev.tools")


def _weather_desc(code, lang: str = "en") -> str:
    """Localized human-readable condition for an open-meteo weather code."""
    key = f"wx.code.{int(code)}"
    desc = t(lang, key)
    return "" if desc == key else desc  # unknown code -> "" (matches old default)


def weather(city: str, lang: str = "en") -> str:
    """Current weather for `city` via open-meteo (no API key)."""
    import httpx

    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=15,
        ).json()
        if not geo.get("results"):
            return t(lang, "tool.wx_city_not_found", city=city)
        loc = geo["results"][0]
        cur = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "auto", "forecast_days": 1,
            },
            timeout=15,
        ).json()
        temp = cur["current"]["temperature_2m"]
        desc = _weather_desc(cur["current"]["weather_code"], lang)
        tmax = cur["daily"]["temperature_2m_max"][0]
        tmin = cur["daily"]["temperature_2m_min"][0]
        return t(lang, "tool.wx_current", name=loc["name"], temp=temp,
                 desc=desc, tmin=tmin, tmax=tmax)
    except Exception as exc:
        log.warning("weather failed (%s)", exc)
        return t(lang, "tool.wx_error", exc=exc)


def moon_phase() -> dict:
    """Current moon phase name + illumination % (computed, no API)."""
    import math
    from datetime import datetime, timezone
    known = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)  # a known new moon
    days = (datetime.now(timezone.utc) - known).total_seconds() / 86400
    syn = 29.53058867
    pos = (days % syn) / syn                                   # 0..1 through the cycle
    illum = round((1 - math.cos(2 * math.pi * pos)) / 2 * 100)
    table = [(0.02, "Lua nova"), (0.24, "Crescente côncava"), (0.28, "Quarto crescente"),
             (0.48, "Crescente gibosa"), (0.52, "Lua cheia"), (0.72, "Minguante gibosa"),
             (0.78, "Quarto minguante"), (0.98, "Minguante côncava"), (1.01, "Lua nova")]
    name = next((nm for th, nm in table if pos <= th), "Lua nova")
    return {"phase": name, "illum": illum, "waxing": pos < 0.5}


def _wicon(code: int, is_day: bool = True) -> str:
    """Open-Meteo weather code -> a lucide icon name for the dashboard."""
    if code == 0:
        return "sun" if is_day else "moon"
    if code in (1, 2):
        return "cloud-sun" if is_day else "cloud-moon"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "cloud-fog"
    if code in (51, 53, 55, 56, 57):
        return "cloud-drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "cloud-rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snowflake"
    if code in (95, 96, 99):
        return "cloud-lightning"
    return "cloud"


def weather_full(city: str, lang: str = "en") -> dict:
    """Rich structured weather for a dashboard (open-meteo, no key).
    Returns {} on failure. Current + next hours + 10-day forecast."""
    import httpx
    from datetime import datetime
    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=15).json()
        if not geo.get("results"):
            return {}
        loc = geo["results"][0]
        r = httpx.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": loc["latitude"], "longitude": loc["longitude"],
            "current": ("temperature_2m,apparent_temperature,weather_code,is_day,"
                        "relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
                        "wind_gusts_10m,surface_pressure,cloud_cover"),
            "hourly": "temperature_2m,weather_code,precipitation_probability,uv_index",
            "daily": ("temperature_2m_max,temperature_2m_min,weather_code,sunrise,"
                      "sunset,uv_index_max,precipitation_probability_max"),
            "timezone": "auto", "forecast_days": 10}, timeout=15).json()
        cur = r.get("current", {})
        day = bool(cur.get("is_day", 1))
        code = int(cur.get("weather_code", 3))
        daily = r.get("daily", {})
        # hourly slice: next 12 hours from the current time
        htimes = (r.get("hourly", {}) or {}).get("time", [])
        htemp = (r.get("hourly", {}) or {}).get("temperature_2m", [])
        hcode = (r.get("hourly", {}) or {}).get("weather_code", [])
        now_iso = cur.get("time", "")
        start = 0
        for i, ht in enumerate(htimes):
            if ht >= now_iso:
                start = i
                break
        hourly = []
        for i in range(start, min(start + 12, len(htimes))):
            hh = htimes[i][11:16]
            hourly.append({"time": hh, "temp": round(htemp[i]),
                           "icon": _wicon(int(hcode[i]), day)})
        days = []
        dt = daily.get("time", [])
        for i in range(len(dt)):
            try:
                lbl = (t(lang, "tool.wx_today") if i == 0
                       else t(lang, f"cal.wd.{datetime.fromisoformat(dt[i]).weekday()}"))
            except Exception:
                lbl = dt[i][5:]
            days.append({"day": lbl,
                         "min": round(daily["temperature_2m_min"][i]),
                         "max": round(daily["temperature_2m_max"][i]),
                         "icon": _wicon(int(daily["weather_code"][i]), True)})
        name = loc["name"] + (f", {loc.get('admin1')}" if loc.get("admin1") else "")
        _DIRS = [t(lang, f"wx.dir.{i}") for i in range(8)]
        wdeg = cur.get("wind_direction_10m", 0)
        uvnow = round(hcode and (r.get("hourly", {}).get("uv_index", []) or [0])[start] or 0, 1) if htimes else 0
        prob = ((r.get("hourly", {}).get("precipitation_probability", []) or [0])[start]) if htimes else 0
        return {
            "location": name,
            "current": {
                "temp": round(cur.get("temperature_2m", 0)),
                "feels": round(cur.get("apparent_temperature", 0)),
                "desc": _weather_desc(code, lang),
                "icon": _wicon(code, day),
                "high": round(daily["temperature_2m_max"][0]) if dt else None,
                "low": round(daily["temperature_2m_min"][0]) if dt else None,
                "humidity": cur.get("relative_humidity_2m"),
                "wind": round(cur.get("wind_speed_10m", 0)),
                "wind_dir": _DIRS[round(wdeg / 45) % 8], "wind_deg": round(wdeg),
                "gusts": round(cur.get("wind_gusts_10m", 0)),
                "pressure": round(cur.get("surface_pressure", 0)),
                "cloud": cur.get("cloud_cover"),
                "uv": uvnow, "precip_prob": prob,
            },
            "today": {
                "sunrise": (daily.get("sunrise", [""])[0] or "")[11:16],
                "sunset": (daily.get("sunset", [""])[0] or "")[11:16],
                "uv_max": round((daily.get("uv_index_max", [0]) or [0])[0], 1),
                "rain_chance": (daily.get("precipitation_probability_max", [0]) or [0])[0],
            },
            "hourly": hourly, "daily": days,
        }
    except Exception as exc:
        log.warning("weather_full failed (%s)", exc)
        return {}


def weather_forecast(city: str, days: int = 3, lang: str = "en") -> str:
    """Accurate multi-day forecast (today + next days) via open-meteo (no key)."""
    import httpx

    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=15,
        ).json()
        if not geo.get("results"):
            return t(lang, "tool.wx_city_not_found_short", city=city)
        loc = geo["results"][0]
        d = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
                "timezone": "auto", "forecast_days": days,
            },
            timeout=15,
        ).json()["daily"]
    except Exception as exc:
        log.warning("weather_forecast failed (%s)", exc)
        return t(lang, "tool.wx_forecast_error", exc=exc)

    labels = {0: t(lang, "tool.wx_today"), 1: t(lang, "tool.wx_tomorrow")}
    lines = [t(lang, "tool.wx_forecast_title", name=loc["name"])]
    for i in range(min(days, len(d["time"]))):
        label = labels.get(i, d["time"][i])
        desc = _weather_desc(d["weather_code"][i], lang)
        prob = d["precipitation_probability_max"][i]
        tmin, tmax = d["temperature_2m_min"][i], d["temperature_2m_max"][i]
        lines.append(t(lang, "tool.wx_forecast_line", label=label,
                       tmin=f"{tmin:.0f}", tmax=f"{tmax:.0f}", desc=desc, prob=prob))
    return "\n".join(lines)


def rain_tomorrow(city: str, lang: str = "en") -> str | None:
    """If rain is likely tomorrow in `city`, return a warning message; else None."""
    import httpx

    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=15,
        ).json()
        if not geo.get("results"):
            return None
        loc = geo["results"][0]
        fc = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "daily": "precipitation_probability_max,weather_code",
                "timezone": "auto", "forecast_days": 2,
            },
            timeout=15,
        ).json()["daily"]
        prob = fc["precipitation_probability_max"][1]
        code = fc["weather_code"][1]
        rainy_codes = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
        if (prob is not None and prob >= 50) or code in rainy_codes:
            desc = _weather_desc(code, lang) or t(lang, "tool.wx_rain_default")
            return t(lang, "tool.wx_rain_alert", name=loc["name"],
                     desc=desc, prob=prob)
        return None
    except Exception as exc:
        log.warning("rain_tomorrow failed (%s)", exc)
        return None
