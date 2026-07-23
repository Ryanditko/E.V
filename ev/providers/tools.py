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

# Read/write scopes for Calendar and Gmail send.
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


def news(topic: str, max_results: int = 4) -> str:
    """Recent news headlines about `topic` (DuckDuckGo, no key)."""
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
    return "\n".join(f"- {i.get('title', '')}" for i in items)


def tavily_search(query: str, api_key: str, max_results: int = 5) -> str:
    """Search via Tavily (AI-focused search; clean relevant results)."""
    import httpx

    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"query": query, "max_results": max_results, "search_depth": "basic"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return "não achei nada relevante na web."
    lines = []
    for r in results[:max_results]:
        body = (r.get("content", "") or "")[:200]
        lines.append(f"- {r.get('title', '')}: {body} ({r.get('url', '')})")
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


def web_search(
    query: str, max_results: int = 5, brave_key: str = "", tavily_key: str = ""
) -> str:
    """Search the web and return a concise summary. Order of preference:
    Tavily -> Brave -> DuckDuckGo (whichever is configured; free/no-key fallback)."""
    if tavily_key:
        try:
            return tavily_search(query, tavily_key, max_results)
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
        creds = Credentials.from_authorized_user_file(str(token_path), _GOOGLE_SCOPES)

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
