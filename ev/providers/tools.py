"""Real-world tools E.V. can call: web search, Google Calendar and email.

Each tool degrades gracefully:
  - web search needs no key (DuckDuckGo);
  - calendar/email need a Google OAuth client secret configured in .env, and are
    simply not exposed to the model when that is missing.

Google imports are lazy so the app runs even without those packages installed.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ev.tools")

# Read/write scopes for Calendar and Gmail send. Reading mail is done over IMAP
# with an app password (gmail.readonly is a "restricted" OAuth scope that Google
# blocks for unverified apps), so it is NOT requested here.
_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
]


# --- web search ------------------------------------------------------------

_WEATHER_CODES = {
    0: "céu limpo", 1: "predominância de sol", 2: "parcialmente nublado",
    3: "nublado", 45: "névoa", 48: "névoa gelada", 51: "garoa fraca",
    53: "garoa", 55: "garoa forte", 61: "chuva fraca", 63: "chuva",
    65: "chuva forte", 71: "neve fraca", 73: "neve", 75: "neve forte",
    80: "pancadas de chuva", 81: "pancadas de chuva", 82: "temporal",
    95: "tempestade", 96: "tempestade com granizo", 99: "tempestade com granizo",
}


def weather(city: str) -> str:
    """Current weather for `city` via open-meteo (no API key)."""
    import httpx

    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=15,
        ).json()
        if not geo.get("results"):
            return f"não achei a cidade '{city}' pro clima."
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
        desc = _WEATHER_CODES.get(cur["current"]["weather_code"], "")
        tmax = cur["daily"]["temperature_2m_max"][0]
        tmin = cur["daily"]["temperature_2m_min"][0]
        return f"{loc['name']}: {temp}°C, {desc} (min {tmin}° / máx {tmax}°)"
    except Exception as exc:
        log.warning("weather failed (%s)", exc)
        return f"não consegui o clima agora ({exc})"


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


def weather_full(city: str) -> dict:
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
        for i, t in enumerate(htimes):
            if t >= now_iso:
                start = i
                break
        hourly = []
        for i in range(start, min(start + 12, len(htimes))):
            hh = htimes[i][11:16]
            hourly.append({"time": hh, "temp": round(htemp[i]),
                           "icon": _wicon(int(hcode[i]), day)})
        _WD = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
        days = []
        dt = daily.get("time", [])
        for i in range(len(dt)):
            try:
                lbl = "Hoje" if i == 0 else _WD[datetime.fromisoformat(dt[i]).weekday()]
            except Exception:
                lbl = dt[i][5:]
            days.append({"day": lbl,
                         "min": round(daily["temperature_2m_min"][i]),
                         "max": round(daily["temperature_2m_max"][i]),
                         "icon": _wicon(int(daily["weather_code"][i]), True)})
        name = loc["name"] + (f", {loc.get('admin1')}" if loc.get("admin1") else "")
        _DIRS = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]
        wdeg = cur.get("wind_direction_10m", 0)
        uvnow = round(hcode and (r.get("hourly", {}).get("uv_index", []) or [0])[start] or 0, 1) if htimes else 0
        prob = ((r.get("hourly", {}).get("precipitation_probability", []) or [0])[start]) if htimes else 0
        return {
            "location": name,
            "current": {
                "temp": round(cur.get("temperature_2m", 0)),
                "feels": round(cur.get("apparent_temperature", 0)),
                "desc": _WEATHER_CODES.get(code, ""),
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


_RAIN_CODES = {51, 53, 55, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def rain_tomorrow(city: str) -> str | None:
    """Return an alert string if rain is likely tomorrow in `city`, else None."""
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
        daily = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "daily": "precipitation_probability_max,weather_code",
                "timezone": "auto", "forecast_days": 2,
            },
            timeout=15,
        ).json()["daily"]
        prob = daily["precipitation_probability_max"][1]
        code = daily["weather_code"][1]
        if (prob is not None and prob >= 50) or code in _RAIN_CODES:
            p = f" ({prob}% de chance)" if prob is not None else ""
            return f"Amanhã deve chover em {loc['name']}{p}. Leva guarda-chuva!"
        return None
    except Exception as exc:
        log.warning("rain_tomorrow failed (%s)", exc)
        return None


def fetch_text(url: str) -> str:
    """Fetch a page and return its visible text (for change monitoring)."""
    import re

    import httpx

    r = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (E.V. assistant)"},
    )
    r.raise_for_status()
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def weather_forecast(city: str, days: int = 3) -> str:
    """Accurate multi-day forecast (today + next days) via open-meteo (no key)."""
    import httpx

    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=15,
        ).json()
        if not geo.get("results"):
            return f"não achei a cidade '{city}'."
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
        return f"não consegui a previsão agora ({exc})"

    labels = {0: "Hoje", 1: "Amanhã"}
    lines = [f"Previsão para {loc['name']}:"]
    for i in range(min(days, len(d["time"]))):
        label = labels.get(i, d["time"][i])
        desc = _WEATHER_CODES.get(d["weather_code"][i], "")
        prob = d["precipitation_probability_max"][i]
        tmin, tmax = d["temperature_2m_min"][i], d["temperature_2m_max"][i]
        lines.append(f"{label}: {tmin:.0f}°–{tmax:.0f}°C, {desc}, chuva {prob}%")
    return "\n".join(lines)


def rain_tomorrow(city: str) -> str | None:
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
            desc = _WEATHER_CODES.get(code, "chuva")
            return (
                f"Alerta: amanhã tem chance de chuva em {loc['name']} "
                f"({desc}, {prob}% de probabilidade). Leva guarda-chuva!"
            )
        return None
    except Exception as exc:
        log.warning("rain_tomorrow failed (%s)", exc)
        return None


def fetch_text(url: str) -> str:
    """Fetch a page and return its visible text (for change monitoring)."""
    import re
    import httpx

    resp = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (E.V. assistant)"},
    )
    resp.raise_for_status()
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", resp.text)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def tabnews(max_results: int = 5) -> str:
    """Top posts from TabNews (Brazilian tech/dev community), with links."""
    import httpx

    try:
        resp = httpx.get(
            "https://www.tabnews.com.br/api/v1/contents",
            params={"strategy": "relevant", "per_page": max_results},
            headers={"User-Agent": "E.V. assistant"},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        log.warning("tabnews failed (%s)", exc)
        return ""
    lines = []
    for it in items[:max_results]:
        title, owner, slug = it.get("title"), it.get("owner_username"), it.get("slug")
        if title and owner and slug:
            lines.append(f"- {title}\n  https://www.tabnews.com.br/{owner}/{slug}")
    return "\n".join(lines)


def news(topic: str, max_results: int = 4, tavily_key: str = "") -> str:
    """Recent news headlines about `topic`, WITH source links. Prefers Tavily
    (fresh, last few days) when a key is set; otherwise DuckDuckGo news."""
    if tavily_key:
        try:
            import httpx

            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "query": f"últimas notícias sobre {topic}",
                    "topic": "news", "days": 3, "max_results": max_results,
                },
                headers={"Authorization": f"Bearer {tavily_key}"},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return "\n".join(
                    f"- {r.get('title', '')}\n  {r.get('url', '')}"
                    for r in results[:max_results]
                )
        except Exception as exc:
            log.warning("tavily news failed (%s); trying DuckDuckGo", exc)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            items = list(ddgs.news(topic, region="br-pt", max_results=max_results))
    except Exception as exc:
        log.warning("news failed (%s)", exc)
        return f"não consegui as notícias agora ({exc})"
    if not items:
        return "sem notícias relevantes agora."
    return "\n".join(
        f"- {i.get('title', '')}\n  {i.get('url', '')}" for i in items
    )


def _fmt_pubdate(s: str) -> str:
    """Format a Tavily published_date (RFC-2822) as 'dd/mm/yyyy · ', or ''."""
    if not s:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%d/%m/%Y") + " · "
    except Exception:
        return ""


def tavily_search(
    query: str, api_key: str, max_results: int = 5, recent: bool = False
) -> str:
    """Search via Tavily. `recent=True` switches to the news topic (last 7 days)
    for current-events queries. Includes Tavily's synthesized answer and shows
    each result's publish date so freshness is visible."""
    import httpx

    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }
    if recent:
        payload["topic"] = "news"
        payload["days"] = 7

    resp = httpx.post(
        "https://api.tavily.com/search",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    answer = (data.get("answer") or "").strip()
    if not results and not answer:
        return "não achei nada relevante na web."
    lines = []
    if answer:
        lines.append(f"Resumo: {answer}\n")
    for r in results[:max_results]:
        body = (r.get("content", "") or "")[:180]
        date = _fmt_pubdate(r.get("published_date", ""))
        lines.append(f"- {date}{r.get('title', '')}: {body} ({r.get('url', '')})")
    return "\n".join(lines)


def brave_search(query: str, api_key: str, max_results: int = 5) -> str:
    """Search via the Brave Search API (better relevance; needs a key)."""
    import httpx

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results, "country": "br"},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("web", {}).get("results", [])
    if not results:
        return "não achei nada relevante na web."
    lines = []
    for r in results[:max_results]:
        lines.append(f"- {r.get('title', '')}: {r.get('description', '')} ({r.get('url', '')})")
    return "\n".join(lines)


