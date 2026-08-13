"""Unified keyword search across the user's own data."""

from __future__ import annotations


class SearchMixin:
    def search_all(self, user_id: str, term: str) -> dict:
        """Keyword search across facts, tasks, reminders, links, journal,
        expenses, recent messages and KB. Each item is {id, text} (id may be
        None for sources with no stable row id, e.g. knowledge chunks)."""
        like = f"%{term}%"
        c = self._conn
        return {
            "facts": [
                {"id": None, "text": r["fact"]} for r in c.execute(
                    "SELECT fact FROM facts WHERE user_id=? AND fact LIKE ?",
                    (user_id, like),
                )
            ],
            "tasks": [
                {"id": r["id"], "text": r["text"]} for r in c.execute(
                    "SELECT id, text FROM tasks WHERE user_id=? AND done=0 AND text LIKE ?",
                    (user_id, like),
                )
            ],
            "reminders": [
                {"id": r["id"], "text": r["text"]} for r in c.execute(
                    "SELECT id, text FROM reminders WHERE user_id=? AND done=0 AND text LIKE ?",
                    (user_id, like),
                )
            ],
            "links": [
                {"id": r["id"], "text": f"{r['name']} — {r['url']}"} for r in c.execute(
                    "SELECT id, name, url FROM links WHERE user_id=? AND "
                    "(name LIKE ? OR url LIKE ? OR category LIKE ?)",
                    (user_id, like, like, like),
                )
            ],
            "journal": [
                {"id": r["id"], "text": r["text"]} for r in c.execute(
                    "SELECT id, text FROM journal WHERE user_id=? AND text LIKE ?",
                    (user_id, like),
                )
            ],
            "expenses": [
                {"id": r["id"], "text": f"{r['description']} — R$ {r['amount']:.2f}"} for r in c.execute(
                    "SELECT id, description, amount FROM expenses WHERE user_id=? AND "
                    "(description LIKE ? OR category LIKE ?) ORDER BY id DESC LIMIT 8",
                    (user_id, like, like),
                )
            ],
            "messages": [
                {"id": None, "text": (r["role"] + ": " + r["content"])[:160]} for r in c.execute(
                    "SELECT role, content FROM messages WHERE user_id=? AND content LIKE ? "
                    "ORDER BY id DESC LIMIT 6",
                    (user_id, like),
                )
            ],
            "knowledge": [
                {"id": None, "text": f"[{r['source']}] {r['chunk'][:120]}…"} for r in c.execute(
                    "SELECT source, chunk FROM knowledge WHERE user_id=? AND chunk LIKE ? LIMIT 5",
                    (user_id, like),
                )
            ],
        }
