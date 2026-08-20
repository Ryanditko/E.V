"""Google Calendar tools."""

from __future__ import annotations

import logging

from ...core.i18n import t
from .google_auth import _google_service

log = logging.getLogger("ev.tools")


def calendar_upcoming(config, account: str, max_results: int = 5,
                      lang: str = "en") -> str:
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
        return t(lang, "tool.cal_access_error", exc=exc)

    if not events:
        return t(lang, "tool.cal_no_events")
    no_title = t(lang, "tool.cal_no_title")
    lines = []
    for e in events:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        lines.append(f"- {start}: {e.get('summary') or no_title}")
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
    config, account: str, summary: str, start_iso: str, end_iso: str,
    lang: str = "en",
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
        return t(lang, "tool.cal_event_created", link=created.get("htmlLink", summary))
    except Exception as exc:
        log.warning("calendar_create failed (%s)", exc)
        return t(lang, "tool.cal_create_error", exc=exc)
