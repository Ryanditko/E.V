"""Knowledge-base (RAG sources) domain routes — Phase 6b, Group 5 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response

from ....core import knowledge
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, owner = ctx.config, ctx.memory, ctx.owner

    @router.get("/api/kb")
    async def kb_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"sources": memory.list_sources(owner),
                "files": memory.kb_file_sources(owner)}

    @router.get("/api/kb/file")
    async def kb_file(request: Request):
        ctx.check(request.headers.get("authorization"))
        f = memory.get_kb_file(owner, request.query_params.get("source", ""))
        if not f:
            raise HTTPException(status_code=404, detail="arquivo não encontrado")
        fn = f["filename"] or "arquivo"
        return Response(
            content=f["data"], media_type=f["mime"] or "application/octet-stream",
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(fn)}"},
        )

    @router.post("/api/kb/url")
    async def kb_url(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        url = (d.get("url") or "").strip()
        name = (d.get("name") or "").strip() or None
        if not url.lower().startswith("http"):
            return {"ok": False, "msg": "Informe uma URL válida (http...)."}
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_url, url, config, memory, owner, name)
            msg = f"{stored} trechos indexados" + (" (parcial)" if trunc else "") if stored else "Não achei texto útil."
            return {"ok": stored > 0, "msg": msg, "sources": memory.list_sources(owner)}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:120]}

    @router.post("/api/kb/text")
    async def kb_text(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        title = (d.get("title") or "Nota").strip()
        text = (d.get("text") or "").strip()
        if not text:
            return {"ok": False, "msg": "Texto vazio."}
        stored, trunc = await asyncio.to_thread(
            knowledge.ingest_text, text, title, config, memory, owner)
        return {"ok": stored > 0, "msg": f"{stored} trechos indexados",
                "sources": memory.list_sources(owner)}

    @router.post("/api/kb/upload")
    async def kb_upload(request: Request):
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("file")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhum arquivo enviado."}
        fname = f.filename or "arquivo"
        if not fname.lower().endswith(knowledge.READABLE_EXTS):
            return {"ok": False, "msg": "Só PDF, Word (.docx) ou texto (.txt/.md)."}
        title = (form.get("title") or "").strip() or None
        data = await f.read()
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_file, data, fname, config, memory, owner, title)
            label = title or fname
            if stored and len(data) <= 25_000_000:  # keep the original for download/open
                mime = getattr(f, "content_type", None) or "application/octet-stream"
                memory.save_kb_file(owner, label, fname, mime, data)
            msg = f"'{label}': {stored} trechos" if stored else "Sem texto extraível."
            return {"ok": stored > 0, "msg": msg, "sources": memory.list_sources(owner)}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:120]}

    @router.post("/api/kb/delete")
    async def kb_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        source = ((await ctx.body(request)).get("source") or "").strip()
        n = memory.delete_source(owner, source) if source else 0
        return {"ok": n > 0, "sources": memory.list_sources(owner)}

    return router
