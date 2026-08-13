"""E.V.'s web interface — a JARVIS-style operator console (voice + dashboard +
terminal + scoped conversations). Reuses the SAME brain/memory/tools as Telegram.

One self-contained page (no build) served by FastAPI. Auth: EV_WEB_TOKEN.
Conversations are scoped by folder -> conv_id = "web:<folder>" (own thread each,
shared data). Runs data commands AND interface commands (provedor/status/...).

Holds create_app(), now reduced (Phase 6b route-router split, complete as of
Group 5) to instantiating WebContext, registering every domain APIRouter
under .routes/, and the remaining structural routes: static assets, the
health check, and the live-update SSE stream. All ~177 domain routes live
in .routes/*.py. The static frontend (HTML/CSS/JS, favicon, service worker,
app icon) lives in .frontend (Phase 6a split).
"""

import asyncio
import hmac
import json
import logging

from ...config import Config
from ...core.brain import Brain
from ...core.commands import Commands
from ...core.memory import Memory

from .context import WebContext
from .frontend import _FAVICON, _SERVICE_WORKER, _icon_png, _PAGE
from .routes import (
    activity, backup, brain_view, budgets, chat, connectors, email, expenses,
    facts, gcal, goals, habits, health_saude, journal, kb, keys, links,
    local_agent, location_map, music, notifications, notify, oauth_github,
    oauth_google, pages, panel, push, recurring, reminders, scan_receipt,
    search, spotify, stt, tasks, vault, vision, voice_tts, watches, weather,
)

log = logging.getLogger("ev.web")


def create_app(config: Config, brain: Brain | None = None):
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import HTMLResponse

    import time as _time
    boot = _time.monotonic()
    memory = Memory(config.db_path)
    brain = brain or Brain(config, memory)
    commands = Commands(config, memory)
    owner = str(config.owner_id) if config.owner_id is not None else "web"
    app = FastAPI(title="E.V.")

    # WebContext bundles the singletons above + small cross-domain helpers
    # (Phase 6b route-router split). All domain routes now live under
    # .routes/ as APIRouters taking `ctx` directly — this function is left
    # with only structural bits (static files, boot-time SSE token check).
    ctx = WebContext(config, memory, brain, commands, owner)
    ctx.boot = boot  # used by panel.py's /api/panel uptime figure

    for _router_mod in (
        activity, backup, brain_view, budgets, chat, connectors, email,
        expenses, facts, gcal, goals, habits, health_saude, journal, kb,
        keys, links, local_agent, location_map, music, notifications,
        notify, oauth_github, oauth_google, pages, panel, push, recurring,
        reminders, scan_receipt, search, spotify, stt, tasks, vault, vision,
        voice_tts, watches, weather,
    ):
        app.include_router(_router_mod.build_router(ctx))

    @app.get("/", response_class=HTMLResponse)
    async def index():
        # never cache the HTML shell, so updates land immediately (no stale UI)
        return HTMLResponse(_PAGE, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    @app.get("/favicon.svg")
    async def favicon_svg():
        return Response(content=_FAVICON, media_type="image/svg+xml")

    @app.get("/favicon.ico")
    async def favicon_ico():
        return Response(content=_FAVICON, media_type="image/svg+xml")

    @app.get("/icon-192.png")
    async def icon192():
        return Response(content=_icon_png(192), media_type="image/png")

    @app.get("/icon-512.png")
    async def icon512():
        return Response(content=_icon_png(512), media_type="image/png")

    @app.get("/manifest.webmanifest")
    async def manifest():
        data = {
            "name": "E.V. — assistente pessoal", "short_name": "E.V.",
            "description": "Sua assistente E.V. — chat, voz, tarefas e agenda.",
            "start_url": "/", "scope": "/", "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#04070c", "theme_color": "#04070c",
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
                {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
            ],
        }
        return Response(content=json.dumps(data),
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    async def service_worker():
        return Response(content=_SERVICE_WORKER, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    @app.get("/api/health")
    async def health_ep():
        return {"ok": True}

    @app.get("/api/events")
    async def events(request: Request):
        # SSE — the browser's EventSource can't set headers, so the token comes as
        # a query param. Streams a tick whenever the DB is changed by ANY process
        # (e.g. the Telegram bot), so the web reflects it near-instantly.
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        from fastapi.responses import StreamingResponse
        import os as _os

        async def gen():
            # same open path as Memory (handles SQLCipher when EV_DB_KEY is set)
            conn, _row = Memory._connect(config.db_path, _os.getenv("EV_DB_KEY", "").strip())

            def _rev():
                return conn.execute("PRAGMA data_version").fetchone()[0]
            try:
                last = _rev()   # fast read, no thread hop needed
                yield "retry: 4000\n\ndata: ready\n\n"
                while True:
                    await asyncio.sleep(2)
                    try:
                        dv = _rev()
                    except Exception:
                        continue
                    if dv != last:
                        last = dv
                        yield f"data: {dv}\n\n"
                    else:
                        yield ": ping\n\n"   # keepalive; also detects client disconnect
            finally:
                conn.close()
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # All remaining domain routes (face/kb/charts/serious/overview/goals/
    # saude/vault/local-tasks/local-scripts/budgets/search/panel/brain/notify,
    # plus chat/threads/history/cmd/commands/briefing/greeting) moved to
    # .routes/ (Phase 6b, Group 5 — the final group of the route-router
    # split). This function now holds only structural routes (static
    # assets, health check, live-update SSE) plus router registration.

    return app


def run():
    import uvicorn

    config = Config.load(require_telegram=False)
    if not config.web_token:
        raise SystemExit("EV_WEB_TOKEN não configurado no .env.")
    logging.basicConfig(level=logging.INFO)
    log.info("E.V. web em http://%s:%s", config.web_host, config.web_port)
    uvicorn.run(create_app(config), host=config.web_host, port=config.web_port)
