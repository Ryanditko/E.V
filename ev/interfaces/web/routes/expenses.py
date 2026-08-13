"""Expenses CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/expenses/update` route
used to live far from the rest of this CRUD (near the end of `create_app()`,
next to recurring/watches updates) — reunified here, same file as
create/list/delete, per Phase 6b Group 2 (no path/method/logic change).
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    def _num(v):
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return None

    @router.get("/api/expenses")
    async def exp_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        return {"items": memory.expenses_since(owner, since)}

    @router.post("/api/expenses")
    async def exp_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
        except Exception:
            return {"ok": False}
        memory.add_expense(owner, amount, (d.get("description") or "").strip() or "gasto",
                           (d.get("category") or "geral").strip() or "geral")
        return {"ok": True}

    @router.post("/api/expenses/delete")
    async def exp_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_expense(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/expenses/update")
    async def exp_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        memory.update_expense(owner, int(d.get("id") or 0), amount=_num(d.get("amount")),
                              description=(d.get("description") or None), category=(d.get("category") or None))
        return {"ok": True}

    return router
