"""Database schema creation and migrations."""

from __future__ import annotations


class SchemaMixin:
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

            CREATE TABLE IF NOT EXISTS learned (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                key      TEXT NOT NULL,
                text     TEXT NOT NULL,
                created  TEXT NOT NULL,
                UNIQUE(user_id, key)
            );

            CREATE TABLE IF NOT EXISTS automations (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                trig     TEXT NOT NULL,
                trig_cfg TEXT NOT NULL,
                act      TEXT NOT NULL,
                act_cfg  TEXT NOT NULL,
                enabled  INTEGER NOT NULL DEFAULT 1,
                state    TEXT NOT NULL DEFAULT '{}',
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS connectors (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                url      TEXT NOT NULL,
                headers  TEXT NOT NULL DEFAULT '{}',
                path     TEXT NOT NULL DEFAULT '',
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pages (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                widgets  TEXT NOT NULL DEFAULT '[]',
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS music (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                label    TEXT NOT NULL,
                kind     TEXT NOT NULL,
                ref      TEXT NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS goals (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                target   REAL NOT NULL,
                saved    REAL NOT NULL DEFAULT 0,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS health (
                user_id  TEXT NOT NULL,
                day      TEXT NOT NULL,
                water    INTEGER NOT NULL DEFAULT 0,
                sleep    REAL,
                mood     TEXT,
                PRIMARY KEY (user_id, day)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                mime     TEXT NOT NULL,
                size     INTEGER NOT NULL,
                text     TEXT NOT NULL DEFAULT '',
                data     BLOB NOT NULL,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS local_scripts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                name     TEXT NOT NULL,
                command  TEXT NOT NULL,
                created  TEXT NOT NULL,
                UNIQUE(user_id, name)
            );

            CREATE TABLE IF NOT EXISTS local_tasks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                kind     TEXT NOT NULL,
                label    TEXT NOT NULL,
                payload  TEXT NOT NULL DEFAULT '{}',
                status   TEXT NOT NULL DEFAULT 'pending',
                risk     TEXT NOT NULL DEFAULT 'normal',
                result   TEXT,
                notified INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL,
                decided  TEXT,
                finished TEXT
            );

            CREATE TABLE IF NOT EXISTS local_confirms (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id  INTEGER NOT NULL,
                user_id  TEXT NOT NULL,
                label    TEXT NOT NULL,
                status   TEXT NOT NULL DEFAULT 'pending',
                notified INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL,
                decided  TEXT
            );
            """
        )
        # Migrations for older DBs.
        loc_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(local_tasks)")}
        if "risk" not in loc_cols:
            self._conn.execute(
                "ALTER TABLE local_tasks ADD COLUMN risk TEXT NOT NULL DEFAULT 'normal'"
            )
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
