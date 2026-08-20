"""Deterministic slash commands — no LLM involved.

Fast, predictable, and free: these run pure Python against memory and the tool
providers. The Telegram interface maps `/command` to these methods; a terminal
or web interface could reuse them the same way.

E.V.'s replies here are short PT-BR strings (the assistant speaks Portuguese).
"""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from ...config import Config
from ..i18n import DEFAULT_LANG
from ..i18n import t as _t
from ..memory import Memory
from ..timeparse import add_months
from .reminders_calendar import RemindersCalendarMixin
from .tasks import TasksMixin
from .task_editing import TaskEditingMixin
from .search_news_weather import SearchNewsWeatherMixin
from .expenses import ExpensesMixin
from .budgets import BudgetsMixin
from .habits import HabitsMixin
from .journal import JournalMixin
from .weekly_summary import WeeklySummaryMixin
from .watches import WatchesMixin
from .subscriptions import SubscriptionsMixin
from .long_term_memory import LongTermMemoryMixin
from .overview import OverviewMixin
from .automations import AutomationsMixin
from .links import LinksMixin
from .kb_docs import KbDocsMixin
from .google_integration import GoogleIntegrationMixin
from .people import PeopleMixin

# Canonical command table: (en_name, pt_name, en_desc, pt_desc).
# Every command has an English name and a Portuguese name — both dispatch to the
# same method (see _dispatch), so PT names keep working (non-breaking). When the
# English and Portuguese names are identical (already-English/universal words like
# menu, backup, kb) the two name fields simply match. Used to populate the
# localized command menu (Telegram/web) via command_list(lang).
_COMMANDS: list[tuple[str, str, str, str]] = [
    ("focus", "modo",
     "Toggle FOCUS MODE (red interface, tactical tone)",
     "Liga/desliga o MODO FOCO (interface vermelha, tom tático)"),
    ("menu", "menu",
     "Open the interactive menu with buttons",
     "Abre o menu interativo com botões"),
    ("ev", "ev",
     "Talk to the AI (useful in groups): /ev your message",
     "Falar com a IA (útil em grupos): /ev sua mensagem"),
    ("plan", "plano",
     "Sort my morning: today's plan (tasks + calendar + weather)",
     "Resolve minha manhã: plano do dia (tarefas + agenda + clima)"),
    ("pending", "pendencias",
     "What's overdue/due — E.V. nudges you",
     "O que está atrasado/vencendo — a E.V. te cobra"),
    ("backup", "backup",
     "Send an encrypted DB backup now (off the VM)",
     "Envia agora um backup cifrado do banco (fora da VM)"),
    ("patterns", "padroes",
     "What E.V. has learned about your patterns",
     "O que a E.V. aprendeu sobre seus padrões"),
    ("automations", "automacoes",
     "Your 'when X, do Y' automations",
     "Suas automações 'quando X, faça Y'"),
    ("automationrm", "automacaorm",
     "Delete an automation: /automationrm <id>",
     "Apaga uma automação: /automacaorm <id>"),
    ("help", "ajuda",
     "List available commands",
     "Lista os comandos disponíveis"),
    ("status", "status",
     "Diagnostics: VM, database, API keys",
     "Diagnóstico: VM, banco, chaves de API"),
    ("mute", "silenciar",
     "Do not disturb: /mute 2h (or off)",
     "Não perturbe: /silenciar 2h (ou off)"),
    ("data", "dados",
     "View/delete your stored data (by category or all)",
     "Ver/apagar seus dados guardados (por categoria ou tudo)"),
    ("clear", "limpar",
     "Clear the conversation (keeps memories and the rest)",
     "Limpar a conversa (mantém memórias e o resto)"),
    ("clearchat", "limparchat",
     "Delete chat bubbles: /clearchat 10 or /clearchat all",
     "Apagar bolhas do chat: /limparchat 10 ou /limparchat tudo"),
    ("summarize", "resumir",
     "Summarize a link: /summarize https://...",
     "Resumir um link: /resumir https://..."),
    ("pomodoro", "foco",
     "Pomodoro: /pomodoro 25 5 (buttons ⏹️/➕/➖) · /pomodoro stop",
     "Pomodoro: /foco 25 5 (botões ⏹️/➕/➖) · /foco parar"),
    ("remind", "lembrete",
     "Create reminder: /remind 10m drink water",
     "Criar lembrete: /lembrete 10m tomar água"),
    ("routine", "rotina",
     "Recurring: /routine daily|weekly|monthly [day] HH:MM text",
     "Recorrente: /rotina diario|semanal|mensal [dia] HH:MM texto"),
    ("reminders", "lembretes",
     "List your reminders",
     "Listar seus lembretes"),
    ("cancel", "cancelar",
     "Cancel reminder: /cancel 3",
     "Cancelar lembrete: /cancelar 3"),
    ("calendar", "calendario",
     "View your day's calendar (reminders + Google)",
     "Ver sua agenda por dia (lembretes + Google)"),
    ("news", "noticias",
     "Latest news with sources: /news technology",
     "Últimas notícias com fontes: /noticias tecnologia"),
    ("task", "tarefa",
     "Add task: /task study #college",
     "Adicionar tarefa: /tarefa estudar #faculdade"),
    ("tasks", "tarefas",
     "List tasks: /tasks [category]",
     "Listar tarefas: /tarefas [categoria]"),
    ("complete", "concluir",
     "Complete task: /complete 3",
     "Concluir tarefa: /concluir 3"),
    ("search", "buscar",
     "Search the web: /search today's news",
     "Pesquisar na web: /buscar notícias de hoje"),
    ("find", "procurar",
     "Search YOUR data: /find calculus",
     "Procurar nos SEUS dados: /procurar cálculo"),
    ("weather", "clima",
     "Weather forecast: /weather São Paulo",
     "Previsão do tempo: /clima São Paulo"),
    ("expense", "gasto",
     "Log expense: /expense 50 groceries #home",
     "Registrar gasto: /gasto 50 mercado #casa"),
    ("expenses", "gastos",
     "This month's expense summary",
     "Resumo de gastos do mês"),
    ("expenserm", "gastorm",
     "Delete expense: /expenserm 3",
     "Apagar gasto: /gastorm 3"),
    ("budget", "orcamento",
     "Set budget: /budget food 800",
     "Definir orçamento: /orcamento comida 800"),
    ("budgets", "orcamentos",
     "See budgets and how much you've spent",
     "Ver orçamentos e quanto já gastou"),
    ("budgetrm", "orcamentorm",
     "Delete budget: /budgetrm food",
     "Apagar orçamento: /orcamentorm comida"),
    ("report", "relatorio",
     "Financial report for the current month",
     "Relatório financeiro do mês atual"),
    ("quiz", "quiz",
     "Study: question about your PDFs (/quiz [document])",
     "Estudar: pergunta sobre seus PDFs (/quiz [documento])"),
    ("insights", "insights",
     "Insights from your week (AI)",
     "Insights da sua semana (IA)"),
    ("model", "modelo",
     "View/switch the main model (Gemini) and today's usage",
     "Ver/trocar o modelo principal (Gemini) e uso do dia"),
    ("provider", "provedor",
     "Force/test a provider: /provider groq (or auto)",
     "Forçar/testar um provedor: /provedor groq (ou auto)"),
    ("language", "idioma",
     "E.V.'s language (replies and speech): /language en or /language pt",
     "Idioma da E.V. (responde e fala): /idioma en ou /idioma pt"),
    ("habit", "habito",
     "Create habit: /habit workout",
     "Criar hábito: /habito treino"),
    ("done", "feito",
     "Mark habit done today: /done workout",
     "Marcar hábito feito hoje: /feito treino"),
    ("habits", "habitos",
     "See habits and streaks",
     "Ver hábitos e sequências"),
    ("habitrm", "habitorm",
     "Delete habit: /habitrm workout",
     "Apagar hábito: /habitorm treino"),
    ("journal", "diario",
     "Write/view journal: /journal today was good",
     "Escrever/ver diário: /diario hoje foi bom"),
    ("journalrm", "diariorm",
     "Delete journal entry: /journalrm 3",
     "Apagar entrada do diário: /diariorm 3"),
    ("week", "semana",
     "Review of your week (also arrives automatically)",
     "Revisão da sua semana (também chega automática)"),
    ("watch", "vigiar",
     "Monitor a page: /watch https://... | keyword",
     "Monitorar página: /vigiar https://... | palavra"),
    ("watches", "vigias",
     "See web monitors",
     "Ver monitores web"),
    ("watchrm", "vigiarm",
     "Delete monitor: /watchrm 3",
     "Apagar monitor: /vigiarm 3"),
    ("subscription", "assinatura",
     "Recurring expense: /subscription 39,90 Netflix 15",
     "Gasto recorrente: /assinatura 39,90 Netflix 15"),
    ("subscriptions", "assinaturas",
     "See recurring subscriptions",
     "Ver assinaturas recorrentes"),
    ("subscriptionrm", "assinaturarm",
     "Delete subscription: /subscriptionrm 3",
     "Apagar assinatura: /assinaturarm 3"),
    ("remember", "lembrar",
     "Save to memory: /remember my car is a Civic",
     "Salvar na memória: /lembrar meu carro é um Civic"),
    ("memories", "memorias",
     "List what E.V. knows about you",
     "Listar o que a E.V. sabe sobre você"),
    ("forget", "esquecer",
     "Delete a memory: /forget 3",
     "Apagar uma memória: /esquecer 3"),
    ("link", "link",
     "Save link: /link college | tasks | http://...",
     "Guardar link: /link faculdade | tarefas | http://..."),
    ("links", "links",
     "List links: /links [category]",
     "Listar links: /links [categoria]"),
    ("linkrm", "linkrm",
     "Remove link: /linkrm 3",
     "Remover link: /linkrm 3"),
    ("kb", "kb",
     "Knowledge base (send a PDF to add)",
     "Base de conhecimento (envie um PDF para adicionar)"),
    ("kbweb", "kbweb",
     "Index a web page: /kbweb https://...",
     "Indexar uma página web: /kbweb https://..."),
    ("kbrm", "kbrm",
     "Remove a document from the base: /kbrm name.pdf",
     "Remover documento da base: /kbrm nome.pdf"),
    ("document", "documento",
     "Create a file: /document pdf Title | content",
     "Criar arquivo: /documento pdf Título | conteúdo"),
    ("export", "exportar",
     "Export data: /export expenses (CSV) or /export data (PDF)",
     "Exportar dados: /exportar gastos (CSV) ou /exportar dados (PDF)"),
    ("transcribe", "transcrever",
     "Transcribe audio to text (send the audio after)",
     "Transcrever áudio em texto (manda o áudio depois)"),
    ("gcal", "agenda",
     "Google Calendar: /gcal [account]",
     "Agenda do Google: /agenda [conta]"),
    ("event", "evento",
     "Create event: /event [account] tomorrow 15:00 Dentist",
     "Criar evento: /evento [conta] amanhã 15:00 Dentista"),
    ("email", "email",
     "Email: /email [account] someone@x.com | Subject | Body",
     "E-mail: /email [conta] fulano@x.com | Assunto | Corpo"),
    ("emails", "emails",
     "See recent emails: /emails [account] [search]",
     "Ver e-mails recentes: /emails [conta] [busca]"),
    ("people", "pessoas",
     "See people you've saved (with birthdays)",
     "Ver pessoas que você registrou (com aniversários)"),
    ("person", "pessoa",
     "Note/view a person: /person Ana | sister, loves coffee | 12/03",
     "Anotar/ver pessoa: /pessoa Ana | irmã, ama café | 12/03"),
]

