"""Knowledge base (PDF/web ingestion) and data export/digest."""

from __future__ import annotations

from datetime import timedelta

from .. import knowledge
from ..i18n import plural as _plural
from ..i18n import t as _t


class KbDocsMixin:
    def kb(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        sources = self._memory.list_sources(user_id)
        if not sources:
            return _t(lang, "kb.empty")
        lines = [_t(lang, "kb.title")]
        for s in sources:
            lines.append(_t(lang, "kb.item", source=s["source"],
                            chunks=_plural(lang, "count.chunks", s["chunks"])))
        lines.append(_t(lang, "kb.footer"))
        return "\n".join(lines)

    def kbrm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        source = argstr.strip()
        if not source:
            return _t(lang, "kb.rm_usage")
        n = self._memory.delete_source(user_id, source)
        if n:
            return _t(lang, "kb.removed", source=source,
                      chunks=_plural(lang, "count.chunks", n))
        return _t(lang, "kb.not_found", source=source)

    def kbweb(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        url = argstr.strip()
        if not url.lower().startswith("http"):
            return _t(lang, "kb.web_usage")
        try:
            stored, truncated = knowledge.ingest_url(
                url, self._config, self._memory, user_id
            )
        except Exception as exc:
            return _t(lang, "kb.web_error", exc=exc)
        if stored == 0:
            return _t(lang, "kb.no_text")
        extra = _t(lang, "kb.large_page") if truncated else ""
        return _t(lang, "kb.web_indexed",
                  stored=_plural(lang, "count.chunks", stored), extra=extra)

    def ingest_document(self, user_id: str, data: bytes, filename: str) -> str:
        """Ingest an uploaded document (PDF, Word or plain text) into the KB."""
        lang = self._memory.assistant_lang()
        if not filename.lower().endswith(knowledge.READABLE_EXTS):
            return _t(lang, "kb.bad_ext")
        try:
            stored, truncated = knowledge.ingest_file(
                data, filename, self._config, self._memory, user_id
            )
        except Exception as exc:
            return _t(lang, "kb.file_error", exc=exc)
        if stored == 0:
            return _t(lang, "kb.no_text_file")
        extra = _t(lang, "kb.large_doc") if truncated else ""
        return _t(lang, "kb.file_indexed", filename=filename,
                  stored=_plural(lang, "count.chunks", stored), extra=extra)

    # --- data export (feature B) -------------------------------------------

    def export_expenses_csv(self, user_id: str, months: int = 6) -> tuple[bytes, str] | str:
        """Build a CSV of the last `months` of expenses. Returns (bytes, name)
        or an error string if there is nothing to export."""
        import csv
        import io as _io

        since = (self._now() - timedelta(days=30 * months)).isoformat()
        rows = self._memory.expenses_since(user_id, since)
        if not rows:
            return _t(self._memory.assistant_lang(), "kb.export_empty")
        buf = _io.StringIO()
        w = csv.writer(buf)
        w.writerow(["data", "categoria", "valor", "descricao"])
        for e in rows:
            w.writerow([
                (e.get("created") or "")[:10],
                e.get("category", ""),
                f"{e.get('amount', 0):.2f}",
                e.get("description", ""),
            ])
        data = buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows accents
        return data, f"gastos_{self._now().strftime('%Y%m%d')}.csv"

    def data_digest(self, user_id: str) -> tuple[str, str]:
        """Human-readable digest of the user's data. Returns (title, content)."""
        m = self._memory
        lang = m.assistant_lang()
        lines: list[str] = []

        tasks = m.open_tasks(user_id)
        lines.append(_t(lang, "kb.digest_tasks", n=len(tasks)))
        lines += [f"- [{t['category']}] {t['text']}" for t in tasks] or [_t(lang, "kb.digest_none_f")]

        facts = m.all_facts(user_id)
        lines.append(_t(lang, "kb.digest_memories", n=len(facts)))
        lines += [f"- {f}" for f in facts] or [_t(lang, "kb.digest_none_f")]

        habits = m.list_habits(user_id)
        lines.append(_t(lang, "kb.digest_habits", n=len(habits)))
        lines += [f"- {h['name']}" for h in habits] or [_t(lang, "kb.digest_none_m")]

        journ = m.recent_journal(user_id, 30)
        lines.append(_t(lang, "kb.digest_journal", n=len(journ)))
        lines += [f"- {e['text']}" for e in journ] or [_t(lang, "kb.digest_empty")]

        title = _t(lang, "kb.digest_title", date=self._now().strftime("%d/%m/%Y"))
        return title, "\n".join(lines)
