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
