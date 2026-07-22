"""Knowledge base ingestion — turn documents into searchable, embedded chunks.

Extracts text (PDF or plain text), splits it into chunks, embeds each chunk and
stores it. The brain later retrieves the most relevant chunks for a question
(RAG) and answers grounded in them.
"""

from __future__ import annotations

import io
import logging

from ..providers import embeddings
from .memory import Memory

log = logging.getLogger("ev.knowledge")

_CHUNK_CHARS = 1200      # approx chunk size
_MAX_CHUNKS = 80         # cap per document to protect embedding quota


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _chunk(text: str, size: int = _CHUNK_CHARS) -> list[str]:
    words = text.split()
    chunks, buf, length = [], [], 0
    for w in words:
        buf.append(w)
        length += len(w) + 1
        if length >= size:
            chunks.append(" ".join(buf))
            buf, length = [], 0
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def ingest_text(
    text: str, source: str, config, memory: Memory, user_id: str
) -> tuple[int, bool]:
    """Store `text` as embedded chunks. Returns (chunks_stored, truncated)."""
    chunks = _chunk(text)
    truncated = len(chunks) > _MAX_CHUNKS
    chunks = chunks[:_MAX_CHUNKS]
    stored = 0
    for c in chunks:
        if not c.strip():
            continue
        memory.add_chunk(user_id, source, c, embeddings.embed(c, config))
        stored += 1
    log.info("Ingested %s chunks from %r (truncated=%s)", stored, source, truncated)
    return stored, truncated


def ingest_pdf(
    data: bytes, source: str, config, memory: Memory, user_id: str
) -> tuple[int, bool]:
    """Extract text from a PDF and ingest it. Returns (chunks_stored, truncated)."""
    text = _pdf_text(data)
    if not text.strip():
        return 0, False
    return ingest_text(text, source, config, memory, user_id)
