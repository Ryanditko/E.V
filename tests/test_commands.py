"""Tests for the deterministic command layer (no LLM, no network)."""

from types import SimpleNamespace

from ev.core.commands import Commands
from ev.core.memory import Memory


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="",
        google_accounts=(),
        gemini_api_key="x",
        embed_backend="gemini",
        embed_model="m",
        imap_address="",
        imap_password="",
        imap_ready=lambda: False,
    )
    return Commands(config, Memory(tmp_path / "t.db"))


def test_open_loops_and_nudge(tmp_path):
    from datetime import datetime, timezone
    c = _commands(tmp_path)
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    m = c._memory
    m.add_task("u", "entregar relatório", due="2026-08-01")   # overdue
    m.add_task("u", "pagar boleto", due="2026-08-04")          # due today
    m.add_task("u", "ler artigo")                              # no due — ignored
    m.add_recurring("u", 39.9, "Netflix", "lazer", 5)          # charges tomorrow
    m.add_recurring("u", 20.0, "Spotify", "lazer", 20)         # far off — ignored
    loops = c.open_loops("u", now=now)
    assert loops["overdue"] == ["entregar relatório"]
    assert loops["due_today"] == ["pagar boleto"]
    assert any("Netflix" in s for s in loops["subs"])
    assert not any("Spotify" in s for s in loops["subs"])
    msg = c.nudge_text("u", now=now)
    assert "Overdue" in msg and "entregar relatório" in msg and "Netflix" in msg
    # clean slate → empty nudge (E.V. stays silent when nothing is slipping)
    assert c.nudge_text("v", now=now) == ""


def test_spoken_status_pt(tmp_path):
    c = _commands(tmp_path)
    c._memory.set_assistant_lang("pt")
    s = c.spoken_status("u")
    assert "Ryan" in s and ("Bom dia" in s or "Boa tarde" in s or "Boa noite" in s)
    assert "tranquila" in s  # nothing open yet
    c.tarefa("u", "comprar pão")
    assert "1 tarefa" in c.spoken_status("u")


def test_spoken_status_en(tmp_path):
    c = _commands(tmp_path)  # default language is English
    s = c.spoken_status("u")
    assert "Ryan" in s and any(
        g in s for g in ("Good morning", "Good afternoon", "Good evening"))
    assert "Your schedule is clear." in s  # nothing open yet
    assert "tranquila" not in s and "Bom dia" not in s


def test_greeting_pluralization_en_vs_pt(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "a")
    c.tarefa("u", "b")
    c._memory.add_reminder("u", "call mom", "2026-12-25T09:00:00")  # 2 tasks, 1 reminder
    en = c.spoken_status("u")
    assert "Today you have 2 tasks and 1 reminder." in en
    c._memory.set_assistant_lang("pt")
    pt = c.spoken_status("u")
    assert "Hoje você tem 2 tarefas e 1 lembrete." in pt


def test_daily_briefing_follows_language(tmp_path):
    c = _commands(tmp_path)
    c._config.google_authorized = lambda: False
    c._config.city = ""
    c._config.news_topic = ""
    assert "Good morning! Here's your summary for today:" in c.daily_briefing("u")
    c._memory.set_assistant_lang("pt")
    assert "Bom dia! Aqui vai seu resumo de hoje:" in c.daily_briefing("u")


def test_i18n_helper():
    from ev.core.i18n import plural, t
    # translate + fall back English -> key
    assert t("pt", "join.and") == "e"
    assert t("en", "join.and") == "and"
    assert t("xx", "join.and") == "and"  # unknown lang -> English
    assert t("en", "does.not.exist") == "does.not.exist"  # unknown key -> key
    assert t("en", "greeting.hello", greeting="Hi", name="Ryan") == "Hi, Ryan."
    # pluralization for both languages (n == 1 singular, else plural, incl. 0)
    assert plural("en", "count.tasks", 1) == "1 task"
    assert plural("en", "count.tasks", 2) == "2 tasks"
    assert plural("en", "count.tasks", 0) == "0 tasks"
    assert plural("pt", "count.reminders", 1) == "1 lembrete"
    assert plural("pt", "count.reminders", 3) == "3 lembretes"


