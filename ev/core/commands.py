"""Deterministic slash commands — no LLM involved.

Fast, predictable, and free: these run pure Python against memory and the tool
providers. The Telegram interface maps `/command` to these methods; a terminal
or web interface could reuse them the same way.

E.V.'s replies here are short PT-BR strings (the assistant speaks Portuguese).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from ..config import Config
from ..providers import embeddings, tools as tools_mod
from . import knowledge
from .memory import Memory
from .timeparse import parse_when

# (command, description) — also used to populate Telegram's command menu.
COMMAND_LIST = [
    ("menu", "Abre o menu interativo com botões"),
    ("ajuda", "Lista os comandos disponíveis"),
    ("lembrete", "Criar lembrete: /lembrete 10m tomar água"),
    ("rotina", "Lembrete recorrente: /rotina diario 08:00 remédio"),
    ("lembretes", "Listar seus lembretes"),
    ("cancelar", "Cancelar lembrete: /cancelar 3"),
    ("tarefa", "Adicionar tarefa: /tarefa estudar #faculdade"),
    ("tarefas", "Listar tarefas: /tarefas [categoria]"),
    ("concluir", "Concluir tarefa: /concluir 3"),
    ("buscar", "Pesquisar na web: /buscar notícias de hoje"),
    ("gasto", "Registrar gasto: /gasto 50 mercado #casa"),
    ("gastos", "Resumo de gastos do mês"),
    ("habito", "Criar hábito: /habito treino"),
    ("feito", "Marcar hábito feito hoje: /feito treino"),
    ("habitos", "Ver hábitos e sequências"),
    ("diario", "Escrever/ver diário: /diario hoje foi bom"),
    ("lembrar", "Salvar na memória: /lembrar meu carro é um Civic"),
    ("memorias", "Listar o que a E.V. sabe sobre você"),
    ("link", "Guardar link: /link faculdade | tarefas | http://..."),
    ("links", "Listar links: /links [categoria]"),
    ("linkrm", "Remover link: /linkrm 3"),
    ("kb", "Base de conhecimento (envie um PDF para adicionar)"),
    ("kbweb", "Indexar uma página web: /kbweb https://..."),
    ("kbrm", "Remover documento da base: /kbrm nome.pdf"),
    ("agenda", "Agenda do Google: /agenda [conta]"),
    ("evento", "Criar evento: /evento [conta] amanhã 15:00 Dentista"),
    ("email", "E-mail: /email [conta] fulano@x.com | Assunto | Corpo"),
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
        return bool(
            getattr(self._config, "google_oauth_client", "")
            and getattr(self._config, "google_accounts", ())
        )

    def _resolve_account(self, argstr: str) -> tuple[str, str]:
        """If the text starts with a known account name, use it; else the default.
        Returns (account, remaining_text)."""
        argstr = argstr.strip()
        tokens = argstr.split()
        accounts = getattr(self._config, "google_accounts", ())
        if tokens and tokens[0] in accounts:
            return tokens[0], argstr[len(tokens[0]):].strip()
        default = accounts[0] if accounts else ""
        return default, argstr

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

    def rotina(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if len(tokens) < 3:
            return "Uso: /rotina <diario|semanal> <HH:MM> <texto>\nEx: /rotina diario 08:00 tomar remédio"
        kw = tokens[0].lower()
        if kw in ("diario", "diária", "diaria", "diariamente"):
            recur, label, step = "daily", "todo dia", timedelta(days=1)
        elif kw in ("semanal", "semana", "semanalmente"):
            recur, label, step = "weekly", "toda semana", timedelta(days=7)
        else:
            return "Recorrência inválida. Use 'diario' ou 'semanal'."
        try:
            hm = datetime.strptime(tokens[1], "%H:%M")
        except ValueError:
            return "Horário inválido. Use HH:MM. Ex: 08:00"
        text = " ".join(tokens[2:]).strip()
        if not text:
            return "Faltou o texto da rotina."
        now = self._now()
        first = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
        if first <= now:
            first += step
        rid = self._memory.add_reminder(user_id, text, first.isoformat(), recur)
        return f"Rotina #{rid} criada ({label} às {tokens[1]}): {text}"

    def cancelar(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /cancelar <id>. Veja os ids em /lembretes."
        ok = self._memory.cancel_reminder(user_id, int(arg))
        return f"Lembrete #{arg} cancelado." if ok else f"Não achei o lembrete #{arg} em aberto."

    def lembretes(self, user_id: str) -> str:
        items = self._memory.open_reminders(user_id)
        if not items:
            return "Você não tem lembretes em aberto."
        marks = {"daily": " [todo dia]", "weekly": " [toda semana]"}
        lines = ["Seus lembretes:"]
        for r in items:
            when = ""
            if r["when_iso"]:
                try:
                    when = " (" + datetime.fromisoformat(r["when_iso"]).strftime("%d/%m %H:%M") + ")"
                except Exception:
                    when = ""
            recur = marks.get(r.get("recur") or "", "")
            lines.append(f"#{r['id']} {r['text']}{when}{recur}")
        lines.append("\nCancelar: /cancelar <id>")
        return "\n".join(lines)

    # --- tasks --------------------------------------------------------------

    def tarefa(self, user_id: str, argstr: str) -> str:
        text = argstr.strip()
        if not text:
            return "Uso: /tarefa <texto> [#categoria]\nEx: /tarefa estudar cálculo #faculdade"
        # Extract a #category tag (default 'geral').
        category = "geral"
        tokens = text.split()
        tags = [t for t in tokens if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            text = " ".join(
                t for t in tokens if not (t.startswith("#") and len(t) > 1)
            ).strip()
        if not text:
            return "Faltou o texto da tarefa."
        tid = self._memory.add_task(user_id, text, category)
        return f"Tarefa #{tid} adicionada em '{category}': {text}"

    def tarefas(self, user_id: str, argstr: str = "") -> str:
        category = argstr.strip().lstrip("#").lower() or None
        items = self._memory.open_tasks(user_id, category)
        if not items:
            return (
                f"Nenhuma tarefa em '{category}'." if category
                else "Sua lista de tarefas está vazia."
            )
        lines = [f"Suas tarefas{' em ' + category if category else ''}:"]
        current = None
        for t in items:
            if not category and t["category"] != current:
                current = t["category"]
                lines.append(f"[{current}]")
            lines.append(f"#{t['id']} {t['text']}")
        lines.append("\nConcluir: /concluir <id>")
        return "\n".join(lines)

    def buscar(self, argstr: str) -> str:
        query = argstr.strip()
        if not query:
            return "Uso: /buscar <termo>. Ex: /buscar notícias de tecnologia hoje"
        return "Resultados da web:\n" + tools_mod.web_search(query)

    # --- expenses -----------------------------------------------------------

    def gasto(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if not tokens:
            return "Uso: /gasto <valor> <descrição> [#categoria]\nEx: /gasto 50 mercado #casa"
        try:
            amount = float(tokens[0].replace(",", "."))
        except ValueError:
            return "Valor inválido. Ex: /gasto 50 mercado"
        rest = tokens[1:]
        category = "geral"
        tags = [t for t in rest if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            rest = [t for t in rest if not (t.startswith("#") and len(t) > 1)]
        desc = " ".join(rest).strip() or "(sem descrição)"
        self._memory.add_expense(user_id, amount, desc, category)
        return f"Gasto registrado: R$ {amount:.2f} em {desc} ({category})"

    def gastos(self, user_id: str, argstr: str = "") -> str:
        since = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        items = self._memory.expenses_since(user_id, since.isoformat())
        if not items:
            return "Nenhum gasto registrado neste mês."
        total = sum(i["amount"] for i in items)
        by: dict[str, float] = {}
        for i in items:
            by[i["category"]] = by.get(i["category"], 0) + i["amount"]
        lines = [f"Gastos do mês: R$ {total:.2f} ({len(items)} lançamentos)"]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: R$ {v:.2f}")
        return "\n".join(lines)

    # --- habits -------------------------------------------------------------

    def _streak(self, habit_id: int, today) -> int:
        days = self._memory.habit_days(habit_id)
        streak, d = 0, today
        if d.strftime("%Y-%m-%d") not in days:
            d = d - timedelta(days=1)  # today not done yet: count up to yesterday
        while d.strftime("%Y-%m-%d") in days:
            streak += 1
            d = d - timedelta(days=1)
        return streak

    def habito(self, user_id: str, argstr: str) -> str:
        name = argstr.strip()
        if not name:
            return "Uso: /habito <nome>. Ex: /habito treino"
        if self._memory.find_habit(user_id, name):
            return f"O hábito '{name}' já existe."
        self._memory.add_habit(user_id, name)
        return f"Hábito '{name}' criado. Marque como feito com /feito {name}"

    def feito(self, user_id: str, argstr: str) -> str:
        name = argstr.strip()
        if not name:
            return "Uso: /feito <nome do hábito>. Ex: /feito treino"
        h = self._memory.find_habit(user_id, name)
        if not h:
            return f"Não achei o hábito '{name}'. Crie com /habito {name}"
        today = self._now().date()
        ok = self._memory.log_habit(h["id"], today.strftime("%Y-%m-%d"))
        streak = self._streak(h["id"], today)
        if not ok:
            return f"'{h['name']}' já estava marcado hoje. Sequência: {streak} dia(s)."
        return f"Boa! '{h['name']}' feito hoje. Sequência: {streak} dia(s)."

    def habitos(self, user_id: str) -> str:
        habits = self._memory.list_habits(user_id)
        if not habits:
            return "Você não tem hábitos. Crie com /habito <nome>."
        today = self._now().date()
        today_s = today.strftime("%Y-%m-%d")
        lines = ["Seus hábitos (hoje):"]
        for h in habits:
            done = "[x]" if today_s in self._memory.habit_days(h["id"]) else "[ ]"
            lines.append(f"{done} {h['name']} — sequência: {self._streak(h['id'], today)} dia(s)")
        lines.append("\nMarcar: /feito <nome>")
        return "\n".join(lines)

    # --- journal ------------------------------------------------------------

    def diario(self, user_id: str, argstr: str) -> str:
        text = argstr.strip()
        if not text:
            entries = self._memory.recent_journal(user_id, 5)
            if not entries:
                return "Diário vazio. Escreva com /diario <texto>."
            lines = ["Últimas entradas do diário:"]
            for e in entries:
                day = ""
                try:
                    day = datetime.fromisoformat(e["created"]).strftime("%d/%m")
                except Exception:
                    pass
                lines.append(f"[{day}] {e['text']}")
            return "\n".join(lines)
        self._memory.add_journal(user_id, text)
        return "Anotado no diário."

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
        vec = embeddings.embed(fact, self._config)
        self._memory.add_fact(user_id, fact, embedding=vec)
        return f"Anotado na memória: {fact}"

    def memorias(self, user_id: str) -> str:
        facts = self._memory.all_facts(user_id)
        if not facts:
            return "Ainda não sei nada sobre você. Use /lembrar pra me contar algo."
        return "O que eu sei sobre você:\n" + "\n".join(f"- {f}" for f in facts)

    # --- daily briefing -----------------------------------------------------

    def daily_briefing(self, user_id: str) -> str:
        parts = ["Bom dia! Aqui vai seu resumo de hoje:"]

        tasks = self._memory.open_tasks(user_id)
        if tasks:
            parts.append("\nTarefas em aberto:")
            parts += [f"- {t['text']}" for t in tasks]

        reminders = self._memory.open_reminders(user_id)
        if reminders:
            parts.append("\nLembretes:")
            for r in reminders:
                when = ""
                if r["when_iso"]:
                    try:
                        when = " (" + datetime.fromisoformat(r["when_iso"]).strftime("%d/%m %H:%M") + ")"
                    except Exception:
                        pass
                parts.append(f"- {r['text']}{when}")

        if self._google_ready():
            parts.append("\nAgenda:")
            parts.append(
                tools_mod.calendar_upcoming(
                    self._config, self._config.default_account, max_results=5
                )
            )

        if len(parts) == 1:
            parts.append("Nada na lista. Dia livre — aproveita!")

        if self._config.city:
            parts.append("\nClima:")
            parts.append(tools_mod.weather(self._config.city))
        if self._config.news_topic:
            parts.append("\nNotícias:")
            parts.append(tools_mod.news(self._config.news_topic))
        return "\n".join(parts)

    # --- links (named, categorized) ----------------------------------------

    def link(self, user_id: str, argstr: str) -> str:
        parts = [p.strip() for p in argstr.split("|")]
        if len(parts) != 3 or not all(parts):
            return "Uso: /link <categoria> | <nome> | <url>\nEx: /link faculdade | lista de tarefas | https://..."
        category, name, url = parts
        lid = self._memory.add_link(user_id, category, name, url)
        return f"Link #{lid} salvo em '{category}': {name}"

    def links(self, user_id: str, argstr: str) -> str:
        category = argstr.strip() or None
        items = self._memory.list_links(user_id, category)
        if not items:
            return (
                f"Nenhum link em '{category}'." if category
                else "Você ainda não guardou links. Use /link."
            )
        lines = [f"Links{' em ' + category if category else ''}:"]
        current = None
        for it in items:
            if not category and it["category"] != current:
                current = it["category"]
                lines.append(f"[{current}]")
            lines.append(f"#{it['id']} {it['name']} — {it['url']}")
        return "\n".join(lines)

    def linkrm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /linkrm <id>. Veja os ids em /links."
        ok = self._memory.delete_link(user_id, int(arg))
        return f"Link #{arg} removido." if ok else f"Não achei o link #{arg}."

    # --- knowledge base -----------------------------------------------------

    def kb(self, user_id: str) -> str:
        sources = self._memory.list_sources(user_id)
        if not sources:
            return (
                "Base de conhecimento vazia. Envie um PDF aqui no chat que eu "
                "indexo e passo a responder com base nele."
            )
        lines = ["Documentos na base de conhecimento:"]
        for s in sources:
            lines.append(f"- {s['source']} ({s['chunks']} trechos)")
        lines.append("\nEnvie um PDF para adicionar. Remover: /kbrm <nome>")
        return "\n".join(lines)

    def kbrm(self, user_id: str, argstr: str) -> str:
        source = argstr.strip()
        if not source:
            return "Uso: /kbrm <nome do documento>. Veja os nomes em /kb."
        n = self._memory.delete_source(user_id, source)
        return f"Removi '{source}' ({n} trechos)." if n else f"Não achei '{source}' na base."

    def kbweb(self, user_id: str, argstr: str) -> str:
        url = argstr.strip()
        if not url.lower().startswith("http"):
            return "Uso: /kbweb <url>. Ex: /kbweb https://pt.wikipedia.org/..."
        try:
            stored, truncated = knowledge.ingest_url(
                url, self._config, self._memory, user_id
            )
        except Exception as exc:
            return f"Não consegui ler essa página ({exc})."
        if stored == 0:
            return "Não achei texto útil nessa página."
        extra = " (página grande — indexei o começo)" if truncated else ""
        return f"Página indexada: {stored} trechos{extra}. Pode me perguntar sobre ela!"

    def ingest_document(self, user_id: str, data: bytes, filename: str) -> str:
        """Ingest an uploaded document (PDF) into the knowledge base."""
        if not filename.lower().endswith(".pdf"):
            return "Por enquanto eu só indexo PDFs. Manda um .pdf que eu guardo."
        try:
            stored, truncated = knowledge.ingest_pdf(
                data, filename, self._config, self._memory, user_id
            )
        except Exception as exc:
            return f"Não consegui ler esse PDF ({exc})."
        if stored == 0:
            return "Esse PDF parece não ter texto extraível (talvez seja escaneado)."
        extra = " (documento grande — indexei o começo)" if truncated else ""
        return f"Documento '{filename}' indexado: {stored} trechos{extra}. Pode me perguntar sobre ele!"

    # --- Google (Calendar + email) -----------------------------------------

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
