"""Reminders CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/reminders/update`
route used to live far from the rest of this CRUD (near the end of
`create_app()`, next to facts/links/... updates) — reunified here, same file
as create/list/delete, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/reminders")
    async def rem_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.open_reminders(owner)}

    @router.post("/api/reminders")
    async def rem_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        text = (d.get("text") or "").strip()
        when = (d.get("when") or "").strip() or None
        if text:
            memory.add_reminder(owner, text, when, ctx.recurval(d.get("recur")))
        return {"ok": bool(text)}

    @router.post("/api/reminders/delete")
    async def rem_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.cancel_reminder(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/reminders/update")
    async def rem_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        recur = ctx.recurval(d.get("recur"), allow_clear=True) if "recur" in d else None
        memory.update_reminder(owner, int(d.get("id") or 0), text=(d.get("text") or None),
                               when_iso=(d.get("when") or None), recur=recur)
        return {"ok": True}

    return router
