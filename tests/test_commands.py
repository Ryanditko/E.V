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


def test_task_flow(tmp_path):
    c = _commands(tmp_path)
    assert "adicionada" in c.tarefa("u", "comprar pão")
    assert "comprar pão" in c.tarefas("u")
    assert "concluída" in c.concluir("u", "1")
    assert "vazia" in c.tarefas("u")


def test_task_category(tmp_path):
    c = _commands(tmp_path)
    out = c.tarefa("u", "estudar cálculo #faculdade")
    assert "faculdade" in out
    listing = c.tarefas("u", "faculdade")
    assert "estudar cálculo" in listing
    assert "#faculdade" not in listing  # tag stripped from the stored text
    assert "Nenhuma" in c.tarefas("u", "trabalho")


def test_buscar_usage(tmp_path):
    c = _commands(tmp_path)
    assert "Uso:" in c.buscar("")


def test_unified_search(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "estudar cálculo #faculdade")
    c.link("u", "faculdade | grade | http://x")
    assert "Uso:" in c.procurar("u", "")
    out = c.procurar("u", "cálculo")
    assert "estudar cálculo" in out
    assert "nada encontrado" in c.procurar("u", "zzzznada").lower()


def test_expenses(tmp_path):
    c = _commands(tmp_path)
    assert "50.00" in c.gasto("u", "50 mercado #casa")
    c.gasto("u", "20,50 uber")
    out = c.gastos("u")
    assert "70.50" in out and "casa" in out


def test_habits(tmp_path):
    c = _commands(tmp_path)
    assert "criado" in c.habito("u", "treino")
    assert "já existe" in c.habito("u", "treino")
    assert "feito hoje" in c.feito("u", "treino")
    assert "Sequência: 1" in c.feito("u", "treino")  # already marked today
    assert "[x] treino" in c.habitos("u")


def test_journal(tmp_path):
    c = _commands(tmp_path)
    assert "vazio" in c.diario("u", "")
    assert "Anotado" in c.diario("u", "hoje foi um bom dia")
    assert "bom dia" in c.diario("u", "")


def test_weekly_review(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "estudar")
    c.concluir("u", "1")
    c.gasto("u", "30 mercado")
    out = c.semana("u")
    assert "Sua semana" in out
    assert "concluídas: 1" in out


def test_report_current_vs_previous_month(tmp_path):
    c = _commands(tmp_path)
    # empty month -> friendly message
    assert "nenhum gasto" in c.relatorio("u").lower()
    c.gasto("u", "50 mercado #comida")
    # default report = CURRENT month, so a just-added expense shows up
    cur = c.relatorio("u")
    assert "Relatório" in cur and "50" in cur and "comida" in cur
    # previous month (offset=-1) has nothing yet, and its label differs
    prev = c.relatorio("u", offset=-1)
    assert "nenhum gasto" in prev.lower()
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
    assert "atualizado" in out
    e = c._memory.expenses_since("u", "2000-01-01")[0]
    assert e["amount"] == 65.0 and e["description"] == "mercado grande" and e["category"] == "lazer"
    c.lembrete("u", "amanhã 09:00 pagar conta")
    assert "atualizado" in c.lembreteeditar("u", "pagar conta | pagar aluguel")
    assert c._memory.open_reminders("u")[0]["text"] == "pagar aluguel"
    assert "não achei" in c.gastoeditar("u", "inexistente | 10").lower()


def test_delete_by_name_across_types(tmp_path):
    c = _commands(tmp_path)
    c.gasto("u", "50 mercado #casa")
    assert "apagado" in c.gastorm("u", "mercado")
    c.lembrete("u", "10m tomar remédio")
    assert "cancelado" in c.cancelar("u", "remédio")
    c.lembrar("u", "gosto de café")
    assert "Esqueci" in c.esquecer("u", "café")
    c.link("u", "dev | github | http://x")
    assert "removido" in c.linkrm("u", "github")
    # name that doesn't exist -> friendly message, not a crash
    assert "não achei" in c.gastorm("u", "inexistente").lower()


def test_task_crud_by_name(tmp_path):
    c = _commands(tmp_path)
    c.tarefa("u", "comprar leite #mercado")
    # complete by name (not id)
    assert "concluída" in c.concluir("u", "comprar leite")
    assert c._memory.open_tasks("u") == []
    # edit by name
    c.tarefa("u", "estudar")
    assert "atualizada" in c.tarefaeditar("u", "estudar | estudar cálculo #faculdade")
    t = c._memory.open_tasks("u")[0]
    assert t["text"] == "estudar cálculo" and t["category"] == "faculdade"
    # delete by name
    assert "apagada" in c.tarefarm("u", "estudar")
    assert c._memory.open_tasks("u") == []
    # ambiguous name -> asks which
    c.tarefa("u", "reunião manhã"); c.tarefa("u", "reunião tarde")
    assert "mais de uma" in c.concluir("u", "reunião").lower()


