"""Gmail tools: sending (OAuth) and reading (IMAP + app password)."""

from __future__ import annotations

import logging

from ...core.i18n import t
from .google_auth import _google_service

log = logging.getLogger("ev.tools")


def send_email(config, account: str, to: str, subject: str, body: str,
               lang: str = "en") -> str:
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
        return t(lang, "tool.email_sent", to=to)
    except Exception as exc:
        log.warning("send_email failed (%s)", exc)
        return t(lang, "tool.email_send_error", exc=exc)


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
                max_results: int = 8, lang: str = "en") -> list[dict]:
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
                "subject": (_decode_header(msg.get("Subject", ""))
                            or t(lang, "tool.email_no_subject")),
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
                  max_results: int = 8, lang: str = "en") -> str:
    """Human-readable summary of recent emails, formatted for chat rendering."""
    from ev.providers.tools import list_emails as _list_emails  # late import: lets
    # callers monkeypatch tools.list_emails and have it take effect here too.
    try:
        items = _list_emails(config, account, query, max_results, lang)
    except Exception as exc:
        msg = str(exc)
        if "imap-not-configured" in msg:
            return t(lang, "tool.email_read_not_configured")
        log.warning("inbox_summary failed (%s)", exc)
        low = msg.lower()
        if "authenticationfailed" in low or "invalid credentials" in low or "login" in low:
            return t(lang, "tool.email_login_error")
        return t(lang, "tool.email_read_error", exc=msg[:120])
    if not items:
        return t(lang, "tool.email_none_new")
    lines = [t(lang, "tool.email_inbox_header", n=len(items)), ""]
    for i, m in enumerate(items, 1):
        line = f"#{i} {m['from']} — {m['subject']}"
        lines.append(line)
    return "\n".join(lines)