def test_automations_crud(tmp_path):
    c = _commands(tmp_path)
    aid, msg = c.create_automation("u", "expense_over", "notify", amount=200,
                                   message="Gasto alto")
    assert aid and "200" in msg
    listing = c.automacoes("u")
    assert "200" in listing and "warn me" in listing
    # a time+command automation
    aid2, _ = c.create_automation("u", "time", "command", hour=18, weekday=4,
                                  command="semana")
    assert aid2 and "Friday" in c.automacoes("u")
    # validation: bad trigger / missing field
    assert c.create_automation("u", "bogus", "notify")[0] is None
    assert c.create_automation("u", "expense_over", "notify")[0] is None  # no amount
    # a Spotify 'play' automation
    aid3, m3 = c.create_automation("u", "time", "play", hour=8, playlist="Foco")
    assert aid3 and "Foco" in m3
    assert c.create_automation("u", "time", "play", hour=8)[0] is None  # no target
    # remove
    assert "removed" in c.automacao_rm("u", str(aid))
    assert c.automacao_rm("u", "999") == "Couldn't find that automation."


def test_learned_patterns_and_persistence(tmp_path):
    from datetime import datetime, timezone, timedelta
    c = _commands(tmp_path)
    m = c._memory
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    today = now.date()
    hid = m.add_habit("u", "academia")
    # marked every day in the last 4 weeks EXCEPT Mondays → clear Monday-skip pattern
    for i in range(1, 29):
        d = today - timedelta(days=i)
        if d.weekday() != 0:  # skip Mondays
            m.log_habit(hid, d.isoformat())
    pats = c.learned_patterns("u", now=now)
    skip = [p for p in pats if p["key"].startswith("habit-skip:")]
    assert skip and "academia" in skip[0]["text"] and "Monday" in skip[0]["text"]

    # spending: this month already exceeds last month's total for a category
    conn = m._conn
    conn.execute("INSERT INTO expenses (user_id, amount, description, category, created)"
                 " VALUES (?,?,?,?,?)", ("u", 40, "ifood", "comida", "2026-07-15T12:00:00+00:00"))
    conn.execute("INSERT INTO expenses (user_id, amount, description, category, created)"
                 " VALUES (?,?,?,?,?)", ("u", 100, "ifood", "comida", "2026-08-02T12:00:00+00:00"))
    conn.commit()
    pats = c.learned_patterns("u", now=now)
    assert any(p["key"].startswith("spend-over:") and "comida" in p["text"] for p in pats)

    # persistence + dedup: add_learned only once per key
    key = skip[0]["key"]
    assert not m.learned_seen("u", key)
    assert m.add_learned("u", key, skip[0]["text"]) is True
    assert m.learned_seen("u", key) is True
    assert m.add_learned("u", key, skip[0]["text"]) is False
    assert "learned" in c.learned_text("u").lower()

    # a fresh user with no history → E.V. stays humble, no false patterns
    assert c.learned_patterns("v", now=now) == []
    assert "getting to know" in c.learned_text("v").lower()


def test_budget_alerts(tmp_path):
    c = _commands(tmp_path)
    c.orcamento("u", "comida 100")
    assert c.budget_alerts("u") == []          # nothing spent yet
    c.gasto("u", "95 mercado #comida")
    warn = c.budget_alerts("u")
    assert warn and warn[0]["level"] == "warn" and warn[0]["pct"] == 95
    c.gasto("u", "20 doce #comida")
    over = c.budget_alerts("u")
    assert over and over[0]["level"] == "over" and over[0]["pct"] >= 100


