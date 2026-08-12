"""Tests for the SQLite memory layer (facts, tasks, links, reminders, KB)."""

from datetime import datetime

from ev.core.memory import Memory


def test_facts_and_semantic_recall(tmp_path):
    m = Memory(tmp_path / "t.db")
    m.add_fact("u", "gosto de café", [1.0, 0.0])
    m.add_fact("u", "tenho um gato", [0.0, 1.0])
    assert set(m.all_facts("u")) == {"gosto de café", "tenho um gato"}
    # Query close to the coffee vector should rank coffee first.
    assert m.relevant_facts("u", [1.0, 0.0], k=1) == ["gosto de café"]


def test_tasks(tmp_path):
    m = Memory(tmp_path / "t.db")
    tid = m.add_task("u", "comprar pão")
    assert [t["text"] for t in m.open_tasks("u")] == ["comprar pão"]
    assert m.complete_task("u", tid) is True
    assert m.open_tasks("u") == []


def test_next_due_rolls_to_future():
    now = datetime(2026, 7, 25, 12, 0)  # Saturday
    # daily: 3 days ago -> next future day
    assert Memory._next_due("2026-07-22T09:00", "daily", now) == "2026-07-26T09:00:00"
    # weekly: last Monday -> next Monday after now
    assert Memory._next_due("2026-07-20T09:00", "weekly", now) == "2026-07-27T09:00:00"
    # monthly: the 10th, this month passed -> next month's 10th
    assert Memory._next_due("2026-07-10T09:00", "monthly", now) == "2026-08-10T09:00:00"
    # already future -> unchanged
    assert Memory._next_due("2026-08-01T09:00", "daily", now) == "2026-08-01T09:00"


def test_recurring_task_rolls_on_complete_and_worker(tmp_path):
    m = Memory(tmp_path / "t.db")
    tid = m.add_task("u", "revisar metas", "trabalho", recur="weekly", due="2026-07-20T09:00")
    # worker rolls an overdue recurring task forward — single instance, no pile-up
    now = datetime(2026, 7, 25, 12, 0)
    assert m.roll_due_tasks(now) == 1
    rows = m.open_tasks("u")
    assert len(rows) == 1 and rows[0]["id"] == tid
    assert rows[0]["due"] == "2026-07-27T09:00:00"
    # completing rolls forward again (same row stays open, never disappears)
    assert m.complete_task("u", tid) is True
    rows = m.open_tasks("u")
    assert len(rows) == 1 and rows[0]["id"] == tid and rows[0]["recur"] == "weekly"


def test_recurring_task_without_due_regenerates_copy(tmp_path):
    m = Memory(tmp_path / "t.db")
    tid = m.add_task("u", "treino", recur="daily")  # no due
    assert m.complete_task("u", tid) is True
    rows = m.open_tasks("u")
    assert len(rows) == 1 and rows[0]["text"] == "treino" and rows[0]["id"] != tid


def test_plain_task_with_due_completes_normally(tmp_path):
    m = Memory(tmp_path / "t.db")
    tid = m.add_task("u", "pagar boleto", due="2026-07-30T10:00")
    assert m.open_tasks("u")[0]["due"] == "2026-07-30T10:00"
    assert m.complete_task("u", tid) is True
    assert m.open_tasks("u") == []


def test_links(tmp_path):
    m = Memory(tmp_path / "t.db")
    lid = m.add_link("u", "faculdade", "grade", "http://x")
    assert m.list_links("u", "faculdade")[0]["name"] == "grade"
    assert m.list_links("u", "trabalho") == []
    assert m.delete_link("u", lid) is True


def test_reminders(tmp_path):
    m = Memory(tmp_path / "t.db")
    rid = m.add_reminder("u", "beber água", "2020-01-01T00:00:00")
    assert len(m.pending_reminders()) == 1
    m.mark_reminder_done(rid)
    assert m.pending_reminders() == []


def test_knowledge_search(tmp_path):
    m = Memory(tmp_path / "t.db")
    m.add_chunk("u", "doc", "o café é ótimo de manhã", [1.0, 0.0])
    m.add_chunk("u", "doc", "gatos dormem muito", [0.0, 1.0])
    hits = m.search_knowledge("u", [1.0, 0.0], k=1)
    assert hits and "café" in hits[0]["chunk"]


def test_cancel_and_reschedule(tmp_path):
    m = Memory(tmp_path / "t.db")
    rid = m.add_reminder("u", "beber", "2020-01-01T00:00:00", recur="daily")
    assert m.open_reminders("u")[0]["recur"] == "daily"
    m.reschedule_reminder(rid, "2030-01-01T00:00:00")
    assert m.open_reminders("u")[0]["when_iso"] == "2030-01-01T00:00:00"
    assert m.cancel_reminder("u", rid) is True
    assert m.open_reminders("u") == []


def test_usage_and_settings(tmp_path):
    m = Memory(tmp_path / "t.db")
    m.bump_usage("groq", "2026-01-01")
    m.bump_usage("groq", "2026-01-01")
    m.bump_usage("gemini", "2026-01-01")
    u = m.usage_for_day("2026-01-01")
    assert u["groq"] == 2 and u["gemini"] == 1
    m.set_setting("model", "x")
    assert m.get_setting("model") == "x"
    m.set_setting("model", "y")  # upsert
    assert m.get_setting("model") == "y"


def test_budget_storage(tmp_path):
    m = Memory(tmp_path / "t.db")
    m.set_budget("u", "comida", 800.0)
    assert m.get_budget("u", "comida") == 800.0
    m.set_budget("u", "comida", 500.0)  # upsert replaces
    assert m.get_budget("u", "comida") == 500.0
    assert m.delete_budget("u", "comida") is True


def test_backup(tmp_path):
    m = Memory(tmp_path / "t.db")
    m.add_fact("u", "algo importante")
    dest = tmp_path / "backup.db"
    m.backup(dest)
    assert dest.exists()
    restored = Memory(dest)
    assert restored.all_facts("u") == ["algo importante"]
