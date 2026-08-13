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

from ...config import Config
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

# (command, description) — also used to populate Telegram's command menu.
COMMAND_LIST = [
    ("modo", "Liga/desliga o MODO FOCO (interface vermelha, tom tático)"),
    ("menu", "Abre o menu interativo com botões"),
    ("ev", "Falar com a IA (útil em grupos): /ev sua mensagem"),
    ("plano", "Resolve minha manhã: plano do dia (tarefas + agenda + clima)"),
    ("pendencias", "O que está atrasado/vencendo — a E.V. te cobra"),
    ("backup", "Envia agora um backup cifrado do banco (fora da VM)"),
    ("padroes", "O que a E.V. aprendeu sobre seus padrões"),
    ("automacoes", "Suas automações 'quando X, faça Y'"),
    ("automacaorm", "Apaga uma automação: /automacaorm <id>"),
    ("ajuda", "Lista os comandos disponíveis"),
    ("status", "Diagnóstico: VM, banco, chaves de API"),
    ("silenciar", "Não perturbe: /silenciar 2h (ou off)"),
    ("dados", "Ver/apagar seus dados guardados (por categoria ou tudo)"),
    ("limpar", "Limpar a conversa (mantém memórias e o resto)"),
    ("limparchat", "Apagar bolhas do chat: /limparchat 10 ou /limparchat tudo"),
    ("resumir", "Resumir um link: /resumir https://..."),
    ("foco", "Pomodoro: /foco 25 5 (botões ⏹️/➕/➖) · /foco parar"),
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
    ("relatorio", "Relatório financeiro do mês atual"),
    ("quiz", "Estudar: pergunta sobre seus PDFs (/quiz [documento])"),
    ("insights", "Insights da sua semana (IA)"),
    ("modelo", "Ver/trocar o modelo principal (Gemini) e uso do dia"),
    ("provedor", "Forçar/testar um provedor: /provedor groq (ou auto)"),
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
    ("emails", "Ver e-mails recentes: /emails [conta] [busca]"),
    ("pessoas", "Ver pessoas que você registrou (com aniversários)"),
    ("pessoa", "Anotar/ver pessoa: /pessoa Ana | irmã, ama café | 12/03"),
]


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
    def _pick(items, arg, textkey, label):
        """Find one item by id or by a case-insensitive substring of `textkey`.
        Returns (item|None, error_msg|None). Lets voice/chat act by name."""
        arg = (arg or "").strip().lstrip("#")
        if arg.isdigit():
            for it in items:
                if it.get("id") == int(arg):
                    return it, None
            return None, f"Não achei {label} #{arg}."
        if not arg:
            return None, f"Preciso do nome ou número ({label})."
        low = arg.lower()
        matches = [it for it in items if low in str(it.get(textkey, "")).lower()]
        if not matches:
            return None, f"Não achei {label} com \"{arg}\"."
        if len(matches) > 1:
            opts = ", ".join(f"#{it['id']} {str(it.get(textkey, ''))[:30]}" for it in matches[:6])
            return None, f"Achei mais de um parecido: {opts}. Qual? (me diz o número)"
        return matches[0], None

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

    # --- generic dispatcher (lets the AI run any command hands-free) --------

    def _dispatch(self) -> dict:
        """name -> callable(user_id, argstr) for every command the AI can run
        on the user's behalf (voice/text). Interface-only commands (documento,
        exportar, status, foco, silenciar, limpar*, dados) are handled elsewhere."""
        return {
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

    def runnable(self) -> list[str]:
        return sorted(self._dispatch())

    def run(self, user_id: str, name: str, argstr: str = "") -> str:
        """Run a command by name (as if the user typed /name argstr)."""
        key = (name or "").strip().lower().lstrip("/")
        fn = self._dispatch().get(key)
        if not fn:
            return (f"Não conheço o comando '{name}'. Comandos que posso executar: "
                    + ", ".join(self.runnable()))
        try:
            return fn(user_id, argstr or "")
        except Exception as exc:  # never crash the chat turn
            return f"Erro ao executar {key}: {exc}"