def test_subscriptions_due(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    c = _commands(tmp_path)
    # Use the SAME timezone the command computes "today" in, so this test isn't
    # off-by-one when CI runs near a UTC/local day boundary.
    today = datetime.now(ZoneInfo(c._config.timezone)).day
    tomorrow = today + 1
    c._memory.add_recurring("u", 50, "Netflix", "lazer", tomorrow)
    due = c.subscriptions_due("u")
    # a charge set for "day 32+" won't happen this month; guard on that
    if tomorrow <= 28:
        assert due and due[0]["description"] == "Netflix" and due[0]["days_until"] == 1
    far = c.subscriptions_due("u", days_ahead=0)
    assert far == []


def test_task_flow(tmp_path):
    c = _commands(tmp_path)
    assert "added" in c.tarefa("u", "comprar pão")
    assert "comprar pão" in c.tarefas("u")
    assert "completed" in c.concluir("u", "1")
    assert "empty" in c.tarefas("u")


def test_task_category(tmp_path):
    c = _commands(tmp_path)
    out = c.tarefa("u", "estudar cálculo #faculdade")
    assert "faculdade" in out
    listing = c.tarefas("u", "faculdade")
    assert "estudar cálculo" in listing
    assert "#faculdade" not in listing  # tag stripped from the stored text
    assert "No tasks" in c.tarefas("u", "trabalho")


def test_buscar_usage(tmp_path):
    c = _commands(tmp_path)
    assert "Usage:" in c.buscar("")


def test_unified_search(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "estudar cálculo #faculdade")
    c.link("u", "faculdade | grade | http://x")
    assert "Usage:" in c.procurar("u", "")
    out = c.procurar("u", "cálculo")
    assert "estudar cálculo" in out
    assert "nothing found" in c.procurar("u", "zzzznada").lower()


def test_expenses(tmp_path):
    c = _commands(tmp_path)
    assert "50.00" in c.gasto("u", "50 mercado #casa")
    c.gasto("u", "20,50 uber")
    out = c.gastos("u")
    assert "70.50" in out and "casa" in out


def test_habits(tmp_path):
    c = _commands(tmp_path)
    assert "created" in c.habito("u", "treino")
    assert "already exists" in c.habito("u", "treino")
    assert "done today" in c.feito("u", "treino")
    assert "Streak: 1" in c.feito("u", "treino")  # already marked today
    assert "[x] treino" in c.habitos("u")


def test_journal(tmp_path):
    c = _commands(tmp_path)
    assert "empty" in c.diario("u", "")
    assert "Noted" in c.diario("u", "hoje foi um bom dia")
    assert "bom dia" in c.diario("u", "")


def test_weekly_review(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "estudar")
    c.concluir("u", "1")
    c.gasto("u", "30 mercado")
    out = c.semana("u")
    assert "Your week" in out
    assert "completed: 1" in out


def test_report_current_vs_previous_month(tmp_path):
    c = _commands(tmp_path)
    # empty month -> friendly message
    assert "no expenses" in c.relatorio("u").lower()
    c.gasto("u", "50 mercado #comida")
    # default report = CURRENT month, so a just-added expense shows up
    cur = c.relatorio("u")
    assert "report" in cur and "50" in cur and "comida" in cur
    # previous month (offset=-1) has nothing yet, and its label differs
    prev = c.relatorio("u", offset=-1)
    assert "no expenses" in prev.lower()
    assert c._month_bounds(0)[0] != c._month_bounds(-1)[0]


def test_month_bounds_are_utc_iso(tmp_path):
    # boundaries must be UTC ISO (matches how expenses.created is stored), so a
    # lexical DB comparison equals a chronological one.
    c = _commands(tmp_path)
    label, start, end = c._month_bounds(0)
    assert start.endswith("+00:00") and end.endswith("+00:00")
    assert start < end and len(label) == 7  # 'MM/YYYY'


def test_edit_by_name_expense_and_reminder(tmp_path):
    c = _commands(tmp_path)
    c.gasto("u", "50 mercado #casa")
    out = c.gastoeditar("u", "mercado | 65 mercado grande #lazer")
    assert "updated" in out
    e = c._memory.expenses_since("u", "2000-01-01")[0]
    assert e["amount"] == 65.0 and e["description"] == "mercado grande" and e["category"] == "lazer"
    c.lembrete("u", "amanhã 09:00 pagar conta")
    assert "updated" in c.lembreteeditar("u", "pagar conta | pagar aluguel")
    assert c._memory.open_reminders("u")[0]["text"] == "pagar aluguel"
    assert "couldn't find" in c.gastoeditar("u", "inexistente | 10").lower()


def test_delete_by_name_across_types(tmp_path):
    c = _commands(tmp_path)
    c.gasto("u", "50 mercado #casa")
    assert "deleted" in c.gastorm("u", "mercado")
    c.lembrete("u", "10m tomar remédio")
    assert "canceled" in c.cancelar("u", "remédio")
    c.lembrar("u", "gosto de café")
    assert "Forgot" in c.esquecer("u", "café")
    c.link("u", "dev | github | http://x")
    assert "removed" in c.linkrm("u", "github")
    # name that doesn't exist -> friendly message, not a crash
    assert "couldn't find" in c.gastorm("u", "inexistente").lower()


def test_task_crud_by_name(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "comprar leite #mercado")
    # complete by name (not id)
    assert "completed" in c.concluir("u", "comprar leite")
    assert c._memory.open_tasks("u") == []
    # edit by name
    c.tarefa("u", "estudar")
    assert "updated" in c.tarefaeditar("u", "estudar | estudar cálculo #faculdade")
    t = c._memory.open_tasks("u")[0]
    assert t["text"] == "estudar cálculo" and t["category"] == "faculdade"
    # delete by name
    assert "deleted" in c.tarefarm("u", "estudar")
    assert c._memory.open_tasks("u") == []
    # ambiguous name -> asks which
    c.tarefa("u", "reunião manhã"); c.tarefa("u", "reunião tarde")
    assert "more than one" in c.concluir("u", "reunião").lower()


def test_watches(tmp_path):
    c = _commands(tmp_path)
    assert "created" in c.vigiar("u", "https://exemplo.com | vaga aberta")
    assert "exemplo.com" in c.vigias("u")
    assert "removed" in c.vigiarm("u", "1")


def test_command_output_follows_language(tmp_path):
    # deterministic command replies follow assistant_lang (English default / PT)
    c = _commands(tmp_path)
    # English default
    assert "Your task list is empty." in c.tarefas("u")
    assert "monitors" in c.vigias("u").lower()
    assert "Your week" in c.semana("u")
    assert "knowledge base empty" in c.kb("u").lower()
    # Portuguese
    c._memory.set_assistant_lang("pt")
    assert "vazia" in c.tarefas("u").lower()
    assert "monitores" in c.vigias("u").lower()
    assert "Sua semana" in c.semana("u")
    assert "base de conhecimento vazia" in c.kb("u").lower()


def test_budget_alert(tmp_path):
    c = _commands(tmp_path)
    assert "set" in c.orcamento("u", "comida 100")
    warn = c.gasto("u", "85 mercado #comida")  # 85% of the limit
    assert "budget" in warn.lower()
    # the alert is also recorded in the notification center
    notifs = c._memory.list_notifications("u")
    assert notifs and "Budget" in notifs[0]["title"]
    assert "comida" in c.orcamentos("u")
    assert "removed" in c.orcamentorm("u", "comida")


def test_recurring_expense(tmp_path):
    c = _commands(tmp_path)
    out = c.assinatura("u", "39,90 Netflix 15")
    assert "Netflix" in out and "day 15" in out
    assert "Netflix" in c.assinaturas("u")
    assert "removed" in c.assinaturarm("u", "1")


def test_delete_operations(tmp_path):
    c = _commands(tmp_path)
    c._memory.add_fact("u", "gosto de café")
    assert "#1" in c.memorias("u")
    assert "Forgot" in c.esquecer("u", "1")
    assert "couldn't find" in c.esquecer("u", "1").lower()

    c.gasto("u", "10 pão")
    assert "deleted" in c.gastorm("u", "1")

    c.habito("u", "treino")
    assert "removed" in c.habitorm("u", "treino")

    c.diario("u", "entrada teste")
    assert "deleted" in c.diariorm("u", "1")


def test_reminder_command(tmp_path):
    c = _commands(tmp_path)
    out = c.lembrete("u", "10m tomar água")
    assert "created" in out
    assert "tomar água" in c.lembretes("u")


def test_link_flow(tmp_path):
    c = _commands(tmp_path)
    assert "saved" in c.link("u", "faculdade | grade | http://x")
    listing = c.links("u", "")
    assert "grade" in listing and "faculdade" in listing


def test_google_disabled(tmp_path):
    c = _commands(tmp_path)
    assert "isn't set up" in c.agenda()
    assert "isn't set up" in c.email("a@b.com | oi | teste")
    # reading needs IMAP creds, not Google
    assert "isn't set up" in c.emails().lower()


def test_inbox_summary_formatting(monkeypatch):
    from ev.providers import tools
    monkeypatch.setattr(tools, "list_emails", lambda *a, **k: [
        {"from": "Banco", "subject": "Fatura", "date": "", "snippet": "", "unread": True}])
    out = tools.inbox_summary(None, "", "")
    assert "Fatura" in out and "Banco" in out and "#1" in out
    # empty inbox -> friendly line (English is the default; pt when asked)
    monkeypatch.setattr(tools, "list_emails", lambda *a, **k: [])
    assert "no new emails" in tools.inbox_summary(None, "", "").lower()
    assert "nenhum e-mail" in tools.inbox_summary(None, "", "", lang="pt").lower()
    # not-configured -> tells the user to set the IMAP creds
    def _boom(*a, **k):
        raise RuntimeError("imap-not-configured")
    monkeypatch.setattr(tools, "list_emails", _boom)
    assert "isn't set up" in tools.inbox_summary(None, "", "").lower()
    assert "não configurada" in tools.inbox_summary(None, "", "", lang="pt").lower()


def test_imap_query_mapping():
    from ev.providers import tools
    assert tools._imap_query("") == ("UNSEEN",)
    assert tools._imap_query("is:unread") == ("UNSEEN",)
    assert tools._imap_query("fatura") == ("TEXT", "fatura")


def test_provider_tool_strings_follow_lang(monkeypatch):
    """Tool result/error strings default to English and switch to Portuguese
    when lang='pt' — the last user-facing i18n slice (tool outputs)."""
    import httpx

    from ev.providers import tools

    # weather: city-not-found message (geocode returns no results, no network).
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [], "web": {"results": []}}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    assert "couldn't find the city" in tools.weather("Nowhere").lower()
    assert "não achei a cidade" in tools.weather("Nowhere", lang="pt").lower()

    # websearch: nothing-found message (Brave path, empty results).
    en = tools.web_search("x", brave_key="k")
    pt = tools.web_search("x", brave_key="k", lang="pt")
    assert "couldn't find anything relevant" in en.lower()
    assert "não achei nada relevante" in pt.lower()


