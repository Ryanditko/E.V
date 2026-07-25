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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .timeparse import add_months


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

            CREATE TABLE IF NOT EXISTS budgets (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                category TEXT NOT NULL,
                amount   REAL NOT NULL,          -- monthly limit
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS flashcards (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                source   TEXT NOT NULL,
                question TEXT NOT NULL,
                answer   TEXT NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS usage_log (
                day      TEXT NOT NULL,
                provider TEXT NOT NULL,
                n        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, provider)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS kb_files (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                source   TEXT NOT NULL,   -- the friendly name used for its KB chunks
                filename TEXT NOT NULL,
                mime     TEXT,
                data     BLOB NOT NULL,
                created  TEXT NOT NULL
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
        if "recur" not in task_cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN recur TEXT")
        if "due" not in task_cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN due TEXT")
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

    def prune_messages(self, keep_per_user: int = 500) -> int:
        """Keep only the newest `keep_per_user` chat messages per user.

        Only trims raw conversation history (the brain uses just the last ~20);
        facts, tasks, reminders, etc. are never touched. Returns rows deleted.
        """
        cur = self._conn.execute(
            "DELETE FROM messages WHERE id IN ("
            "  SELECT id FROM messages m WHERE ("
            "    SELECT COUNT(*) FROM messages m2"
            "    WHERE m2.user_id = m.user_id AND m2.id > m.id"
            "  ) >= ?"
            ")",
            (keep_per_user,),
        )
        self._conn.commit()
        return cur.rowcount

    def clear_conversation(self, conv_id: str) -> int:
        """Delete all messages of one conversation thread (e.g. a web folder)."""
        cur = self._conn.execute("DELETE FROM messages WHERE user_id = ?", (conv_id,))
        self._conn.commit()
        return cur.rowcount

    def rename_conversation(self, old: str, new: str) -> int:
        """Move a conversation's messages to a new key (rename a folder)."""
        cur = self._conn.execute(
            "UPDATE messages SET user_id = ? WHERE user_id = ?", (new, old)
        )
        self._conn.commit()
        return cur.rowcount

    # --- storage control (user-owned data) ---------------------------------

    # key -> friendly label. Every table here is scoped by user_id (habit_logs
    # cascades from habits). usage_log/settings are NOT user data and excluded.
    DATA_TABLES = (
        ("messages", "conversa"),
        ("facts", "memórias"),
        ("reminders", "lembretes"),
        ("tasks", "tarefas"),
        ("links", "links"),
        ("knowledge", "base de conhecimento"),
        ("expenses", "gastos"),
        ("recurring_expenses", "assinaturas"),
        ("budgets", "orçamentos"),
        ("habits", "hábitos"),
        ("journal", "diário"),
        ("watches", "monitores web"),
        ("flashcards", "flashcards"),
    )
    _DATA_TABLE_NAMES = frozenset(k for k, _ in DATA_TABLES)

    def count_rows(self, table: str, user_id: str) -> int:
        if table not in self._DATA_TABLE_NAMES:
            raise ValueError(f"unknown table {table!r}")
        return int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        )

    def clear_table(self, table: str, user_id: str) -> int:
        """Delete all of a user's rows in one data table. Returns rows deleted.
        (Table name is validated against a whitelist — no SQL injection.)"""
        if table not in self._DATA_TABLE_NAMES:
            raise ValueError(f"unknown table {table!r}")
        if table == "habits":  # cascade: drop this user's habit logs first
            self._conn.execute(
                "DELETE FROM habit_logs WHERE habit_id IN "
                "(SELECT id FROM habits WHERE user_id = ?)",
                (user_id,),
            )
        cur = self._conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        self._conn.commit()
        return cur.rowcount

    def storage_summary(self, user_id: str) -> list[dict]:
        """[{key, label, count}] for every user-data table."""
        return [
            {"key": k, "label": lbl, "count": self.count_rows(k, user_id)}
            for k, lbl in self.DATA_TABLES
        ]

    def clear_all_user_data(self, user_id: str) -> int:
        """Wipe ALL of the user's data (every table above). Returns total rows."""
        total = sum(self.clear_table(k, user_id) for k, _ in self.DATA_TABLES)
        try:
            self._conn.execute("VACUUM")  # reclaim disk after a big delete
        except Exception:
            pass
        return total

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

    @staticmethod
    def _next_due(due_iso: str, recur: str, now: datetime | None = None) -> str:
        """Advance a due datetime to the next future occurrence of `recur`."""
        try:
            due = datetime.fromisoformat(due_iso)
        except Exception:
            return due_iso
        now = now or datetime.now()
        if due.tzinfo and now.tzinfo is None:
            now = now.replace(tzinfo=due.tzinfo)
        elif now.tzinfo and due.tzinfo is None:
            due = due.replace(tzinfo=now.tzinfo)
        if due > now:
            return due_iso  # already in the future — leave untouched
        if recur == "monthly":
            nxt = due
            while nxt <= now:
                nxt = add_months(nxt, 1)
            return nxt.isoformat()
        step = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(recur)
        if not step:
            return due_iso
        nxt = due
        while nxt <= now:
            nxt += step
        return nxt.isoformat()

    def add_task(self, user_id: str, text: str, category: str = "geral",
                 recur: str | None = None, due: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO tasks (user_id, text, category, recur, due, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, text, category, recur or None, due or None, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def open_tasks(self, user_id: str, category: str | None = None) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT id, text, category, recur, due FROM tasks "
                "WHERE user_id = ? AND done = 0 AND category = ? ORDER BY id",
                (user_id, category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, text, category, recur, due FROM tasks "
                "WHERE user_id = ? AND done = 0 ORDER BY category, id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def roll_due_tasks(self, now: datetime | None = None) -> int:
        """Roll every open recurring task whose due date has passed forward to its
        next occurrence (single rolling instance — never piles up). Returns how
        many were advanced. Safe to call often (idempotent within a period)."""
        now = now or datetime.now()
        rows = self._conn.execute(
            "SELECT id, recur, due FROM tasks "
            "WHERE done = 0 AND recur IS NOT NULL AND due IS NOT NULL"
        ).fetchall()
        advanced = 0
        for r in rows:
            if (r["recur"] or "") not in ("daily", "weekly", "monthly"):
                continue
            nxt = self._next_due(r["due"], r["recur"], now)
            if nxt != r["due"]:
                self._conn.execute("UPDATE tasks SET due = ? WHERE id = ?", (nxt, r["id"]))
                advanced += 1
        if advanced:
            self._conn.commit()
        return advanced

    def complete_task(self, user_id: str, task_id: int) -> bool:
        row = self._conn.execute(
            "SELECT text, category, recur, due FROM tasks "
            "WHERE id = ? AND user_id = ? AND done = 0",
            (task_id, user_id),
        ).fetchone()
        if not row:
            return False
        recur = (row["recur"] or "")
        # Recurring with a due date: roll the same task forward (single instance).
        if recur in ("daily", "weekly", "monthly") and row["due"]:
            self._conn.execute(
                "UPDATE tasks SET due = ? WHERE id = ?",
                (self._next_due(row["due"], recur), task_id),
            )
            self._conn.commit()
            return True
        # Recurring without a due date: regenerate a fresh open copy so it returns.
        if recur in ("daily", "weekly", "monthly"):
            self._conn.execute(
                "UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
                (self._now(), task_id),
            )
            self._conn.execute(
                "INSERT INTO tasks (user_id, text, category, recur, created) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, row["text"], row["category"], recur, self._now()),
            )
            self._conn.commit()
            return True
        # Plain one-off task.
        self._conn.execute(
            "UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
            (self._now(), task_id),
        )
        self._conn.commit()
        return True

    def delete_task(self, user_id: str, task_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_task(self, user_id: str, task_id: int, text: str | None = None,
                    category: str | None = None, recur: str | None = None,
                    due: str | None = None) -> bool:
        sets, params = [], []
        if text is not None:
            sets.append("text = ?"); params.append(text)
        if category is not None:
            sets.append("category = ?"); params.append(category)
        if recur is not None:
            sets.append("recur = ?"); params.append(recur or None)
        if due is not None:
            sets.append("due = ?"); params.append(due or None)
        if not sets:
            return False
        params += [task_id, user_id]
        cur = self._conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ? AND user_id = ?", params
        )
        self._conn.commit()
        return cur.rowcount > 0

    def _update(self, table: str, user_id: str, row_id: int, fields: dict) -> bool:
        """Generic partial UPDATE (table/column names are fixed literals, no injection)."""
        fields = {k: v for k, v in fields.items() if v is not None}
        if not fields:
            return False
        sets = ", ".join(f"{k} = ?" for k in fields)
        cur = self._conn.execute(
            f"UPDATE {table} SET {sets} WHERE id = ? AND user_id = ?",
            (*fields.values(), row_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_expense(self, u, i, amount=None, description=None, category=None):
        return self._update("expenses", u, i, {"amount": amount, "description": description, "category": category})

    def update_reminder(self, u, i, text=None, when_iso=None, recur=None):
        return self._update("reminders", u, i, {"text": text, "when_iso": when_iso, "recur": recur})

    def update_fact(self, u, i, fact):
        return self._update("facts", u, i, {"fact": fact})

    def update_link(self, u, i, category=None, name=None, url=None):
        return self._update("links", u, i, {"category": category, "name": name, "url": url})

    def update_journal(self, u, i, text):
        return self._update("journal", u, i, {"text": text})

    def update_recurring(self, u, i, amount=None, description=None, category=None, day=None):
        return self._update("recurring_expenses", u, i, {"amount": amount, "description": description, "category": category, "day": day})

    def update_watch(self, u, i, url=None, keyword=None):
        return self._update("watches", u, i, {"url": url, "keyword": keyword})

    def rename_habit(self, u, i, name):
        return self._update("habits", u, i, {"name": name})

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
        self._conn.execute(  # drop the stored original file too
            "DELETE FROM kb_files WHERE user_id = ? AND source = ?", (user_id, source))
        self._conn.commit()
        return cur.rowcount

    # --- original KB files (for download / open) ---------------------------

    def save_kb_file(self, user_id: str, source: str, filename: str,
                     mime: str, data: bytes) -> None:
        self._conn.execute(
            "DELETE FROM kb_files WHERE user_id = ? AND source = ?", (user_id, source))
        self._conn.execute(
            "INSERT INTO kb_files (user_id, source, filename, mime, data, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, source, filename, mime, data, self._now()),
        )
        self._conn.commit()

    def get_kb_file(self, user_id: str, source: str) -> dict | None:
        row = self._conn.execute(
            "SELECT filename, mime, data FROM kb_files WHERE user_id = ? AND source = ?",
            (user_id, source),
        ).fetchone()
        return dict(row) if row else None

    def kb_file_sources(self, user_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT source FROM kb_files WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [r["source"] for r in rows]

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
            "SELECT id, amount, description, category, created FROM expenses "
            "WHERE user_id = ? AND created >= ? ORDER BY id",
            (user_id, since_iso),
        ).fetchall()
        return [dict(r) for r in rows]

    def expenses_between(self, user_id: str, start_iso: str, end_iso: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT amount, description, category FROM expenses "
            "WHERE user_id = ? AND created >= ? AND created < ? ORDER BY id",
            (user_id, start_iso, end_iso),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_expense(self, user_id: str, expense_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def category_total_since(self, user_id: str, category: str, since_iso: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses "
            "WHERE user_id = ? AND category = ? AND created >= ?",
            (user_id, category, since_iso),
        ).fetchone()
        return float(row["t"])

    # --- budgets ------------------------------------------------------------

    def set_budget(self, user_id: str, category: str, amount: float) -> None:
        self._conn.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category)
        )
        self._conn.execute(
            "INSERT INTO budgets (user_id, category, amount, created) VALUES (?, ?, ?, ?)",
            (user_id, category, amount, self._now()),
        )
        self._conn.commit()

    def get_budget(self, user_id: str, category: str) -> float | None:
        row = self._conn.execute(
            "SELECT amount FROM budgets WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchone()
        return float(row["amount"]) if row else None

    def list_budgets(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT category, amount FROM budgets WHERE user_id = ? ORDER BY category",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_budget(self, user_id: str, category: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def random_chunk(self, user_id: str, source: str | None = None) -> dict | None:
        if source:
            row = self._conn.execute(
                "SELECT source, chunk FROM knowledge WHERE user_id = ? AND source = ? "
                "ORDER BY RANDOM() LIMIT 1",
                (user_id, source),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT source, chunk FROM knowledge WHERE user_id = ? "
                "ORDER BY RANDOM() LIMIT 1",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

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

    # --- unified search (across the user's own data) -----------------------

    def search_all(self, user_id: str, term: str) -> dict:
        """Keyword search across facts, tasks, reminders, links, journal and KB."""
        like = f"%{term}%"
        c = self._conn
        return {
            "facts": [
                r["fact"] for r in c.execute(
                    "SELECT fact FROM facts WHERE user_id=? AND fact LIKE ?",
                    (user_id, like),
                )
            ],
            "tasks": [
                r["text"] for r in c.execute(
                    "SELECT text FROM tasks WHERE user_id=? AND done=0 AND text LIKE ?",
                    (user_id, like),
                )
            ],
            "reminders": [
                r["text"] for r in c.execute(
                    "SELECT text FROM reminders WHERE user_id=? AND done=0 AND text LIKE ?",
                    (user_id, like),
                )
            ],
            "links": [
                f"{r['name']} — {r['url']}" for r in c.execute(
                    "SELECT name, url FROM links WHERE user_id=? AND "
                    "(name LIKE ? OR url LIKE ? OR category LIKE ?)",
                    (user_id, like, like, like),
                )
            ],
            "journal": [
                r["text"] for r in c.execute(
                    "SELECT text FROM journal WHERE user_id=? AND text LIKE ?",
                    (user_id, like),
                )
            ],
            "knowledge": [
                (r["source"], r["chunk"]) for r in c.execute(
                    "SELECT source, chunk FROM knowledge WHERE user_id=? AND chunk LIKE ? LIMIT 5",
                    (user_id, like),
                )
            ],
        }

    # --- usage tracking & settings -----------------------------------------

    def bump_usage(self, provider: str, day: str) -> None:
        self._conn.execute(
            "INSERT INTO usage_log (day, provider, n) VALUES (?, ?, 1) "
            "ON CONFLICT(day, provider) DO UPDATE SET n = n + 1",
            (day, provider),
        )
        self._conn.commit()

    def usage_for_day(self, day: str) -> dict:
        rows = self._conn.execute(
            "SELECT provider, n FROM usage_log WHERE day = ?", (day,)
        ).fetchall()
        return {r["provider"]: r["n"] for r in rows}

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
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
