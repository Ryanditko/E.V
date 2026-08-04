"""Tests for the web interface (auth, chat, commands, folders), with a fake brain."""

from types import SimpleNamespace

from ev.interfaces.web import create_app


class _FakeBrain:
    def __init__(self):
        self.last = None

    async def respond(self, owner, conv_id=None, text=None, image=None, image_mime=None):
        self.last = (owner, conv_id, text)
        return ("viu a imagem: " + (text or "")) if image else f"echo: {text}"

    def current_model(self):
        return "gemini-flash-latest"

    async def ask(self, system, prompt):
        return "resposta de teste"

    async def transcribe(self, audio, mime):
        self.last_audio = (audio, mime)
        return "texto transcrito"

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
        web_base_url="", google_login_client="", google_login_secret="",
        github_login_client="", github_login_secret="",
        vapid_public="", vapid_private="", vapid_subject="mailto:x@x.com",
    )
    brain = _FakeBrain()
    return TestClient(create_app(cfg, brain=brain)), brain


def _auth():
    return {"Authorization": "Bearer secret"}


def test_backup_download(tmp_path):
    client, _ = _client(tmp_path)
    # browser downloads can't set headers → token via ?k=
    r = client.get("/api/backup?k=secret")
    assert r.status_code == 200
    assert len(r.content) > 0  # a real DB copy came back
    assert client.get("/api/backup?k=wrong").status_code == 401
    assert client.get("/api/backup").status_code == 401


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