def test_bad_input(tmp_path):
    c = _commands(tmp_path)
    assert "Usage:" in c.tarefa("u", "")
    assert "time" in c.lembrete("u", "sem tempo aqui")


def test_resolve_account(tmp_path):
    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="x",
        google_accounts=("pessoal", "faculdade"),
        gemini_api_key="x",
        embed_backend="gemini",
        embed_model="m",
    )
    c = Commands(cfg, Memory(tmp_path / "t.db"))
    assert c._resolve_account("faculdade oi tudo bem") == ("faculdade", "oi tudo bem")
    assert c._resolve_account("oi tudo bem") == ("pessoal", "oi tudo bem")


def test_cancel_reminder(tmp_path):
    c = _commands(tmp_path)
    c.lembrete("u", "10m tomar água")
    assert "canceled" in c.cancelar("u", "1")
    assert "couldn't find" in c.cancelar("u", "1").lower()


def test_rotina(tmp_path):
    c = _commands(tmp_path)
    out = c.rotina("u", "diario 08:00 tomar remédio")
    assert "Routine" in out and "every day" in out
    assert "[every day]" in c.lembretes("u")
    assert "invalid" in c.rotina("u", "anual 08:00 x").lower()


def test_receipt_json_parsing():
    from ev.core.brain import Brain
    p = Brain._parse_receipt_json
    assert p('{"valor": 42.5, "descricao": "Mercado X", "categoria": "Mercado"}') == {
        "amount": 42.5, "description": "Mercado X", "category": "mercado"}
    # comma decimal + text around the JSON
    r = p('claro! {"valor":"19,90","descricao":"Uber","categoria":"transporte"} pronto')
    assert r["amount"] == 19.9 and r["category"] == "transporte"
    # not a receipt / zero / garbage -> None
    assert p('{"valor": 0}') is None
    assert p('sem json') is None


