"""Deterministic slash commands — no LLM involved.

Fast, predictable, and free: these run pure Python against memory and the tool
providers. The Telegram interface maps `/command` to these methods; a terminal
or web interface could reuse them the same way.

E.V.'s replies here are short PT-BR strings (the assistant speaks Portuguese).
"""

from __future__ import annotations

from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from ..config import Config
from ..providers import embeddings, tools as tools_mod
from .memory import Memory
from .timeparse import parse_when

# (command, description) — also used to populate Telegram's command menu.
COMMAND_LIST = [
    ("ajuda", "Lista os comandos disponíveis"),
    ("lembrete", "Criar lembrete: /lembrete 10m tomar água"),
    ("lembretes", "Listar seus lembretes"),
    ("tarefa", "Adicionar tarefa: /tarefa comprar pão"),
    ("tarefas", "Listar suas tarefas"),
    ("concluir", "Concluir tarefa: /concluir 3"),
    ("lembrar", "Salvar na memória: /lembrar meu carro é um Civic"),
    ("memorias", "Listar o que a E.V. sabe sobre você"),
    ("agenda", "Ver próximos eventos do Google Agenda"),
    ("evento", "Criar evento: /evento amanhã 15:00 Dentista"),
    ("email", "Enviar e-mail: /email fulano@x.com | Assunto | Corpo"),
]


class Commands:
    def __init__(self, config: Config, memory: Memory) -> None:
        self._config = config
        self._memory = memory

    # --- helpers ------------------------------------------------------------

    def _now(self) -> datetime:
        try:
            tz = ZoneInfo(self._config.timezone) if ZoneInfo else None
            return datetime.now(tz)
        except Exception:
            return datetime.now()

    def _google_ready(self) -> bool:
        return bool(self._config.google_oauth_client)

    # --- help ---------------------------------------------------------------

    def help(self) -> str:
        lines = ["Comandos disponíveis (não usam IA):"]
        for name, desc in COMMAND_LIST:
            lines.append(f"/{name} — {desc}")
        lines.append("")
        lines.append("Pra conversar de verdade, é só mandar mensagem normal ou áudio.")
        return "\n".join(lines)

    # --- reminders ----------------------------------------------------------

    def lembrete(self, user_id: str, argstr: str) -> str:
        argstr = argstr.strip()
        if not argstr:
            return "Uso: /lembrete <tempo> <texto>\nEx: /lembrete 10m tomar água | /lembrete amanhã 09:00 reunião"
        when, text = parse_when(argstr, self._now())
        if when is None:
            return (
                "Não entendi o horário. Use algo como: 10m, 2h, 1d, "
                "'hoje 18:00', 'amanhã 09:00' ou '25/12 14:30'."
            )
        if not text.strip():
            return "Faltou o texto do lembrete. Ex: /lembrete 10m tomar água"
        rid = self._memory.add_reminder(user_id, text.strip(), when.isoformat())
        return f"Lembrete #{rid} criado para {when.strftime('%d/%m %H:%M')}: {text.strip()}"

    def lembretes(self, user_id: str) -> str:
        items = self._memory.open_reminders(user_id)
        if not items:
            return "Você não tem lembretes em aberto."
        lines = ["Seus lembretes:"]
        for r in items:
            when = ""
            if r["when_iso"]:
                try:
                    when = " (" + datetime.fromisoformat(r["when_iso"]).strftime("%d/%m %H:%M") + ")"
                except Exception:
                    when = ""
            lines.append(f"#{r['id']} {r['text']}{when}")
        return "\n".join(lines)

    # --- tasks --------------------------------------------------------------

    def tarefa(self, user_id: str, argstr: str) -> str:
        text = argstr.strip()
        if not text:
            return "Uso: /tarefa <texto>. Ex: /tarefa comprar pão"
        tid = self._memory.add_task(user_id, text)
        return f"Tarefa #{tid} adicionada: {text}"

    def tarefas(self, user_id: str) -> str:
        items = self._memory.open_tasks(user_id)
        if not items:
            return "Sua lista de tarefas está vazia."
        lines = ["Suas tarefas:"]
        for t in items:
            lines.append(f"#{t['id']} {t['text']}")
        lines.append("\nConcluir: /concluir <id>")
        return "\n".join(lines)

    def concluir(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /concluir <id>. Veja os ids em /tarefas."
        ok = self._memory.complete_task(user_id, int(arg))
        return f"Tarefa #{arg} concluída!" if ok else f"Não achei a tarefa #{arg} em aberto."

    # --- memory -------------------------------------------------------------

    def lembrar(self, user_id: str, argstr: str) -> str:
        fact = argstr.strip()
        if not fact:
            return "Uso: /lembrar <fato>. Ex: /lembrar meu carro é um Civic preto"
        vec = embeddings.embed(
            fact, api_key=self._config.gemini_api_key, model=self._config.embed_model
        )
        self._memory.add_fact(user_id, fact, embedding=vec)
        return f"Anotado na memória: {fact}"

    def memorias(self, user_id: str) -> str:
        facts = self._memory.all_facts(user_id)
        if not facts:
            return "Ainda não sei nada sobre você. Use /lembrar pra me contar algo."
        return "O que eu sei sobre você:\n" + "\n".join(f"- {f}" for f in facts)

    # --- Google (Calendar + email) -----------------------------------------

    def agenda(self) -> str:
        if not self._google_ready():
            return "Agenda do Google ainda não configurada. Conecte sua conta primeiro."
        return tools_mod.calendar_upcoming(self._config)

    def evento(self, argstr: str) -> str:
        if not self._google_ready():
            return "Agenda do Google ainda não configurada. Conecte sua conta primeiro."
        when, title = parse_when(argstr.strip(), self._now())
        if when is None or not title.strip():
            return "Uso: /evento <tempo> <título>. Ex: /evento amanhã 15:00 Dentista"
        end = when + timedelta(hours=1)
        return tools_mod.calendar_create(
            self._config, title.strip(), when.isoformat(), end.isoformat()
        )

    def email(self, argstr: str) -> str:
        if not self._google_ready():
            return "E-mail do Google ainda não configurado. Conecte sua conta primeiro."
        parts = [p.strip() for p in argstr.split("|")]
        if len(parts) != 3 or not all(parts):
            return "Uso: /email destinatário | assunto | corpo"
        to, subject, body = parts
        return tools_mod.send_email(self._config, to, subject, body)