def test_recurring_task_regenerates_on_complete(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/tasks", json={"text": "treino", "category": "saude", "recur": "daily"}, headers=_auth())
    t = client.get("/api/tasks", headers=_auth()).json()["tasks"][0]
    assert t["recur"] == "daily"
    client.post("/api/tasks/complete", json={"id": t["id"]}, headers=_auth())
    tasks = client.get("/api/tasks", headers=_auth()).json()["tasks"]
    # a fresh open copy comes back, keeping text + recurrence, with a new id
    assert len(tasks) == 1 and tasks[0]["text"] == "treino"
    assert tasks[0]["recur"] == "daily" and tasks[0]["id"] != t["id"]


def test_non_recurring_task_does_not_regenerate(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/tasks", json={"text": "pagar boleto"}, headers=_auth())
    t = client.get("/api/tasks", headers=_auth()).json()["tasks"][0]
    assert t["recur"] is None
    client.post("/api/tasks/complete", json={"id": t["id"]}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"] == []


def test_task_recur_update_and_invalid_ignored(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/tasks", json={"text": "x"}, headers=_auth())
    t = client.get("/api/tasks", headers=_auth()).json()["tasks"][0]
    # set recurrence
    client.post("/api/tasks/update", json={"id": t["id"], "recur": "weekly"}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"][0]["recur"] == "weekly"
    # clear it
    client.post("/api/tasks/update", json={"id": t["id"], "recur": ""}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"][0]["recur"] is None
    # invalid value is rejected (treated as clear on update)
    client.post("/api/tasks/update", json={"id": t["id"], "recur": "hourly"}, headers=_auth())
    assert client.get("/api/tasks", headers=_auth()).json()["tasks"][0]["recur"] is None
    # a category-only update (drag-drop) must NOT wipe an existing recurrence
    client.post("/api/tasks/update", json={"id": t["id"], "recur": "monthly"}, headers=_auth())
    client.post("/api/tasks/update", json={"id": t["id"], "category": "nova"}, headers=_auth())
    row = client.get("/api/tasks", headers=_auth()).json()["tasks"][0]
    assert row["category"] == "nova" and row["recur"] == "monthly"


def test_reminder_recurrence_create_update(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/reminders", json={"text": "backup", "when": "2026-08-01T09:00", "recur": "weekly"}, headers=_auth())
    r = client.get("/api/reminders", headers=_auth()).json()["items"][0]
    assert r["recur"] == "weekly"
    # clear recurrence via update
    client.post("/api/reminders/update", json={"id": r["id"], "recur": ""}, headers=_auth())
    assert not client.get("/api/reminders", headers=_auth()).json()["items"][0]["recur"]
    # invalid recur on create is ignored (one-off)
    client.post("/api/reminders", json={"text": "once", "when": "2026-08-02T09:00", "recur": "yearly"}, headers=_auth())
    items = {i["text"]: i for i in client.get("/api/reminders", headers=_auth()).json()["items"]}
    assert not items["once"]["recur"]


def test_stt_transcribes_uploaded_audio(tmp_path):
    client, brain = _client(tmp_path)
    r = client.post("/api/stt", headers=_auth(),
                    files={"audio": ("rec.webm", b"\x1a\x45\xdf\xa3fake", "audio/webm")})
    assert r.status_code == 200 and r.json()["text"] == "texto transcrito"
    assert brain.last_audio[1] == "audio/webm"


def test_stt_rejects_empty(tmp_path):
    client, _ = _client(tmp_path)
    # no file part
    assert client.post("/api/stt", headers=_auth(), data={}).status_code == 400


def test_kb_upload_recognizes_multipart_file(tmp_path):
    # Regression: fastapi.UploadFile != starlette.UploadFile, so the old
    # isinstance() check silently rejected every upload. A wrong-extension file
    # must now reach the type check (proving the file was parsed), not "no file".
    client, _ = _client(tmp_path)
    r = client.post("/api/kb/upload", headers=_auth(),
                    files={"file": ("x.exe", b"MZ", "application/octet-stream")}).json()
    assert r["ok"] is False and "PDF" in r["msg"]


def test_email_endpoint_validates(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/api/email", headers=_auth(), json={"to": "", "body": ""}).json()
    assert r["ok"] is False and "destinat" in r["msg"].lower()


def test_notify_endpoint_validates(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/api/notify", headers=_auth(), json={"text": ""}).json()
    assert r["ok"] is False


def test_chat_stream(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/api/chat/stream", json={"message": "oi", "thread": "geral"}, headers=_auth())
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "".join(r.text.split()) == "echo:oi"  # streamed word chunks reassemble


def test_vision_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    # no image -> graceful message
    assert "Nenhuma imagem" in client.post("/api/vision", headers=_auth(), data={}).json()["reply"]
    # with an image -> routed to brain.respond(image=...)
    r = client.post("/api/vision", headers=_auth(),
                    data={"text": "o que é isso?"},
                    files={"image": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")}).json()
    assert "viu a imagem" in r["reply"]


def test_habits_expose_days_for_heatmap(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/habits", json={"name": "treino"}, headers=_auth())
    h = client.get("/api/habits", headers=_auth()).json()["items"][0]
    client.post("/api/habits/done", json={"id": h["id"]}, headers=_auth())
    h = client.get("/api/habits", headers=_auth()).json()["items"][0]
    assert isinstance(h["days"], list) and len(h["days"]) == 1


def test_oauth_login_disabled_when_unconfigured(tmp_path):
    client, _ = _client(tmp_path)  # fake config has no OAuth client ids
    for path in ("/auth/google", "/auth/github"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 403 and "não configurado" in r.text
    # a bad callback (no code/state) is rejected, not crashed
    assert client.get("/auth/google/callback").status_code == 403


def test_gcal_endpoints_guarded(tmp_path):
    client, _ = _client(tmp_path)
    # not authorized in the fake config -> graceful empty, no crash
    r = client.get("/api/gcal?start=2026-07-01T00:00:00Z&end=2026-08-01T00:00:00Z", headers=_auth()).json()
    assert r["ok"] is False and r["events"] == []
    # create/delete validate input before touching Google
    assert client.post("/api/gcal/create", headers=_auth(), json={"summary": "", "start": ""}).json()["ok"] is False
    assert client.post("/api/gcal/delete", headers=_auth(), json={"id": ""}).json()["ok"] is False


def test_push_subscribe_and_key(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/push/key", headers=_auth()).json()["key"] == ""  # from fake cfg
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/api/push/subscribe", headers=_auth(), json=sub).json()["ok"] is True
    from ev.core.memory import Memory
    m = Memory(tmp_path / "t.db")
    assert m.list_push_subs() and m.list_push_subs()[0]["endpoint"] == sub["endpoint"]
    # no VAPID keys configured -> test push sends 0, no crash
    assert client.post("/api/push/test", headers=_auth()).json()["sent"] == 0


def test_activity_history(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/tasks", json={"text": "estudar", "category": "faculdade"}, headers=_auth())
    t = client.get("/api/tasks", headers=_auth()).json()["tasks"][0]
    client.post("/api/tasks/complete", json={"id": t["id"]}, headers=_auth())
    d = client.get("/api/activity", headers=_auth()).json()
    actions = [a["action"] for a in d["items"]]
    assert "task.new" in actions and "task.done" in actions
    assert "faculdade" in d["categories"]
    # category filter
    only = client.get("/api/activity?category=faculdade", headers=_auth()).json()["items"]
    assert only and all(a["category"] == "faculdade" for a in only)


def test_pwa_manifest_and_service_worker(tmp_path):
    client, _ = _client(tmp_path)
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and "manifest" in m.headers["content-type"]
    data = m.json()
    assert data["name"] and data["display"] == "standalone" and data["icons"]
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert "notificationclick" in sw.text and "fetch" in sw.text


def test_geral_folder_protected(tmp_path):
    client, _ = _client(tmp_path)
    out = client.post("/api/threads/delete", json={"name": "geral"}, headers=_auth()).json()
    assert "geral" in out["threads"]  # can't delete the home folder


def test_panel_has_system_indicators(tmp_path):
    client, _ = _client(tmp_path)
    # a tz-naive reminder time must not crash the agenda count (older rows are naive)
    client.post("/api/reminders", json={"text": "x", "when": "2030-01-01T09:00"},
                headers=_auth())
    d = client.get("/api/panel", headers=_auth()).json()
    # the new pinnable "Sistema" indicators must all be present
    for k in ("agenda", "activity", "disk", "ram", "uptime", "kbfiles",
              "notifs", "provider", "model"):
        assert k in d, f"missing panel key: {k}"
    assert isinstance(d["notifs"], int) and isinstance(d["agenda"], int)


def test_notification_center(tmp_path):
    client, _ = _client(tmp_path)
    # empty at first
    assert client.get("/api/notifications", headers=_auth()).json() == {
        "items": [], "unread": 0}
    # a test push logs a notification (no VAPID -> not sent, but still recorded)
    client.post("/api/push/test", headers=_auth())
    d = client.get("/api/notifications", headers=_auth()).json()
    assert d["unread"] == 1 and len(d["items"]) == 1
    nid = d["items"][0]["id"]
    # mark read -> unread drops
    client.post("/api/notifications/read", json={"id": nid}, headers=_auth())
    assert client.get("/api/notifications", headers=_auth()).json()["unread"] == 0
    # delete -> gone
    client.post("/api/notifications/delete", json={"id": nid}, headers=_auth())
    assert client.get("/api/notifications", headers=_auth()).json()["items"] == []