def test_people_memory_and_birthdays(tmp_path):
    c = _commands(tmp_path)
    assert "No people" in c.pessoas("u")
    assert "Noted" in c.pessoa("u", "Ana | irmã, ama café | 12/03")
    out = c.pessoas("u")
    assert "Ana" in out and "irmã" in out and "03-12" in out
    # view by name
    assert "café" in c.pessoa("u", "Ana")
    # update appends notes, keeps birthday
    c.pessoa("u", "Ana | trabalha com design")
    v = c.pessoa("u", "ana")
    assert "design" in v and "café" in v
    # birthday lookup by MM-DD
    bd = c._memory.birthdays_on("u", "03-12")
    assert bd and bd[0]["name"] == "Ana"


def test_birthday_normalization(tmp_path):
    m = _commands(tmp_path)._memory
    assert m._norm_bday("12/03") == "03-12"       # DD/MM (Brazilian)
    assert m._norm_bday("12/03/1998") == "1998-03-12"
    assert m._norm_bday("1998-03-12") == "1998-03-12"
    assert m._norm_bday("") == ""


def test_chat_image_persistence(tmp_path):
    from ev.core.memory import Memory
    m = Memory(tmp_path / "t.db")
    conv = "web:geral"
    m.add_message(conv, "user", "O que há nesta imagem?")
    m.add_message(conv, "model", "é um gato")
    iid = m.add_chat_image(conv, b"\x89PNG-fake-bytes", "image/png")
    m.mark_last_user_image(conv, iid)
    got = m.get_chat_image(iid)
    assert got and got["data"] == b"\x89PNG-fake-bytes" and got["mime"] == "image/png"
    user = [x for x in m.recent_messages(conv, 10) if x["role"] == "user"][-1]
    assert f"[img:{iid}]" in user["content"]
    assert m.get_chat_image(999999) is None


def test_places_crud(tmp_path):
    from ev.core.memory import Memory
    m = Memory(tmp_path / "t.db")
    pid = m.add_place("u", "Casa", -23.55, -46.63)
    assert [p["name"] for p in m.list_places("u")] == ["Casa"]
    m.add_place("u", "Trabalho", -23.56, -46.64)
    assert len(m.list_places("u")) == 2
    m.delete_place("u", pid)
    assert [p["name"] for p in m.list_places("u")] == ["Trabalho"]


def test_haversine_and_kinds(tmp_path):
    from ev.providers import tools
    # ~1.1 km per 0.01 deg latitude
    d = tools._haversine_m(-23.55, -46.63, -23.56, -46.63)
    assert 1000 < d < 1200
    assert "farmácia" in tools._OSM_KINDS and "restaurante" in tools._OSM_KINDS


def test_clear_facts(tmp_path):
    from ev.core.memory import Memory
    m = Memory(tmp_path / "t.db")
    m.add_fact("u", "gosto de café")
    m.add_fact("u", "moro em SP")
    assert len(m.list_facts("u")) == 2
    assert m.clear_facts("u") == 2
    assert m.list_facts("u") == []
