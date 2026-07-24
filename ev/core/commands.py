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
from .timeparse import add_months, parse_when

# (command, description) — also used to populate Telegram's command menu.
COMMAND_LIST = [
    ("menu", "Abre o menu interativo com botões"),
    ("ajuda", "Lista os comandos disponíveis"),
    ("status", "Diagnóstico: VM, banco, chaves de API"),
    ("silenciar", "Não perturbe: /silenciar 2h (ou off)"),
    ("dados", "Ver/apagar seus dados guardados (por categoria ou tudo)"),
    ("limpar", "Limpar a conversa (mantém memórias e o resto)"),
    ("limparchat", "Apagar bolhas do chat: /limparchat 10 ou /limparchat tudo"),
    ("resumir", "Resumir um link: /resumir https://..."),
    ("foco", "Timer de foco/Pomodoro: /foco 25 5"),
    ("lembrete", "Criar lembrete: /lembrete 10m tomar água"),
    ("rotina", "Recorrente: /rotina diario|semanal|mensal [dia] HH:MM texto"),
    ("lembretes", "Listar seus lembretes"),
    ("cancelar", "Cancelar lembrete: /cancelar 3"),
    ("calendario", "Ver sua agenda por dia (lembretes + Google)"),
    ("noticias", "Últimas notícias com fontes: /noticias tecnologia"),
    ("tarefa", "Adicionar tarefa: /tarefa estudar #faculdade"),
    ("tarefas", "Listar tarefas: /tarefas [categoria]"),
    ("concluir", "Concluir tarefa: /concluir 3"),
    ("buscar", "Pesquisar na web: /buscar notícias de hoje"),
    ("procurar", "Procurar nos SEUS dados: /procurar cálculo"),
    ("clima", "Previsão do tempo: /clima São Paulo"),
    ("gasto", "Registrar gasto: /gasto 50 mercado #casa"),
    ("gastos", "Resumo de gastos do mês"),
    ("gastorm", "Apagar gasto: /gastorm 3"),
    ("orcamento", "Definir orçamento: /orcamento comida 800"),
    ("orcamentos", "Ver orçamentos e quanto já gastou"),
    ("orcamentorm", "Apagar orçamento: /orcamentorm comida"),
    ("relatorio", "Relatório financeiro do mês passado"),
    ("quiz", "Estudar: pergunta sobre seus PDFs (/quiz [documento])"),
    ("insights", "Insights da sua semana (IA)"),
    ("modelo", "Ver/trocar o modelo de IA e uso do dia"),
    ("habito", "Criar hábito: /habito treino"),
    ("feito", "Marcar hábito feito hoje: /feito treino"),
    ("habitos", "Ver hábitos e sequências"),
    ("habitorm", "Apagar hábito: /habitorm treino"),
    ("diario", "Escrever/ver diário: /diario hoje foi bom"),
    ("diariorm", "Apagar entrada do diário: /diariorm 3"),
    ("semana", "Revisão da sua semana (também chega automática)"),
    ("vigiar", "Monitorar página: /vigiar https://... | palavra"),
    ("vigias", "Ver monitores web"),
    ("vigiarm", "Apagar monitor: /vigiarm 3"),
    ("assinatura", "Gasto recorrente: /assinatura 39,90 Netflix 15"),
    ("assinaturas", "Ver assinaturas recorrentes"),
    ("assinaturarm", "Apagar assinatura: /assinaturarm 3"),
    ("lembrar", "Salvar na memória: /lembrar meu carro é um Civic"),
    ("memorias", "Listar o que a E.V. sabe sobre você"),
    ("esquecer", "Apagar uma memória: /esquecer 3"),
    ("link", "Guardar link: /link faculdade | tarefas | http://..."),
    ("links", "Listar links: /links [categoria]"),
    ("linkrm", "Remover link: /linkrm 3"),
    ("kb", "Base de conhecimento (envie um PDF para adicionar)"),
    ("kbweb", "Indexar uma página web: /kbweb https://..."),
    ("kbrm", "Remover documento da base: /kbrm nome.pdf"),
    ("documento", "Criar arquivo: /documento pdf Título | conteúdo"),
    ("exportar", "Exportar dados: /exportar gastos (CSV) ou /exportar dados (PDF)"),
    ("transcrever", "Transcrever áudio em texto (manda o áudio depois)"),
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
        return (
            "🕷️ E.V. — todos os comandos\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏠 Geral\n"
            "   /menu · /ajuda · /modelo · /status · /silenciar\n"
            "   /dados (armazenamento) · /limpar (memória) · /limparchat (bolhas)\n\n"
            "🎯 Foco & Web\n"
            "   /foco (pomodoro) · /resumir (link)\n\n"
            "📋 Tarefas\n"
            "   /tarefa · /tarefas · /concluir\n\n"
            "⏰ Lembretes & Agenda\n"
            "   /lembrete · /rotina · /lembretes · /cancelar · /calendario\n\n"
            "🧠 Memória\n"
            "   /lembrar · /memorias · /esquecer\n\n"
            "🔗 Links\n"
            "   /link · /links · /linkrm\n\n"
            "📄 Conhecimento & Estudo\n"
            "   envie um PDF/Word/txt · /kb · /kbweb · /kbrm · /quiz\n"
            "   /documento (criar) · /exportar (dados) · /transcrever (áudio)\n\n"
            "💰 Finanças\n"
            "   /gasto · /gastos · /gastorm · /relatorio\n"
            "   /orcamento · /orcamentos · /orcamentorm\n"
            "   /assinatura · /assinaturas · /assinaturarm\n\n"
            "✅ Hábitos\n"
            "   /habito · /feito · /habitos · /habitorm\n\n"
            "📔 Diário\n"
            "   /diario · /diariorm\n\n"
            "📊 Resumos & Automação\n"
            "   /semana · /insights · /vigiar · /vigias · /vigiarm\n\n"
            "🔎 Busca, Notícias & Clima\n"
            "   /buscar (web) · /procurar (seus dados) · /noticias · /clima\n\n"
            "📅 Google\n"
            "   /agenda · /evento · /email\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💬 Ou toque em /menu pra usar por botões. Também entendo mensagem, áudio, foto e PDF!"
        )

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

    _USO_ROTINA = (
        "Uso: /rotina <diario|semanal|mensal> [dia] <HH:MM> <texto>\n"
        "Ex: /rotina diario 08:00 tomar remédio\n"
        "Ex: /rotina semanal 09:00 revisar metas\n"
        "Ex: /rotina mensal 5 10:00 pagar aluguel  (todo dia 5)"
    )

    def rotina(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if len(tokens) < 3:
            return self._USO_ROTINA
        kw = tokens[0].lower()
        now = self._now()
        if kw in ("diario", "diária", "diaria", "diariamente"):
            recur, label = "daily", "todo dia"
        elif kw in ("semanal", "semana", "semanalmente"):
            recur, label = "weekly", "toda semana"
        elif kw in ("mensal", "mensalmente", "mes", "mês", "monthly"):
            recur = "monthly"
        else:
            return "Recorrência inválida. Use 'diario', 'semanal' ou 'mensal'."

        if recur == "monthly":
            # /rotina mensal <dia> <HH:MM> <texto>
            if len(tokens) < 4 or not tokens[1].isdigit():
                return "Uso mensal: /rotina mensal <dia> <HH:MM> <texto>\nEx: /rotina mensal 5 10:00 pagar aluguel"
            day = int(tokens[1])
            if not 1 <= day <= 31:
                return "Dia do mês inválido (use 1 a 31)."
            time_tok, text = tokens[2], " ".join(tokens[3:]).strip()
        else:
            time_tok, text = tokens[1], " ".join(tokens[2:]).strip()

        try:
            hm = datetime.strptime(time_tok, "%H:%M")
        except ValueError:
            return "Horário inválido. Use HH:MM. Ex: 08:00"
        if not text:
            return "Faltou o texto da rotina."

        if recur == "monthly":
            first = self._monthly_first(now, day, hm.hour, hm.minute)
            label = f"todo dia {day}"
        else:
            step = timedelta(days=1) if recur == "daily" else timedelta(days=7)
            first = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
            if first <= now:
                first += step

        rid = self._memory.add_reminder(user_id, text, first.isoformat(), recur)
        return f"Rotina #{rid} criada ({label} às {time_tok}): {text}"

    @staticmethod
    def _clamp_day(dt: datetime, day: int) -> datetime:
        """Set dt's day to `day`, clamped to the last valid day of dt's month."""
        if dt.month == 12:
            last = 31
        else:
            last = (dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)).day
        return dt.replace(day=min(day, last))

    @staticmethod
    def _monthly_first(now: datetime, day: int, hour: int, minute: int) -> datetime:
        """First future occurrence of a monthly reminder on `day` at hour:minute."""
        base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        cand = Commands._clamp_day(base.replace(day=1), day)
        if cand <= now:
            cand = Commands._clamp_day(add_months(base.replace(day=1), 1), day)
        return cand

    _WEEKDAYS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

    def calendario(self, user_id: str) -> str:
        """Agenda view: reminders grouped by day (+ Google Calendar if connected)."""
        dated = []
        for r in self._memory.open_reminders(user_id):
            if r["when_iso"]:
                try:
                    dated.append((datetime.fromisoformat(r["when_iso"]), r))
                except Exception:
                    pass
        dated.sort(key=lambda x: x[0])
        lines = ["📅 Sua agenda"]
        if not dated:
            lines.append("Nada agendado. Crie com /lembrete ou /rotina.")
        else:
            current = None
            for dt, r in dated:
                day = f"{dt.strftime('%d/%m')} ({self._WEEKDAYS_PT[dt.weekday()]})"
                if day != current:
                    current = day
                    lines.append(f"\n📌 {day}")
                recur = " 🔁" if (r.get("recur")) else ""
                lines.append(f"  {dt.strftime('%H:%M')} — {r['text']}{recur}")
        if self._config.google_authorized():
            lines.append("\n📆 Google Agenda:")
            lines.append(
                tools_mod.calendar_upcoming(self._config, self._config.default_account, 5)
            )
        return "\n".join(lines)

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
        marks = {"daily": " [todo dia]", "weekly": " [toda semana]", "monthly": " [todo mês]"}
        lines = ["⏰ Seus lembretes:"]
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
        lines = [f"📋 Suas tarefas{' em ' + category if category else ''}:"]
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
        return "Resultados da web:\n" + tools_mod.web_search(
            query,
            brave_key=getattr(self._config, "brave_api_key", ""),
            tavily_key=getattr(self._config, "tavily_api_key", ""),
        )

    def procurar(self, user_id: str, argstr: str) -> str:
        """Unified search across everything the user stored (not the web)."""
        term = argstr.strip()
        if not term:
            return "Uso: /procurar <termo>. Procuro em tudo que você guardou (memória, tarefas, lembretes, links, diário, documentos)."
        r = self._memory.search_all(user_id, term)
        labels = [
            ("facts", "🧠 Memórias"), ("tasks", "📋 Tarefas"),
            ("reminders", "⏰ Lembretes"), ("links", "🔗 Links"),
            ("journal", "📔 Diário"), ("knowledge", "📄 Conhecimento"),
        ]
        lines = [f"🔎 Resultados para '{term}':"]
        found = False
        for key, label in labels:
            items = r.get(key) or []
            if not items:
                continue
            found = True
            lines.append(f"\n{label}:")
            for it in items[:5]:
                if key == "knowledge":
                    src, chunk = it
                    lines.append(f"- [{src}] {chunk[:120]}…")
                else:
                    lines.append(f"- {it}")
        if not found:
            return f"Nada encontrado pra '{term}' nos seus dados."
        return "\n".join(lines)

    def noticias(self, argstr: str = "") -> str:
        topic = argstr.strip() or getattr(self._config, "news_topic", "") or "Brasil"
        out = tools_mod.news(
            topic, tavily_key=getattr(self._config, "tavily_api_key", "")
        )
        parts = [f"📰 Notícias — {topic}:", out]
        tab = tools_mod.tabnews(5)
        if tab:
            parts.append("\n💻 TabNews (tech):")
            parts.append(tab)
        return "\n".join(parts)

    def clima(self, argstr: str) -> str:
        city = argstr.strip() or getattr(self._config, "city", "")
        if not city:
            return "Uso: /clima <cidade>. Ex: /clima São Paulo"
        return tools_mod.weather_forecast(city)

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
        msg = f"Gasto registrado: R$ {amount:.2f} em {desc} ({category})"
        # Budget alert (if a limit is set for this category).
        budget = self._memory.get_budget(user_id, category)
        if budget:
            since = datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            spent = self._memory.category_total_since(user_id, category, since)
            pct = spent / budget * 100 if budget else 0
            if pct >= 100:
                msg += f"\n🔴 Estourou o orçamento de {category}: R$ {spent:.2f} / R$ {budget:.2f}."
            elif pct >= 80:
                msg += f"\n🟡 Atenção: {pct:.0f}% do orçamento de {category} (R$ {spent:.2f} / R$ {budget:.2f})."
        return msg

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
        lines = [f"💰 Gastos do mês: R$ {total:.2f} ({len(items)} lançamentos)"]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: R$ {v:.2f}")
        lines.append("\nLançamentos recentes:")
        for i in items[-10:]:
            lines.append(f"#{i['id']} R$ {i['amount']:.2f} {i['description']} ({i['category']})")
        lines.append("\nApagar: /gastorm <id>")
        return "\n".join(lines)

    def gastorm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /gastorm <id>. Veja os ids em /gastos."
        ok = self._memory.delete_expense(user_id, int(arg))
        return f"Gasto #{arg} apagado." if ok else f"Não achei o gasto #{arg}."

    def relatorio(self, user_id: str) -> str:
        """Financial report for the PREVIOUS month, by category vs budget."""
        now = datetime.now(timezone.utc)
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_prev = (first_this - timedelta(seconds=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        label = first_prev.strftime("%m/%Y")
        items = self._memory.expenses_between(
            user_id, first_prev.isoformat(), first_this.isoformat()
        )
        if not items:
            return f"📈 Relatório de {label}: nenhum gasto registrado."
        total = sum(i["amount"] for i in items)
        by: dict[str, float] = {}
        for i in items:
            by[i["category"]] = by.get(i["category"], 0) + i["amount"]
        lines = [f"📈 Relatório de {label}", f"Total: R$ {total:.2f} ({len(items)} lançamentos)", ""]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            budget = self._memory.get_budget(user_id, cat)
            vs = f" · orçamento R$ {budget:.0f} ({v / budget * 100:.0f}%)" if budget else ""
            lines.append(f"- {cat}: R$ {v:.2f}{vs}")
        return "\n".join(lines)

    # --- budgets ------------------------------------------------------------

    def orcamento(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if len(tokens) < 2:
            return "Uso: /orcamento <categoria> <valor>\nEx: /orcamento comida 800"
        category = tokens[0].lstrip("#").lower()
        try:
            amount = float(tokens[1].replace(",", "."))
        except ValueError:
            return "Valor inválido. Ex: /orcamento comida 800"
        self._memory.set_budget(user_id, category, amount)
        return f"💰 Orçamento de '{category}' definido: R$ {amount:.2f}/mês."

    def orcamentos(self, user_id: str) -> str:
        budgets = self._memory.list_budgets(user_id)
        if not budgets:
            return "Nenhum orçamento. Crie com /orcamento <categoria> <valor>."
        since = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        lines = ["💰 Orçamentos do mês:"]
        for b in budgets:
            spent = self._memory.category_total_since(user_id, b["category"], since)
            pct = spent / b["amount"] * 100 if b["amount"] else 0
            dot = "🔴" if pct >= 100 else "🟡" if pct >= 80 else "🟢"
            lines.append(
                f"{dot} {b['category']}: R$ {spent:.2f} / R$ {b['amount']:.2f} ({pct:.0f}%)"
            )
        lines.append("\nApagar: /orcamentorm <categoria>")
        return "\n".join(lines)

    def orcamentorm(self, user_id: str, argstr: str) -> str:
        cat = argstr.strip().lstrip("#").lower()
        if not cat:
            return "Uso: /orcamentorm <categoria>."
        ok = self._memory.delete_budget(user_id, cat)
        return f"Orçamento de '{cat}' removido." if ok else f"Não achei orçamento pra '{cat}'."

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
        lines = ["✅ Seus hábitos (hoje):"]
        for h in habits:
            done = "[x]" if today_s in self._memory.habit_days(h["id"]) else "[ ]"
            lines.append(f"{done} {h['name']} — sequência: {self._streak(h['id'], today)} dia(s)")
        lines.append("\nMarcar: /feito <nome> · Apagar: /habitorm <nome>")
        return "\n".join(lines)

    def habitorm(self, user_id: str, argstr: str) -> str:
        name = argstr.strip()
        if not name:
            return "Uso: /habitorm <nome>. Ex: /habitorm treino"
        h = self._memory.find_habit(user_id, name)
        if not h:
            return f"Não achei o hábito '{name}'."
        self._memory.delete_habit(user_id, h["id"])
        return f"Hábito '{h['name']}' removido."

    # --- journal ------------------------------------------------------------

    def diario(self, user_id: str, argstr: str) -> str:
        text = argstr.strip()
        if not text:
            entries = self._memory.recent_journal(user_id, 5)
            if not entries:
                return "Diário vazio. Escreva com /diario <texto>."
            lines = ["📔 Últimas entradas do diário:"]
            for e in entries:
                day = ""
                try:
                    day = datetime.fromisoformat(e["created"]).strftime("%d/%m")
                except Exception:
                    pass
                lines.append(f"#{e['id']} [{day}] {e['text']}")
            lines.append("\nApagar: /diariorm <id>")
            return "\n".join(lines)
        self._memory.add_journal(user_id, text)
        return "Anotado no diário."

    def diariorm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /diariorm <id>. Veja os ids em /diario."
        ok = self._memory.delete_journal(user_id, int(arg))
        return f"Entrada #{arg} apagada." if ok else f"Não achei a entrada #{arg}."

    # --- weekly review ------------------------------------------------------

    def semana(self, user_id: str) -> str:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        done = self._memory.tasks_completed_since(user_id, since)
        exp = self._memory.expenses_since(user_id, since)
        total = sum(e["amount"] for e in exp)
        parts = [
            "📊 Sua semana:",
            f"✅ Tarefas concluídas: {done}",
            f"📋 Tarefas em aberto: {len(self._memory.open_tasks(user_id))}",
            f"💰 Gastos (7 dias): R$ {total:.2f} ({len(exp)} lançamentos)",
        ]
        habits = self._memory.list_habits(user_id)
        if habits:
            today = self._now().date()
            parts.append("🔥 Hábitos (sequência):")
            for h in habits:
                parts.append(f"  • {h['name']}: {self._streak(h['id'], today)} dia(s)")
        return "\n".join(parts)

    # --- web watches --------------------------------------------------------

    def vigiar(self, user_id: str, argstr: str) -> str:
        parts = [p.strip() for p in argstr.split("|")]
        url = parts[0].strip()
        keyword = parts[1] if len(parts) > 1 and parts[1] else None
        if not url.lower().startswith("http"):
            return "Uso: /vigiar <url> [| palavra-chave]\nEx: /vigiar https://... | inscrições abertas"
        wid = self._memory.add_watch(user_id, url, keyword)
        extra = (
            f" (te aviso quando aparecer '{keyword}')" if keyword
            else " (te aviso quando a página mudar)"
        )
        return f"👁️ Monitor #{wid} criado{extra}."

    def vigias(self, user_id: str) -> str:
        items = self._memory.list_watches(user_id)
        if not items:
            return "Você não tem monitores. Crie com /vigiar <url> [| palavra]."
        lines = ["👁️ Monitores web:"]
        for w in items:
            k = f" [{w['keyword']}]" if w["keyword"] else ""
            lines.append(f"#{w['id']} {w['url']}{k}")
        lines.append("\nApagar: /vigiarm <id>")
        return "\n".join(lines)

    def vigiarm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /vigiarm <id>. Veja em /vigias."
        ok = self._memory.delete_watch(user_id, int(arg))
        return f"Monitor #{arg} removido." if ok else f"Não achei o monitor #{arg}."

    # --- recurring expenses (subscriptions) --------------------------------

    def assinatura(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if len(tokens) < 2:
            return "Uso: /assinatura <valor> <descrição> [dia] [#categoria]\nEx: /assinatura 39,90 Netflix 15"
        try:
            amount = float(tokens[0].replace(",", "."))
        except ValueError:
            return "Valor inválido. Ex: /assinatura 39,90 Netflix 15"
        rest = tokens[1:]
        category = "assinatura"
        tags = [t for t in rest if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            rest = [t for t in rest if not (t.startswith("#") and len(t) > 1)]
        day = self._now().day
        if rest and rest[-1].isdigit() and 1 <= int(rest[-1]) <= 28:
            day = int(rest[-1])
            rest = rest[:-1]
        desc = " ".join(rest).strip() or "(assinatura)"
        rid = self._memory.add_recurring(user_id, amount, desc, category, day)
        return f"🔁 Assinatura #{rid}: R$ {amount:.2f} em {desc} — lanço todo dia {day}."

    def assinaturas(self, user_id: str) -> str:
        items = self._memory.list_recurring(user_id)
        if not items:
            return "Nenhuma assinatura recorrente. Crie com /assinatura."
        lines = ["🔁 Assinaturas (lançadas sozinhas todo mês):"]
        for r in items:
            lines.append(
                f"#{r['id']} R$ {r['amount']:.2f} {r['description']} — dia {r['day']} ({r['category']})"
            )
        lines.append("\nApagar: /assinaturarm <id>")
        return "\n".join(lines)

    def assinaturarm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /assinaturarm <id>. Veja em /assinaturas."
        ok = self._memory.delete_recurring(user_id, int(arg))
        return f"Assinatura #{arg} removida." if ok else f"Não achei a assinatura #{arg}."

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
        facts = self._memory.list_facts(user_id)
        if not facts:
            return "Ainda não sei nada sobre você. Use /lembrar pra me contar algo."
        lines = ["🧠 O que eu sei sobre você:"]
        lines += [f"#{f['id']} {f['fact']}" for f in facts]
        lines.append("\nApagar: /esquecer <id>")
        return "\n".join(lines)

    def esquecer(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /esquecer <id>. Veja os ids em /memorias."
        ok = self._memory.delete_fact(user_id, int(arg))
        return f"Esqueci a memória #{arg}." if ok else f"Não achei a memória #{arg}."

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

        if self._config.google_authorized():
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
            parts.append(
                tools_mod.news(
                    self._config.news_topic,
                    max_results=3,
                    tavily_key=getattr(self._config, "tavily_api_key", ""),
                )
            )
            tab = tools_mod.tabnews(3)
            if tab:
                parts.append("\nTabNews (tech):")
                parts.append(tab)
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
        lines = [f"🔗 Links{' em ' + category if category else ''}:"]
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
        lines = ["📄 Documentos na base de conhecimento:"]
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
        """Ingest an uploaded document (PDF, Word or plain text) into the KB."""
        if not filename.lower().endswith(knowledge.READABLE_EXTS):
            return "Consigo ler PDF, Word (.docx) e texto (.txt, .md). Manda um desses."
        try:
            stored, truncated = knowledge.ingest_file(
                data, filename, self._config, self._memory, user_id
            )
        except Exception as exc:
            return f"Não consegui ler esse arquivo ({exc})."
        if stored == 0:
            return "Esse arquivo parece não ter texto extraível (talvez seja escaneado/imagem)."
        extra = " (documento grande — indexei o começo)" if truncated else ""
        return f"Documento '{filename}' indexado: {stored} trechos{extra}. Pode me perguntar sobre ele!"

    # --- data export (feature B) -------------------------------------------

    def export_expenses_csv(self, user_id: str, months: int = 6) -> tuple[bytes, str] | str:
        """Build a CSV of the last `months` of expenses. Returns (bytes, name)
        or an error string if there is nothing to export."""
        import csv
        import io as _io

        since = (self._now() - timedelta(days=30 * months)).isoformat()
        rows = self._memory.expenses_since(user_id, since)
        if not rows:
            return "Você ainda não tem gastos registrados nesse período."
        buf = _io.StringIO()
        w = csv.writer(buf)
        w.writerow(["data", "categoria", "valor", "descricao"])
        for e in rows:
            w.writerow([
                (e.get("created") or "")[:10],
                e.get("category", ""),
                f"{e.get('amount', 0):.2f}",
                e.get("description", ""),
            ])
        data = buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows accents
        return data, f"gastos_{self._now().strftime('%Y%m%d')}.csv"

    def data_digest(self, user_id: str) -> tuple[str, str]:
        """Human-readable digest of the user's data. Returns (title, content)."""
        m = self._memory
        lines: list[str] = []

        tasks = m.open_tasks(user_id)
        lines.append(f"TAREFAS EM ABERTO ({len(tasks)})")
        lines += [f"- [{t['category']}] {t['text']}" for t in tasks] or ["- (nenhuma)"]

        facts = m.all_facts(user_id)
        lines.append(f"\nMEMÓRIAS ({len(facts)})")
        lines += [f"- {f}" for f in facts] or ["- (nenhuma)"]

        habits = m.list_habits(user_id)
        lines.append(f"\nHÁBITOS ({len(habits)})")
        lines += [f"- {h['name']}" for h in habits] or ["- (nenhum)"]

        journ = m.recent_journal(user_id, 30)
        lines.append(f"\nDIÁRIO (últimas {len(journ)} entradas)")
        lines += [f"- {e['text']}" for e in journ] or ["- (vazio)"]

        title = f"Meus dados — E.V. ({self._now().strftime('%d/%m/%Y')})"
        return title, "\n".join(lines)

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
