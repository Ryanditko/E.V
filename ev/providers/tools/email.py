"""Gmail tools: sending (OAuth) and reading (IMAP + app password)."""

from __future__ import annotations

import logging

from .google_auth import _google_service

log = logging.getLogger("ev.tools")


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
    from ev.providers.tools import list_emails as _list_emails  # late import: lets
    # callers monkeypatch tools.list_emails and have it take effect here too.
    try:
        items = _list_emails(config, account, query, max_results)
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
