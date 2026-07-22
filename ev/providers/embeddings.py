"""Text embeddings for semantic recall (facts + knowledge base).

Two backends, chosen by config.embed_backend:
  - "gemini": Gemini embeddings API (good quality, uses quota).
  - "ollama": local Ollama embeddings (no quota, never runs out).

Everything degrades gracefully: on any failure `embed` returns None and callers
fall back to non-semantic recall. Vectors of different dimensions simply score 0
in cosine (so switching backends never crashes, it just ignores old vectors).
"""

from __future__ import annotations

import math


def embed(text: str, config) -> list[float] | None:
    """Return an embedding vector for `text`, or None on failure."""
    backend = getattr(config, "embed_backend", "gemini")
    if backend == "ollama":
        return _embed_ollama(text, config)
    return _embed_gemini(text, config)


def _embed_gemini(text: str, config) -> list[float] | None:
    try:
        from google import genai

        client = genai.Client(api_key=config.gemini_api_key)
        resp = client.models.embed_content(model=config.embed_model, contents=text)
        return [float(v) for v in resp.embeddings[0].values]
    except Exception:
        return None


def _embed_ollama(text: str, config) -> list[float] | None:
    try:
        from openai import OpenAI

        client = OpenAI(base_url=config.ollama_base_url, api_key="ollama")
        resp = client.embeddings.create(
            model=config.ollama_embed_model, input=text
        )
        return [float(v) for v in resp.data[0].embedding]
    except Exception:
        return None


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors (0 if degenerate)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
