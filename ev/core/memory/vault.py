"""Document vault and chat images — both store binary blobs for the user."""

from __future__ import annotations

import sqlite3


class VaultMixin:
    def add_document(self, user_id: str, name: str, mime: str, data: bytes,
                     text: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO documents (user_id, name, mime, size, text, data, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, mime, len(data), text, data, self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_documents(self, user_id: str, q: str = "") -> list[dict]:
        if q:
            like = f"%{q}%"
            rows = self._conn.execute(
                "SELECT id, name, mime, size, created FROM documents WHERE user_id = ? "
                "AND (name LIKE ? OR text LIKE ?) ORDER BY id DESC", (user_id, like, like)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, name, mime, size, created FROM documents WHERE user_id = ? "
                "ORDER BY id DESC", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_document(self, user_id: str, doc_id: int) -> dict | None:
        r = self._conn.execute(
            "SELECT name, mime, data FROM documents WHERE id = ? AND user_id = ?",
            (doc_id, user_id)).fetchone()
        return dict(r) if r else None

    def delete_document(self, user_id: str, doc_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?",
                                 (doc_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

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

    # --- conversation history -----------------------------------------------

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
