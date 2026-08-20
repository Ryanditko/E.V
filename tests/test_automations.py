"""Tests for the deterministic automations engine (pure predicates)."""

from datetime import datetime, timezone

from ev.core import automations as au


def test_time_due():
    now = datetime(2026, 8, 7, 18, 5, tzinfo=timezone.utc)  # a Friday
    daily = {"hour": 18, "minute": 0, "weekday": -1}
    assert au.time_due(daily, now, None) is True            # daily, at/after 18:00
    assert au.time_due(daily, now, "2026-08-07") is False   # already fired today
    assert au.time_due({"hour": 19, "minute": 0, "weekday": -1}, now, None) is False  # too early
    wd = now.weekday()
    assert au.time_due({"hour": 0, "minute": 0, "weekday": wd}, now, None) is True
    assert au.time_due({"hour": 0, "minute": 0, "weekday": (wd + 1) % 7}, now, None) is False


def test_expense_matches():
    assert au.expense_matches({"amount": 200}, {"amount": 250}) is True
    assert au.expense_matches({"amount": 200}, {"amount": 150}) is False
    assert au.expense_matches({"amount": 100, "category": "comida"},
                              {"amount": 150, "category": "lazer"}) is False
    # category match is case-insensitive
    assert au.expense_matches({"amount": 100, "category": "comida"},
                              {"amount": 150, "category": "Comida"}) is True


def test_describe():
    # English is the default language
    a = {"id": 1, "trig": "expense_over", "trig_cfg": {"amount": 200},
         "act": "notify", "act_cfg": {"message": "alto"}, "enabled": True}
    d = au.describe(a)
    assert "200" in d and "warn me" in d
    t = {"id": 2, "trig": "time", "trig_cfg": {"hour": 18, "minute": 0, "weekday": 4},
         "act": "command", "act_cfg": {"command": "semana"}, "enabled": False}
    dt = au.describe(t)
    assert "Friday" in dt and "18:00" in dt and "semana" in dt and "paused" in dt


def test_describe_pt():
    t = {"id": 2, "trig": "time", "trig_cfg": {"hour": 18, "minute": 0, "weekday": 4},
         "act": "command", "act_cfg": {"command": "semana"}, "enabled": False}
    dt = au.describe(t, "pt")
    assert "sexta" in dt and "18:00" in dt and "semana" in dt and "pausada" in dt
