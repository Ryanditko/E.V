"""E.V.'s terminal interface — a simple text REPL.

Reuses the exact same brain as the Telegram bot; only the I/O changes. Useful
for quick local testing and for chatting without Telegram. Text only (no voice).
"""

from __future__ import annotations

import asyncio

from ..config import Config
from ..core.brain import Brain
from ..core.memory import Memory

_USER_ID = "terminal"  # own memory namespace for the terminal session
_QUIT = {"/sair", "/quit", "/exit", "sair"}


async def _repl(config: Config) -> None:
    memory = Memory(config.db_path)
    brain = Brain(config, memory)

    print("E.V. (terminal). Digite e aperte Enter. '/sair' para encerrar.\n")
    while True:
        try:
            text = (await asyncio.to_thread(input, "você > ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in _QUIT:
            break
        answer = await brain.respond(_USER_ID, text=text)
        print(f"E.V.  > {answer}\n")

    print("Até mais!")


def run() -> None:
    # Terminal doesn't need the Telegram token.
    asyncio.run(_repl(Config.load(require_telegram=False)))
