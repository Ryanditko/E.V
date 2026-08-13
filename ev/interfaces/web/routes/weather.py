"""Weather/astro/radar domain routes — Phase 6b, Group 4 route split
(external-API-dependent: weather provider, wheretheiss.at, exchange rates,
CoinGecko, TabNews headlines).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio

from fastapi import APIRouter, Request

from ....providers import tools as tools_mod
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config = ctx.config

    @router.get("/api/astro")
    async def astro_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        import httpx
        city = (request.query_params.get("city") or getattr(config, "city", "") or "").strip()
        moon = tools_mod.moon_phase()
        sun = {}
        if city:
            try:
                wf = await asyncio.to_thread(tools_mod.weather_full, city)
                t = wf.get("today", {})
                sun = {"sunrise": t.get("sunrise"), "sunset": t.get("sunset")}
            except Exception:
                pass
        iss = {}
        try:
            r = await asyncio.to_thread(
                lambda: httpx.get("https://api.wheretheiss.at/v1/satellites/25544", timeout=8).json())
            iss = {"lat": round(r.get("latitude", 0), 1), "lng": round(r.get("longitude", 0), 1),
                   "alt": round(r.get("altitude", 0))}
        except Exception:
            pass
        return {"moon": moon, "sun": sun, "iss": iss, "city": city}

    @router.get("/api/radar")
    async def radar_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        import httpx
        def _work():
            out = {"rates": {}, "headlines": []}
            try:
                r = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=10).json().get("rates", {})
                if r.get("BRL"):
                    out["rates"]["usd"] = round(r["BRL"], 2)
                    if r.get("EUR"):
                        out["rates"]["eur"] = round(r["BRL"] / r["EUR"], 2)
            except Exception:
                pass
            try:
                b = httpx.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl",
                              timeout=10).json()
                if b.get("bitcoin", {}).get("brl"):
                    out["rates"]["btc"] = round(b["bitcoin"]["brl"])
            except Exception:
                pass
            try:
                c = httpx.get("https://www.tabnews.com.br/api/v1/contents?per_page=6&strategy=relevant",
                              timeout=10).json()
                for x in (c or [])[:6]:
                    out["headlines"].append({
                        "title": x.get("title"),
                        "url": "https://www.tabnews.com.br/" + (x.get("owner_username") or "") + "/" + (x.get("slug") or "")})
            except Exception:
                pass
            return out
        return await asyncio.to_thread(_work)

    @router.get("/api/weather")
    async def weather_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        city = (request.query_params.get("city") or getattr(config, "city", "") or "").strip()
        if not city:
            return {"error": "defina uma cidade (EV_CITY) ou busque uma no campo acima"}
        data = await asyncio.to_thread(tools_mod.weather_full, city)
        return data or {"error": f"não consegui o clima de '{city}'"}

    return router
