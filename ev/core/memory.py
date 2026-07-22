"""Memória do E.V. — persistência local em SQLite.

Três coisas ficam guardadas:
  - `messages`: histórico da conversa (para o E.V. ter contexto).
  - `facts`:    fatos que o E.V. decidiu lembrar sobre o usuário.
  - `reminders`: lembretes que o usuário pediu.

Tudo local, num único arquivo .db. Simples de propósito — dá pra evoluir
para busca vetorial (embeddings) mais tarde sem mudar as interfaces.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Memory:
    def __init__(self, db_path: Path) -> None:
        # check_same_thread=False porque o bot é async e pode tocar o DB
        # de tasks diferentes. As escritas aqui são curtas e serializadas.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                role     TEXT NOT NULL,   -- 'user' ou 'model'
                content  TEXT NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                fact     TEXT NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                text     TEXT NOT NULL,
                when_iso TEXT,            -- ISO 8601, opcional
                done     INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # --- histórico de conversa ---------------------------------------------

    def add_message(self, user_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (user_id, role, content, created) "
            "VALUES (?, ?, ?, ?)",
            (user_id, role, content, self._now()),
        )
        self._conn.commit()

    def recent_messages(self, user_id: str, limit: int = 20) -> list[dict]:
        """Últimas `limit` mensagens, em ordem cronológica (mais antiga primeiro)."""
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # --- fatos (memória de longo prazo) ------------------------------------

    def add_fact(self, user_id: str, fact: str) -> None:
        self._conn.execute(
            "INSERT INTO facts (user_id, fact, created) VALUES (?, ?, ?)",
            (user_id, fact, self._now()),
        )
        self._conn.commit()

    def all_facts(self, user_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT fact FROM facts WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [r["fact"] for r in rows]

    # --- lembretes ----------------------------------------------------------

    def add_reminder(self, user_id: str, text: str, when_iso: str | None) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders (user_id, text, when_iso, created) "
            "VALUES (?, ?, ?, ?)",
            (user_id, text, when_iso, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def open_reminders(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, when_iso FROM reminders "
            "WHERE user_id = ? AND done = 0 ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
