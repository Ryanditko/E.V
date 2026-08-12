"""Tests for web-search recency detection and date formatting."""

from ev.providers import tools


def test_looks_recent_detects_current_queries():
    assert tools._looks_recent("notícias de tecnologia hoje")
    assert tools._looks_recent("cotação do dólar agora")
    assert tools._looks_recent("o que aconteceu em 2026")


def test_looks_recent_false_for_evergreen():
    assert not tools._looks_recent("como fazer pão caseiro")
    assert not tools._looks_recent("capital da França")


def test_fmt_pubdate():
    assert tools._fmt_pubdate("Thu, 23 Jul 2026 01:00:00 GMT") == "23/07/2026 · "
    assert tools._fmt_pubdate("") == ""
    assert tools._fmt_pubdate("lixo") == ""
