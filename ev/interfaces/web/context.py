"""Shared web request context — Phase 6b (route-router split) of the ongoing
interfaces refactor. `WebContext` bundles the app-wide singletons that used to
be plain local variables inside `create_app()` (config, memory, brain,
commands, owner) plus the small cross-domain helpers that used to be closures
inside `create_app()` (auth check, JSON body parsing, recurrence validation,
folder listing, conversation-id scoping, status text, and the /api/cmd
command runner). Route routers under `ev/interfaces/web/routes/` take a
`WebContext` instance instead of closing over `create_app()`'s locals.

Extract-and-recompose: logic is moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`, only `self.` is added where
locals were previously closed over.
"""

import asyncio
import hmac
import json
import logging

from ...core import health
from ...core.brain import Brain
from ...core.i18n import t as _t
from ...core.commands import Commands, english_name, portuguese_name
from ...core.memory import Memory
from ...providers import tools as tools_mod

log = logging.getLogger("ev.web")


class WebContext:
    """Bundles the app-wide singletons + small helpers shared by route routers."""

    def __init__(self, config, memory: Memory, brain: Brain, commands: Commands, owner: str):
        self.config = config
        self.memory = memory
        self.brain = brain
        self.commands = commands
        self.owner = owner
        # Shared OAuth CSRF-state set (Phase 6b, Group 3): a single set instance,
        # added to and discarded from by the Google, GitHub, and Spotify OAuth
        # routers alike — mirrors the single `_oauth_states` closure variable
        # they all shared inside create_app() before the split. Do NOT give each
        # router its own set; that would silently break cross-provider CSRF
        # validation (state values generated on one flow must be recognized on
        # its own callback, which is preserved by sharing the same set object).
        self.oauth_states: set[str] = set()

    def check(self, auth):
        from fastapi import HTTPException
        tok = (auth or "").removeprefix("Bearer ").strip()
        if not self.config.web_token or not hmac.compare_digest(tok, self.config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")

    async def body(self, request):
        try:
            return await request.json()
        except Exception:
            return {}

    def recurval(self, v, allow_clear=False):
        """Normalize a recurrence value to 'daily'/'weekly'/'monthly'. Returns
        None (skip) for invalid/absent, or '' to clear when allow_clear."""
        v = (v or "").strip()
        if v in ("daily", "weekly", "monthly"):
            return v
        return "" if allow_clear else None

    def folders(self):
        from .frontend import _DEFAULT_FOLDERS
        raw = self.memory.get_setting("web_folders")
        try:
            fs = json.loads(raw) if raw else None
        except Exception:
            fs = None
        return fs if isinstance(fs, list) and fs else list(_DEFAULT_FOLDERS)

    def conv(self, thread):
        t = (thread or "geral").strip() or "geral"
        return f"web:{t}"

    def status_text(self):
        lang = self.memory.assistant_lang()
        rep = health.system_report(self.config, self.memory)
        keys = health.keys_status(self.config)
        out = [_t(lang, "status.title"), ""]
        if "disk_used_pct" in rep:
            out.append(_t(lang, "status.disk", pct=rep["disk_used_pct"],
                          free=rep.get("disk_free_gb", "?")))
        if "mem_used_pct" in rep:
            out.append(_t(lang, "status.memory", pct=rep["mem_used_pct"]))
        db_state = _t(lang, "status.ok" if rep.get("db_query_ok") else "status.error")
        out.append(_t(lang, "status.database", state=db_state, size=rep.get("db_size_mb", 0)))
        out.append("")
        out.append(_t(lang, "status.keys_header"))
        for k in keys:
            mark = _t(lang, "status.ok") if k["ok"] else (k["note"] or _t(lang, "status.no"))
            out.append(f"- {k['name']}: {mark}")
        return "\n".join(out)

    async def run_command(self, cmd_str: str, thread=None) -> str:
        """Run a slash command from the web (data + interface commands)."""
        config, memory, brain, commands, owner = (
            self.config, self.memory, self.brain, self.commands, self.owner)
        lang = memory.assistant_lang()
        parts = (cmd_str or "").strip().split(None, 1)
        if not parts:
            return _t(lang, "web.empty_cmd")
        # Accept English aliases: route them exactly like their PT twin.
        name = portuguese_name(parts[0].lstrip("/").lower())
        rest = parts[1] if len(parts) > 1 else ""
        if name in ("limpar", "limparchat"):  # clear THIS folder's conversation
            memory.clear_conversation(self.conv(thread))
            return _t(lang, "web.conv_cleared")
        if name in ("plano", "manha", "manhã"):  # agentic day plan
            return await brain.plan_day(owner)
        if name in ("pendencias", "pendências", "cobrar"):  # proactive open loops
            return commands.nudge_text(owner) or _t(lang, "web.all_clear")
        if name in ("padroes", "padrões", "aprendi"):  # continuous learning view
            return commands.learned_text(owner)
        if name in ("automacoes", "automações", "automacao", "automação"):
            return commands.automacoes(owner)
        if name == "automacaorm":
            return commands.automacao_rm(owner, rest)
        if name in commands.runnable():
            return commands.run(owner, name, rest)
        if name == "provedor":
            v = rest.strip().lower()
            if v in ("", "auto", "gemini", "groq", "openrouter", "ollama"):
                memory.set_setting("force_provider", "" if v in ("", "auto") else v)
                return _t(lang, "web.provider_set", v=v) if v else _t(lang, "web.provider_auto")
            return _t(lang, "web.provider_usage")
        if name == "status":
            return self.status_text()
        if name == "modelo":
            from datetime import datetime, timezone
            usage = memory.usage_for_day(datetime.now(timezone.utc).date().isoformat())
            caps = {"gemini": 20, "groq": 1000, "openrouter": 1000}
            forced = memory.get_setting("force_provider") or "auto"
            out = [_t(lang, "web.model_main", model=brain.current_model())]
            if config.groq_api_key:
                out.append(_t(lang, "web.model_fallback", model=config.groq_model, provider="Groq"))
            if config.openrouter_api_key:
                out.append(_t(lang, "web.model_fallback", model=config.openrouter_model,
                              provider="OpenRouter"))
            out.append(_t(lang, "web.model_active", forced=forced))
            out.append("")
            out.append(_t(lang, "web.model_usage_today"))
            for prov in ("gemini", "groq", "openrouter", "ollama"):
                used = usage.get(prov, 0)
                cap = caps.get(prov)
                if cap:
                    out.append(_t(lang, "web.model_line_cap", prov=prov, used=used,
                                  left=max(0, cap - used), cap=cap))
                elif prov == "ollama" and config.ollama_enabled:
                    out.append(_t(lang, "web.model_line_unlimited", used=used))
            return "\n".join(out)
        if name == "ajuda":
            return commands.help()
        if name == "dados":
            summ = memory.storage_summary(owner)
            out = [_t(lang, "web.data_title"), ""]
            out += [_t(lang, "web.data_item", label=s['label'], count=s['count']) for s in summ]
            out.append(_t(lang, "web.data_footer"))
            return "\n".join(out)
        if name == "resumir":
            if not rest.lower().startswith("http"):
                return _t(lang, "web.summarize_usage")
            try:
                text = await asyncio.to_thread(tools_mod.fetch_text, rest)
            except Exception as e:
                return _t(lang, "web.page_error", e=str(e)[:80])
            if not text or len(text.strip()) < 80:
                return _t(lang, "web.page_no_text")
            s = await brain.ask(
                "Você é a E.V. Resuma o artigo em português: um parágrafo de contexto "
                "e depois 3 a 6 bullets com os pontos principais.",
                f"Conteúdo de {rest}:\n\n{text[:12000]}")
            return s or _t(lang, "web.summarize_fail")
        if name == "quiz":
            chunk = memory.random_chunk(owner, rest or None)
            if not chunk:
                return _t(lang, "web.kb_empty_tab")
            out = await brain.ask(
                "Você é um tutor. Com base no trecho, crie UMA pergunta de estudo "
                "objetiva e a resposta. Formato:\nPERGUNTA: <pergunta>\nRESPOSTA: <resposta>",
                f"Trecho de [{chunk['source']}]:\n{chunk['chunk']}")
            return out or _t(lang, "web.quiz_fail")
        if name in ("foco", "exportar", "transcrever", "documento", "insights", "menu"):
            shown = english_name(name) if lang == "en" else name
            return _t(lang, "web.telegram_only", name=shown)
        return commands.run(owner, name, rest)  # -> "não conheço"

    def base_url(self, request) -> str:
        """Shared by the Google/GitHub login and Spotify-connect OAuth routers
        to build redirect_uri values (must match what's registered with each
        provider)."""
        return self.config.web_base_url or str(request.base_url).rstrip("/")

    def login_ok_html(self):
        """Passed the identity check: hand the app token to this browser and
        enter. Shared by the Google/GitHub login OAuth callbacks."""
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>E.V.</title>"
            "<script>localStorage.setItem('ev_token'," + json.dumps(self.config.web_token)
            + ");location.replace('/');</script>"
            "<p style='font:14px system-ui;color:#888;padding:24px'>Entrando…</p>")

    def login_denied_html(self, msg: str):
        """Shared by the Google/GitHub login and Spotify-connect OAuth routers."""
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>E.V.</title>"
            "<div style='font:15px system-ui;color:#d6e9fb;background:#04070c;"
            "height:100vh;display:flex;flex-direction:column;align-items:center;"
            "justify-content:center;gap:16px;text-align:center;padding:24px'>"
            "<p>" + msg + "</p><a href='/' style='color:#8ab4f8'>voltar</a></div>",
            status_code=403)

    def env_write(self, var, value):
        """Persist a var=value line to .env (survives restart; Telegram picks
        it up too). Shared by the keys/custom-keys routes and the voice
        settings route in app.py."""
        import re
        p = self.config.db_path.parent / ".env"
        try:
            s = p.read_text() if p.exists() else ""
        except Exception:
            s = ""
        line = f"{var}={value}"
        if re.search(rf"(?m)^{re.escape(var)}=", s):
            s = re.sub(rf"(?m)^{re.escape(var)}=.*$", line, s)
        else:
            s = (s.rstrip("\n") + "\n" + line + "\n") if s else line + "\n"
        p.write_text(s)
