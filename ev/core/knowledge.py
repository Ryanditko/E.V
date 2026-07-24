"""Knowledge base ingestion — turn documents into searchable, embedded chunks.

Extracts text (PDF or plain text), splits it into chunks, embeds each chunk and
stores it. The brain later retrieves the most relevant chunks for a question
(RAG) and answers grounded in them.
"""

from __future__ import annotations

import io
import logging
import re

from ..providers import embeddings
from .memory import Memory

log = logging.getLogger("ev.knowledge")

_CHUNK_CHARS = 1200      # approx chunk size
_MAX_CHUNKS = 80         # cap per document to protect embedding quota


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _docx_text(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


# Filename extensions we can read into text.
READABLE_EXTS = (".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".log")


def extract_text(data: bytes, filename: str) -> str:
    """Extract plain text from a supported file (PDF, Word, or plain text)."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _pdf_text(data)
    if name.endswith(".docx"):
        return _docx_text(data)
    # Everything else: best-effort decode as UTF-8 text.
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def ingest_file(
    data: bytes, filename: str, config, memory: Memory, user_id: str
) -> tuple[int, bool]:
    """Extract text from a supported file and ingest it. Returns (stored, truncated)."""
    text = extract_text(data, filename)
    if not text.strip():
        return 0, False
    return ingest_text(text, filename, config, memory, user_id)


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


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ingest_url(
    url: str, config, memory: Memory, user_id: str
) -> tuple[int, bool]:
    """Fetch a web page, extract its text and ingest it. Returns (stored, truncated)."""
    import httpx

    resp = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (E.V. assistant)"},
    )
    resp.raise_for_status()
    text = _html_to_text(resp.text)
    if not text:
        return 0, False
    return ingest_text(text, url, config, memory, user_id)
