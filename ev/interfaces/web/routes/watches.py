"""Page-watches CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/watches/update` route
used to live far from the rest of this CRUD (near the end of `create_app()`,
next to recurring/habits/... updates) — reunified here, same file as
create/list/delete, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/watches")
    async def wat_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_watches(owner)}

    @router.post("/api/watches")
    async def wat_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        url = (d.get("url") or "").strip()
        kw = (d.get("keyword") or "").strip() or None
        if url:
            memory.add_watch(owner, url, kw)
        return {"ok": bool(url)}

    @router.post("/api/watches/delete")
    async def wat_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_watch(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/watches/update")
    async def wat_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        memory.update_watch(owner, int(d.get("id") or 0), url=(d.get("url") or None),
                            keyword=(d.get("keyword") or None))
        return {"ok": True}

    return router
