"""Document vault (encrypted, OCR-searchable) domain routes — Phase 6b,
Group 5 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import hmac

from fastapi import APIRouter, HTTPException, Request, Response

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, brain, owner = ctx.config, ctx.memory, ctx.brain, ctx.owner

    @router.get("/api/vault")
    async def vault_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_documents(owner, (request.query_params.get("q") or "").strip())}

    @router.post("/api/vault")
    async def vault_add(request: Request):
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("file")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            raise HTTPException(status_code=400, detail="nenhum arquivo enviado")
        data = await f.read()
        if len(data) > 15_000_000:
            raise HTTPException(status_code=400, detail="arquivo grande demais (máx 15 MB)")
        mime = getattr(f, "content_type", "") or "application/octet-stream"
        name = getattr(f, "filename", "documento") or "documento"
        text = ""
        if mime.startswith("image/") and brain:
            try:
                text = (await brain.ocr_image(data, mime)) or ""
            except Exception:
                text = ""
        memory.add_document(owner, name[:120], mime, data, text[:20000])
        return {"ok": True}

    @router.get("/api/vault/file")
    async def vault_file(request: Request):
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        doc = memory.get_document(owner, int(request.query_params.get("id") or 0))
        if not doc:
            raise HTTPException(status_code=404, detail="não encontrado")
        safe = (doc["name"] or "documento").replace('"', "")
        return Response(content=doc["data"], media_type=doc["mime"],
                        headers={"Content-Disposition": f'inline; filename="{safe}"'})

    @router.post("/api/vault/delete")
    async def vault_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_document(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    return router
