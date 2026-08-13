"""Google Calendar + email."""

from __future__ import annotations

from datetime import timedelta

from ...providers import tools as tools_mod
from ..timeparse import parse_when


class GoogleIntegrationMixin:
    def agenda(self, argstr: str = "") -> str:
        if not self._google_ready():
            return "Agenda do Google ainda não configurada. Conecte sua conta primeiro."
        account, _ = self._resolve_account(argstr)
        header = f"[{account}]\n" if len(self._config.google_accounts) > 1 else ""
        return header + tools_mod.calendar_upcoming(self._config, account)

    def evento(self, argstr: str) -> str:
        if not self._google_ready():
            return "Agenda do Google ainda não configurada. Conecte sua conta primeiro."
        account, rest = self._resolve_account(argstr)
        when, title = parse_when(rest.strip(), self._now())
        if when is None or not title.strip():
            return "Uso: /evento [conta] <tempo> <título>. Ex: /evento pessoal amanhã 15:00 Dentista"
        end = when + timedelta(hours=1)
        return tools_mod.calendar_create(
            self._config, account, title.strip(), when.isoformat(), end.isoformat()
        )

    def email(self, argstr: str) -> str:
        if not self._google_ready():
            return "E-mail do Google ainda não configurado. Conecte sua conta primeiro."
        account, rest = self._resolve_account(argstr)
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) != 3 or not all(parts):
            return "Uso: /email [conta] destinatário | assunto | corpo"
        to, subject, body = parts
        return tools_mod.send_email(self._config, account, to, subject, body)

    def emails(self, argstr: str = "") -> str:
        if not self._config.imap_ready():
            return ("Leitura de e-mail ainda não configurada. Defina EV_IMAP_ADDRESS "
                    "e EV_IMAP_PASSWORD (senha de app do Gmail).")
        return tools_mod.inbox_summary(self._config, "", argstr.strip())
