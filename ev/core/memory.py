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
        # Optional encryption at rest: if EV_DB_KEY is set (64-hex) AND sqlcipher3
        # is installed, the DB is opened encrypted (SQLCipher). Otherwise plain
        # SQLite — so tests/CI and a fresh install work unchanged.
        import os
        key = os.getenv("EV_DB_KEY", "").strip()
        self._conn, self._row = self._connect(db_path, key)
        self._conn.row_factory = self._row
        # WAL + busy_timeout so the Telegram (`ev`) and web (`ev-web`) processes
        # can share this one file safely: WAL lets readers and one writer work
        # concurrently, and busy_timeout makes a write wait for the lock instead
        # of failing immediately with "database is locked".
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        self._init_schema()

    @staticmethod
    def _connect(db_path, key):
        """Return (connection, row_factory). Encrypted via SQLCipher when a key is
        set and sqlcipher3 is available; falls back to plain SQLite otherwise."""
        if key:
            try:
                from sqlcipher3 import dbapi2 as sq
                conn = sq.connect(str(db_path), check_same_thread=False)
                conn.execute(f"PRAGMA key = \"x'{key}'\"")
                conn.execute("SELECT count(*) FROM sqlite_master").fetchone()  # verify key
                return conn, sq.Row
            except Exception:
                pass  # sqlcipher missing or wrong key -> fall back to plaintext
        return sqlite3.connect(str(db_path), check_same_thread=False), sqlite3.Row

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

            CREATE TABLE IF NOT EXISTS activity (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                action   TEXT NOT NULL,   -- e.g. 'task.done', 'expense.new'
                label    TEXT NOT NULL,   -- human text (the item's name)
                category TEXT,            -- category / workspace, when it has one
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS push_subs (
                endpoint TEXT PRIMARY KEY,
                sub      TEXT NOT NULL,   -- full Web Push subscription JSON
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                title    TEXT NOT NULL,
                body     TEXT,
                url      TEXT,
                read     INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS people (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                notes    TEXT,
                birthday TEXT,   -- 'MM-DD' or 'YYYY-MM-DD'
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_images (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                conv_id  TEXT NOT NULL,
                mime     TEXT,
                data     BLOB NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS places (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                lat      REAL NOT NULL,
                lng      REAL NOT NULL,
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

    # --- activity log (CRUD tracking, shared by Telegram + web) -------------

    def log_activity(self, user_id: str, action: str, label: str,
                     category: str | None = None) -> None:
        try:
            self._conn.execute(
                "INSERT INTO activity (user_id, action, label, category, created) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, action, (label or "")[:200], category, self._now()),
            )
            self._conn.commit()
        except sqlite3.Error:
            pass  # tracking must never break the actual operation

    def list_activity(self, user_id: str, category: str | None = None,
                      limit: int = 300) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT action, label, category, created FROM activity "
                "WHERE user_id = ? AND category = ? ORDER BY id DESC LIMIT ?",
                (user_id, category, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT action, label, category, created FROM activity "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- web push subscriptions --------------------------------------------

    def add_push_sub(self, endpoint: str, sub_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO push_subs (endpoint, sub, created) VALUES (?, ?, ?)",
            (endpoint, sub_json, self._now()),
        )
        self._conn.commit()

    def list_push_subs(self) -> list[dict]:
        rows = self._conn.execute("SELECT endpoint, sub FROM push_subs").fetchall()
        return [dict(r) for r in rows]

    def delete_push_sub(self, endpoint: str) -> None:
        self._conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        self._conn.commit()

    # --- notification center (persisted so they can be reviewed later) ------

    def add_notification(self, user_id: str, title: str, body: str = "",
                         url: str = "/") -> None:
        """Store a notification so it shows up in the web notification center,
        whether or not a device was actually reachable via push."""
        try:
            self._conn.execute(
                "INSERT INTO notifications (user_id, title, body, url, read, created) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (user_id, (title or "")[:200], (body or "")[:1000], url or "/", self._now()),
            )
            # keep it bounded: retain only the newest 200 per user
            self._conn.execute(
                "DELETE FROM notifications WHERE user_id = ? AND id NOT IN "
                "(SELECT id FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 200)",
                (user_id, user_id),
            )
            self._conn.commit()
        except sqlite3.Error:
            pass  # a logging failure must never break delivery

    def list_notifications(self, user_id: str, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, body, url, read, created FROM notifications "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def unread_notifications(self, user_id: str) -> int:
        r = self._conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()
        return r["c"] if r else 0

    def mark_notification_read(self, user_id: str, notif_id: int | None = None) -> None:
        if notif_id:
            self._conn.execute(
                "UPDATE notifications SET read = 1 WHERE user_id = ? AND id = ?",
                (user_id, notif_id),
            )
        else:  # no id -> mark all read
            self._conn.execute(
                "UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))
        self._conn.commit()

    def delete_notification(self, user_id: str, notif_id: int) -> None:
        self._conn.execute(
            "DELETE FROM notifications WHERE user_id = ? AND id = ?", (user_id, notif_id))
        self._conn.commit()

    def clear_notifications(self, user_id: str, only_read: bool = False) -> None:
        if only_read:
            self._conn.execute(
                "DELETE FROM notifications WHERE user_id = ? AND read = 1", (user_id,))
        else:
            self._conn.execute(
                "DELETE FROM notifications WHERE user_id = ?", (user_id,))
        self._conn.commit()

    # --- people / relationships (who's who, birthdays) ---------------------

    @staticmethod
    def _norm_bday(bday: str) -> str:
        """Normalize a birthday to 'MM-DD' (year kept if given as YYYY-MM-DD)."""
        b = (bday or "").strip()
        if not b:
            return ""
        # accept DD/MM, DD/MM/YYYY, YYYY-MM-DD, MM-DD
        import re
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", b)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            mmdd = f"{int(mo):02d}-{int(d):02d}"
            return f"{y}-{mmdd}" if y and len(y) == 4 else mmdd
        m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", b)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return b

    def add_person(self, user_id: str, name: str, notes: str = "",
                   birthday: str = "") -> int:
        """Add or update a person (matched by name, case-insensitive). Notes are
        appended; a new birthday overwrites the old one."""
        name = (name or "").strip()
        bday = self._norm_bday(birthday)
        row = self._conn.execute(
            "SELECT id, notes FROM people WHERE user_id = ? AND lower(name) = lower(?)",
            (user_id, name),
        ).fetchone()
        if row:
            notes_new = (row["notes"] or "").strip()
            if notes and notes not in notes_new:
                notes_new = (notes_new + " • " + notes).strip(" •")
            self._conn.execute(
                "UPDATE people SET notes = ?, birthday = COALESCE(NULLIF(?, ''), birthday) "
                "WHERE id = ?", (notes_new, bday, row["id"]))
            self._conn.commit()
            return int(row["id"])
        cur = self._conn.execute(
            "INSERT INTO people (user_id, name, notes, birthday, created) "
            "VALUES (?, ?, ?, ?, ?)", (user_id, name, notes, bday, self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_people(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, notes, birthday FROM people WHERE user_id = ? "
            "ORDER BY lower(name)", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def find_person(self, user_id: str, name: str) -> dict | None:
        n = (name or "").strip()
        row = self._conn.execute(
            "SELECT id, name, notes, birthday FROM people WHERE user_id = ? "
            "AND lower(name) LIKE lower(?) ORDER BY length(name) LIMIT 1",
            (user_id, f"%{n}%")).fetchone()
        return dict(row) if row else None

    def delete_person(self, user_id: str, name: str) -> bool:
        p = self.find_person(user_id, name)
        if not p:
            return False
        self._conn.execute("DELETE FROM people WHERE id = ?", (p["id"],))
        self._conn.commit()
        return True

    def birthdays_on(self, user_id: str, mmdd: str) -> list[dict]:
        """People whose birthday falls on the given 'MM-DD' (year ignored)."""
        out = []
        for p in self.list_people(user_id):
            b = p.get("birthday") or ""
            if b and b[-5:] == mmdd:
                out.append(p)
        return out

    # --- chat images (pasted/sent images kept in the conversation) ---------

    def add_chat_image(self, conv_id: str, data: bytes, mime: str = "image/png") -> int:
        cur = self._conn.execute(
            "INSERT INTO chat_images (conv_id, mime, data, created) VALUES (?, ?, ?, ?)",
            (conv_id, mime or "image/png", sqlite3.Binary(data), self._now()),
        )
        # bound the store — keep only the newest 80 images overall
        self._conn.execute(
            "DELETE FROM chat_images WHERE id NOT IN "
            "(SELECT id FROM chat_images ORDER BY id DESC LIMIT 80)")
        self._conn.commit()
        return int(cur.lastrowid)

    def get_chat_image(self, image_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT mime, data FROM chat_images WHERE id = ?", (image_id,)).fetchone()
        return {"mime": row["mime"], "data": bytes(row["data"])} if row else None

    # --- saved places / points of interest --------------------------------

    def add_place(self, user_id: str, name: str, lat: float, lng: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO places (user_id, name, lat, lng, created) VALUES (?, ?, ?, ?, ?)",
            (user_id, (name or "ponto").strip()[:80], float(lat), float(lng), self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_places(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, lat, lng FROM places WHERE user_id = ? ORDER BY id",
            (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_place(self, user_id: str, place_id: int) -> None:
        self._conn.execute("DELETE FROM places WHERE user_id = ? AND id = ?",
                           (user_id, place_id))
        self._conn.commit()

    def mark_last_user_image(self, conv_id: str, image_id: int) -> None:
        """Embed an [img:id] marker in the most recent user message so the image
        can be re-rendered when the conversation is reloaded. (The messages table
        stores the conversation id in the user_id column.)"""
        row = self._conn.execute(
            "SELECT id, content FROM messages WHERE user_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT 1", (conv_id,)).fetchone()
        if not row:
            return
        content = (row["content"] or "").strip()
        marker = f"[img:{image_id}]"
        content = marker if content in ("", "[imagem]") else f"{content}\n{marker}"
        self._conn.execute(
            "UPDATE messages SET content = ? WHERE id = ?", (content, row["id"]))
        self._conn.commit()
        self._conn.commit()

    def activity_categories(self, user_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT category FROM activity "
            "WHERE user_id = ? AND category IS NOT NULL AND category != '' "
            "ORDER BY category",
            (user_id,),
        ).fetchall()
        return [r["category"] for r in rows]

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
        self.log_activity(user_id, "reminder.new", text)
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
        row = self._conn.execute(
            "SELECT user_id, text FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()
        if row:
            self.log_activity(row["user_id"], "reminder.done", row["text"])

    def reschedule_reminder(self, reminder_id: int, new_when_iso: str) -> None:
        """Move a (recurring) reminder to its next occurrence, keeping it open."""
        self._conn.execute(
            "UPDATE reminders SET when_iso = ? WHERE id = ?",
            (new_when_iso, reminder_id),
        )
        self._conn.commit()

    def cancel_reminder(self, user_id: str, reminder_id: int) -> bool:
        row = self._conn.execute(
            "SELECT text FROM reminders WHERE id = ? AND user_id = ? AND done = 0",
            (reminder_id, user_id),
        ).fetchone()
        cur = self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ? AND user_id = ? AND done = 0",
            (reminder_id, user_id),
        )
        self._conn.commit()
        if cur.rowcount and row:
            self.log_activity(user_id, "reminder.cancel", row["text"])
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
        self.log_activity(user_id, "task.new", text, category)
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
            self.log_activity(user_id, "task.done", row["text"], row["category"])
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
            self.log_activity(user_id, "task.done", row["text"], row["category"])
            return True
        # Plain one-off task.
        self._conn.execute(
            "UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
            (self._now(), task_id),
        )
        self._conn.commit()
        self.log_activity(user_id, "task.done", row["text"], row["category"])
        return True

    def delete_task(self, user_id: str, task_id: int) -> bool:
        row = self._conn.execute(
            "SELECT text, category FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()
        cur = self._conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        self._conn.commit()
        if cur.rowcount and row:
            self.log_activity(user_id, "task.del", row["text"], row["category"])
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
        self.log_activity(user_id, "expense.new", f"{description} (R$ {amount:.0f})", category)
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
        row = self._conn.execute(
            "SELECT description, category FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        cur = self._conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        self._conn.commit()
        if cur.rowcount and row:
            self.log_activity(user_id, "expense.del", row["description"], row["category"])
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
        h = self._conn.execute(
            "SELECT user_id, name FROM habits WHERE id = ?", (habit_id,)
        ).fetchone()
        if h:
            self.log_activity(h["user_id"], "habit.done", h["name"])
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
        """Consistent online backup of the whole DB to `dest_path`. When the DB is
        encrypted the backup is encrypted too (same key) — so it stays private and
        needs EV_DB_KEY to restore."""
        import os
        from pathlib import Path as _P
        key = os.getenv("EV_DB_KEY", "").strip()
        _P(dest_path).unlink(missing_ok=True)  # export/backup wants a clean target
        if key:
            self._conn.execute(f"ATTACH DATABASE '{dest_path}' AS bak KEY \"x'{key}'\"")
            try:
                self._conn.execute("SELECT sqlcipher_export('bak')")
            finally:
                self._conn.execute("DETACH DATABASE bak")
        else:
            dest = sqlite3.connect(dest_path)
            try:
                self._conn.backup(dest)
            finally:
                dest.close()