def test_watches(tmp_path):
    c = _commands(tmp_path)
    assert "criado" in c.vigiar("u", "https://exemplo.com | vaga aberta")
    assert "exemplo.com" in c.vigias("u")
    assert "removido" in c.vigiarm("u", "1")


def test_budget_alert(tmp_path):
    c = _commands(tmp_path)
    assert "definido" in c.orcamento("u", "comida 100")
    warn = c.gasto("u", "85 mercado #comida")  # 85% of the limit
    assert "orçamento" in warn.lower()
    # the alert is also recorded in the notification center
    notifs = c._memory.list_notifications("u")
    assert notifs and "rçamento" in notifs[0]["title"]
    assert "comida" in c.orcamentos("u")
    assert "removido" in c.orcamentorm("u", "comida")


def test_recurring_expense(tmp_path):
    c = _commands(tmp_path)
    out = c.assinatura("u", "39,90 Netflix 15")
    assert "Netflix" in out and "dia 15" in out
    assert "Netflix" in c.assinaturas("u")
    assert "removida" in c.assinaturarm("u", "1")


def test_delete_operations(tmp_path):
    c = _commands(tmp_path)
    c._memory.add_fact("u", "gosto de café")
    assert "#1" in c.memorias("u")
    assert "Esqueci" in c.esquecer("u", "1")
    assert "não achei" in c.esquecer("u", "1").lower()

    c.gasto("u", "10 pão")
    assert "apagado" in c.gastorm("u", "1")

    c.habito("u", "treino")
    assert "removido" in c.habitorm("u", "treino")

    c.diario("u", "entrada teste")
    assert "apagada" in c.diariorm("u", "1")


def test_reminder_command(tmp_path):
    c = _commands(tmp_path)
    out = c.lembrete("u", "10m tomar água")
    assert "criado" in out
    assert "tomar água" in c.lembretes("u")


def test_link_flow(tmp_path):
    c = _commands(tmp_path)
    assert "salvo" in c.link("u", "faculdade | grade | http://x")
    listing = c.links("u", "")
    assert "grade" in listing and "faculdade" in listing


def test_google_disabled(tmp_path):
    c = _commands(tmp_path)
    assert "não configurada" in c.agenda()
    assert "não configurado" in c.email("a@b.com | oi | teste")
    # reading needs IMAP creds, not Google
    assert "não configurada" in c.emails().lower()


def test_inbox_summary_formatting(monkeypatch):
    from ev.providers import tools
    monkeypatch.setattr(tools, "list_emails", lambda *a, **k: [
        {"from": "Banco", "subject": "Fatura", "date": "", "snippet": "", "unread": True}])
    out = tools.inbox_summary(None, "", "")
    assert "Fatura" in out and "Banco" in out and "#1" in out
    # empty inbox -> friendly line
    monkeypatch.setattr(tools, "list_emails", lambda *a, **k: [])
    assert "nenhum e-mail" in tools.inbox_summary(None, "", "").lower()
    # not-configured -> tells the user to set the IMAP creds
    def _boom(*a, **k):
        raise RuntimeError("imap-not-configured")
    monkeypatch.setattr(tools, "list_emails", _boom)
    assert "não configurada" in tools.inbox_summary(None, "", "").lower()


def test_imap_query_mapping():
    from ev.providers import tools
    assert tools._imap_query("") == ("UNSEEN",)
    assert tools._imap_query("is:unread") == ("UNSEEN",)
    assert tools._imap_query("fatura") == ("TEXT", "fatura")


def test_bad_input(tmp_path):
    c = _commands(tmp_path)
    assert "Uso:" in c.tarefa("u", "")
    assert "horário" in c.lembrete("u", "sem tempo aqui")


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
    assert "cancelado" in c.cancelar("u", "1")
    assert "não achei" in c.cancelar("u", "1").lower()


def test_rotina(tmp_path):
    c = _commands(tmp_path)
    out = c.rotina("u", "diario 08:00 tomar remédio")
    assert "Rotina" in out and "todo dia" in out
    assert "[todo dia]" in c.lembretes("u")
    assert "inválida" in c.rotina("u", "anual 08:00 x").lower()


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
    assert "Nenhuma pessoa" in c.pessoas("u")
    assert "Anotado" in c.pessoa("u", "Ana | irmã, ama café | 12/03")
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
