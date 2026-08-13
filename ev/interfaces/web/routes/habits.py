"""Habits CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/habits/update` route
used to live far from the rest of this CRUD (near the end of `create_app()`,
next to journal/recurring/... updates) — reunified here, same file as
create/list/delete/done, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/habits")
    async def habits_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        from datetime import date
        today = date.today().isoformat()
        out = []
        for h in memory.list_habits(owner):
            days = memory.habit_days(h["id"])
            out.append({"id": h["id"], "name": h["name"],
                        "done_today": today in days, "total": len(days),
                        "days": sorted(days)[-180:]})  # recent days for the heatmap
        return {"items": out}

    @router.post("/api/habits")
    async def habits_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        name = ((await ctx.body(request)).get("name") or "").strip()
        if name:
            memory.add_habit(owner, name)
        return {"ok": bool(name)}

    @router.post("/api/habits/done")
    async def habits_done(request: Request):
        ctx.check(request.headers.get("authorization"))
        from datetime import date
        memory.log_habit(int((await ctx.body(request)).get("id") or 0), date.today().isoformat())
        return {"ok": True}

    @router.post("/api/habits/delete")
    async def habits_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_habit(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/habits/update")
    async def hab_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        n = (d.get("name") or "").strip()
        if n:
            memory.rename_habit(owner, int(d.get("id") or 0), n)
        return {"ok": bool(n)}

    return router