# Query words that signal the user wants CURRENT info (switch Tavily to news mode).
_RECENT_KW = (
    "hoje", "agora", "últimas", "ultimas", "notícia", "noticia", "notícias",
    "noticias", "atual", "atualmente", "recente", "recentes", "2026", "preço",
    "preco", "cotação", "cotacao", "dólar", "dolar", "resultado", "placar",
    "última hora", "ultima hora",
)


def _looks_recent(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in _RECENT_KW)


def web_search(
    query: str, max_results: int = 5, brave_key: str = "", tavily_key: str = ""
) -> str:
    """Search the web and return a concise summary. Order of preference:
    Tavily -> Brave -> DuckDuckGo (whichever is configured; free/no-key fallback)."""
    if tavily_key:
        try:
            return tavily_search(
                query, tavily_key, max_results, recent=_looks_recent(query)
            )
        except Exception as exc:
            log.warning("tavily_search failed (%s); trying next", exc)
    if brave_key:
        try:
            return brave_search(query, brave_key, max_results)
        except Exception as exc:
            log.warning("brave_search failed (%s); falling back to DuckDuckGo", exc)
    try:
        try:
            from ddgs import DDGS
        except ImportError:  # older package name
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    query, region="br-pt", safesearch="off", max_results=max_results
                )
            )
    except Exception as exc:
        log.warning("web_search failed (%s)", exc)
        return f"não consegui buscar na web agora ({exc})"

    if not results:
        return "não achei nada relevante na web."

    lines = []
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        lines.append(f"- {title}: {body} ({href})")
    return "\n".join(lines)


