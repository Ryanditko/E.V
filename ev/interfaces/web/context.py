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
from ...core.commands import Commands
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
        rep = health.system_report(self.config, self.memory)
        keys = health.keys_status(self.config)
        out = ["🩺 Status da E.V.", ""]
        if "disk_used_pct" in rep:
            out.append(f"Disco: {rep['disk_used_pct']}% · {rep.get('disk_free_gb','?')} GB livres")
        if "mem_used_pct" in rep:
            out.append(f"Memória: {rep['mem_used_pct']}%")
        out.append(f"Banco: {'ok' if rep.get('db_query_ok') else 'erro'} ({rep.get('db_size_mb',0)} MB)")
        out.append("")
        out.append("Chaves / integrações:")
        for k in keys:
            mark = "ok" if k["ok"] else (k["note"] or "não")
            out.append(f"- {k['name']}: {mark}")
        return "\n".join(out)

    async def run_command(self, cmd_str: str, thread=None) -> str:
        """Run a slash command from the web (data + interface commands)."""
        config, memory, brain, commands, owner = (
            self.config, self.memory, self.brain, self.commands, self.owner)
        parts = (cmd_str or "").strip().split(None, 1)
        if not parts:
            return "Digite um comando."
        name = parts[0].lstrip("/").lower()
        rest = parts[1] if len(parts) > 1 else ""
        if name in ("limpar", "limparchat"):  # clear THIS folder's conversation
            memory.clear_conversation(self.conv(thread))
            return "Conversa limpa nesta pasta."
        if name in ("plano", "manha", "manhã"):  # agentic day plan
            return await brain.plan_day(owner)
        if name in ("pendencias", "pendências", "cobrar"):  # proactive open loops
            return commands.nudge_text(owner) or "Tudo em dia, Ryan — nada atrasado. 👌"
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
                return f"Provedor: {v or 'auto'}." if v else "Provedor: automático."
            return "Uso: /provedor auto|gemini|groq|openrouter|ollama"
        if name == "status":
            return self.status_text()
        if name == "modelo":
            from datetime import datetime, timezone
            usage = memory.usage_for_day(datetime.now(timezone.utc).date().isoformat())
            caps = {"gemini": 20, "groq": 1000, "openrouter": 1000}
            forced = memory.get_setting("force_provider") or "auto"
            out = [f"🧠 Principal: {brain.current_model()} (Gemini)"]
            if config.groq_api_key:
                out.append(f"Fallback: {config.groq_model} (Groq)")
            if config.openrouter_api_key:
                out.append(f"Fallback: {config.openrouter_model} (OpenRouter)")
            out.append(f"Provedor ativo: {forced}")
            out.append("")
            out.append("📊 Uso hoje (zera à meia-noite UTC):")
            for prov in ("gemini", "groq", "openrouter", "ollama"):
                used = usage.get(prov, 0)
                cap = caps.get(prov)
                if cap:
                    out.append(f"- {prov}: {used} usados · ~{max(0, cap - used)} restantes (de ~{cap})")
                elif prov == "ollama" and config.ollama_enabled:
                    out.append(f"- ollama: {used} usados · ilimitado")
            return "\n".join(out)
        if name == "ajuda":
            return commands.help()
        if name == "dados":
            summ = memory.storage_summary(owner)
            out = ["🗄️ Seus dados guardados:", ""]
            out += [f"- {s['label']}: {s['count']}" for s in summ]
            out.append("\nPra apagar por categoria, use as abas (Tarefas/Gastos/...) "
                       "ou o /dados no Telegram (com dupla confirmação pra apagar tudo).")
            return "\n".join(out)
        if name == "resumir":
            if not rest.lower().startswith("http"):
                return "Uso: /resumir <url>"
            try:
                text = await asyncio.to_thread(tools_mod.fetch_text, rest)
            except Exception as e:
                return f"Não consegui abrir a página ({str(e)[:80]})."
            if not text or len(text.strip()) < 80:
                return "Não achei texto útil nessa página."
            s = await brain.ask(
                "Você é a E.V. Resuma o artigo em português: um parágrafo de contexto "
                "e depois 3 a 6 bullets com os pontos principais.",
                f"Conteúdo de {rest}:\n\n{text[:12000]}")
            return s or "Não consegui resumir agora, tenta de novo?"
        if name == "quiz":
            chunk = memory.random_chunk(owner, rest or None)
            if not chunk:
                return "Base de conhecimento vazia. Adicione algo na aba Base primeiro."
            out = await brain.ask(
                "Você é um tutor. Com base no trecho, crie UMA pergunta de estudo "
                "objetiva e a resposta. Formato:\nPERGUNTA: <pergunta>\nRESPOSTA: <resposta>",
                f"Trecho de [{chunk['source']}]:\n{chunk['chunk']}")
            return out or "Não consegui gerar a pergunta agora."
        if name in ("foco", "exportar", "transcrever", "documento", "insights", "menu"):
            return (f"O /{name} é melhor no Telegram ou pela interface: use a aba/botão "
                    "correspondente (ex: Pomodoro, exportar no painel).")
        return commands.run(owner, name, rest)  # -> "não conheço"

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
