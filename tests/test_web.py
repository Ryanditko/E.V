"""Tests for the web interface (auth + chat endpoint), with a fake brain."""

from types import SimpleNamespace

import pytest

from ev.interfaces.web import create_app


class _FakeBrain:
    def __init__(self):
        self.last = None

    async def respond(self, owner, conv_id=None, text=None):
        self.last = (owner, conv_id, text)
        return f"echo: {text}"

    def pop_documents(self):
        return []

    def pop_actions(self):
        return []


def _client(tmp_path):
    from fastapi.testclient import TestClient

    cfg = SimpleNamespace(web_token="secret", owner_id=123, db_path=tmp_path / "t.db")
    brain = _FakeBrain()
    return TestClient(create_app(cfg, brain=brain)), brain


def test_index_served(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200 and "E.V." in r.text


def test_chat_requires_token(tmp_path):
    client, _ = _client(tmp_path)
    assert client.post("/api/chat", json={"message": "oi"}).status_code == 401
    assert client.post("/api/chat", json={"message": "oi"},
                       headers={"Authorization": "Bearer errado"}).status_code == 401


def test_chat_ok_with_token(tmp_path):
    client, brain = _client(tmp_path)
    r = client.post("/api/chat", json={"message": "oi E.V."},
                    headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
    assert r.json()["reply"] == "echo: oi E.V."
    # owner + web conversation thread
    assert brain.last == ("123", "web", "oi E.V.")


def test_health(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/health").json() == {"ok": True}
