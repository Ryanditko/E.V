"""Facts CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/facts/update` route
used to live far from the rest of this CRUD (near the end of `create_app()`,
next to links/journal/... updates) — reunified here, same file as
create/list/delete/clear, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/facts")
    async def fact_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_facts(owner)}

    @router.post("/api/facts")
    async def fact_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        text = ((await ctx.body(request)).get("text") or "").strip()
        if text:
            memory.add_fact(owner, text)
        return {"ok": bool(text)}

    @router.post("/api/facts/delete")
    async def fact_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_fact(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/facts/clear")
    async def fact_clear(request: Request):
        ctx.check(request.headers.get("authorization"))
        n = memory.clear_facts(owner)
        return {"ok": True, "cleared": n}

    @router.post("/api/facts/update")
    async def fact_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        t = (d.get("text") or "").strip()
        if t:
            memory.update_fact(owner, int(d.get("id") or 0), t)
        return {"ok": bool(t)}

    return router
