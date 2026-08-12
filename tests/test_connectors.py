"""Tests for user-defined API connectors — SSRF guard + JSON path (offline)."""

from ev.providers import connectors as cn
from ev.core.memory import Memory


def test_https_only():
    val, err = cn.fetch("http://example.com/x")
    assert val is None and "https" in err


def test_blocks_private_and_loopback():
    # IP literals + localhost resolve without network; all must be refused
    for url in ("https://127.0.0.1/x", "https://10.0.0.1/x",
                "https://192.168.1.1/x", "https://169.254.169.254/latest",
                "https://localhost/x"):
        val, err = cn.fetch(url)
        assert val is None and "interno" in err.lower(), url


def test_json_path():
    data = {"rates": {"BRL": 5.42}, "list": [{"price": 10}, {"price": 20}]}
    assert cn.json_path(data, "rates.BRL") == 5.42
    assert cn.json_path(data, "$.list[1].price") == 20
    assert cn.json_path(data, "list[0].price") == 10
    assert cn.json_path(data, "nope.x") is None


def test_connector_crud(tmp_path):
    m = Memory(tmp_path / "t.db")
    cid = m.add_connector("u", "Dólar", "https://api.x/usd",
                          {"Authorization": "Bearer {{FX_KEY}}"}, "rates.BRL")
    items = m.list_connectors("u")
    assert len(items) == 1 and items[0]["name"] == "Dólar"
    assert items[0]["headers"]["Authorization"].startswith("Bearer ")
    assert m.get_connector("u", "dólar")["path"] == "rates.BRL"
    assert m.delete_connector("u", cid) is True
    assert m.list_connectors("u") == []


def test_pages_crud(tmp_path):
    m = Memory(tmp_path / "p.db")
    pid = m.add_page("u", "Faculdade", [
        {"type": "tasks", "category": "faculdade"}, {"type": "chart"}])
    pages = m.list_pages("u")
    assert len(pages) == 1 and pages[0]["name"] == "Faculdade"
    assert pages[0]["widgets"][0]["type"] == "tasks"
    assert m.update_page("u", pid, name="Fac 2") is True
    assert m.list_pages("u")[0]["name"] == "Fac 2"
    assert m.delete_page("u", pid) is True
    assert m.list_pages("u") == []


def test_goals_health_vault(tmp_path):
    m = Memory(tmp_path / "t3.db")
    # goals
    gid = m.add_goal("u", "Viagem", 5000)
    m.add_to_goal("u", gid, 1200); m.add_to_goal("u", gid, 300)
    g = m.list_goals("u")[0]
    assert g["saved"] == 1500 and g["target"] == 5000
    m.add_to_goal("u", gid, -100000)  # can't go below 0
    assert m.list_goals("u")[0]["saved"] == 0
    assert m.delete_goal("u", gid) is True
    # health
    assert m.health_water_inc("u", "2026-08-06") == 1
    m.health_water_inc("u", "2026-08-06", 2)
    m.health_set("u", "2026-08-06", "sleep", 7.5)
    m.health_set("u", "2026-08-06", "mood", "🙂")
    hd = m.health_day("u", "2026-08-06")
    assert hd["water"] == 3 and hd["sleep"] == 7.5 and hd["mood"] == "🙂"
    # vault
    did = m.add_document("u", "rg.jpg", "image/jpeg", b"\x89PNGdata", "documento de identidade")
    assert len(m.list_documents("u")) == 1
    assert len(m.list_documents("u", "identidade")) == 1  # search by ocr text
    assert len(m.list_documents("u", "nada")) == 0
    assert m.get_document("u", did)["data"] == b"\x89PNGdata"
    assert m.delete_document("u", did) is True
