"""Tests for the deterministic command layer (no LLM, no network)."""

from types import SimpleNamespace

from ev.core.commands import Commands
from ev.core.memory import Memory


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="",
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
