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


from .schema import SchemaMixin
from .activity import ActivityMixin
from .push import PushMixin
from .patterns import PatternsMixin
from .local_agent import LocalAgentMixin
from .music import MusicMixin
from .goals import GoalsMixin
from .health_log import HealthLogMixin
from .vault import VaultMixin
from .people import PeopleMixin
from .places import PlacesMixin
from .storage import StorageMixin
from .facts import FactsMixin
from .reminders import RemindersMixin
from .tasks import TasksMixin
from .links import LinksMixin
from .knowledge_base import KnowledgeBaseMixin
from .expenses import ExpensesMixin
from .habits import HabitsMixin
from .journal import JournalMixin
from .watches import WatchesMixin
from .search import SearchMixin
from .settings import SettingsMixin


class Memory(
    SchemaMixin, ActivityMixin, PushMixin, PatternsMixin, LocalAgentMixin,
    MusicMixin, GoalsMixin, HealthLogMixin, VaultMixin, PeopleMixin,
    PlacesMixin, StorageMixin, FactsMixin, RemindersMixin, TasksMixin,
    LinksMixin, KnowledgeBaseMixin, ExpensesMixin, HabitsMixin, JournalMixin,
    WatchesMixin, SearchMixin, SettingsMixin,
):
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

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

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
