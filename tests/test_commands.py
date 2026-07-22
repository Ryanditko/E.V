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
