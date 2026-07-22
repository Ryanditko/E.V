"""Tests for the SQLite memory layer (facts, tasks, links, reminders, KB)."""

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


def test_backup(tmp_path):
    m = Memory(tmp_path / "t.db")
    m.add_fact("u", "algo importante")
    dest = tmp_path / "backup.db"
    m.backup(dest)
    assert dest.exists()
    restored = Memory(dest)
    assert restored.all_facts("u") == ["algo importante"]
