"""Web-push domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio
import json

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, owner = ctx.config, ctx.memory, ctx.owner

    @router.get("/api/push/key")
    async def push_key(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"key": config.vapid_public}

    @router.post("/api/push/subscribe")
    async def push_subscribe(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        ep = d.get("endpoint")
        if not ep:
            return {"ok": False}
        memory.add_push_sub(ep, json.dumps(d))
        return {"ok": True}

    @router.post("/api/push/unsubscribe")
    async def push_unsubscribe(request: Request):
        ctx.check(request.headers.get("authorization"))
        ep = (await ctx.body(request)).get("endpoint")
        if ep:
            memory.delete_push_sub(ep)
        return {"ok": True}

    @router.post("/api/push/test")
    async def push_test(request: Request):
        ctx.check(request.headers.get("authorization"))
        from ....providers import push
        # owner passed so the test also shows up in the notification center
        n = await asyncio.to_thread(push.send_push, config, memory,
                                    "E.V.", "Notificação de teste funcionando.", "/", owner)
        return {"ok": n > 0, "sent": n}

    return router
