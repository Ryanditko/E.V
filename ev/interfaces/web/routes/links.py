"""Links CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/links/update` route
used to live far from the rest of this CRUD (near the end of `create_app()`,
next to expenses/reminders/facts/... updates) — reunified here, same file as
create/list/delete, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/links")
    async def links_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_links(owner)}

    @router.post("/api/links")
    async def links_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        name = (d.get("name") or "").strip()
        url = (d.get("url") or "").strip()
        cat = (d.get("category") or "geral").strip() or "geral"
        if name and url:
            memory.add_link(owner, cat, name, url)
        return {"ok": bool(name and url)}

    @router.post("/api/links/delete")
    async def links_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_link(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/links/update")
    async def link_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        memory.update_link(owner, int(d.get("id") or 0), category=(d.get("category") or None),
                           name=(d.get("name") or None), url=(d.get("url") or None))
        return {"ok": True}

    return router
