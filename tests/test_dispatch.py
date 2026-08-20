"""Tests for the generic command dispatcher (Commands.run) — the layer the AI's
executar_comando tool calls so E.V. can run any command hands-free."""

from types import SimpleNamespace

from ev.core.commands import Commands
from ev.core.memory import Memory


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="", google_accounts=(),
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
    )
    return Commands(config, Memory(tmp_path / "t.db"))


def test_run_creates_task(tmp_path):
    c = _commands(tmp_path)
    out = c.run("u", "tarefa", "comprar pão #casa")
    assert "added" in out
    assert "comprar pão" in c.run("u", "tarefas", "")


def test_run_logs_expense(tmp_path):
    c = _commands(tmp_path)
    out = c.run("u", "gasto", "50 mercado #casa")
    assert "50" in out
    assert "mercado" in c.run("u", "gastos", "")


def test_run_save_and_forget_memory(tmp_path):
    c = _commands(tmp_path)
    c.run("u", "lembrar", "meu carro é um Civic")
    assert "Civic" in c.run("u", "memorias", "")
    assert "forgot" in c.run("u", "esquecer", "1").lower()


def test_run_strips_leading_slash(tmp_path):
    c = _commands(tmp_path)
    assert "added" in c.run("u", "/tarefa", "estudar")


def test_run_unknown_command(tmp_path):
    c = _commands(tmp_path)
    out = c.run("u", "voar", "")
    assert "don't know" in out.lower()


def test_runnable_lists_core_commands(tmp_path):
    names = _commands(tmp_path).runnable()
    for expected in ("tarefa", "gasto", "habito", "lembrete", "esquecer", "diario"):
        assert expected in names
