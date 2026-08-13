"""Facts — long-term memory, with optional embeddings for semantic recall."""

from __future__ import annotations

import json

from .base import _cosine


class FactsMixin:
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

    def clear_facts(self, user_id: str) -> int:
        """Wipe all of a user's remembered facts (the 'brain'). Returns how many."""
        cur = self._conn.execute("DELETE FROM facts WHERE user_id = ?", (user_id,))
        self._conn.commit()
        return cur.rowcount

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

    def update_fact(self, u, i, fact):
        return self._update("facts", u, i, {"fact": fact})
