"""Google Calendar + email."""

from __future__ import annotations

from datetime import timedelta

from ...providers import tools as tools_mod
from ..i18n import t as _t
from ..timeparse import parse_when


class GoogleIntegrationMixin:
    def agenda(self, argstr: str = "") -> str:
        if not self._google_ready():
            return _t(self._memory.assistant_lang(), "gcal.not_configured_cal")
        account, _ = self._resolve_account(argstr)
        header = f"[{account}]\n" if len(self._config.google_accounts) > 1 else ""
        return header + tools_mod.calendar_upcoming(self._config, account)

    def evento(self, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        if not self._google_ready():
            return _t(lang, "gcal.not_configured_cal")
        account, rest = self._resolve_account(argstr)
        when, title = parse_when(rest.strip(), self._now())
        if when is None or not title.strip():
            return _t(lang, "gcal.event_usage")
        end = when + timedelta(hours=1)
        return tools_mod.calendar_create(
            self._config, account, title.strip(), when.isoformat(), end.isoformat()
        )

    def email(self, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        if not self._google_ready():
            return _t(lang, "gcal.email_not_configured")
        account, rest = self._resolve_account(argstr)
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) != 3 or not all(parts):
            return _t(lang, "gcal.email_usage")
        to, subject, body = parts
        return tools_mod.send_email(self._config, account, to, subject, body)

    def emails(self, argstr: str = "") -> str:
        if not self._config.imap_ready():
            return _t(self._memory.assistant_lang(), "gcal.imap_not_configured")
        return tools_mod.inbox_summary(self._config, "", argstr.strip())
