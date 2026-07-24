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
