"""Tests for health/diagnostics helpers and quiet-hours duration parsing."""

from types import SimpleNamespace

from ev.core import health
from ev.core.memory import Memory
from ev.interfaces.telegram_bot import TelegramInterface


def _config(tmp_path):
    return SimpleNamespace(
        db_path=tmp_path / "t.db",
        telegram_token="tok",
        gemini_api_key="g",
        groq_api_key="q",
        openrouter_api_key="",
        tavily_api_key="",
        brave_api_key="",
        ollama_enabled=False,
        google_ready=lambda: False,
        google_authorized=lambda account=None: False,
    )


def test_system_report(tmp_path):
    cfg = _config(tmp_path)
    mem = Memory(cfg.db_path)
    rep = health.system_report(cfg, mem)
    assert rep["db_ok"] is True
    assert rep["db_query_ok"] is True
    assert "disk_used_pct" in rep


def test_keys_status(tmp_path):
    keys = health.keys_status(_config(tmp_path))
    by = {k["name"].split(" ")[0]: k for k in keys}
    assert by["Gemini"]["ok"] is True
    assert by["OpenRouter"]["ok"] is False
    assert by["Tavily"]["note"] == "opcional"
    assert by["Google"]["ok"] is False


def test_parse_duration():
    assert TelegramInterface._parse_duration("2h") == 7200
    assert TelegramInterface._parse_duration("30m") == 1800
    assert TelegramInterface._parse_duration("1d") == 86400
    assert TelegramInterface._parse_duration("xyz") is None


def test_parse_count():
    assert TelegramInterface._parse_count("") == 30        # default
    assert TelegramInterface._parse_count("10") == 10
    assert TelegramInterface._parse_count("999") == 100    # capped
    assert TelegramInterface._parse_count("0") == 1        # floored
    assert TelegramInterface._parse_count("abc") is None
