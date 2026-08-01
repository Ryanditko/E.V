"""The AI's executar_comando routes data-commands to Commands.run and
interface-commands to a queue drained by the Telegram layer. These two sides
must stay in sync and not overlap."""

from types import SimpleNamespace

from ev.core.brain import _INTERFACE_COMMANDS
from ev.core.commands import Commands
from ev.core.memory import Memory
from ev.interfaces.telegram_bot import TelegramInterface


def test_interface_command_sets_match():
    # Every command the brain queues must have a handler in the interface.
    assert set(TelegramInterface._AI_INTERFACE_CMDS) == set(_INTERFACE_COMMANDS)


def test_no_overlap_between_data_and_interface(tmp_path):
    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo", google_oauth_client="", google_accounts=(),
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
    )
    data_cmds = set(Commands(cfg, Memory(tmp_path / "t.db")).runnable())
    assert data_cmds.isdisjoint(_INTERFACE_COMMANDS)


def test_google_tool_wrappers_pass_account(tmp_path, monkeypatch):
    """ver_agenda / criar_evento / enviar_email must call the tools layer with the
    account argument (a regression: they used to drop it -> TypeError at runtime)."""
    from ev.core.brain import Brain
    from ev.providers import tools as tools_mod

    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo", google_oauth_client="client.json",
        google_accounts=("pessoal",), default_account="pessoal",
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
        model="gemini-flash-latest",
        groq_api_key="", openrouter_api_key="", ollama_enabled=False,
        tavily_api_key="", brave_api_key="", websearch_enabled=False,
    )
    brain = Brain(cfg, Memory(tmp_path / "t.db"))
    calls = {}
    monkeypatch.setattr(tools_mod, "calendar_upcoming",
                        lambda c, acct, *a, **k: calls.update(agenda=acct) or "ok")
    monkeypatch.setattr(tools_mod, "calendar_create",
                        lambda c, acct, s, si, ei: calls.update(evento=(acct, s, si, ei)) or "ok")
    monkeypatch.setattr(tools_mod, "send_email",
                        lambda c, acct, to, subj, body: calls.update(email=(acct, to, subj, body)) or "ok")
    fns = brain._tool_callables("u")
    assert fns["ver_agenda"]() == "ok"
    assert fns["criar_evento"]("Dentista", "2026-08-02T19:00", "2026-08-02T20:00") == "ok"
    assert fns["enviar_email"]("a@b.com", "Oi", "Corpo") == "ok"
    assert calls["agenda"] == "pessoal"
    assert calls["evento"] == ("pessoal", "Dentista", "2026-08-02T19:00", "2026-08-02T20:00")
    assert calls["email"] == ("pessoal", "a@b.com", "Oi", "Corpo")


def test_executar_comando_handles_inline_args(tmp_path):
    """The model sometimes puts args in `comando` ("tarefa comprar pão"); that
    must still route to the right command instead of "não conheço"."""
    from ev.core.brain import Brain

    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo", google_oauth_client="", google_accounts=(),
        default_account="", gemini_api_key="x", embed_backend="gemini",
        embed_model="m", model="gemini-flash-latest", groq_api_key="",
        openrouter_api_key="", ollama_enabled=False, tavily_api_key="",
        brave_api_key="", websearch_enabled=False,
    )
    brain = Brain(cfg, Memory(tmp_path / "t.db"))
    ec = brain._tool_callables("u")["executar_comando"]
    assert "adicionada" in ec("tarefa comprar pão #casa")   # args inside comando
    assert "adicionada" in ec("tarefa", "estudar #faculdade")  # normal form
    assert "comprar pão" in brain._commands.tarefas("u")


def test_event_alert_lead_window():
    from ev.interfaces.telegram_bot import TelegramInterface as TI
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    f = TI._alert_lead_minutes
    # 20 min ahead, lead 30 -> alert (20)
    assert f((now + timedelta(minutes=20)).isoformat(), now, 30) == 20
    # 45 min ahead, lead 30 -> out of window
    assert f((now + timedelta(minutes=45)).isoformat(), now, 30) is None
    # already started -> None
    assert f((now - timedelta(minutes=5)).isoformat(), now, 30) is None
    # tz-naive start is treated as UTC
    assert f("2026-08-01T12:10:00", now, 30) == 10
    # garbage -> None
    assert f("nope", now, 30) is None


def test_location_tools(tmp_path, monkeypatch):
    from ev.core.brain import Brain
    from ev.providers import tools
    assert "google.com/maps" in tools.maps_search_link(-23.5, -46.6, "farmácia")
    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo", google_oauth_client="", google_accounts=(),
        default_account="", gemini_api_key="x", embed_backend="gemini",
        embed_model="m", model="gemini-flash-latest", groq_api_key="",
        openrouter_api_key="", ollama_enabled=False, tavily_api_key="",
        brave_api_key="", websearch_enabled=False,
    )
    b = Brain(cfg, Memory(tmp_path / "t.db"))
    fns = b._tool_callables("u")
    # no location yet -> guidance
    assert "não sei" in fns["locais_proximos"]("farmácia").lower()
    assert "não sei" in fns["minha_localizacao"]().lower() or "ainda não" in fns["minha_localizacao"]().lower()
    assert "não salvou" in fns["meus_locais"]().lower()
    # with location + mocked OSM lookup -> a real list (name + distance)
    b._memory.set_setting("loc_lat", "-23.5"); b._memory.set_setting("loc_lng", "-46.6")
    monkeypatch.setattr(tools, "nearby_places", lambda *a, **k: [
        {"name": "Drogaria X", "lat": -23.5, "lng": -46.6, "dist": 120, "kind": "pharmacy"}])
    out = fns["locais_proximos"]("farmácia")
    assert "Drogaria X" in out and "120" in out
    assert "-23.5" in fns["minha_localizacao"]()
    # saved places surface via meus_locais
    b._memory.add_place("u", "Casa", -23.5, -46.6)
    assert "Casa" in fns["meus_locais"]()
    # salvar_local by address (geocode mocked)
    monkeypatch.setattr(tools, "geocode",
                        lambda q: {"lat": -23.4, "lng": -46.5, "name": q})
    assert "salvo" in fns["salvar_local"]("Faculdade", "Rua X, 123").lower()
    assert any(p["name"] == "Faculdade" for p in b._memory.list_places("u"))
