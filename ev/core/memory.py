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
                recur    TEXT,            -- 'daily' | 'weekly' | NULL (one-off)
                done     INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                text     TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'geral',
                done     INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS links (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                category TEXT NOT NULL,
                name     TEXT NOT NULL,
                url      TEXT NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                source    TEXT NOT NULL,   -- e.g. the document name
                chunk     TEXT NOT NULL,
                embedding TEXT,            -- JSON float array
                created   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                amount      REAL NOT NULL,
                description TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'geral',
                created     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habits (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name    TEXT NOT NULL,
                created TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habit_logs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL,
                day      TEXT NOT NULL       -- YYYY-MM-DD
            );

            CREATE TABLE IF NOT EXISTS journal (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                text    TEXT NOT NULL,
                created TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watches (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                url      TEXT NOT NULL,
                keyword  TEXT,               -- optional: alert when this appears
                state    TEXT,               -- last seen hash / keyword-present flag
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recurring_expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                amount      REAL NOT NULL,
                description TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'assinatura',
                day         INTEGER NOT NULL,   -- day of month to log
                last_month  TEXT,               -- 'YYYY-MM' already logged
                created     TEXT NOT NULL
            );
            """
        )
        # Migrations for older DBs.
        fact_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(facts)")}
        if "embedding" not in fact_cols:
            self._conn.execute("ALTER TABLE facts ADD COLUMN embedding TEXT")
        rem_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(reminders)")}
        if "recur" not in rem_cols:
            self._conn.execute("ALTER TABLE reminders ADD COLUMN recur TEXT")
        task_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(tasks)")}
        if "category" not in task_cols:
            self._conn.execute(
                "ALTER TABLE tasks ADD COLUMN category TEXT NOT NULL DEFAULT 'geral'"
            )
        if "done_at" not in task_cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN done_at TEXT")
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

    def list_facts(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, fact FROM facts WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_fact(self, user_id: str, fact_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM facts WHERE id = ? AND user_id = ?", (fact_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

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

    def add_reminder(
        self, user_id: str, text: str, when_iso: str | None, recur: str | None = None
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders (user_id, text, when_iso, recur, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, text, when_iso, recur, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def open_reminders(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, when_iso, recur FROM reminders "
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
            "SELECT id, user_id, text, when_iso, recur FROM reminders "
            "WHERE done = 0 AND when_iso IS NOT NULL ORDER BY when_iso"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_done(self, reminder_id: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()

    def reschedule_reminder(self, reminder_id: int, new_when_iso: str) -> None:
        """Move a (recurring) reminder to its next occurrence, keeping it open."""
        self._conn.execute(
            "UPDATE reminders SET when_iso = ? WHERE id = ?",
            (new_when_iso, reminder_id),
        )
        self._conn.commit()

    def cancel_reminder(self, user_id: str, reminder_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ? AND user_id = ? AND done = 0",
            (reminder_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- tasks (to-do list) -------------------------------------------------

    def add_task(self, user_id: str, text: str, category: str = "geral") -> int:
        cur = self._conn.execute(
            "INSERT INTO tasks (user_id, text, category, created) VALUES (?, ?, ?, ?)",
            (user_id, text, category, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def open_tasks(self, user_id: str, category: str | None = None) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT id, text, category FROM tasks "
                "WHERE user_id = ? AND done = 0 AND category = ? ORDER BY id",
                (user_id, category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, text, category FROM tasks "
                "WHERE user_id = ? AND done = 0 ORDER BY category, id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def complete_task(self, user_id: str, task_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE tasks SET done = 1, done_at = ? WHERE id = ? AND user_id = ? AND done = 0",
            (self._now(), task_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def tasks_completed_since(self, user_id: str, since_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM tasks "
            "WHERE user_id = ? AND done = 1 AND done_at >= ?",
            (user_id, since_iso),
        ).fetchone()
        return int(row["n"])

    # --- links (named, categorized) ----------------------------------------

    def add_link(self, user_id: str, category: str, name: str, url: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO links (user_id, category, name, url, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, category, name, url, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_links(self, user_id: str, category: str | None = None) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT id, category, name, url FROM links "
                "WHERE user_id = ? AND category = ? ORDER BY id",
                (user_id, category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, category, name, url FROM links "
                "WHERE user_id = ? ORDER BY category, id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_link(self, user_id: str, link_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM links WHERE id = ? AND user_id = ?", (link_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- knowledge base (document chunks) ----------------------------------

    def add_chunk(
        self, user_id: str, source: str, chunk: str, embedding: list[float] | None
    ) -> None:
        self._conn.execute(
            "INSERT INTO knowledge (user_id, source, chunk, embedding, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                user_id,
                source,
                chunk,
                json.dumps(embedding) if embedding else None,
                self._now(),
            ),
        )
        self._conn.commit()

    def search_knowledge(
        self, user_id: str, query_embedding: list[float] | None, k: int = 4
    ) -> list[dict]:
        """Top-k knowledge chunks most similar to the query (empty if none)."""
        if query_embedding is None:
            return []
        rows = self._conn.execute(
            "SELECT source, chunk, embedding FROM knowledge WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        scored: list[tuple[float, dict]] = []
        for r in rows:
            if not r["embedding"]:
                continue
            score = _cosine(query_embedding, json.loads(r["embedding"]))
            scored.append((score, {"source": r["source"], "chunk": r["chunk"]}))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [item for score, item in scored[:k] if score > 0.1]

    def list_sources(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT source, COUNT(*) AS chunks FROM knowledge "
            "WHERE user_id = ? GROUP BY source ORDER BY source",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_source(self, user_id: str, source: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM knowledge WHERE user_id = ? AND source = ?",
            (user_id, source),
        )
        self._conn.commit()
        return cur.rowcount

    # --- expenses -----------------------------------------------------------

    def add_expense(
        self, user_id: str, amount: float, description: str, category: str = "geral"
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO expenses (user_id, amount, description, category, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, description, category, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def expenses_since(self, user_id: str, since_iso: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, amount, description, category FROM expenses "
            "WHERE user_id = ? AND created >= ? ORDER BY id",
            (user_id, since_iso),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_expense(self, user_id: str, expense_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- habits -------------------------------------------------------------

    def add_habit(self, user_id: str, name: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO habits (user_id, name, created) VALUES (?, ?, ?)",
            (user_id, name, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_habits(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name FROM habits WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_habit(self, user_id: str, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name FROM habits WHERE user_id = ? AND LOWER(name) = LOWER(?)",
            (user_id, name),
        ).fetchone()
        return dict(row) if row else None

    def log_habit(self, habit_id: int, day: str) -> bool:
        """Mark a habit done on `day` (YYYY-MM-DD). Returns False if already logged."""
        exists = self._conn.execute(
            "SELECT 1 FROM habit_logs WHERE habit_id = ? AND day = ?", (habit_id, day)
        ).fetchone()
        if exists:
            return False
        self._conn.execute(
            "INSERT INTO habit_logs (habit_id, day) VALUES (?, ?)", (habit_id, day)
        )
        self._conn.commit()
        return True

    def delete_habit(self, user_id: str, habit_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id)
        )
        self._conn.execute("DELETE FROM habit_logs WHERE habit_id = ?", (habit_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def habit_days(self, habit_id: int) -> set[str]:
        rows = self._conn.execute(
            "SELECT day FROM habit_logs WHERE habit_id = ?", (habit_id,)
        ).fetchall()
        return {r["day"] for r in rows}

    # --- journal ------------------------------------------------------------

    def add_journal(self, user_id: str, text: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO journal (user_id, text, created) VALUES (?, ?, ?)",
            (user_id, text, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent_journal(self, user_id: str, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, created FROM journal WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def delete_journal(self, user_id: str, entry_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM journal WHERE id = ? AND user_id = ?", (entry_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- web watches --------------------------------------------------------

    def add_watch(self, user_id: str, url: str, keyword: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO watches (user_id, url, keyword, created) VALUES (?, ?, ?, ?)",
            (user_id, url, keyword, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_watches(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, url, keyword FROM watches WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_watch(self, user_id: str, watch_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM watches WHERE id = ? AND user_id = ?", (watch_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def all_watches(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, user_id, url, keyword, state FROM watches ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def set_watch_state(self, watch_id: int, state: str) -> None:
        self._conn.execute(
            "UPDATE watches SET state = ? WHERE id = ?", (state, watch_id)
        )
        self._conn.commit()

    # --- recurring expenses (subscriptions) --------------------------------

    def add_recurring(
        self, user_id: str, amount: float, description: str, category: str, day: int
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO recurring_expenses "
            "(user_id, amount, description, category, day, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, description, category, day, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_recurring(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, amount, description, category, day FROM recurring_expenses "
            "WHERE user_id = ? ORDER BY day, id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_recurring(self, user_id: str, rec_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM recurring_expenses WHERE id = ? AND user_id = ?",
            (rec_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def due_recurring(self, day: int, month_str: str) -> list[dict]:
        """Recurring expenses whose day is today and not yet logged this month."""
        rows = self._conn.execute(
            "SELECT id, user_id, amount, description, category FROM recurring_expenses "
            "WHERE day = ? AND (last_month IS NULL OR last_month != ?)",
            (day, month_str),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_recurring_logged(self, rec_id: int, month_str: str) -> None:
        self._conn.execute(
            "UPDATE recurring_expenses SET last_month = ? WHERE id = ?",
            (month_str, rec_id),
        )
        self._conn.commit()

    # --- backup -------------------------------------------------------------

    def backup(self, dest_path: Path) -> None:
        """Consistent online backup of the whole DB to `dest_path` (SQLite API)."""
        dest = sqlite3.connect(dest_path)
        try:
            self._conn.backup(dest)
        finally:
            dest.close()
