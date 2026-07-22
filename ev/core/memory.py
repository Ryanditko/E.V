"""E.V.'s memory — local SQLite persistence.

Three things are stored:
  - messages:  conversation history (so E.V. has context).
  - facts:     long-term facts about the user, each with an optional embedding
               for semantic recall.
  - reminders: reminders the user asked for.

Everything local, in a single .db file. Deliberately simple — it can grow into a
proper vector store later without changing the interfaces.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class Memory:
    def __init__(self, db_path: Path) -> None:
        # check_same_thread=False because the bot is async and may touch the DB
        # from different tasks. Writes here are short and serialized.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                role     TEXT NOT NULL,   -- 'user' or 'model'
                content  TEXT NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                fact      TEXT NOT NULL,
                embedding TEXT,           -- JSON float array, optional
                created   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                text     TEXT NOT NULL,
                when_iso TEXT,            -- ISO 8601, optional
                done     INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL
            );
            """
        )
        # Migration: add `embedding` to older DBs that predate semantic memory.
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(facts)")}
        if "embedding" not in cols:
            self._conn.execute("ALTER TABLE facts ADD COLUMN embedding TEXT")
        self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # --- conversation history ----------------------------------------------

    def add_message(self, user_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (user_id, role, content, created) "
            "VALUES (?, ?, ?, ?)",
            (user_id, role, content, self._now()),
        )
        self._conn.commit()

    def recent_messages(self, user_id: str, limit: int = 20) -> list[dict]:
        """Last `limit` messages, chronological (oldest first)."""
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # --- facts (long-term memory) ------------------------------------------

    def add_fact(
        self, user_id: str, fact: str, embedding: list[float] | None = None
    ) -> None:
        self._conn.execute(
            "INSERT INTO facts (user_id, fact, embedding, created) "
            "VALUES (?, ?, ?, ?)",
            (
                user_id,
                fact,
                json.dumps(embedding) if embedding else None,
                self._now(),
            ),
        )
        self._conn.commit()

    def all_facts(self, user_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT fact FROM facts WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [r["fact"] for r in rows]

    def relevant_facts(
        self, user_id: str, query_embedding: list[float] | None, k: int = 8
    ) -> list[str]:
        """Top-k facts most similar to the query embedding.

        Falls back to all facts when there is no query embedding or none of the
        stored facts have embeddings yet.
        """
        rows = self._conn.execute(
            "SELECT fact, embedding FROM facts WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        if not rows:
            return []
        if query_embedding is None:
            return [r["fact"] for r in rows]

        scored: list[tuple[float, str]] = []
        any_embedded = False
        for r in rows:
            if r["embedding"]:
                any_embedded = True
                score = _cosine(query_embedding, json.loads(r["embedding"]))
            else:
                score = 0.0
            scored.append((score, r["fact"]))

        if not any_embedded:
            return [r["fact"] for r in rows]

        scored.sort(key=lambda s: s[0], reverse=True)
        return [fact for _, fact in scored[:k]]

    # --- reminders ----------------------------------------------------------

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

    def pending_reminders(self) -> list[dict]:
        """All open reminders that have a scheduled time (across all users).

        The scheduler parses `when_iso` and compares by real datetime — robust to
        different timezone offsets, unlike a lexical string comparison.
        """
        rows = self._conn.execute(
            "SELECT id, user_id, text, when_iso FROM reminders "
            "WHERE done = 0 AND when_iso IS NOT NULL ORDER BY when_iso"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_done(self, reminder_id: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()