# English alias -> Portuguese (canonical) name, for every command in the menu
# whose two names differ. Extended below with dispatch-only commands (the *rm /
# *editar variants the AI can run but that don't appear in the menu).
_EN_TO_PT: dict[str, str] = {en: pt for en, pt, _, _ in _COMMANDS if en != pt}
_EN_TO_PT.update({
    "taskrm": "tarefarm",
    "taskedit": "tarefaeditar",
    "remindedit": "lembreteeditar",
    "expenseedit": "gastoeditar",
})


def command_list(lang: str = DEFAULT_LANG) -> list[tuple[str, str]]:
    """(name, description) pairs for the command menu in the given language.

    Returns the English name+description when ``lang == "en"`` and the
    Portuguese name+description otherwise. Used to populate Telegram's command
    menu and the web command palette."""
    if lang == "pt":
        return [(pt, pt_desc) for _, pt, _, pt_desc in _COMMANDS]
    return [(en, en_desc) for en, _, en_desc, _ in _COMMANDS]


# Backward-compatible export (English menu). Prefer command_list(lang).
COMMAND_LIST = command_list(DEFAULT_LANG)


class Commands(
    RemindersCalendarMixin,
    TasksMixin,
    TaskEditingMixin,
    SearchNewsWeatherMixin,
    ExpensesMixin,
    BudgetsMixin,
    HabitsMixin,
    JournalMixin,
    WeeklySummaryMixin,
    WatchesMixin,
    SubscriptionsMixin,
    LongTermMemoryMixin,
    OverviewMixin,
    AutomationsMixin,
    LinksMixin,
    KbDocsMixin,
    GoogleIntegrationMixin,
    PeopleMixin,
):
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

    def _month_bounds(self, offset: int = 0) -> tuple[str, str, str]:
        """Boundaries of a calendar month in the user's LOCAL timezone, returned as
        UTC ISO strings for querying (expenses are stored in UTC). offset 0 = current
        month, -1 = previous. Returns (label 'MM/YYYY', start_iso_utc, end_iso_utc)."""
        first = self._now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if offset:
            first = add_months(first, offset)
        nxt = add_months(first, 1)

        def _utc(dt: datetime) -> str:
            return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).isoformat()

        return first.strftime("%m/%Y"), _utc(first), _utc(nxt)

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

    @staticmethod
    def _pick(items, arg, textkey, label, lang=DEFAULT_LANG):
        """Find one item by id or by a case-insensitive substring of `textkey`.
        Returns (item|None, error_msg|None). Lets voice/chat act by name."""
        arg = (arg or "").strip().lstrip("#")
        if arg.isdigit():
            for it in items:
                if it.get("id") == int(arg):
                    return it, None
            return None, _t(lang, "pick.not_found_id", label=label, arg=arg)
        if not arg:
            return None, _t(lang, "pick.need_name", label=label)
        low = arg.lower()
        matches = [it for it in items if low in str(it.get(textkey, "")).lower()]
        if not matches:
            return None, _t(lang, "pick.not_found_name", label=label, arg=arg)
        if len(matches) > 1:
            opts = ", ".join(f"#{it['id']} {str(it.get(textkey, ''))[:30]}" for it in matches[:6])
            return None, _t(lang, "pick.ambiguous", opts=opts)
        return matches[0], None

    # --- help ---------------------------------------------------------------

    def help(self) -> str:
        return _t(self._memory.assistant_lang(), "help.text")

    # --- generic dispatcher (lets the AI run any command hands-free) --------

    def _dispatch(self) -> dict:
        """name -> callable(user_id, argstr) for every command the AI can run
        on the user's behalf (voice/text). Interface-only commands (documento,
        exportar, status, foco, silenciar, limpar*, dados) are handled elsewhere."""
        d = {
            "modo": lambda u, a: self.modo(u, a),
            "tarefa": lambda u, a: self.tarefa(u, a),
            "tarefas": lambda u, a: self.tarefas(u, a),
            "concluir": lambda u, a: self.concluir(u, a),
            "tarefarm": lambda u, a: self.tarefarm(u, a),
            "tarefaeditar": lambda u, a: self.tarefaeditar(u, a),
            "lembrete": lambda u, a: self.lembrete(u, a),
            "lembretes": lambda u, a: self.lembretes(u),
            "rotina": lambda u, a: self.rotina(u, a),
            "cancelar": lambda u, a: self.cancelar(u, a),
            "lembreteeditar": lambda u, a: self.lembreteeditar(u, a),
            "calendario": lambda u, a: self.calendario(u),
            "lembrar": lambda u, a: self.lembrar(u, a),
            "memorias": lambda u, a: self.memorias(u),
            "esquecer": lambda u, a: self.esquecer(u, a),
            "gasto": lambda u, a: self.gasto(u, a),
            "gastos": lambda u, a: self.gastos(u),
            "gastorm": lambda u, a: self.gastorm(u, a),
            "gastoeditar": lambda u, a: self.gastoeditar(u, a),
            "orcamento": lambda u, a: self.orcamento(u, a),
            "orcamentos": lambda u, a: self.orcamentos(u),
            "orcamentorm": lambda u, a: self.orcamentorm(u, a),
            "relatorio": lambda u, a: self.relatorio(u),
            "habito": lambda u, a: self.habito(u, a),
            "feito": lambda u, a: self.feito(u, a),
            "habitos": lambda u, a: self.habitos(u),
            "habitorm": lambda u, a: self.habitorm(u, a),
            "diario": lambda u, a: self.diario(u, a),
            "diariorm": lambda u, a: self.diariorm(u, a),
            "link": lambda u, a: self.link(u, a),
            "links": lambda u, a: self.links(u, a),
            "linkrm": lambda u, a: self.linkrm(u, a),
            "procurar": lambda u, a: self.procurar(u, a),
            "buscar": lambda u, a: self.buscar(a),
            "noticias": lambda u, a: self.noticias(a),
            "clima": lambda u, a: self.clima(a),
            "kb": lambda u, a: self.kb(u),
            "kbrm": lambda u, a: self.kbrm(u, a),
            "kbweb": lambda u, a: self.kbweb(u, a),
            "semana": lambda u, a: self.semana(u),
            "vigiar": lambda u, a: self.vigiar(u, a),
            "vigias": lambda u, a: self.vigias(u),
            "vigiarm": lambda u, a: self.vigiarm(u, a),
            "assinatura": lambda u, a: self.assinatura(u, a),
            "assinaturas": lambda u, a: self.assinaturas(u),
            "assinaturarm": lambda u, a: self.assinaturarm(u, a),
            "agenda": lambda u, a: self.agenda(a),
            "evento": lambda u, a: self.evento(a),
            "email": lambda u, a: self.email(a),
            "emails": lambda u, a: self.emails(a),
            "pessoa": lambda u, a: self.pessoa(u, a),
            "pessoas": lambda u, a: self.pessoas(u),
        }
        # Add English aliases -> same callable (PT names keep working).
        for en, pt in _EN_TO_PT.items():
            if pt in d:
                d.setdefault(en, d[pt])
        return d

    def runnable(self) -> list[str]:
        return sorted(self._dispatch())

    def run(self, user_id: str, name: str, argstr: str = "") -> str:
        """Run a command by name (as if the user typed /name argstr)."""
        lang = self._memory.assistant_lang()
        key = (name or "").strip().lower().lstrip("/")
        fn = self._dispatch().get(key)
        if not fn:
            return _t(lang, "cmd.unknown", name=name, cmds=", ".join(self.runnable()))
        try:
            return fn(user_id, argstr or "")
        except Exception as exc:  # never crash the chat turn
            return _t(lang, "cmd.error", key=key, exc=exc)
