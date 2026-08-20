"""Real-world tools E.V. can call: weather, web search, maps, Google Calendar
and email.

Each tool degrades gracefully:
  - weather/web search need no key (open-meteo / DuckDuckGo);
  - maps need no key (OpenStreetMap);
  - calendar/email need a Google OAuth client secret configured in .env, and are
    simply not exposed to the model when that is missing.

Google imports are lazy so the app runs even without those packages installed.

This package re-exports every public name that used to live directly in
`ev/providers/tools.py`, so `from ev.providers import tools` and
`tools.<name>(...)` keep working unchanged everywhere in the codebase.
"""

from __future__ import annotations

from .weather import (
    weather,
    moon_phase,
    _wicon,
    weather_full,
    weather_forecast,
    rain_tomorrow,
)
from .websearch import (
    fetch_text,
    tabnews,
    news,
    _fmt_pubdate,
    tavily_search,
    brave_search,
    _RECENT_KW,
    _looks_recent,
    web_search,
)
from .google_auth import _GOOGLE_SCOPES, _google_service
from .maps import (
    reverse_geocode,
    _OSM_KINDS,
    _haversine_m,
    nearby_places,
    geocode,
    route,
    maps_search_link,
    static_map_url,
    directions_link,
)
from .calendar import (
    calendar_upcoming,
    calendar_list_range,
    calendar_delete,
    calendar_create,
)
from .email import (
    send_email,
    _clean_from,
    _imap_query,
    _decode_header,
    list_emails,
    inbox_summary,
)

__all__ = [
    "weather", "moon_phase", "weather_full", "weather_forecast", "rain_tomorrow",
    "fetch_text", "tabnews", "news", "tavily_search", "brave_search", "web_search",
    "reverse_geocode", "nearby_places", "geocode", "route", "maps_search_link",
    "static_map_url", "directions_link",
    "calendar_upcoming", "calendar_list_range", "calendar_delete", "calendar_create",
    "send_email", "list_emails", "inbox_summary",
]
