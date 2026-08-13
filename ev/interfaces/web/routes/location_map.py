"""Location/map domain routes — Phase 6b, Group 4 route split
(external-API-dependent: reverse geocoding, nearby places, geocoding and
routing via `ev/providers/tools`).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio

from fastapi import APIRouter, Request

from ....providers import tools as tools_mod
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.post("/api/location")
    async def set_location(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"ok": False}
        from datetime import datetime, timezone
        memory.set_setting("loc_lat", f"{lat:.6f}")
        memory.set_setting("loc_lng", f"{lng:.6f}")
        memory.set_setting("loc_time", datetime.now(timezone.utc).isoformat())
        try:  # best-effort readable address so E.V. can say where you are
            addr = await asyncio.to_thread(tools_mod.reverse_geocode, lat, lng)
            if addr:
                memory.set_setting("loc_addr", addr)
        except Exception:
            pass
        return {"ok": True}

    @router.post("/api/nearby")
    async def nearby(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"items": [], "msg": "sem localização"}
        query = (d.get("query") or "").strip()
        items = await asyncio.to_thread(tools_mod.nearby_places, lat, lng, query)
        return {"items": items}

    @router.get("/api/places")
    async def places_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_places(owner)}

    @router.post("/api/places")
    async def places_add(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"ok": False}
        name = (d.get("name") or "Ponto").strip()
        pid = memory.add_place(owner, name, lat, lng)
        return {"ok": True, "id": pid, "items": memory.list_places(owner)}

    @router.post("/api/places/delete")
    async def places_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_place(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True, "items": memory.list_places(owner)}

    @router.get("/api/geocode")
    async def geocode_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return {"ok": False}
        g = await asyncio.to_thread(tools_mod.geocode, q)
        return {"ok": bool(g), **(g or {})}

    @router.post("/api/route")
    async def route_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        try:
            fr, to = d.get("from"), d.get("to")
            fl, fg = float(fr[0]), float(fr[1])
            tl, tg = float(to[0]), float(to[1])
        except (TypeError, ValueError, IndexError):
            return {"ok": False}
        r = await asyncio.to_thread(
            tools_mod.route, fl, fg, tl, tg, (d.get("mode") or "car"))
        return {"ok": bool(r), **(r or {})}

    return router
