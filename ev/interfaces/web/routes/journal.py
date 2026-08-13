"""Journal CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/journal/update` route
used to live far from the rest of this CRUD (near the end of `create_app()`,
next to links/habits/... updates) — reunified here, same file as
create/list/delete, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/journal")
    async def journal_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.recent_journal(owner, 60)}

    @router.post("/api/journal")
    async def journal_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        text = ((await ctx.body(request)).get("text") or "").strip()
        if text:
            memory.add_journal(owner, text)
        return {"ok": bool(text)}

    @router.post("/api/journal/delete")
    async def journal_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_journal(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/journal/update")
    async def jou_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        t = (d.get("text") or "").strip()
        if t:
            memory.update_journal(owner, int(d.get("id") or 0), t)
        return {"ok": bool(t)}

    return router
