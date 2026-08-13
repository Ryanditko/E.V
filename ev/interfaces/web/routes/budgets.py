"""Budgets CRUD domain routes — Phase 6b, Group 5 route split. (Subscriptions
and watches CRUD were already split out in Group 2 — see recurring.py and
watches.py; only budgets remained inline in app.py.)

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/budgets")
    async def bud_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_budgets(owner)}

    @router.post("/api/budgets")
    async def bud_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        cat = (d.get("category") or "").strip()
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
        except Exception:
            return {"ok": False}
        if cat:
            memory.set_budget(owner, cat, amount)
        return {"ok": bool(cat)}

    @router.post("/api/budgets/delete")
    async def bud_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_budget(owner, ((await ctx.body(request)).get("category") or "").strip())
        return {"ok": True}

    return router
