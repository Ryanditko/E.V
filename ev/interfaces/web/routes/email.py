"""Email-sending domain routes — Phase 6b, Group 4 route split
(external-API-dependent: sends via the configured email provider in
`ev/providers/tools`).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config = ctx.config

    @router.post("/api/email")
    async def api_email(request: Request):
        ctx.check(request.headers.get("authorization"))
        from ....providers import tools
        d = await ctx.body(request)
        to = (d.get("to") or "").strip()
        subject = (d.get("subject") or "").strip()
        body = (d.get("body") or "").strip()
        if not to or not body:
            return {"ok": False, "msg": "Preencha destinatário e mensagem."}
        account = (d.get("account") or "").strip() or config.default_account
        try:
            msg = await asyncio.to_thread(
                tools.send_email, config, account, to, subject, body
            )
            return {"ok": True, "msg": msg}
        except Exception as exc:
            return {"ok": False, "msg": f"Falha ao enviar o email: {exc}"}

    return router
