"""Tasks CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/tasks")
    async def tasks_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.roll_due_tasks()  # keep recurring tasks rolled to their next occurrence
        return {"tasks": memory.open_tasks(owner)}

    @router.post("/api/tasks")
    async def tasks_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        text = (data.get("text") or "").strip()
        cat = (data.get("category") or "geral").strip() or "geral"
        if text:
            memory.add_task(owner, text, cat, recur=ctx.recurval(data.get("recur")),
                            due=(data.get("due") or "").strip() or None)
        return {"tasks": memory.open_tasks(owner)}

    @router.post("/api/tasks/update")
    async def tasks_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        recur = ctx.recurval(data.get("recur"), allow_clear=True) if "recur" in data else None
        due = (data.get("due") or "").strip() if "due" in data else None
        memory.update_task(owner, int(data.get("id") or 0),
                           text=(data.get("text") or None),
                           category=(data.get("category") or None),
                           recur=recur, due=due)
        return {"tasks": memory.open_tasks(owner)}

    @router.post("/api/tasks/complete")
    async def tasks_complete(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.complete_task(owner, int((await ctx.body(request)).get("id") or 0))
        return {"tasks": memory.open_tasks(owner)}

    @router.post("/api/tasks/delete")
    async def tasks_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_task(owner, int((await ctx.body(request)).get("id") or 0))
        return {"tasks": memory.open_tasks(owner)}

    return router
