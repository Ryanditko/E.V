"""Tests for Telegram helper utilities (message splitting)."""

from ev.interfaces.telegram_bot import TelegramInterface


def test_split_short():
    assert TelegramInterface._split("oi") == ["oi"]


def test_split_respects_limit():
    text = "\n".join(f"linha {i}" for i in range(500))
    parts = TelegramInterface._split(text, limit=200)
    assert all(len(p) <= 200 for p in parts)
    assert len(parts) > 1


def test_split_long_single_line():
    parts = TelegramInterface._split("x" * 5000, limit=1000)
    assert all(len(p) <= 1000 for p in parts)
    assert "".join(parts) == "x" * 5000
