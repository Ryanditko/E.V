"""Tests for the web interface (auth, chat, commands, folders), with a fake brain."""

from types import SimpleNamespace

from ev.interfaces.web import create_app


class _FakeBrain:
    def __init__(self):
        self.last = None

    async def respond(self, owner, conv_id=None, text=None):
        self.last = (owner, conv_id, text)
        return f"echo: {text}"

    def current_model(self):
        return "gemini-flash-latest"

    def pop_documents(self):
        return []

    def pop_actions(self):
        return []


def _client(tmp_path):
    from fastapi.testclient import TestClient

    cfg = SimpleNamespace(
        web_token="secret", owner_id=123, db_path=tmp_path / "t.db",
        timezone="America/Sao_Paulo", google_oauth_client="", google_accounts=(),
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
    )
    brain = _FakeBrain()
    return TestClient(create_app(cfg, brain=brain)), brain


def _auth():
    return {"Authorization": "Bearer secret"}


def test_index_served(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200 and "E.V." in r.text


def test_chat_requires_token(tmp_path):
    client, _ = _client(tmp_path)
    assert client.post("/api/chat", json={"message": "oi"}).status_code == 401


def test_chat_uses_scoped_conv(tmp_path):
    client, brain = _client(tmp_path)
    r = client.post("/api/chat", json={"message": "oi", "thread": "work"}, headers=_auth())
    assert r.status_code == 200 and r.json()["reply"] == "echo: oi"
    assert brain.last == ("123", "web:work", "oi")  # folder -> its own thread


def test_chat_default_thread(tmp_path):
    client, brain = _client(tmp_path)
    client.post("/api/chat", json={"message": "hey"}, headers=_auth())
    assert brain.last[1] == "web:geral"


def test_commands_list(tmp_path):
    client, _ = _client(tmp_path)
    names = [c["name"] for c in client.get("/api/commands", headers=_auth()).json()["commands"]]
    assert "tarefa" in names and "provedor" in names and "foco" in names


def test_folders_default_and_create(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/threads", headers=_auth()).json()["threads"] == \
        ["geral", "work", "university", "personal"]
    out = client.post("/api/threads", json={"name": "projetos"}, headers=_auth()).json()
    assert "projetos" in out["threads"]


def test_cmd_provider_works(tmp_path):
    # The bug in the screenshot: interface commands must run from the web.
    client, _ = _client(tmp_path)
    r = client.post("/api/cmd", json={"command": "provedor groq"}, headers=_auth())
    assert "groq" in r.json()["reply"].lower()


def test_cmd_data_command(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/api/cmd", json={"command": "tarefa comprar pão"}, headers=_auth())
    assert "adicionada" in r.json()["reply"].lower()
