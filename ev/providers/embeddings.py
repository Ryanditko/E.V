"""Text embeddings for semantic memory recall (via Gemini).

Produces float vectors for facts and queries so E.V. can retrieve the memories
most relevant to the current message (cosine similarity), instead of dumping all
facts into the prompt. Degrades gracefully: on any failure the caller falls back
to keyword/all-facts recall.
"""

from __future__ import annotations

import math

from google import genai


def embed(text: str, *, api_key: str, model: str) -> list[float] | None:
    """Return the embedding vector for `text`, or None on failure."""
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.embed_content(model=model, contents=text)
        values = resp.embeddings[0].values
        return [float(v) for v in values]
    except Exception:
        return None


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors (0 if degenerate)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
