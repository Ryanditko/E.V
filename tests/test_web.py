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


def test_folder_rename_and_delete(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/threads", json={"name": "temp"}, headers=_auth())
    # a command persists into the folder (chat needs the real brain to persist)
    client.post("/api/cmd", json={"command": "tarefas", "thread": "temp"}, headers=_auth())
    out = client.post("/api/threads/rename", json={"old": "temp", "new": "trabalho"}, headers=_auth()).json()
    assert "trabalho" in out["threads"] and "temp" not in out["threads"]
    assert client.get("/api/history?thread=trabalho", headers=_auth()).json()["messages"]
    out = client.post("/api/threads/delete", json={"name": "trabalho"}, headers=_auth()).json()
    assert "trabalho" not in out["threads"]
    assert client.get("/api/history?thread=trabalho", headers=_auth()).json()["messages"] == []


def test_config_actions_customizable(tmp_path):
    client, _ = _client(tmp_path)
    d = client.get("/api/config", headers=_auth()).json()
    assert "buscar" in d["actions"] and "tasks" in d["stats"]
    client.post("/api/config", json={"actions": ["foco", "clima"]}, headers=_auth())
    d = client.get("/api/config", headers=_auth()).json()
    assert d["actions"] == ["foco", "clima"]  # e.g. added Pomodoro, removed others


def test_nested_folders(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/threads", json={"name": "projeto-x", "parent": "work"}, headers=_auth())
    out = client.get("/api/threads", headers=_auth()).json()["threads"]
    assert "work/projeto-x" in out
    # deleting the parent removes the subfolder too
    out = client.post("/api/threads/delete", json={"name": "work"}, headers=_auth()).json()["threads"]
    assert "work" not in out and "work/projeto-x" not in out


def test_rename_folder_moves_descendants(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/threads", json={"name": "sub", "parent": "personal"}, headers=_auth())
    out = client.post("/api/threads/rename", json={"old": "personal", "new": "pessoal"}, headers=_auth()).json()["threads"]
    assert "pessoal" in out and "pessoal/sub" in out and "personal" not in out


def test_tasks_crud(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"] == []
    client.post("/api/tasks", json={"text": "estudar", "category": "faculdade"}, headers=_auth())
    tasks = client.get("/api/tasks", headers=_auth()).json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["category"] == "faculdade"
    tid = tasks[0]["id"]
    client.post("/api/tasks/update", json={"id": tid, "text": "estudar cálculo"}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"][0]["text"] == "estudar cálculo"
    client.post("/api/tasks/complete", json={"id": tid}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"] == []
    # a second one, then hard delete
    client.post("/api/tasks", json={"text": "x"}, headers=_auth())
    tid2 = client.get("/api/tasks", headers=_auth()).json()["tasks"][0]["id"]
    client.post("/api/tasks/delete", json={"id": tid2}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"] == []


def test_limparchat_clears_folder(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/cmd", json={"command": "tarefas", "thread": "work"}, headers=_auth())
    assert client.get("/api/history?thread=work", headers=_auth()).json()["messages"]
    r = client.post("/api/cmd", json={"command": "limparchat", "thread": "work"}, headers=_auth())
    assert "limpa" in r.json()["reply"].lower()
    assert client.get("/api/history?thread=work", headers=_auth()).json()["messages"] == []


def test_move_folder_into_another(tmp_path):
    client, _ = _client(tmp_path)
    out = client.post("/api/threads/move", json={"path": "work", "parent": "personal"}, headers=_auth()).json()["threads"]
    assert "personal/work" in out and "work" not in out


def test_geral_folder_protected(tmp_path):
    client, _ = _client(tmp_path)
    out = client.post("/api/threads/delete", json={"name": "geral"}, headers=_auth()).json()
    assert "geral" in out["threads"]  # can't delete the home folder
