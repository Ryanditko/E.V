"""Tests for storage-control methods (view/clear user data)."""

import pytest

from ev.core.memory import Memory


def _mem(tmp_path):
    return Memory(tmp_path / "t.db")


def test_count_and_clear_table(tmp_path):
    m = _mem(tmp_path)
    m.add_fact("u", "gosto de café")
    m.add_fact("u", "moro em SP")
    assert m.count_rows("facts", "u") == 2
    assert m.clear_table("facts", "u") == 2
    assert m.count_rows("facts", "u") == 0


def test_clear_table_is_per_user(tmp_path):
    m = _mem(tmp_path)
    m.add_fact("u", "x")
    m.add_fact("outro", "y")
    m.clear_table("facts", "u")
    assert m.count_rows("facts", "u") == 0
    assert m.count_rows("facts", "outro") == 1


def test_clear_habits_cascades_logs(tmp_path):
    m = _mem(tmp_path)
    hid = m.add_habit("u", "treino")
    m.log_habit(hid, "2026-07-24")
    assert m.habit_days(hid) == {"2026-07-24"}
    m.clear_table("habits", "u")
    assert m.count_rows("habits", "u") == 0
    assert m.habit_days(hid) == set()  # logs gone too


def test_storage_summary(tmp_path):
    m = _mem(tmp_path)
    m.add_task("u", "estudar")
    m.add_message("u", "user", "oi")
    summ = {s["key"]: s["count"] for s in m.storage_summary("u")}
    assert summ["tasks"] == 1
    assert summ["messages"] == 1
    assert summ["facts"] == 0


def test_clear_all_user_data(tmp_path):
    m = _mem(tmp_path)
    m.add_fact("u", "x")
    m.add_task("u", "y")
    m.add_message("u", "user", "z")
    total = m.clear_all_user_data("u")
    assert total == 3
    assert all(s["count"] == 0 for s in m.storage_summary("u"))


def test_delete_fact_by_id(tmp_path):
    # Primitives behind the AI's apagar_memoria tool.
    m = _mem(tmp_path)
    m.add_fact("u", "meu id do sistema X é 123")
    m.add_fact("u", "gosto de café")
    facts = m.list_facts("u")
    assert {f["fact"] for f in facts} and all("id" in f for f in facts)
    target = next(f["id"] for f in facts if "123" in f["fact"])
    assert m.delete_fact("u", target) is True
    assert m.delete_fact("u", 99999) is False
    remaining = [f["fact"] for f in m.list_facts("u")]
    assert remaining == ["gosto de café"]


def test_cancel_reminder_by_id(tmp_path):
    # Primitive behind the AI's apagar_lembrete tool.
    m = _mem(tmp_path)
    rid = m.add_reminder("u", "pagar conta", None)
    assert m.cancel_reminder("u", rid) is True
    assert m.cancel_reminder("u", rid) is False


def test_unknown_table_rejected(tmp_path):
    m = _mem(tmp_path)
    with pytest.raises(ValueError):
        m.count_rows("usage_log", "u")
    with pytest.raises(ValueError):
        m.clear_table("settings; DROP TABLE facts", "u")
