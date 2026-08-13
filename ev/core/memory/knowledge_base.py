"""Knowledge base — document chunks with optional embeddings, plus the
original uploaded files kept for download/open."""

from __future__ import annotations

import json

from .base import _cosine


class KnowledgeBaseMixin:
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
