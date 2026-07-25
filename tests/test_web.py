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

    async def ask(self, system, prompt):
        return "resposta de teste"

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
        telegram_token="t", groq_api_key="", openrouter_api_key="",
        tavily_api_key="", brave_api_key="", ollama_enabled=False,
        groq_model="g", openrouter_model="o", ollama_model="l",
        google_ready=lambda: False, google_authorized=lambda account=None: False,
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


def test_kb_endpoints(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/kb", headers=_auth()).json()["sources"] == []
    # invalid URL is rejected without touching the network
    r = client.post("/api/kb/url", json={"url": "nao-e-url"}, headers=_auth())
    assert r.json()["ok"] is False
    # deleting a missing source is a no-op
    assert client.post("/api/kb/delete", json={"source": "x"}, headers=_auth()).json()["ok"] is False


def test_expenses_crud(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/expenses", json={"amount": "50,5", "description": "mercado", "category": "casa"}, headers=_auth())
    items = client.get("/api/expenses", headers=_auth()).json()["items"]
    assert len(items) == 1 and items[0]["amount"] == 50.5
    client.post("/api/expenses/delete", json={"id": items[0]["id"]}, headers=_auth())
    assert client.get("/api/expenses", headers=_auth()).json()["items"] == []


def test_reminders_and_facts_crud(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/reminders", json={"text": "pagar conta", "when": "2026-08-01T09:00"}, headers=_auth())
    rem = client.get("/api/reminders", headers=_auth()).json()["items"]
    assert rem and rem[0]["text"] == "pagar conta"
    client.post("/api/reminders/delete", json={"id": rem[0]["id"]}, headers=_auth())
    assert client.get("/api/reminders", headers=_auth()).json()["items"] == []
    client.post("/api/facts", json={"text": "gosto de café"}, headers=_auth())
    fs = client.get("/api/facts", headers=_auth()).json()["items"]
    assert fs and fs[0]["fact"] == "gosto de café"
    client.post("/api/facts/delete", json={"id": fs[0]["id"]}, headers=_auth())
    assert client.get("/api/facts", headers=_auth()).json()["items"] == []


def test_dados_shows_summary_on_web(tmp_path):
    # was returning "funciona no Telegram" — must show the storage summary now.
    client, _ = _client(tmp_path)
    reply = client.post("/api/cmd", json={"command": "dados"}, headers=_auth()).json()["reply"]
    assert "guardados" in reply.lower()
    assert "funciona no telegram" not in reply.lower()


# Commands that run locally (no external network) — must never crash on web.
_SAFE_CMDS = [
    "tarefas", "memorias", "gastos", "habitos", "lembretes", "links",
    "orcamentos", "assinaturas", "vigias", "diario", "calendario", "procurar",
    "status", "modelo", "dados", "ajuda", "quiz", "insights", "provedor",
]


def test_commands_do_not_crash(tmp_path):
    client, _ = _client(tmp_path)
    for c in _SAFE_CMDS:
        r = client.post("/api/cmd", json={"command": c}, headers=_auth())
        assert r.status_code == 200, c
        assert isinstance(r.json().get("reply"), str) and r.json()["reply"], c


def test_api_keys_manage(tmp_path):
    client, _ = _client(tmp_path)
    keys = {k["field"]: k["set"] for k in client.get("/api/keys", headers=_auth()).json()["keys"]}
    assert keys["tavily_api_key"] is False and keys["gemini_api_key"] is True  # from fake cfg
    r = client.post("/api/keys", json={"tavily_api_key": "tvly-abc"}, headers=_auth())
    assert r.json()["ok"] is True
    keys = {k["field"]: k["set"] for k in client.get("/api/keys", headers=_auth()).json()["keys"]}
    assert keys["tavily_api_key"] is True  # now set (in memory + .env)


def test_links_habits_journal_crud(tmp_path):
    client, _ = _client(tmp_path)
    # links (with category)
    client.post("/api/links", json={"name": "GitHub", "url": "https://github.com", "category": "dev"}, headers=_auth())
    items = client.get("/api/links", headers=_auth()).json()["items"]
    assert items and items[0]["category"] == "dev" and items[0]["url"] == "https://github.com"
    client.post("/api/links/delete", json={"id": items[0]["id"]}, headers=_auth())
    assert client.get("/api/links", headers=_auth()).json()["items"] == []
    # habits
    client.post("/api/habits", json={"name": "treino"}, headers=_auth())
    h = client.get("/api/habits", headers=_auth()).json()["items"][0]
    assert h["name"] == "treino" and h["done_today"] is False
    client.post("/api/habits/done", json={"id": h["id"]}, headers=_auth())
    assert client.get("/api/habits", headers=_auth()).json()["items"][0]["done_today"] is True
    client.post("/api/habits/delete", json={"id": h["id"]}, headers=_auth())
    assert client.get("/api/habits", headers=_auth()).json()["items"] == []
    # journal
    client.post("/api/journal", json={"text": "dia produtivo"}, headers=_auth())
    j = client.get("/api/journal", headers=_auth()).json()["items"]
    assert j and j[0]["text"] == "dia produtivo"
    client.post("/api/journal/delete", json={"id": j[0]["id"]}, headers=_auth())
    assert client.get("/api/journal", headers=_auth()).json()["items"] == []


def test_kb_file_download(tmp_path):
    client, _ = _client(tmp_path)
    # no file yet
    assert client.get("/api/kb", headers=_auth()).json()["files"] == []
    assert client.get("/api/kb/file?source=x", headers=_auth()).status_code == 404
    # store one directly and fetch it back
    from ev.core.memory import Memory
    m = Memory(tmp_path / "t.db")
    m.save_kb_file("123", "meu.pdf", "meu.pdf", "application/pdf", b"%PDF-1.4 test")
    assert "meu.pdf" in client.get("/api/kb", headers=_auth()).json()["files"]
    r = client.get("/api/kb/file?source=meu.pdf", headers=_auth())
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test"


def test_recurring_budgets_watches_crud(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/recurring", json={"amount": "39,90", "description": "Netflix", "day": 15}, headers=_auth())
    r = client.get("/api/recurring", headers=_auth()).json()["items"]
    assert r and r[0]["description"] == "Netflix" and r[0]["day"] == 15
    client.post("/api/recurring/delete", json={"id": r[0]["id"]}, headers=_auth())
    assert client.get("/api/recurring", headers=_auth()).json()["items"] == []
    client.post("/api/budgets", json={"category": "comida", "amount": 800}, headers=_auth())
    b = client.get("/api/budgets", headers=_auth()).json()["items"]
    assert b and b[0]["category"] == "comida" and b[0]["amount"] == 800
    client.post("/api/budgets/delete", json={"category": "comida"}, headers=_auth())
    assert client.get("/api/budgets", headers=_auth()).json()["items"] == []
    client.post("/api/watches", json={"url": "https://x.com", "keyword": "promo"}, headers=_auth())
    w = client.get("/api/watches", headers=_auth()).json()["items"]
    assert w and w[0]["keyword"] == "promo"
    client.post("/api/watches/delete", json={"id": w[0]["id"]}, headers=_auth())
    assert client.get("/api/watches", headers=_auth()).json()["items"] == []


def test_crud_update_endpoints(tmp_path):
    client, _ = _client(tmp_path)
    # expense
    client.post("/api/expenses", json={"amount": "10", "description": "x", "category": "casa"}, headers=_auth())
    e = client.get("/api/expenses", headers=_auth()).json()["items"][0]
    client.post("/api/expenses/update", json={"id": e["id"], "amount": "25,5", "description": "y", "category": "lazer"}, headers=_auth())
    e = client.get("/api/expenses", headers=_auth()).json()["items"][0]
    assert e["amount"] == 25.5 and e["description"] == "y" and e["category"] == "lazer"
    # reminder
    client.post("/api/reminders", json={"text": "a", "when": "2026-08-01T09:00"}, headers=_auth())
    r = client.get("/api/reminders", headers=_auth()).json()["items"][0]
    client.post("/api/reminders/update", json={"id": r["id"], "text": "b", "when": "2026-09-02T10:30"}, headers=_auth())
    r = client.get("/api/reminders", headers=_auth()).json()["items"][0]
    assert r["text"] == "b" and r["when_iso"].startswith("2026-09-02T10:30")
    # fact
    client.post("/api/facts", json={"text": "old"}, headers=_auth())
    f = client.get("/api/facts", headers=_auth()).json()["items"][0]
    client.post("/api/facts/update", json={"id": f["id"], "text": "new"}, headers=_auth())
    assert client.get("/api/facts", headers=_auth()).json()["items"][0]["fact"] == "new"
    # link
    client.post("/api/links", json={"name": "n", "url": "https://a.com", "category": "c"}, headers=_auth())
    l = client.get("/api/links", headers=_auth()).json()["items"][0]
    client.post("/api/links/update", json={"id": l["id"], "name": "n2", "url": "https://b.com", "category": "c2"}, headers=_auth())
    l = client.get("/api/links", headers=_auth()).json()["items"][0]
    assert l["name"] == "n2" and l["url"] == "https://b.com" and l["category"] == "c2"
    # habit rename
    client.post("/api/habits", json={"name": "h1"}, headers=_auth())
    h = client.get("/api/habits", headers=_auth()).json()["items"][0]
    client.post("/api/habits/update", json={"id": h["id"], "name": "h2"}, headers=_auth())
    assert client.get("/api/habits", headers=_auth()).json()["items"][0]["name"] == "h2"
    # journal
    client.post("/api/journal", json={"text": "j1"}, headers=_auth())
    j = client.get("/api/journal", headers=_auth()).json()["items"][0]
    client.post("/api/journal/update", json={"id": j["id"], "text": "j2"}, headers=_auth())
    assert client.get("/api/journal", headers=_auth()).json()["items"][0]["text"] == "j2"
    # recurring
    client.post("/api/recurring", json={"amount": "9", "description": "Spotify", "day": 5}, headers=_auth())
    rec = client.get("/api/recurring", headers=_auth()).json()["items"][0]
    client.post("/api/recurring/update", json={"id": rec["id"], "amount": "19,9", "description": "Spotify Duo", "category": "musica", "day": 12}, headers=_auth())
    rec = client.get("/api/recurring", headers=_auth()).json()["items"][0]
    assert rec["amount"] == 19.9 and rec["description"] == "Spotify Duo" and rec["day"] == 12
    # watch
    client.post("/api/watches", json={"url": "https://x.com", "keyword": "k1"}, headers=_auth())
    w = client.get("/api/watches", headers=_auth()).json()["items"][0]
    client.post("/api/watches/update", json={"id": w["id"], "url": "https://y.com", "keyword": "k2"}, headers=_auth())
    w = client.get("/api/watches", headers=_auth()).json()["items"][0]
    assert w["url"] == "https://y.com" and w["keyword"] == "k2"


def test_panel_extended_counts(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/links", json={"name": "n", "url": "https://a.com", "category": "c"}, headers=_auth())
    client.post("/api/habits", json={"name": "h"}, headers=_auth())
    client.post("/api/journal", json={"text": "j"}, headers=_auth())
    client.post("/api/recurring", json={"amount": "9", "description": "Sub", "day": 5}, headers=_auth())
    client.post("/api/budgets", json={"category": "comida", "amount": 100}, headers=_auth())
    client.post("/api/watches", json={"url": "https://x.com", "keyword": "k"}, headers=_auth())
    p = client.get("/api/panel", headers=_auth()).json()
    assert p["links"] == 1 and p["habits"] == 1 and p["journal"] == 1
    assert p["subscriptions"] == 1 and p["budgets"] == 1 and p["watches"] == 1


def test_geral_folder_protected(tmp_path):
    client, _ = _client(tmp_path)
    out = client.post("/api/threads/delete", json={"name": "geral"}, headers=_auth()).json()
    assert "geral" in out["threads"]  # can't delete the home folder
