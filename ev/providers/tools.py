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

def web_search(query: str, max_results: int = 5) -> str:
    """Search the web (DuckDuckGo) and return a concise, readable summary."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:  # older package name
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
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

def _google_service(config, api: str, version: str):
    """Build an authorized Google API client. Requires GOOGLE_OAUTH_CLIENT.

    On first use, opens a browser to authorize and caches the token. On a
    headless server, run it once locally to generate the token file, then copy
    the token over.
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = config.google_token_path
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.google_oauth_client, _GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build(api, version, credentials=creds, cache_discovery=False)


def calendar_upcoming(config, max_results: int = 5) -> str:
    """List the user's upcoming Google Calendar events."""
    from datetime import datetime, timezone

    try:
        service = _google_service(config, "calendar", "v3")
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


def calendar_create(config, summary: str, start_iso: str, end_iso: str) -> str:
    """Create a Google Calendar event."""
    try:
        service = _google_service(config, "calendar", "v3")
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


def send_email(config, to: str, subject: str, body: str) -> str:
    """Send an email through the user's Gmail account."""
    import base64
    from email.message import EmailMessage

    try:
        service = _google_service(config, "gmail", "v1")
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
