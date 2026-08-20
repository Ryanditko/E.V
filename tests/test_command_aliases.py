"""English command aliases + localized command menu.

Every slash command has an English name and a Portuguese name; both dispatch to
the same method (non-breaking). The command menu/palette follows the assistant
language, and the proactive nudge notification title is localized.
"""

from types import SimpleNamespace

from ev.core.commands import Commands, COMMAND_LIST, command_list
from ev.core.commands.base import _COMMANDS, _EN_TO_PT
from ev.core.i18n import t
from ev.core.memory import Memory


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="", google_accounts=(),
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
    )
    return Commands(config, Memory(tmp_path / "t.db"))


def test_en_and_pt_names_dispatch_to_same_method(tmp_path):
    # Interface-only commands (plan, mute, status, ...) live outside _dispatch;
    # for every command the AI CAN run, the EN alias must reach the same method.
    d = _commands(tmp_path)._dispatch()
    checked = 0
    for en, pt in _EN_TO_PT.items():
        if pt not in d:
            continue
        assert en in d, f"missing EN alias {en}"
        assert d[en] is d[pt], f"{en} and {pt} should map to the same callable"
        checked += 1
    assert checked > 20  # sanity: most commands are dispatchable


def test_english_alias_runs_same_as_portuguese(tmp_path):
    c = _commands(tmp_path)
    # /reminders (en) and /lembretes (pt) both list reminders
    assert c.run("u", "reminders", "") == c.run("u", "lembretes", "")
    # /task then /complete (english names) works end-to-end
    assert "added" in c.run("u", "task", "buy bread")
    assert "completed" in c.run("u", "complete", "buy bread").lower()


def test_portuguese_names_still_work(tmp_path):
    c = _commands(tmp_path)
    out = c.run("u", "tarefa", "comprar pão")
    assert "added" in out and "don't know" not in out.lower()
    # PT name dispatches (reply language follows assistant_lang, default en)
    assert "completed" in c.run("u", "concluir", "comprar pão").lower()


def test_command_names_are_unique():
    seen: dict[str, str] = {}
    for en, pt, _, _ in _COMMANDS:
        for name in ({en, pt}):
            assert name not in seen, f"duplicate command name {name} ({seen.get(name)})"
            seen[name] = en
    for alias in _EN_TO_PT:
        # dispatch-only aliases must not collide with any menu name
        if alias not in {e for e, _, _, _ in _COMMANDS}:
            assert alias not in seen, f"alias {alias} collides with a command name"


def test_command_list_english():
    en = command_list("en")
    names = {n for n, _ in en}
    assert ("focus", "Toggle FOCUS MODE (red interface, tactical tone)") in en
    assert "reminders" in names and "complete" in names and "expense" in names
    assert "lembretes" not in names  # english menu has no PT names
    assert COMMAND_LIST == en  # backward-compatible export defaults to English


def test_command_list_portuguese():
    pt = command_list("pt")
    names = {n for n, _ in pt}
    assert ("modo", "Liga/desliga o MODO FOCO (interface vermelha, tom tático)") in pt
    assert "lembretes" in names and "concluir" in names and "gasto" in names
    assert "reminders" not in names  # portuguese menu has no EN names


def test_command_list_same_length():
    assert len(command_list("en")) == len(command_list("pt")) == len(_COMMANDS)


def test_nudge_title_localized():
    assert t("en", "notif.nudge_title") == "👋 E.V. checking in"
    assert t("pt", "notif.nudge_title") == "👋 E.V. te cobrando"
    assert t("en", "notif.nudge_title") != t("pt", "notif.nudge_title")
