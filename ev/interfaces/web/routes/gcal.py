"""Google Calendar domain routes — Phase 6b, Group 4 route split
(external-API-dependent: Google Calendar via `ev/providers/tools/calendar.py`).
Distinct from the Group-5 aggregation "calendar" item, which refers to a
different, not-yet-existing aggregate view — there is no separate `/api/calendar`
endpoint in `app.py` today, only this Google-specific `/api/gcal*` family.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config = ctx.config

    def _tz_iso(v: str) -> str:
        """A naive datetime-local value -> ISO with the configured tz offset."""
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(config.timezone))
            return dt.isoformat()
        except Exception:
            return v

    @router.get("/api/gcal")
    async def gcal_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        if not config.google_ready() or not config.google_authorized():
            return {"ok": False, "events": [], "msg": "Google não autorizado."}
        start = request.query_params.get("start") or ""
        end = request.query_params.get("end") or ""
        from ....providers import tools
        try:
            events = await asyncio.to_thread(
                tools.calendar_list_range, config, config.default_account, start, end)
            return {"ok": True, "events": events}
        except Exception as exc:
            return {"ok": False, "events": [], "msg": str(exc)}

    @router.post("/api/gcal/create")
    async def gcal_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        summary = (d.get("summary") or "").strip()
        start = (d.get("start") or "").strip()
        end = (d.get("end") or "").strip()
        if not summary or not start:
            return {"ok": False, "msg": "Faltou título ou início."}
        start_iso = _tz_iso(start)
        if end:
            end_iso = _tz_iso(end)
        else:
            from datetime import datetime, timedelta
            try:
                end_iso = (datetime.fromisoformat(start_iso) + timedelta(hours=1)).isoformat()
            except Exception:
                end_iso = start_iso
        from ....providers import tools
        try:
            msg = await asyncio.to_thread(
                tools.calendar_create, config, config.default_account,
                summary, start_iso, end_iso)
            ok = "criei" in msg.lower() or "criado" in msg.lower() or "http" in msg.lower()
            return {"ok": ok, "msg": msg}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    @router.post("/api/gcal/delete")
    async def gcal_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        eid = ((await ctx.body(request)).get("id") or "").strip()
        if not eid:
            return {"ok": False}
        from ....providers import tools
        try:
            await asyncio.to_thread(
                tools.calendar_delete, config, config.default_account, eid)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    return router