# --- Google (Calendar + Gmail) ---------------------------------------------

def _google_service(config, account: str, api: str, version: str, allow_interactive: bool = False):
    """Build an authorized Google API client for `account`. Requires
    GOOGLE_OAUTH_CLIENT. One OAuth client serves many accounts; each account has
    its own cached token (google_token_<account>.json).

    `allow_interactive` opens a browser to authorize (only authorize_google.py
    uses this). The bot itself never does — on a headless server it raises a
    clear error instead of trying to open a browser.
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = config.token_path_for(account)
    creds = None
    if token_path.exists():
        # Load with the scopes ALREADY granted in the token file (not the full
        # _GOOGLE_SCOPES list). Otherwise adding a new scope makes refresh request
        # a scope the token never had -> Google returns invalid_scope and breaks
        # even the previously-working calls. New scopes take effect only after a
        # re-authorization (authorize_google.py), which rewrites the token file.
        creds = Credentials.from_authorized_user_file(str(token_path))

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif allow_interactive:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.google_oauth_client, _GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError(
                f"conta '{account}' ainda não autorizada — rode "
                f"authorize_google.py {account} num PC com navegador."
            )
        token_path.write_text(creds.to_json())

    return build(api, version, credentials=creds, cache_discovery=False)


def reverse_geocode(lat: float, lng: float) -> str:
    """Best-effort human-readable address for coordinates (OpenStreetMap/Nominatim)."""
    import json
    import urllib.request
    url = (f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}"
           "&format=json&zoom=16&addressdetails=0")
    req = urllib.request.Request(url, headers={"User-Agent": "E.V.-assistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        return (data.get("display_name") or "").strip()
    except Exception as exc:
        log.warning("reverse_geocode failed (%s)", exc)
        return ""


# Friendly place types -> OpenStreetMap tag filters (for Overpass queries).
_OSM_KINDS = {
    "farmácia": '["amenity"="pharmacy"]', "farmacia": '["amenity"="pharmacy"]',
    "mercado": '["shop"~"supermarket|convenience|grocery"]',
    "supermercado": '["shop"="supermarket"]',
    "restaurante": '["amenity"="restaurant"]',
    "padaria": '["shop"="bakery"]',
    "café": '["amenity"="cafe"]', "cafe": '["amenity"="cafe"]',
    "posto": '["amenity"="fuel"]', "gasolina": '["amenity"="fuel"]',
    "banco": '["amenity"="bank"]', "caixa": '["amenity"="atm"]',
    "hospital": '["amenity"~"hospital|clinic"]', "saúde": '["amenity"~"hospital|clinic|pharmacy"]',
    "ônibus": '["highway"="bus_stop"]', "onibus": '["highway"="bus_stop"]',
    "metrô": '["station"="subway"]', "metro": '["station"="subway"]',
    "trem": '["railway"="station"]', "estação": '["railway"="station"]',
    "academia": '["leisure"="fitness_centre"]',
    "escola": '["amenity"="school"]', "hotel": '["tourism"="hotel"]',
    "estacionamento": '["amenity"="parking"]',
}


def _haversine_m(lat1, lng1, lat2, lng2) -> int:
    from math import radians, sin, cos, asin, sqrt
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return int(6371000 * 2 * asin(sqrt(a)))


def nearby_places(lat: float, lng: float, query: str, radius_m: int = 1600,
                  limit: int = 20) -> list[dict]:
    """Find POIs near (lat,lng) via OpenStreetMap Overpass. Returns items sorted
    by distance: {name, lat, lng, dist, kind}. Empty list on any failure."""
    import json
    import urllib.parse
    import urllib.request

    q = (query or "").strip().lower()
    flt = _OSM_KINDS.get(q)
    if flt:
        selector = f"nwr{flt}(around:{radius_m},{lat},{lng});"
    else:  # free text -> match by name
        safe = re.sub(r'["\\]', "", query.strip())[:40]
        selector = f'nwr["name"~"{safe}",i](around:{radius_m},{lat},{lng});'
    oql = f"[out:json][timeout:25];({selector});out center {limit * 3};"
    data = urllib.parse.urlencode({"data": oql}).encode()
    res = None
    for ep in ("https://overpass-api.de/api/interpreter",
               "https://overpass.kumi.systems/api/interpreter",
               "https://overpass.private.coffee/api/interpreter",
               "https://maps.mail.ru/osm/tools/overpass/api/interpreter"):
        try:
            req = urllib.request.Request(
                ep, data=data, headers={"User-Agent": "E.V.-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                res = json.loads(r.read().decode())
            break
        except Exception as exc:
            log.warning("nearby_places via %s failed (%s)", ep.split("/")[2], exc)
    if res is None:
        return []
    out = []
    for e in res.get("elements", []):
        tags = e.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        plat = e.get("lat") or (e.get("center") or {}).get("lat")
        plng = e.get("lon") or (e.get("center") or {}).get("lon")
        if plat is None or plng is None:
            continue
        out.append({
            "name": name, "lat": plat, "lng": plng,
            "dist": _haversine_m(lat, lng, plat, plng),
            "kind": tags.get("amenity") or tags.get("shop") or tags.get("leisure") or "",
        })
    out.sort(key=lambda p: p["dist"])
    # dedupe by name, keep nearest
    seen, uniq = set(), []
    for p in out:
        k = p["name"].lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq[:limit]


def geocode(query: str) -> dict | None:
    """Forward-geocode an address/place to coords (OpenStreetMap/Nominatim)."""
    import json
    import urllib.parse
    import urllib.request
    url = ("https://nominatim.openstreetmap.org/search?"
           + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1}))
    req = urllib.request.Request(url, headers={"User-Agent": "E.V.-assistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=9) as r:
            data = json.loads(r.read().decode())
        if not data:
            return None
        return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"]),
                "name": data[0].get("display_name", "")}
    except Exception as exc:
        log.warning("geocode failed (%s)", exc)
        return None


def route(from_lat, from_lng, to_lat, to_lng, mode: str = "car") -> dict | None:
    """Driving/walking route between two points (OSRM, free). Returns
    {distance_m, duration_s, geometry(GeoJSON LineString)} or None."""
    import json
    import urllib.request
    prof = {"foot": "routed-foot", "bike": "routed-bike"}.get(mode, "routed-car")
    pname = {"foot": "foot", "bike": "bike"}.get(mode, "driving")
    url = (f"https://routing.openstreetmap.de/{prof}/route/v1/{pname}/"
           f"{from_lng},{from_lat};{to_lng},{to_lat}?overview=full&geometries=geojson")
    req = urllib.request.Request(url, headers={"User-Agent": "E.V.-assistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=13) as r:
            data = json.loads(r.read().decode())
        rt = (data.get("routes") or [None])[0]
        if not rt:
            return None
        return {"distance": int(rt["distance"]), "duration": int(rt["duration"]),
                "geometry": rt["geometry"]}
    except Exception as exc:
        log.warning("route failed (%s)", exc)
        return None


def maps_search_link(lat, lng, query: str) -> str:
    """Google Maps search link for `query` near coordinates."""
    import urllib.parse
    return (f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"
            f"/@{lat},{lng},15z")


def static_map_url(center_lat, center_lng, markers=None, zoom: int = 15,
                   w: int = 600, h: int = 320) -> str:
    """Free OpenStreetMap static-map image (no API key). `markers` = list of
    (lat, lng), pinned in red. It's a community service — best-effort, may be
    slow or occasionally unavailable; the route links work regardless."""
    import urllib.parse
    params = [("center", f"{center_lat},{center_lng}"), ("zoom", str(zoom)),
              ("size", f"{w}x{h}")]
    for mlat, mlng in (markers or []):
        params.append(("markers", f"{mlat},{mlng},red-pushpin"))
    return "https://staticmap.openstreetmap.de/staticmap.php?" + urllib.parse.urlencode(params)


def directions_link(from_lat, from_lng, to_lat, to_lng, mode: str = "walking") -> str:
    """Google Maps directions (route) link from the user's location to a place."""
    tm = mode if mode in ("walking", "driving", "bicycling", "transit") else "walking"
    return (f"https://www.google.com/maps/dir/?api=1&origin={from_lat},{from_lng}"
            f"&destination={to_lat},{to_lng}&travelmode={tm}")


