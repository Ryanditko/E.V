"""Document scan + receipt extraction domain routes — Phase 6b, Group 4
route split (external-API-dependent: OCR / structured extraction via the
Brain).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio

from fastapi import APIRouter, Request

from ....core import knowledge
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, brain, owner = ctx.config, ctx.memory, ctx.brain, ctx.owner

    @router.post("/api/scan")
    async def scan(request: Request):
        """Scan a document: OCR the frame and save the text to the knowledge base."""
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhuma imagem."}
        data = await f.read()
        text = await brain.ocr_image(data, f.content_type or "image/jpeg")
        if not text or text.strip() in ("", "(sem texto)"):
            return {"ok": False, "msg": "Não achei texto legível no documento."}
        from datetime import datetime, timezone
        title = "Documento " + datetime.now(timezone.utc).strftime("%d/%m %H:%M")
        try:
            stored = await asyncio.to_thread(
                knowledge.ingest_text, text, title, config, memory, owner)
            return {"ok": True, "msg": f"Documento salvo na Base: {title} "
                    f"({len(text)} caracteres).", "stored": stored}
        except Exception as exc:
            return {"ok": True, "msg": f"Li o documento ({len(text)} caracteres), "
                    f"mas não consegui salvar na Base ({str(exc)[:50]}).", "text": text[:300]}

    @router.post("/api/receipt")
    async def receipt(request: Request):
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhuma imagem enviada."}
        data = await f.read()
        if not data:
            return {"ok": False, "msg": "Imagem vazia."}
        try:
            exp = await brain.extract_receipt(data, f.content_type or "image/jpeg")
        except Exception as exc:
            return {"ok": False, "msg": f"Não consegui ler o comprovante: {exc}"}
        if not exp:
            return {"ok": False,
                    "msg": "Não consegui identificar um valor nesse comprovante."}
        return {"ok": True, **exp}

    return router
