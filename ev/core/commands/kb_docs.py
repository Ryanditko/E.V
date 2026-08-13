"""Knowledge base (PDF/web ingestion) and data export/digest."""

from __future__ import annotations

from datetime import timedelta

from .. import knowledge


class KbDocsMixin:
    def kb(self, user_id: str) -> str:
        sources = self._memory.list_sources(user_id)
        if not sources:
            return (
                "Base de conhecimento vazia. Envie um PDF aqui no chat que eu "
                "indexo e passo a responder com base nele."
            )
        lines = ["📄 Documentos na base de conhecimento:"]
        for s in sources:
            lines.append(f"- {s['source']} ({s['chunks']} trechos)")
        lines.append("\nEnvie um PDF para adicionar. Remover: /kbrm <nome>")
        return "\n".join(lines)

    def kbrm(self, user_id: str, argstr: str) -> str:
        source = argstr.strip()
        if not source:
            return "Uso: /kbrm <nome do documento>. Veja os nomes em /kb."
        n = self._memory.delete_source(user_id, source)
        return f"Removi '{source}' ({n} trechos)." if n else f"Não achei '{source}' na base."

    def kbweb(self, user_id: str, argstr: str) -> str:
        url = argstr.strip()
        if not url.lower().startswith("http"):
            return "Uso: /kbweb <url>. Ex: /kbweb https://pt.wikipedia.org/..."
        try:
            stored, truncated = knowledge.ingest_url(
                url, self._config, self._memory, user_id
            )
        except Exception as exc:
            return f"Não consegui ler essa página ({exc})."
        if stored == 0:
            return "Não achei texto útil nessa página."
        extra = " (página grande — indexei o começo)" if truncated else ""
        return f"Página indexada: {stored} trechos{extra}. Pode me perguntar sobre ela!"

    def ingest_document(self, user_id: str, data: bytes, filename: str) -> str:
        """Ingest an uploaded document (PDF, Word or plain text) into the KB."""
        if not filename.lower().endswith(knowledge.READABLE_EXTS):
            return "Consigo ler PDF, Word (.docx) e texto (.txt, .md). Manda um desses."
        try:
            stored, truncated = knowledge.ingest_file(
                data, filename, self._config, self._memory, user_id
            )
        except Exception as exc:
            return f"Não consegui ler esse arquivo ({exc})."
        if stored == 0:
            return "Esse arquivo parece não ter texto extraível (talvez seja escaneado/imagem)."
        extra = " (documento grande — indexei o começo)" if truncated else ""
        return f"Documento '{filename}' indexado: {stored} trechos{extra}. Pode me perguntar sobre ele!"

    # --- data export (feature B) -------------------------------------------

    def export_expenses_csv(self, user_id: str, months: int = 6) -> tuple[bytes, str] | str:
        """Build a CSV of the last `months` of expenses. Returns (bytes, name)
        or an error string if there is nothing to export."""
        import csv
        import io as _io

        since = (self._now() - timedelta(days=30 * months)).isoformat()
        rows = self._memory.expenses_since(user_id, since)
        if not rows:
            return "Você ainda não tem gastos registrados nesse período."
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
        lines: list[str] = []

        tasks = m.open_tasks(user_id)
        lines.append(f"TAREFAS EM ABERTO ({len(tasks)})")
        lines += [f"- [{t['category']}] {t['text']}" for t in tasks] or ["- (nenhuma)"]

        facts = m.all_facts(user_id)
        lines.append(f"\nMEMÓRIAS ({len(facts)})")
        lines += [f"- {f}" for f in facts] or ["- (nenhuma)"]

        habits = m.list_habits(user_id)
        lines.append(f"\nHÁBITOS ({len(habits)})")
        lines += [f"- {h['name']}" for h in habits] or ["- (nenhum)"]

        journ = m.recent_journal(user_id, 30)
        lines.append(f"\nDIÁRIO (últimas {len(journ)} entradas)")
        lines += [f"- {e['text']}" for e in journ] or ["- (vazio)"]

        title = f"Meus dados — E.V. ({self._now().strftime('%d/%m/%Y')})"
        return title, "\n".join(lines)