def calendar_upcoming(config, account: str, max_results: int = 5) -> str:
    """List the user's upcoming Google Calendar events."""
    from datetime import datetime, timezone

    try:
        service = _google_service(config, account, "calendar", "v3")
        now = datetime.now(timezone.utc).isoformat()
        events = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
            .get("items", [])
        )
    except Exception as exc:
        log.warning("calendar_upcoming failed (%s)", exc)
        return f"não consegui acessar a agenda ({exc})"

    if not events:
        return "nenhum evento próximo na agenda."
    lines = []
    for e in events:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        lines.append(f"- {start}: {e.get('summary', '(sem título)')}")
    return "\n".join(lines)


def calendar_list_range(
    config, account: str, start_iso: str, end_iso: str, max_results: int = 250
) -> list[dict]:
    """List Google Calendar events between start and end as structured dicts."""
    service = _google_service(config, account, "calendar", "v3")
    events = (
        service.events()
        .list(
            calendarId="primary", timeMin=start_iso, timeMax=end_iso,
            maxResults=max_results, singleEvents=True, orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )
    out = []
    for e in events:
        s, en = e.get("start", {}), e.get("end", {})
        out.append({
            "id": e.get("id"),
            "summary": e.get("summary", "(sem título)"),
            "start": s.get("dateTime") or s.get("date"),
            "end": en.get("dateTime") or en.get("date"),
            "all_day": "date" in s and "dateTime" not in s,
            "link": e.get("htmlLink"),
        })
    return out


def calendar_delete(config, account: str, event_id: str) -> bool:
    """Delete a Google Calendar event by id."""
    service = _google_service(config, account, "calendar", "v3")
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return True


def calendar_create(
    config, account: str, summary: str, start_iso: str, end_iso: str
) -> str:
    """Create a Google Calendar event."""
    try:
        service = _google_service(config, account, "calendar", "v3")
        event = {
            "summary": summary,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        created = (
            service.events().insert(calendarId="primary", body=event).execute()
        )
        return f"evento criado: {created.get('htmlLink', summary)}"
    except Exception as exc:
        log.warning("calendar_create failed (%s)", exc)
        return f"não consegui criar o evento ({exc})"


def send_email(config, account: str, to: str, subject: str, body: str) -> str:
    """Send an email through the user's Gmail account."""
    import base64
    from email.message import EmailMessage

    try:
        service = _google_service(config, account, "gmail", "v1")
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"e-mail enviado para {to}"
    except Exception as exc:
        log.warning("send_email failed (%s)", exc)
        return f"não consegui enviar o e-mail ({exc})"


def _clean_from(value: str) -> str:
    """'Fulano <a@b.com>' -> 'Fulano'; bare address -> the address."""
    value = (value or "").strip()
    if "<" in value:
        name = value.split("<", 1)[0].strip().strip('"')
        return name or value.split("<", 1)[1].rstrip(">").strip()
    return value


def _imap_query(query: str):
    """Map a small, friendly query to an IMAP SEARCH criterion.

    "" / "unread" / "is:unread" -> only unread; anything else -> full-text TEXT
    search across recent mail. Returns a criteria tuple for imaplib search().
    """
    q = (query or "").strip().lower()
    if q in ("", "unread", "is:unread", "in:inbox", "is:unread in:inbox", "não lidos", "nao lidos"):
        return ("UNSEEN",)
    return ("TEXT", query.strip())


def _decode_header(raw: str) -> str:
    from email.header import decode_header
    out = []
    for part, enc in decode_header(raw or ""):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", "replace"))
            except (LookupError, TypeError):
                out.append(part.decode("utf-8", "replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def list_emails(config, account: str = "", query: str = "",
                max_results: int = 8) -> list[dict]:
    """Return recent emails from the configured Gmail inbox via IMAP.

    Reading uses IMAP + an app password (config.imap_address/imap_password), not
    OAuth. Each item: {from, subject, date, snippet, unread}. `account` is
    accepted for call-site compatibility but ignored (single mailbox).
    """
    import email as _email
    import imaplib

    if not config.imap_ready():
        raise RuntimeError("imap-not-configured")

    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        conn.login(config.imap_address, config.imap_password)
        conn.select("INBOX", readonly=True)
        typ, data = conn.search(None, *_imap_query(query))
        ids = data[0].split() if data and data[0] else []
        ids = ids[-max_results:][::-1]  # newest first
        out: list[dict] = []
        for mid in ids:
            typ, msg_data = conn.fetch(
                mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if not msg_data or not msg_data[0]:
                continue
            msg = _email.message_from_bytes(msg_data[0][1])
            out.append({
                "from": _clean_from(_decode_header(msg.get("From", ""))),
                "subject": _decode_header(msg.get("Subject", "")) or "(sem assunto)",
                "date": msg.get("Date", ""),
                "snippet": "",
                "unread": True,  # default UNSEEN search; best-effort otherwise
            })
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def inbox_summary(config, account: str = "", query: str = "",
                  max_results: int = 8) -> str:
    """Human-readable summary of recent emails, formatted for chat rendering."""
    try:
        items = list_emails(config, account, query, max_results)
    except Exception as exc:
        msg = str(exc)
        if "imap-not-configured" in msg:
            return ("leitura de e-mail ainda não configurada. Defina EV_IMAP_ADDRESS "
                    "e EV_IMAP_PASSWORD (senha de app do Gmail) para eu ler sua caixa.")
        log.warning("inbox_summary failed (%s)", exc)
        low = msg.lower()
        if "authenticationfailed" in low or "invalid credentials" in low or "login" in low:
            return ("não consegui entrar no e-mail — confira a senha de app "
                    "(EV_IMAP_PASSWORD) e se o IMAP está ativado no Gmail.")
        return f"não consegui ler os e-mails ({msg[:120]})"
    if not items:
        return "nenhum e-mail novo por aqui."
    lines = [f"📥 E-mails ({len(items)}):", ""]
    for i, m in enumerate(items, 1):
        line = f"#{i} {m['from']} — {m['subject']}"
        when = m.get("date", "")
        lines.append(line)
    return "\n".join(lines)
