"""Tests for the deterministic command layer (no LLM, no network)."""

from types import SimpleNamespace

from ev.core.commands import Commands
from ev.core.memory import Memory


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="",
        google_accounts=(),
        gemini_api_key="x",
        embed_backend="gemini",
        embed_model="m",
    )
    return Commands(config, Memory(tmp_path / "t.db"))


def test_task_flow(tmp_path):
    c = _commands(tmp_path)
    assert "adicionada" in c.tarefa("u", "comprar pão")
    assert "comprar pão" in c.tarefas("u")
    assert "concluída" in c.concluir("u", "1")
    assert "vazia" in c.tarefas("u")


def test_task_category(tmp_path):
    c = _commands(tmp_path)
    out = c.tarefa("u", "estudar cálculo #faculdade")
    assert "faculdade" in out
    listing = c.tarefas("u", "faculdade")
    assert "estudar cálculo" in listing
    assert "#faculdade" not in listing  # tag stripped from the stored text
    assert "Nenhuma" in c.tarefas("u", "trabalho")


def test_buscar_usage(tmp_path):
    c = _commands(tmp_path)
    assert "Uso:" in c.buscar("")


def test_expenses(tmp_path):
    c = _commands(tmp_path)
    assert "50.00" in c.gasto("u", "50 mercado #casa")
    c.gasto("u", "20,50 uber")
    out = c.gastos("u")
    assert "70.50" in out and "casa" in out


def test_habits(tmp_path):
    c = _commands(tmp_path)
    assert "criado" in c.habito("u", "treino")
    assert "já existe" in c.habito("u", "treino")
    assert "feito hoje" in c.feito("u", "treino")
    assert "Sequência: 1" in c.feito("u", "treino")  # already marked today
    assert "[x] treino" in c.habitos("u")


def test_journal(tmp_path):
    c = _commands(tmp_path)
    assert "vazio" in c.diario("u", "")
    assert "Anotado" in c.diario("u", "hoje foi um bom dia")
    assert "bom dia" in c.diario("u", "")


def test_weekly_review(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "estudar")
    c.concluir("u", "1")
    c.gasto("u", "30 mercado")
    out = c.semana("u")
    assert "Sua semana" in out
    assert "concluídas: 1" in out


def test_monthly_report(tmp_path):
    c = _commands(tmp_path)
    # No expenses last month -> friendly message
    out = c.relatorio("u")
    assert "Relatório" in out
    # An expense created "now" is in the current month, not last month, so the
    # previous-month report stays empty — that's the correct behavior.
    c.gasto("u", "50 mercado #comida")
    assert "Relatório" in c.relatorio("u")


def test_watches(tmp_path):
    c = _commands(tmp_path)
    assert "criado" in c.vigiar("u", "https://exemplo.com | vaga aberta")
    assert "exemplo.com" in c.vigias("u")
    assert "removido" in c.vigiarm("u", "1")


def test_budget_alert(tmp_path):
    c = _commands(tmp_path)
    assert "definido" in c.orcamento("u", "comida 100")
    warn = c.gasto("u", "85 mercado #comida")  # 85% of the limit
    assert "orçamento" in warn.lower()
    assert "comida" in c.orcamentos("u")
    assert "removido" in c.orcamentorm("u", "comida")


def test_recurring_expense(tmp_path):
    c = _commands(tmp_path)
    out = c.assinatura("u", "39,90 Netflix 15")
    assert "Netflix" in out and "dia 15" in out
    assert "Netflix" in c.assinaturas("u")
    assert "removida" in c.assinaturarm("u", "1")


def test_delete_operations(tmp_path):
    c = _commands(tmp_path)
    c._memory.add_fact("u", "gosto de café")
    assert "#1" in c.memorias("u")
    assert "Esqueci" in c.esquecer("u", "1")
    assert "não achei" in c.esquecer("u", "1").lower()

    c.gasto("u", "10 pão")
    assert "apagado" in c.gastorm("u", "1")

    c.habito("u", "treino")
    assert "removido" in c.habitorm("u", "treino")

    c.diario("u", "entrada teste")
    assert "apagada" in c.diariorm("u", "1")


def test_reminder_command(tmp_path):
    c = _commands(tmp_path)
    out = c.lembrete("u", "10m tomar água")
    assert "criado" in out
    assert "tomar água" in c.lembretes("u")


def test_link_flow(tmp_path):
    c = _commands(tmp_path)
    assert "salvo" in c.link("u", "faculdade | grade | http://x")
    listing = c.links("u", "")
    assert "grade" in listing and "faculdade" in listing


def test_google_disabled(tmp_path):
    c = _commands(tmp_path)
    assert "não configurada" in c.agenda()
    assert "não configurado" in c.email("a@b.com | oi | teste")


def test_bad_input(tmp_path):
    c = _commands(tmp_path)
    assert "Uso:" in c.tarefa("u", "")
    assert "horário" in c.lembrete("u", "sem tempo aqui")


def test_resolve_account(tmp_path):
    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="x",
        google_accounts=("pessoal", "faculdade"),
        gemini_api_key="x",
        embed_backend="gemini",
        embed_model="m",
    )
    c = Commands(cfg, Memory(tmp_path / "t.db"))
    assert c._resolve_account("faculdade oi tudo bem") == ("faculdade", "oi tudo bem")
    assert c._resolve_account("oi tudo bem") == ("pessoal", "oi tudo bem")


def test_cancel_reminder(tmp_path):
    c = _commands(tmp_path)
    c.lembrete("u", "10m tomar água")
    assert "cancelado" in c.cancelar("u", "1")
    assert "não achei" in c.cancelar("u", "1").lower()


def test_rotina(tmp_path):
    c = _commands(tmp_path)
    out = c.rotina("u", "diario 08:00 tomar remédio")
    assert "Rotina" in out and "todo dia" in out
    assert "[todo dia]" in c.lembretes("u")
    assert "inválida" in c.rotina("u", "mensal 08:00 x").lower()
