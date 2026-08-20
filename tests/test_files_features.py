"""Tests for the file-related features: monthly reminders, text extraction,
data export."""

from datetime import datetime
from types import SimpleNamespace

from ev.core import knowledge
from ev.core.commands import Commands
from ev.core.memory import Memory
from ev.core.timeparse import add_months
from ev.providers import documents


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="", google_accounts=(),
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
    )
    return Commands(config, Memory(tmp_path / "t.db"))


# --- monthly recurrence -----------------------------------------------------

def test_add_months_clamps_end_of_month():
    jan31 = datetime(2026, 1, 31, 9, 0)
    assert add_months(jan31, 1) == datetime(2026, 2, 28, 9, 0)
    assert add_months(jan31, 12) == datetime(2027, 1, 31, 9, 0)


def test_add_months_crosses_year():
    assert add_months(datetime(2026, 12, 10, 8, 0), 1) == datetime(2027, 1, 10, 8, 0)


def test_rotina_monthly(tmp_path):
    c = _commands(tmp_path)
    out = c.rotina("u", "mensal 5 10:00 pagar aluguel")
    assert "every 5" in out
    rems = c._memory.open_reminders("u")
    assert rems and rems[0]["recur"] == "monthly"
    assert datetime.fromisoformat(rems[0]["when_iso"]).day == 5


def test_rotina_monthly_requires_day(tmp_path):
    c = _commands(tmp_path)
    assert "monthly" in c.rotina("u", "mensal 10:00 texto").lower()


def test_rotina_still_supports_daily(tmp_path):
    c = _commands(tmp_path)
    assert "every day" in c.rotina("u", "diario 08:00 remédio")


# --- text extraction (feature A) --------------------------------------------

def test_extract_text_from_txt():
    assert "olá mundo" in knowledge.extract_text("olá mundo".encode("utf-8"), "n.txt")


def test_extract_text_from_docx_roundtrip():
    data, _ = documents.build("docx", "Título", "primeira linha\nsegunda linha")
    text = knowledge.extract_text(data, "arquivo.docx")
    assert "primeira linha" in text and "segunda linha" in text


# --- export (feature B) -----------------------------------------------------

def test_export_expenses_csv(tmp_path):
    c = _commands(tmp_path)
    c._memory.add_expense("u", 50.0, "mercado", "casa")
    res = c.export_expenses_csv("u")
    assert isinstance(res, tuple)
    data, name = res
    text = data.decode("utf-8-sig")
    assert name.endswith(".csv")
    assert "categoria" in text and "mercado" in text and "50.00" in text


def test_export_expenses_csv_empty(tmp_path):
    c = _commands(tmp_path)
    assert isinstance(c.export_expenses_csv("u"), str)


def test_data_digest(tmp_path):
    c = _commands(tmp_path)
    c._memory.add_task("u", "estudar", "faculdade")
    c._memory.add_fact("u", "gosto de café")
    title, content = c.data_digest("u")
    assert "My data" in title
    assert "estudar" in content and "café" in content
