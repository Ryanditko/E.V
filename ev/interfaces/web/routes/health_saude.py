"""Health & routine ("saúde") domain routes — Phase 6b, Group 5 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, owner = ctx.config, ctx.memory, ctx.owner

    def _today_local():
        from datetime import datetime, timezone as _tz
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(getattr(config, "timezone", "UTC"))).date().isoformat()
        except Exception:
            return datetime.now(_tz.utc).date().isoformat()

    @router.get("/api/saude")
    async def saude_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        day = _today_local()
        return {"day": day, "today": memory.health_day(owner, day),
                "history": memory.health_history(owner, 7)}

    @router.post("/api/saude")
    async def saude_post(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        day = _today_local()
        if d.get("water_inc") is not None:
            memory.health_water_inc(owner, day, int(d["water_inc"]))
        if d.get("sleep") is not None:
            memory.health_set(owner, day, "sleep", float(d["sleep"]))
        if d.get("mood") is not None:
            memory.health_set(owner, day, "mood", str(d["mood"])[:20])
        return {"ok": True, "today": memory.health_day(owner, day)}

    return router
