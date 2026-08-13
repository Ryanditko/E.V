"""Recurring expenses CRUD domain routes — Phase 6b, Group 2 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. The `/api/recurring/update`
route used to live far from the rest of this CRUD (near the end of
`create_app()`, next to habits/watches/... updates) — reunified here, same
file as create/list/delete, per Phase 6b Group 2 (no path/method/logic
change).

`budgets` (also declared under the "Subscriptions / Budgets / Watches CRUD"
comment in `app.py`) is NOT part of this domain split — it stays in
`app.py`, scheduled for a later group per the refactor plan.
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

    @router.get("/api/recurring")
    async def rec_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_recurring(owner)}

    @router.post("/api/recurring")
    async def rec_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
            day = max(1, min(28, int(d.get("day") or 1)))
        except Exception:
            return {"ok": False}
        memory.add_recurring(owner, amount, (d.get("description") or "assinatura").strip(),
                             (d.get("category") or "assinatura").strip() or "assinatura", day)
        return {"ok": True}

    @router.post("/api/recurring/delete")
    async def rec_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_recurring(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/recurring/update")
    async def rec_update(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            day = int(d.get("day")) if d.get("day") else None
        except Exception:
            day = None
        memory.update_recurring(owner, int(d.get("id") or 0), amount=_num(d.get("amount")),
                                description=(d.get("description") or None),
                                category=(d.get("category") or None), day=day)
        return {"ok": True}

    return router
