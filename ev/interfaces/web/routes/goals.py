"""Financial goals ("cofrinho") domain routes — Phase 6b, Group 5 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/goals")
    async def goals_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_goals(owner)}

    @router.post("/api/goals")
    async def goals_add(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        name = (d.get("name") or "").strip()
        target = float(d.get("target") or 0)
        if not name or target <= 0:
            raise HTTPException(status_code=400, detail="nome e valor alvo obrigatórios")
        return {"ok": True, "id": memory.add_goal(owner, name[:60], target)}

    @router.post("/api/goals/add")
    async def goals_addmoney(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        memory.add_to_goal(owner, int(d.get("id") or 0), float(d.get("amount") or 0))
        return {"ok": True}

    @router.post("/api/goals/delete")
    async def goals_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_goal(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    return router
