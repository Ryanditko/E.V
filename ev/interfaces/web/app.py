"""E.V.'s web interface — a JARVIS-style operator console (voice + dashboard +
terminal + scoped conversations). Reuses the SAME brain/memory/tools as Telegram.

One self-contained page (no build) served by FastAPI. Auth: EV_WEB_TOKEN.
Conversations are scoped by folder -> conv_id = "web:<folder>" (own thread each,
shared data). Runs data commands AND interface commands (provedor/status/...).

Holds create_app() and its ~177 routes. The static frontend (HTML/CSS/JS,
favicon, service worker, app icon) lives in .frontend (Phase 6a split).
"""

import asyncio
import hmac
import json
import logging

from ...config import Config
from ...core import health, knowledge
from ...core.brain import Brain
from ...core.commands import COMMAND_LIST, Commands
from ...core.memory import Memory
from ...providers import tools as tools_mod, voice as voice_mod

from .context import WebContext
from .frontend import _DEFAULT_FOLDERS, _FAVICON, _SERVICE_WORKER, _icon_png, _PAGE
from .routes import activity, backup, connectors, keys, notifications, pages, push

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
    # (Phase 6b route-router split). Aliased to the historical bare names so
    # every route defined below (still inline in this function) keeps working
    # unchanged, while routers under .routes/ take `ctx` directly.
    ctx = WebContext(config, memory, brain, commands, owner)
    _check = ctx.check
    _body = ctx.body
    _recurval = ctx.recurval
    _folders = ctx.folders
    _conv = ctx.conv
    _status_text = ctx.status_text
    run_command = ctx.run_command
    _env_write = ctx.env_write

    for _router_mod in (activity, backup, connectors, keys, notifications, pages, push):
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

    _greet = []  # cache the welcome audio (edge-tts, no LLM) for the server's life

    @app.get("/api/briefing")
    async def briefing(request: Request):
        # A live spoken boot briefing (deterministic status). Shown + spoken.
        _check(request.headers.get("authorization"))
        try:
            return {"text": commands.spoken_status(owner)}
        except Exception:
            return {"text": "Bem-vindo de volta, Ryan. Sistemas online, tudo pronto pra você."}

    @app.get("/api/greeting")
    async def greeting(request: Request):
        from fastapi import Response as R
        _check(request.headers.get("authorization"))
        try:
            phrase = commands.spoken_status(owner)
        except Exception:
            phrase = "Bem-vindo de volta, Ryan. Sistemas online, tudo pronto pra você."
        try:
            audio, mime = await voice_mod.synth_web(config, phrase)
        except Exception:
            audio, mime = b"", "audio/mpeg"
        return R(content=audio, media_type=mime)

    @app.get("/api/health")
    async def health_ep():
        return {"ok": True}

    @app.get("/api/commands")
    async def commands_ep(request: Request):
        _check(request.headers.get("authorization"))
        return {"commands": [{"name": n, "desc": d} for n, d in COMMAND_LIST]}

    @app.get("/api/threads")
    async def threads_get(request: Request):
        _check(request.headers.get("authorization"))
        return {"threads": _folders()}

    @app.post("/api/threads")
    async def threads_post(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        name = (data.get("name") or "").strip().lower().replace(" ", "-").replace("/", "-")
        parent = (data.get("parent") or "").strip().lower()
        if name:
            path = f"{parent}/{name}" if parent else name
            fs = _folders()
            if path not in fs:
                fs.append(path)
                memory.set_setting("web_folders", json.dumps(fs))
        return {"threads": _folders()}

    @app.post("/api/threads/move")
    async def threads_move(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        path = (data.get("path") or "").strip().lower()
        parent = (data.get("parent") or "").strip().lower()  # "" = to root
        if not path or path == "geral" or parent == path or parent.startswith(path + "/"):
            return {"threads": _folders()}  # can't move into itself/descendant
        leaf = path.rsplit("/", 1)[-1]
        newpath = f"{parent}/{leaf}" if parent else leaf
        fs = _folders()
        if newpath != path and path in fs and newpath not in fs:
            out = []
            for f in fs:
                if f == path or f.startswith(path + "/"):
                    nf = newpath + f[len(path):]
                    memory.rename_conversation(_conv(f), _conv(nf))
                    out.append(nf)
                else:
                    out.append(f)
            memory.set_setting("web_folders", json.dumps(out))
        return {"threads": _folders()}

    @app.get("/api/history")
    async def history_ep(request: Request):
        _check(request.headers.get("authorization"))
        thread = request.query_params.get("thread", "geral")
        msgs = memory.recent_messages(_conv(thread), limit=50)
        return {"messages": msgs}

    @app.post("/api/chat")
    async def chat(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo. 🙂"}
        reply = await brain.respond(owner, conv_id=_conv(data.get("thread")), text=text)
        brain.pop_documents()
        brain.pop_actions()
        steps = brain.pop_steps() if hasattr(brain, "pop_steps") else []
        return {"reply": reply, "steps": steps}

    @app.post("/api/chat/stream")
    async def chat_stream(request: Request):
        _check(request.headers.get("authorization"))
        from fastapi.responses import StreamingResponse
        import re as _re
        data = await _body(request)
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo."}
        reply = await brain.respond(owner, conv_id=_conv(data.get("thread")), text=text)
        brain.pop_documents()
        brain.pop_actions()

        async def gen():
            # progressive reveal of the computed reply (live-typing feel)
            for w in (_re.findall(r"\S+\s*", reply) or [reply]):
                yield w
                await asyncio.sleep(0.015)
        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    @app.post("/api/cmd")
    async def cmd(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        command = (data.get("command") or "").strip()
        thread = data.get("thread")
        reply = await run_command(command, thread)
        name = command.lstrip("/").split()[0].lower() if command else ""
        if name not in ("limpar", "limparchat"):  # don't re-log after clearing
            conv = _conv(thread)
            memory.add_message(conv, "user", "/" + command)
            memory.add_message(conv, "model", reply)
        return {"reply": reply}

    @app.post("/api/threads/delete")
    async def threads_delete(request: Request):
        _check(request.headers.get("authorization"))
        name = ((await _body(request)).get("name") or "").strip().lower()
        if name and name != "geral":
            fs = _folders()
            victims = [f for f in fs if f == name or f.startswith(name + "/")]
            if victims:
                memory.set_setting(
                    "web_folders", json.dumps([f for f in fs if f not in victims]))
                for v in victims:  # drop the folder and its subfolders' conversations
                    memory.clear_conversation(_conv(v))
        return {"threads": _folders()}

    @app.post("/api/threads/rename")
    async def threads_rename(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        old = (data.get("old") or "").strip().lower()
        new = (data.get("new") or "").strip().lower().replace(" ", "-").replace("/", "-")
        if old and new and old != "geral":
            parent = old.rsplit("/", 1)[0] if "/" in old else ""
            newpath = f"{parent}/{new}" if parent else new
            fs = _folders()
            if old in fs and newpath not in fs:
                out = []
                for f in fs:  # rename the folder AND all its descendants
                    if f == old or f.startswith(old + "/"):
                        nf = newpath + f[len(old):]
                        memory.rename_conversation(_conv(f), _conv(nf))
                        out.append(nf)
                    else:
                        out.append(f)
                memory.set_setting("web_folders", json.dumps(out))
        return {"threads": _folders()}

    _DEF_ACTIONS = ["plano", "buscar", "noticias", "clima", "relatorio", "semana"]
    _DEF_STATS = ["tasks", "reminders", "expenses", "memories", "kb"]

    def _cfg_list(key, default):
        raw = memory.get_setting(key)
        try:
            v = json.loads(raw) if raw else None
        except Exception:
            v = None
        return v if isinstance(v, list) else list(default)

    @app.get("/api/config")
    async def cfg_get(request: Request):
        _check(request.headers.get("authorization"))
        return {"actions": _cfg_list("web_actions", _DEF_ACTIONS),
                "stats": _cfg_list("web_stats", _DEF_STATS),
                "mapillary": bool(getattr(config, "mapillary_token", ""))}

    @app.get("/api/mapillary")
    async def mapillary_token(request: Request):
        # The in-app street-level viewer runs client-side and needs the token.
        _check(request.headers.get("authorization"))
        tok = getattr(config, "mapillary_token", "") or ""
        return {"enabled": bool(tok), "token": tok}

    @app.post("/api/config")
    async def cfg_set(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        if isinstance(data.get("actions"), list):
            memory.set_setting("web_actions", json.dumps(data["actions"][:24]))
        if isinstance(data.get("stats"), list):
            memory.set_setting("web_stats", json.dumps(data["stats"][:10]))
        return {"ok": True}

    # --- Tasks CRUD (dedicated panel) --------------------------------------
    @app.get("/api/tasks")
    async def tasks_get(request: Request):
        _check(request.headers.get("authorization"))
        memory.roll_due_tasks()  # keep recurring tasks rolled to their next occurrence
        return {"tasks": memory.open_tasks(owner)}

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

    @app.get("/api/face")
    async def face_get(request: Request):
        # Owner face descriptor (greeting/personalization only). Never other people.
        _check(request.headers.get("authorization"))
        raw = memory.get_setting("face_descriptor") or ""
        try:
            desc = json.loads(raw) if raw else None
        except ValueError:
            desc = None
        return {"enrolled": bool(desc), "descriptor": desc}

    @app.post("/api/face")
    async def face_set(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        if data.get("clear"):
            memory.set_setting("face_descriptor", "")
            return {"ok": True, "enrolled": False}
        desc = data.get("descriptor")
        if (not isinstance(desc, list) or len(desc) != 128
                or not all(isinstance(x, (int, float)) for x in desc)):
            raise HTTPException(status_code=400, detail="invalid descriptor")
        memory.set_setting("face_descriptor", json.dumps([float(x) for x in desc]))
        return {"ok": True, "enrolled": True}

    @app.post("/api/tasks")
    async def tasks_create(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        text = (data.get("text") or "").strip()
        cat = (data.get("category") or "geral").strip() or "geral"
        if text:
            memory.add_task(owner, text, cat, recur=_recurval(data.get("recur")),
                            due=(data.get("due") or "").strip() or None)
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/update")
    async def tasks_update(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        recur = _recurval(data.get("recur"), allow_clear=True) if "recur" in data else None
        due = (data.get("due") or "").strip() if "due" in data else None
        memory.update_task(owner, int(data.get("id") or 0),
                           text=(data.get("text") or None),
                           category=(data.get("category") or None),
                           recur=recur, due=due)
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/complete")
    async def tasks_complete(request: Request):
        _check(request.headers.get("authorization"))
        memory.complete_task(owner, int((await _body(request)).get("id") or 0))
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/delete")
    async def tasks_delete(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_task(owner, int((await _body(request)).get("id") or 0))
        return {"tasks": memory.open_tasks(owner)}

    # --- Knowledge base ----------------------------------------------------
    @app.get("/api/kb")
    async def kb_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"sources": memory.list_sources(owner),
                "files": memory.kb_file_sources(owner)}

    @app.get("/api/kb/file")
    async def kb_file(request: Request):
        from urllib.parse import quote
        _check(request.headers.get("authorization"))
        f = memory.get_kb_file(owner, request.query_params.get("source", ""))
        if not f:
            raise HTTPException(status_code=404, detail="arquivo não encontrado")
        fn = f["filename"] or "arquivo"
        return Response(
            content=f["data"], media_type=f["mime"] or "application/octet-stream",
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(fn)}"},
        )

    @app.post("/api/kb/url")
    async def kb_url(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        url = (d.get("url") or "").strip()
        name = (d.get("name") or "").strip() or None
        if not url.lower().startswith("http"):
            return {"ok": False, "msg": "Informe uma URL válida (http...)."}
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_url, url, config, memory, owner, name)
            msg = f"{stored} trechos indexados" + (" (parcial)" if trunc else "") if stored else "Não achei texto útil."
            return {"ok": stored > 0, "msg": msg, "sources": memory.list_sources(owner)}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:120]}

    @app.post("/api/kb/text")
    async def kb_text(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        title = (d.get("title") or "Nota").strip()
        text = (d.get("text") or "").strip()
        if not text:
            return {"ok": False, "msg": "Texto vazio."}
        stored, trunc = await asyncio.to_thread(
            knowledge.ingest_text, text, title, config, memory, owner)
        return {"ok": stored > 0, "msg": f"{stored} trechos indexados",
                "sources": memory.list_sources(owner)}

    @app.post("/api/kb/upload")
    async def kb_upload(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("file")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhum arquivo enviado."}
        fname = f.filename or "arquivo"
        if not fname.lower().endswith(knowledge.READABLE_EXTS):
            return {"ok": False, "msg": "Só PDF, Word (.docx) ou texto (.txt/.md)."}
        title = (form.get("title") or "").strip() or None
        data = await f.read()
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_file, data, fname, config, memory, owner, title)
            label = title or fname
            if stored and len(data) <= 25_000_000:  # keep the original for download/open
                mime = getattr(f, "content_type", None) or "application/octet-stream"
                memory.save_kb_file(owner, label, fname, mime, data)
            msg = f"'{label}': {stored} trechos" if stored else "Sem texto extraível."
            return {"ok": stored > 0, "msg": msg, "sources": memory.list_sources(owner)}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:120]}

    @app.post("/api/kb/delete")
    async def kb_delete(request: Request):
        _check(request.headers.get("authorization"))
        source = ((await _body(request)).get("source") or "").strip()
        n = memory.delete_source(owner, source) if source else 0
        return {"ok": n > 0, "sources": memory.list_sources(owner)}

    # --- Expenses / Reminders / Memories CRUD ------------------------------
    @app.get("/api/expenses")
    async def exp_list(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        return {"items": memory.expenses_since(owner, since)}

    @app.post("/api/expenses")
    async def exp_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
        except Exception:
            return {"ok": False}
        memory.add_expense(owner, amount, (d.get("description") or "").strip() or "gasto",
                           (d.get("category") or "geral").strip() or "geral")
        return {"ok": True}

    @app.post("/api/expenses/delete")
    async def exp_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_expense(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/reminders")
    async def rem_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.open_reminders(owner)}

    @app.post("/api/reminders")
    async def rem_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        text = (d.get("text") or "").strip()
        when = (d.get("when") or "").strip() or None
        if text:
            memory.add_reminder(owner, text, when, _recurval(d.get("recur")))
        return {"ok": bool(text)}

    @app.post("/api/reminders/delete")
    async def rem_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.cancel_reminder(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/facts")
    async def fact_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_facts(owner)}

    @app.post("/api/facts")
    async def fact_create(request: Request):
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if text:
            memory.add_fact(owner, text)
        return {"ok": bool(text)}

    @app.post("/api/facts/delete")
    async def fact_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_fact(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.post("/api/facts/clear")
    async def fact_clear(request: Request):
        _check(request.headers.get("authorization"))
        n = memory.clear_facts(owner)
        return {"ok": True, "cleared": n}

    @app.get("/api/charts")
    async def charts(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        qp = request.query_params

        def _pd(s):
            try:
                return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return None
        frm = _pd(qp.get("from", ""))
        to = _pd(qp.get("to", ""))
        if not frm:  # default = current month
            _, since, _ = commands._month_bounds(0)
            frm = datetime.fromisoformat(since)
        if not to:
            to = datetime.now(timezone.utc)
        to_end = (to.replace(hour=0, minute=0, second=0, microsecond=0)
                  + timedelta(days=1)).isoformat()
        exps = [e for e in memory.expenses_since(owner, frm.isoformat())
                if (e.get("created") or "") < to_end]

        bycat: dict = {}
        for e in exps:
            bycat[e["category"]] = bycat.get(e["category"], 0) + e.get("amount", 0)
        cat = sorted(bycat.items(), key=lambda x: -x[1])[:8]

        span = max(1, (to.date() - frm.date()).days)
        by_month = span > 62
        buckets: dict = {}
        d = frm.date()
        while d <= to.date():
            key = d.strftime("%Y-%m") if by_month else d.isoformat()
            buckets.setdefault(key, 0)
            d += timedelta(days=1)
        for e in exps:
            c = (e.get("created") or "")[:10]
            key = c[:7] if by_month else c
            if key in buckets:
                buckets[key] += e.get("amount", 0)
        series = [{"label": (k[5:] if not by_month else k),
                   "value": round(v, 2)} for k, v in buckets.items()]

        fd, td = frm.date().isoformat(), to.date().isoformat()
        habits = []
        for h in memory.list_habits(owner):
            try:
                done = sum(1 for x in memory.habit_days(h["id"]) if fd <= x <= td)
            except Exception:
                done = 0
            habits.append({"label": h["name"], "value": done})
        return {
            "exp_cat": [{"label": k, "value": round(v, 2)} for k, v in cat],
            "exp_day": series,
            "habits": habits[:10],
            "range": {"from": fd, "to": td},
        }

    # keys/custom-keys/connectors/pages routes moved to .routes/ (Phase 6b,
    # Group 1). `os`/`re` are still imported here because other, not-yet-split
    # routes below (e.g. /api/chat/stream, /api/events) use `_re`/`_os`.
    import os as _os
    import re as _re

    @app.get("/api/astro")
    async def astro_ep(request: Request):
        _check(request.headers.get("authorization"))
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

    @app.get("/api/radar")
    async def radar_ep(request: Request):
        _check(request.headers.get("authorization"))
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

    @app.get("/api/weather")
    async def weather_ep(request: Request):
        _check(request.headers.get("authorization"))
        city = (request.query_params.get("city") or getattr(config, "city", "") or "").strip()
        if not city:
            return {"error": "defina uma cidade (EV_CITY) ou busque uma no campo acima"}
        data = await asyncio.to_thread(tools_mod.weather_full, city)
        return data or {"error": f"não consegui o clima de '{city}'"}

    # --- music (Spotify embed player) --------------------------------------
    from ...providers import spotify as _sp
    _SP_PT = {"playlist": "Playlist", "track": "Faixa", "album": "Álbum",
              "artist": "Artista", "show": "Podcast", "episode": "Episódio"}

    @app.get("/api/music")
    async def music_list(request: Request):
        _check(request.headers.get("authorization"))
        items = memory.list_music(owner)
        for it in items:
            it["embed"] = _sp.embed_url(it["kind"], it["ref"])
        return {"items": items}

    @app.post("/api/music")
    async def music_add(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        parsed = _sp.parse(d.get("url") or "")
        if not parsed:
            raise HTTPException(status_code=400, detail=(
                "link não suportado — cole uma playlist, faixa, álbum, artista, "
                "podcast ou episódio do Spotify (perfil não tem player)"))
        kind, ref = parsed
        label = (d.get("label") or "").strip() or _SP_PT.get(kind, kind)
        mid = memory.add_music(owner, label[:80], kind, ref)
        return {"ok": True, "id": mid, "embed": _sp.embed_url(kind, ref)}

    @app.post("/api/music/delete")
    async def music_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_music(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    def _today_local():
        from datetime import datetime, timezone as _tz
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(getattr(config, "timezone", "UTC"))).date().isoformat()
        except Exception:
            return datetime.now(_tz.utc).date().isoformat()

    # --- modo foco (alerta vermelho) --------------------------------------
    @app.post("/api/serious")
    async def serious_set(request: Request):
        _check(request.headers.get("authorization"))
        body = await request.json()
        memory.set_setting("serious_mode", "1" if body.get("on") else "0")
        return {"ok": True, "serious": bool(body.get("on"))}

    # --- home dashboard overview -------------------------------------------
    @app.get("/api/overview")
    async def overview_ep(request: Request):
        _check(request.headers.get("authorization"))
        return commands.overview(owner)

    # --- financial goals (cofrinho) ----------------------------------------
    @app.get("/api/goals")
    async def goals_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_goals(owner)}

    @app.post("/api/goals")
    async def goals_add(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        name = (d.get("name") or "").strip()
        target = float(d.get("target") or 0)
        if not name or target <= 0:
            raise HTTPException(status_code=400, detail="nome e valor alvo obrigatórios")
        return {"ok": True, "id": memory.add_goal(owner, name[:60], target)}

    @app.post("/api/goals/add")
    async def goals_addmoney(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.add_to_goal(owner, int(d.get("id") or 0), float(d.get("amount") or 0))
        return {"ok": True}

    @app.post("/api/goals/delete")
    async def goals_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_goal(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    # --- health & routine --------------------------------------------------
    @app.get("/api/saude")
    async def saude_get(request: Request):
        _check(request.headers.get("authorization"))
        day = _today_local()
        return {"day": day, "today": memory.health_day(owner, day),
                "history": memory.health_history(owner, 7)}

    @app.post("/api/saude")
    async def saude_post(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        day = _today_local()
        if d.get("water_inc") is not None:
            memory.health_water_inc(owner, day, int(d["water_inc"]))
        if d.get("sleep") is not None:
            memory.health_set(owner, day, "sleep", float(d["sleep"]))
        if d.get("mood") is not None:
            memory.health_set(owner, day, "mood", str(d["mood"])[:20])
        return {"ok": True, "today": memory.health_day(owner, day)}

    # --- document vault (encrypted, OCR-searchable) ------------------------
    @app.get("/api/vault")
    async def vault_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_documents(owner, (request.query_params.get("q") or "").strip())}

    @app.post("/api/vault")
    async def vault_add(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("file")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            raise HTTPException(status_code=400, detail="nenhum arquivo enviado")
        data = await f.read()
        if len(data) > 15_000_000:
            raise HTTPException(status_code=400, detail="arquivo grande demais (máx 15 MB)")
        mime = getattr(f, "content_type", "") or "application/octet-stream"
        name = getattr(f, "filename", "documento") or "documento"
        text = ""
        if mime.startswith("image/") and brain:
            try:
                text = (await brain.ocr_image(data, mime)) or ""
            except Exception:
                text = ""
        memory.add_document(owner, name[:120], mime, data, text[:20000])
        return {"ok": True}

    @app.get("/api/vault/file")
    async def vault_file(request: Request):
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        doc = memory.get_document(owner, int(request.query_params.get("id") or 0))
        if not doc:
            raise HTTPException(status_code=404, detail="não encontrado")
        safe = (doc["name"] or "documento").replace('"', "")
        return Response(content=doc["data"], media_type=doc["mime"],
                        headers={"Content-Disposition": f'inline; filename="{safe}"'})

    @app.post("/api/vault/delete")
    async def vault_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_document(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    # --- local execution agent (runs on the user's own PC) -----------------
    # Every task requires explicit human approval — no kind auto-runs, ever.
    _LOCAL_TASK_KINDS = {"script", "open", "browser", "shell"}

    @app.get("/api/local-tasks")
    async def local_tasks_list(request: Request):
        _check(request.headers.get("authorization"))
        status = (request.query_params.get("status") or "").strip() or None
        return {"items": memory.list_local_tasks(owner, status)}

    @app.post("/api/local-tasks")
    async def local_tasks_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        kind = (d.get("kind") or "").strip().lower()
        label = (d.get("label") or "").strip()
        if kind not in _LOCAL_TASK_KINDS or not label:
            raise HTTPException(status_code=400, detail="kind/label inválidos")
        tid = memory.add_local_task(owner, kind, label[:200], {"command": d.get("command") or ""})
        return {"ok": True, "id": tid}

    @app.post("/api/local-tasks/approve")
    async def local_tasks_approve(request: Request):
        _check(request.headers.get("authorization"))
        tid = int((await _body(request)).get("id") or 0)
        ok = memory.set_local_task_status(owner, tid, "approved")
        return {"ok": ok}

    @app.post("/api/local-tasks/reject")
    async def local_tasks_reject(request: Request):
        _check(request.headers.get("authorization"))
        tid = int((await _body(request)).get("id") or 0)
        ok = memory.set_local_task_status(owner, tid, "rejected")
        return {"ok": ok}

    @app.get("/api/local-tasks/claim")
    async def local_tasks_claim(request: Request):
        # The local daemon polls this from the user's own machine using the
        # same bearer token as the web console — it only ever receives tasks
        # a human already approved.
        _check(request.headers.get("authorization"))
        task = memory.claim_local_task(owner)
        return {"task": task}

    @app.post("/api/local-tasks/result")
    async def local_tasks_result(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        tid = int(d.get("id") or 0)
        ok = memory.finish_local_task(owner, tid, bool(d.get("ok")), d.get("output") or {})
        return {"ok": ok}

    @app.get("/api/local-scripts")
    async def local_scripts_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_local_scripts(owner)}

    @app.post("/api/local-scripts")
    async def local_scripts_add(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        name = (d.get("name") or "").strip()
        command = (d.get("command") or "").strip()
        if not name or not command:
            raise HTTPException(status_code=400, detail="nome e comando obrigatórios")
        return {"ok": True, "id": memory.add_local_script(owner, name[:60], command)}

    @app.post("/api/local-scripts/delete")
    async def local_scripts_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_local_script(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    _BROWSER_AGENT_SYSTEM = (
        "Você controla um navegador de verdade para cumprir um objetivo do "
        "usuário. Responda SOMENTE com um objeto JSON compacto, sem markdown e "
        "sem texto fora do JSON. Campos: "
        "action (um de: goto, click_text, type_text, press_enter, scroll, "
        "read_more, done), "
        "value (string — URL para goto, texto visível do elemento para "
        "click_text, texto a digitar para type_text, ou o resultado final para "
        "done), "
        "risky (bool — true se esta ação específica for enviar mensagem, "
        "publicar, curtir, seguir, comprar, excluir ou qualquer coisa "
        "irreversível feita em nome do usuário), "
        "note (string curta, em português, explicando a ação para o usuário). "
        "Se a tarefa for marcada como alto risco (WhatsApp/Instagram), SEMPRE "
        "marque risky=true antes de clicar em enviar/postar ou de digitar uma "
        "mensagem que será enviada. Use 'done' assim que o objetivo estiver "
        "cumprido ou se for impossível continuar; nesse caso 'value' deve "
        "resumir o resultado para o usuário."
    )

    @app.post("/api/local-tasks/decide")
    async def local_tasks_decide(request: Request):
        # Called by the local browser agent at each step of an autonomous
        # browsing task — the LLM only ever picks the NEXT action, it never
        # executes anything itself (local_agent.py does that, on the user's PC).
        _check(request.headers.get("authorization"))
        d = await _body(request)
        goal = (d.get("goal") or "")[:2000]
        url = (d.get("url") or "")[:500]
        page_text = (d.get("page_text") or "")[:6000]
        history = d.get("history") or []
        high_risk = bool(d.get("high_risk"))
        prompt = (
            f"Objetivo: {goal}\n"
            f"Alto risco (WhatsApp/Instagram): {'sim' if high_risk else 'não'}\n"
            f"URL atual: {url}\n"
            f"Últimas ações: {json.dumps(history[-8:], ensure_ascii=False)}\n"
            f"Texto visível da página (truncado):\n{page_text}"
        )
        raw = await brain.ask(_BROWSER_AGENT_SYSTEM, prompt)
        action = {"action": "done", "value": "não consegui decidir o próximo passo",
                  "risky": False, "note": "erro ao interpretar a resposta do modelo"}
        if raw:
            text = raw.strip()
            if text.startswith("```"):
                text = text.strip("`")
                text = text.split("\n", 1)[1] if "\n" in text else text
                text = text.rsplit("```", 1)[0] if "```" in text else text
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and parsed.get("action"):
                    action = parsed
            except (ValueError, TypeError):
                pass
        return {"action": action}

    @app.post("/api/local-tasks/confirms")
    async def local_confirms_create(request: Request):
        # The local agent calls this right before a 'risky' in-flight action —
        # a SECOND, separate approval on top of the task's original approval.
        _check(request.headers.get("authorization"))
        d = await _body(request)
        tid = int(d.get("task_id") or 0)
        label = (d.get("label") or "ação de alto risco").strip()
        cid = memory.add_local_confirm(owner, tid, label[:200])
        return {"ok": True, "id": cid}

    @app.get("/api/local-tasks/confirms")
    async def local_confirms_list(request: Request):
        _check(request.headers.get("authorization"))
        status = (request.query_params.get("status") or "").strip() or None
        return {"items": memory.list_local_confirms(owner, status)}

    @app.get("/api/local-tasks/confirms/status")
    async def local_confirms_status(request: Request):
        _check(request.headers.get("authorization"))
        cid = int(request.query_params.get("id") or 0)
        c = memory.get_local_confirm(owner, cid)
        return {"status": (c or {}).get("status") or "unknown"}

    @app.post("/api/local-tasks/confirms/approve")
    async def local_confirms_approve(request: Request):
        _check(request.headers.get("authorization"))
        cid = int((await _body(request)).get("id") or 0)
        ok = memory.set_local_confirm_status(owner, cid, "approved")
        return {"ok": ok}

    @app.post("/api/local-tasks/confirms/reject")
    async def local_confirms_reject(request: Request):
        _check(request.headers.get("authorization"))
        cid = int((await _body(request)).get("id") or 0)
        ok = memory.set_local_confirm_status(owner, cid, "rejected")
        return {"ok": ok}

    # --- Spotify OAuth + Web API (Premium: read playlists + control playback) --
    import time as _time

    def _sp_redirect(request: Request) -> str:
        return _sp.norm_redirect(config.web_base_url or str(request.base_url))

    def _sp_save(tokens: dict):
        memory.set_setting("spotify_tokens", json.dumps(tokens))

    def _sp_tokens() -> dict:
        try:
            return json.loads(memory.get_setting("spotify_tokens") or "{}")
        except (ValueError, TypeError):
            return {}

    def _sp_access() -> str | None:
        """A valid access token, refreshing with the refresh_token if expired."""
        import httpx
        t = _sp_tokens()
        if not t.get("refresh"):
            return None
        if t.get("access") and t.get("exp", 0) > _time.time() + 30:
            return t["access"]
        try:
            data = {"grant_type": "refresh_token", "refresh_token": t["refresh"],
                    "client_id": config.spotify_client_id}
            if config.spotify_client_secret:
                data["client_secret"] = config.spotify_client_secret
            r = httpx.post("https://accounts.spotify.com/api/token",
                           data=data, timeout=15).json()
        except Exception:
            return None
        if not r.get("access_token"):
            return None
        t["access"] = r["access_token"]
        t["exp"] = _time.time() + int(r.get("expires_in", 3600))
        if r.get("refresh_token"):
            t["refresh"] = r["refresh_token"]
        _sp_save(t)
        return t["access"]

    def _sp_api(method: str, path: str, token: str, **kw):
        import httpx
        url = path if path.startswith("http") else ("https://api.spotify.com/v1" + path)
        return httpx.request(method, url, headers={"Authorization": "Bearer " + token},
                             timeout=15, **kw)

    @app.get("/spotify/connect")
    async def spotify_connect(request: Request):
        if not config.spotify_client_id:
            return _login_denied_html("Configure o Spotify Client ID em Chaves de API.")
        state = _secrets.token_urlsafe(16); _oauth_states.add(state)
        verifier, challenge = _sp.pkce_pair(); _sp_pkce[state] = verifier
        return RedirectResponse(_sp.auth_url(
            config.spotify_client_id, _sp_redirect(request), state, challenge))

    @app.get("/spotify/callback")
    async def spotify_callback(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in _oauth_states:
            return _login_denied_html("Sessão do Spotify inválida. Tente de novo.")
        _oauth_states.discard(state)
        redirect = _sp_redirect(request)
        verifier = _sp_pkce.pop(state, "")

        def _work():
            data = {"grant_type": "authorization_code", "code": code,
                    "redirect_uri": redirect, "client_id": config.spotify_client_id}
            if verifier:  # PKCE — sem secret
                data["code_verifier"] = verifier
            elif config.spotify_client_secret:
                data["client_secret"] = config.spotify_client_secret
            return httpx.post("https://accounts.spotify.com/api/token",
                              data=data, timeout=15).json()
        try:
            r = await asyncio.to_thread(_work)
        except Exception as exc:
            return _login_denied_html(f"Falha ao conectar o Spotify: {exc}")
        if not r.get("refresh_token"):
            return _login_denied_html("Spotify não devolveu o token. Confira o Client Secret e a Redirect URI.")
        _sp_save({"access": r.get("access_token"), "refresh": r["refresh_token"],
                  "exp": _time.time() + int(r.get("expires_in", 3600))})
        return HTMLResponse("<script>location.href='/'</script>Spotify conectado! Redirecionando…")

    @app.get("/api/spotify/status")
    async def spotify_status(request: Request):
        _check(request.headers.get("authorization"))
        return {"configured": bool(config.spotify_client_id),
                "connected": bool(_sp_tokens().get("refresh")),
                "redirect_uri": _sp_redirect(request)}

    @app.post("/api/spotify/disconnect")
    async def spotify_disconnect(request: Request):
        _check(request.headers.get("authorization"))
        memory.set_setting("spotify_tokens", "")
        return {"ok": True}

    @app.get("/api/spotify/token")
    async def spotify_token(request: Request):
        # fresh access token for the Web Playback SDK (client-side)
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        return {"token": tok}

    @app.get("/api/spotify/playlists")
    async def spotify_playlists(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        def _work():
            r = _sp_api("GET", "/me/playlists?limit=50", tok)
            return r.json() if r.status_code == 200 else {}
        data = await asyncio.to_thread(_work)
        items = [{"name": p.get("name"), "uri": p.get("uri"), "id": (p.get("id") or ""),
                  # a API passou a devolver a contagem em items.total (antes tracks.total)
                  "tracks": ((p.get("tracks") or p.get("items") or {}).get("total", 0))}
                 for p in (data.get("items") or []) if p]
        return {"items": items}

    @app.post("/api/spotify/play")
    async def spotify_play(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        d = await _body(request)
        body, dev = {}, d.get("device_id")
        if d.get("uris"):
            body["uris"] = d["uris"]
        elif d.get("uri"):
            u = d["uri"]
            if u.startswith("spotify:track:"):
                body["uris"] = [u]           # a single track
            else:
                body["context_uri"] = u      # playlist/album/artist
        if d.get("query"):                   # search then play the top track
            tk = await asyncio.to_thread(_sp.first_track_uri, tok, d["query"])
            if tk:
                body = {"uris": [tk]}
        def _work():
            path = "/me/player/play" + (f"?device_id={dev}" if dev else "")
            r = _sp_api("PUT", path, tok, json=body)
            return r.status_code
        sc = await asyncio.to_thread(_work)
        if sc == 404:
            return {"ok": False, "error": "nenhum dispositivo ativo — abra o Spotify ou use o player da E.V."}
        return {"ok": sc in (200, 202, 204)}

    @app.post("/api/spotify/transfer")
    async def spotify_transfer(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        dev = (await _body(request)).get("device_id")
        if not dev:
            raise HTTPException(status_code=400, detail="sem device da E.V.")
        # move a reprodução pro device da E.V. (toca in-page -> controles do SO)
        sc = await asyncio.to_thread(lambda: _sp_api(
            "PUT", "/me/player", tok, json={"device_ids": [dev], "play": True}).status_code)
        return {"ok": sc in (200, 202, 204)}

    @app.get("/api/spotify/search")
    async def spotify_search(request: Request):
        _check(request.headers.get("authorization"))
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return {"items": []}
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        return {"items": await asyncio.to_thread(_sp.search_tracks, tok, q)}

    @app.get("/api/spotify/current")
    async def spotify_current(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            return {"track": ""}
        return {"track": await asyncio.to_thread(_sp.current_track, tok)}

    @app.get("/api/spotify/nowplaying")
    async def spotify_nowplaying(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            return {"playing": False, "connected": False}
        def _work():
            r = _sp_api("GET", "/me/player", tok)
            if r.status_code != 200:
                return {"playing": False, "connected": True}
            d = r.json() or {}
            it = d.get("item") or {}
            imgs = (it.get("album") or {}).get("images") or []
            tid = it.get("id")
            liked = False
            if tid:
                try:
                    lr = _sp_api("GET", "/me/tracks/contains?ids=" + tid, tok)
                    liked = bool((lr.json() or [False])[0]) if lr.status_code == 200 else False
                except Exception:
                    pass
            dev = d.get("device") or {}
            return {"connected": True, "playing": bool(d.get("is_playing")),
                    "name": it.get("name"), "id": tid, "liked": liked,
                    "artists": ", ".join(a.get("name", "") for a in (it.get("artists") or [])),
                    "image": (imgs[0].get("url") if imgs else ""),
                    "progress": d.get("progress_ms", 0), "duration": it.get("duration_ms", 0),
                    "device": dev.get("name", ""), "volume": dev.get("volume_percent", 50)}
        return await asyncio.to_thread(_work)

    @app.post("/api/spotify/like")
    async def spotify_like(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        d = await _body(request)
        tid = d.get("id")
        if not tid:
            raise HTTPException(status_code=400, detail="sem id")
        method = "PUT" if d.get("on") else "DELETE"
        sc = await asyncio.to_thread(lambda: _sp_api(method, "/me/tracks?ids=" + tid, tok).status_code)
        return {"ok": sc in (200, 201, 202, 204)}

    @app.get("/api/spotify/devices")
    async def spotify_devices(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            return {"items": []}
        def _work():
            r = _sp_api("GET", "/me/player/devices", tok)
            return (r.json().get("devices") or []) if r.status_code == 200 else []
        ds = await asyncio.to_thread(_work)
        return {"items": [{"id": x.get("id"), "name": x.get("name"),
                           "active": x.get("is_active")} for x in ds]}

    @app.post("/api/spotify/volume")
    async def spotify_volume(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        pct = max(0, min(100, int((await _body(request)).get("percent") or 0)))
        sc = await asyncio.to_thread(lambda: _sp_api("PUT", f"/me/player/volume?volume_percent={pct}", tok).status_code)
        return {"ok": sc in (200, 202, 204)}

    @app.post("/api/spotify/queue")
    async def spotify_queue(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        uri = (await _body(request)).get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="sem uri")
        import urllib.parse as _up
        sc = await asyncio.to_thread(lambda: _sp_api("POST", "/me/player/queue?uri=" + _up.quote(uri), tok).status_code)
        return {"ok": sc in (200, 202, 204)}

    @app.post("/api/spotify/control")
    async def spotify_control(request: Request):
        _check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        d = await _body(request)
        act = d.get("action")
        if act == "seek":   # pular pra uma posição (ms)
            ms = max(0, int(d.get("ms") or 0))
            sc = await asyncio.to_thread(
                lambda: _sp_api("PUT", f"/me/player/seek?position_ms={ms}", tok).status_code)
            return {"ok": sc in (200, 202, 204)}
        M = {"pause": ("PUT", "/me/player/pause"), "resume": ("PUT", "/me/player/play"),
             "next": ("POST", "/me/player/next"), "prev": ("POST", "/me/player/previous")}
        if act not in M:
            raise HTTPException(status_code=400, detail="ação inválida")
        method, path = M[act]
        sc = await asyncio.to_thread(lambda: _sp_api(method, path, tok).status_code)
        return {"ok": sc in (200, 202, 204)}

    # --- Links / Habits / Journal CRUD -------------------------------------
    @app.get("/api/links")
    async def links_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_links(owner)}

    @app.post("/api/links")
    async def links_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        name = (d.get("name") or "").strip()
        url = (d.get("url") or "").strip()
        cat = (d.get("category") or "geral").strip() or "geral"
        if name and url:
            memory.add_link(owner, cat, name, url)
        return {"ok": bool(name and url)}

    @app.post("/api/links/delete")
    async def links_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_link(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/habits")
    async def habits_list(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import date
        today = date.today().isoformat()
        out = []
        for h in memory.list_habits(owner):
            days = memory.habit_days(h["id"])
            out.append({"id": h["id"], "name": h["name"],
                        "done_today": today in days, "total": len(days),
                        "days": sorted(days)[-180:]})  # recent days for the heatmap
        return {"items": out}

    @app.post("/api/habits")
    async def habits_create(request: Request):
        _check(request.headers.get("authorization"))
        name = ((await _body(request)).get("name") or "").strip()
        if name:
            memory.add_habit(owner, name)
        return {"ok": bool(name)}

    @app.post("/api/habits/done")
    async def habits_done(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import date
        memory.log_habit(int((await _body(request)).get("id") or 0), date.today().isoformat())
        return {"ok": True}

    @app.post("/api/habits/delete")
    async def habits_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_habit(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/journal")
    async def journal_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.recent_journal(owner, 60)}

    @app.post("/api/journal")
    async def journal_create(request: Request):
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if text:
            memory.add_journal(owner, text)
        return {"ok": bool(text)}

    @app.post("/api/journal/delete")
    async def journal_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_journal(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    # --- Subscriptions / Budgets / Watches CRUD ----------------------------
    @app.get("/api/recurring")
    async def rec_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_recurring(owner)}

    @app.post("/api/recurring")
    async def rec_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
            day = max(1, min(28, int(d.get("day") or 1)))
        except Exception:
            return {"ok": False}
        memory.add_recurring(owner, amount, (d.get("description") or "assinatura").strip(),
                             (d.get("category") or "assinatura").strip() or "assinatura", day)
        return {"ok": True}

    @app.post("/api/recurring/delete")
    async def rec_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_recurring(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/budgets")
    async def bud_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_budgets(owner)}

    @app.post("/api/budgets")
    async def bud_set(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        cat = (d.get("category") or "").strip()
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
        except Exception:
            return {"ok": False}
        if cat:
            memory.set_budget(owner, cat, amount)
        return {"ok": bool(cat)}

    @app.post("/api/budgets/delete")
    async def bud_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_budget(owner, ((await _body(request)).get("category") or "").strip())
        return {"ok": True}

    @app.get("/api/watches")
    async def wat_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_watches(owner)}

    @app.post("/api/watches")
    async def wat_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        url = (d.get("url") or "").strip()
        kw = (d.get("keyword") or "").strip() or None
        if url:
            memory.add_watch(owner, url, kw)
        return {"ok": bool(url)}

    @app.post("/api/watches/delete")
    async def wat_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_watch(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    def _num(v):
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return None

    @app.post("/api/expenses/update")
    async def exp_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.update_expense(owner, int(d.get("id") or 0), amount=_num(d.get("amount")),
                              description=(d.get("description") or None), category=(d.get("category") or None))
        return {"ok": True}

    @app.post("/api/reminders/update")
    async def rem_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        recur = _recurval(d.get("recur"), allow_clear=True) if "recur" in d else None
        memory.update_reminder(owner, int(d.get("id") or 0), text=(d.get("text") or None),
                               when_iso=(d.get("when") or None), recur=recur)
        return {"ok": True}

    @app.post("/api/facts/update")
    async def fact_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        t = (d.get("text") or "").strip()
        if t:
            memory.update_fact(owner, int(d.get("id") or 0), t)
        return {"ok": bool(t)}

    @app.post("/api/links/update")
    async def link_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.update_link(owner, int(d.get("id") or 0), category=(d.get("category") or None),
                           name=(d.get("name") or None), url=(d.get("url") or None))
        return {"ok": True}

    @app.post("/api/journal/update")
    async def jou_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        t = (d.get("text") or "").strip()
        if t:
            memory.update_journal(owner, int(d.get("id") or 0), t)
        return {"ok": bool(t)}

    @app.post("/api/habits/update")
    async def hab_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        n = (d.get("name") or "").strip()
        if n:
            memory.rename_habit(owner, int(d.get("id") or 0), n)
        return {"ok": bool(n)}

    @app.post("/api/recurring/update")
    async def rec_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            day = int(d.get("day")) if d.get("day") else None
        except Exception:
            day = None
        memory.update_recurring(owner, int(d.get("id") or 0), amount=_num(d.get("amount")),
                                description=(d.get("description") or None),
                                category=(d.get("category") or None), day=day)
        return {"ok": True}

    @app.post("/api/watches/update")
    async def wat_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.update_watch(owner, int(d.get("id") or 0), url=(d.get("url") or None),
                            keyword=(d.get("keyword") or None))
        return {"ok": True}

    @app.get("/api/search")
    async def search_ep(request: Request):
        _check(request.headers.get("authorization"))
        term = (request.query_params.get("q") or "").strip()
        if len(term) < 2:
            return {"results": []}
        r = memory.search_all(owner, term)
        views = {"tasks": "tasks", "reminders": "rem", "links": "lnk",
                 "journal": "jou", "expenses": "exp", "facts": "mem",
                 "messages": "chat", "knowledge": "kb"}
        labels = {"tasks": "Tarefa", "reminders": "Lembrete", "links": "Link",
                  "journal": "Diário", "expenses": "Gasto", "facts": "Memória",
                  "messages": "Conversa", "knowledge": "Conhecimento"}
        out = []
        for key, items in r.items():
            for it in items[:6]:
                out.append({"kind": labels.get(key, key), "text": it["text"],
                            "id": it.get("id"), "view": views.get(key)})
        return {"results": out[:30]}

    @app.get("/api/panel")
    async def panel(request: Request):
        _check(request.headers.get("authorization"))
        # "Gastos · mês" = current calendar month in the user's timezone.
        _, since, _ = commands._month_bounds(0)
        exp = memory.expenses_since(owner, since)
        prov = memory.get_setting("force_provider") or "auto"
        # the model that actually answers depends on the forced provider
        model = {
            "groq": config.groq_model,
            "openrouter": config.openrouter_model,
            "ollama": config.ollama_model,
        }.get(prov) or brain.current_model()
        # extra system indicators (pinnable in the "Sistema" panel)
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        rems = memory.open_reminders(owner)
        soon = now + timedelta(days=7)
        agenda = 0
        for r in rems:
            w = r.get("when_iso") or ""
            try:
                dt = datetime.fromisoformat(w)
                if dt.tzinfo is None:  # older rows may be tz-naive -> assume UTC
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt <= soon:
                    agenda += 1
            except ValueError:
                pass
        # activity in the last 24h (created is UTC ISO -> lexical compare is chronological)
        cutoff = (now - timedelta(hours=24)).isoformat()
        acts_24h = sum(1 for a in memory.list_activity(owner, limit=300)
                       if (a.get("created") or "") >= cutoff)
        rep = health.system_report(config, memory)
        up = int(boot and (_time.monotonic() - boot) or 0)
        uptime = (f"{up // 86400}d" if up >= 86400
                  else f"{up // 3600}h" if up >= 3600
                  else f"{up // 60}m")
        return {
            "tasks": len(memory.open_tasks(owner)),
            "reminders": len(rems),
            "expenses": round(sum(e.get("amount", 0) for e in exp)),
            "memories": len(memory.all_facts(owner)),
            "kb": len(memory.list_sources(owner)),
            "kbfiles": len(memory.kb_file_sources(owner)),
            "links": len(memory.list_links(owner)),
            "habits": len(memory.list_habits(owner)),
            "journal": len(memory.recent_journal(owner, 9999)),
            "subscriptions": len(memory.list_recurring(owner)),
            "budgets": len(memory.list_budgets(owner)),
            "watches": len(memory.list_watches(owner)),
            "agenda": agenda,
            "activity": acts_24h,
            "disk": (f"{rep['disk_used_pct']}%" if "disk_used_pct" in rep else "—"),
            "ram": (f"{rep['mem_used_pct']}%" if "mem_used_pct" in rep else "—"),
            "uptime": uptime,
            "notifs": memory.unread_notifications(owner),
            "provider": prov,
            "model": model,
            "serious": memory.get_setting("serious_mode") == "1",
        }

    # groups shown in the "brain" graph: (key, hub label, view to jump to on
    # click, items, text-getter). Capped per group below so a heavy user's DB
    # still renders a smooth graph.
    @app.get("/api/brain")
    async def brain_graph(request: Request):
        _check(request.headers.get("authorization"))
        # idfn: the stable identifier used to edit/delete the item (id for most;
        # name/source/category for the string-keyed tables). editable: shows "Editar".
        groups = [
            ("mem", "Memórias", "mem", memory.list_facts(owner), lambda r: r["fact"], lambda r: r["id"], True),
            ("tasks", "Tarefas", "tasks", memory.open_tasks(owner), lambda r: r["text"], lambda r: r["id"], True),
            ("rem", "Lembretes", "rem", memory.open_reminders(owner), lambda r: r["text"], lambda r: r["id"], True),
            ("people", "Pessoas", "chat", memory.list_people(owner), lambda r: r["name"], lambda r: r["id"], True),
            ("links", "Links", "lnk", memory.list_links(owner), lambda r: r["name"], lambda r: r["id"], True),
            ("kb", "Base", "kb", memory.list_sources(owner), lambda r: r["source"], lambda r: r["source"], False),
            ("hab", "Hábitos", "hab", memory.list_habits(owner), lambda r: r["name"], lambda r: r["id"], True),
            ("jou", "Diário", "jou", memory.recent_journal(owner, 40), lambda r: r["text"], lambda r: r["id"], True),
            ("sub", "Assinaturas", "sub", memory.list_recurring(owner), lambda r: r["description"], lambda r: r["id"], True),
            ("orc", "Orçamentos", "orc", memory.list_budgets(owner), lambda r: r["category"], lambda r: r["category"], False),
            ("mon", "Monitores", "mon", memory.list_watches(owner), lambda r: r["url"], lambda r: r["id"], True),
            ("places", "Lugares", "map", memory.list_places(owner), lambda r: r["name"], lambda r: r["id"], True),
        ]
        nodes = [{"id": "core", "label": "E.V.", "group": "core", "val": 22, "view": "chat"}]
        edges = []
        CAP = 40
        for key, label, view, items, textfn, idfn, editable in groups:
            if not items:
                continue
            hub = f"g:{key}"
            nodes.append({"id": hub, "label": label, "group": key, "val": 12, "view": view})
            edges.append({"source": "core", "target": hub})
            for i, item in enumerate(items[:CAP]):
                nid = f"{key}:{item.get('id', i)}"
                txt = (textfn(item) or "").strip().replace("\n", " ")
                nodes.append({
                    "id": nid, "label": (txt[:60] or "—"), "group": key, "val": 4,
                    "view": view, "ref": idfn(item), "full": txt[:400], "editable": editable,
                })
                edges.append({"source": hub, "target": nid})
            extra = len(items) - CAP
            if extra > 0:
                more_id = f"{key}:more"
                nodes.append({"id": more_id, "label": f"+{extra} mais", "group": key,
                              "val": 5, "view": view})
                edges.append({"source": hub, "target": more_id})
        return {"nodes": nodes, "links": edges}

    def _brain_delete(group: str, ref) -> bool:
        """Delete an item of any brain group by its ref (id, or name/source/category)."""
        if group == "rem":
            return memory.cancel_reminder(owner, int(ref)) or True
        if group == "kb":
            return memory.delete_source(owner, str(ref)) > 0
        if group == "orc":
            return memory.delete_budget(owner, str(ref))
        if group == "hab":
            return memory.delete_habit(owner, int(ref))          # cascades habit_logs
        if group == "people":
            return memory.delete_person_by_id(owner, int(ref))
        byid = {"mem": memory.delete_fact, "tasks": memory.delete_task,
                "links": memory.delete_link, "jou": memory.delete_journal,
                "sub": memory.delete_recurring, "mon": memory.delete_watch,
                "places": memory.delete_place}.get(group)
        if byid:
            return byid(owner, int(ref))
        raise HTTPException(status_code=400, detail="unknown group")

    def _brain_edit(group: str, ref, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        editors = {
            "mem": lambda: memory.update_fact(owner, int(ref), text),
            "tasks": lambda: memory.update_task(owner, int(ref), text=text),
            "rem": lambda: memory.update_reminder(owner, int(ref), text=text),
            "links": lambda: memory.update_link(owner, int(ref), name=text),
            "jou": lambda: memory.update_journal(owner, int(ref), text),
            "sub": lambda: memory.update_recurring(owner, int(ref), description=text),
            "mon": lambda: memory.update_watch(owner, int(ref), url=text),
            "hab": lambda: memory.update_habit(owner, int(ref), text),
            "people": lambda: memory.update_person(owner, int(ref), text),
            "places": lambda: memory.update_place(owner, int(ref), text),
        }.get(group)
        if not editors:
            raise HTTPException(status_code=400, detail="group not editable")
        return editors()

    @app.post("/api/brain/delete")
    async def brain_delete(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        ref = d.get("ref")
        if ref is None:
            raise HTTPException(status_code=400, detail="no ref")
        try:
            _brain_delete(d.get("group", ""), ref)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="bad ref")
        return {"ok": True}

    @app.post("/api/brain/edit")
    async def brain_edit(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        ref = d.get("ref")
        if ref is None:
            raise HTTPException(status_code=400, detail="no ref")
        try:
            ok = _brain_edit(d.get("group", ""), ref, d.get("text", ""))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="bad ref")
        return {"ok": bool(ok)}

    @app.post("/api/tts")
    async def tts(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        text = (d.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="empty")
        # optional per-request overrides (voice picker previews force edge-tts)
        req_voice = d.get("voice")
        voice = req_voice if str(req_voice or "").startswith("pt-BR") else None
        audio, mime = await voice_mod.synth_web(
            config, text[:1200], voice=voice, gvoice=d.get("gvoice"),
            rate=d.get("rate"), pitch=d.get("pitch"))
        return Response(content=audio, media_type=mime)

    @app.get("/api/voice")
    async def voice_get(request: Request):
        _check(request.headers.get("authorization"))
        gv = ([{"id": i, "desc": d} for i, d in voice_mod.GEMINI_VOICES]
              if config.gemini_api_key else [])
        return {"voice": config.voice, "rate": config.voice_rate,
                "pitch": config.voice_pitch,
                "voices": await voice_mod.list_ptbr_voices(),
                "engine": "gemini" if getattr(config, "gemini_tts", False) else "edge",
                "gvoice": getattr(config, "gemini_tts_voice", "Kore"),
                "gemini_voices": gv}

    @app.post("/api/voice")
    async def voice_set(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        voice = (d.get("voice") or "").strip()
        engine = (d.get("engine") or "").strip()
        gset = {i for i, _ in voice_mod.GEMINI_VOICES}
        # --- Gemini voice ---
        if engine == "gemini" or voice in gset:
            if voice not in gset:
                raise HTTPException(status_code=400, detail="invalid gemini voice")
            for f, env, val in (("gemini_tts", "EV_GEMINI_TTS", True),
                                ("gemini_tts_voice", "EV_GEMINI_VOICE", voice)):
                try:
                    object.__setattr__(config, f, val)
                except Exception:
                    pass
                try:
                    _env_write(env, "1" if val is True else val)
                except Exception:
                    pass
            return {"ok": True, "engine": "gemini", "voice": voice}
        # --- edge voice (also turns Gemini off) ---
        voices = {v["id"] for v in await voice_mod.list_ptbr_voices()}
        if not voice.startswith("pt-BR") or (voices and voice not in voices):
            raise HTTPException(status_code=400, detail="invalid voice")
        rate = (d.get("rate") or "+0%").strip()
        pitch = (d.get("pitch") or "+0Hz").strip()
        for f, env, val in (("voice", "EV_VOICE", voice),
                            ("voice_rate", "EV_VOICE_RATE", rate),
                            ("voice_pitch", "EV_VOICE_PITCH", pitch),
                            ("gemini_tts", "EV_GEMINI_TTS", False)):
            try:
                object.__setattr__(config, f, val)
            except Exception:
                pass
            try:
                _env_write(env, "0" if val is False else val)
            except Exception:
                pass
        return {"ok": True, "engine": "edge", "voice": voice, "rate": rate, "pitch": pitch}

    @app.post("/api/vision")
    async def vision(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"reply": "Nenhuma imagem enviada."}
        data = await f.read()
        if not data:
            return {"reply": "Imagem vazia."}
        prompt = (form.get("text") or "").strip() or "O que há nesta imagem?"
        thread = (form.get("thread") or "geral").strip()
        conv = _conv(thread)
        try:
            reply = await brain.respond(
                owner, conv_id=conv, text=prompt,
                image=data, image_mime=(f.content_type or "image/jpeg"))
        except Exception as exc:
            return {"reply": f"Não consegui analisar a imagem: {exc}"}
        # keep the image in the conversation so it re-appears on reload
        img_id = None
        try:
            img_id = memory.add_chat_image(conv, data, f.content_type or "image/png")
            memory.mark_last_user_image(conv, img_id)
        except Exception:
            pass
        return {"reply": reply, "img_id": img_id}

    @app.get("/api/chat/image")
    async def chat_image(request: Request):
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        img = memory.get_chat_image(int(request.query_params.get("id") or 0))
        if not img:
            raise HTTPException(status_code=404, detail="não encontrada")
        return Response(content=img["data"],
                        media_type=img["mime"] or "image/png",
                        headers={"Cache-Control": "private, max-age=86400"})

    @app.post("/api/location")
    async def set_location(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
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

    @app.post("/api/nearby")
    async def nearby(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"items": [], "msg": "sem localização"}
        query = (d.get("query") or "").strip()
        items = await asyncio.to_thread(tools_mod.nearby_places, lat, lng, query)
        return {"items": items}

    @app.get("/api/places")
    async def places_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_places(owner)}

    @app.post("/api/places")
    async def places_add(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"ok": False}
        name = (d.get("name") or "Ponto").strip()
        pid = memory.add_place(owner, name, lat, lng)
        return {"ok": True, "id": pid, "items": memory.list_places(owner)}

    @app.post("/api/places/delete")
    async def places_delete(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_place(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True, "items": memory.list_places(owner)}

    @app.get("/api/geocode")
    async def geocode_ep(request: Request):
        _check(request.headers.get("authorization"))
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return {"ok": False}
        g = await asyncio.to_thread(tools_mod.geocode, q)
        return {"ok": bool(g), **(g or {})}

    @app.post("/api/route")
    async def route_ep(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            fr, to = d.get("from"), d.get("to")
            fl, fg = float(fr[0]), float(fr[1])
            tl, tg = float(to[0]), float(to[1])
        except (TypeError, ValueError, IndexError):
            return {"ok": False}
        r = await asyncio.to_thread(
            tools_mod.route, fl, fg, tl, tg, (d.get("mode") or "car"))
        return {"ok": bool(r), **(r or {})}

    @app.post("/api/see")
    async def see(request: Request):
        """Ephemeral vision for the live camera / 'what is this' — describes the
        frame without saving it to the conversation."""
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"text": ""}
        data = await f.read()
        if not data:
            return {"text": ""}
        mode = (form.get("mode") or "live").strip()
        if mode == "translate":
            prompt = ("Leia TODO o texto visível nesta imagem e traduza para "
                      "português do Brasil. Responda só com a tradução, natural e "
                      "curta. Se não houver texto legível, responda apenas: (sem texto).")
        elif mode == "food":
            prompt = ("Esta é uma foto de comida. Estime em 1-2 frases (pt-BR) o "
                      "prato/itens e as calorias aproximadas totais, e os macros se "
                      "der (proteína/carbo/gordura). Deixe claro que é estimativa. "
                      "Se não for comida, diga: (não parece comida).")
        elif mode == "what":
            prompt = ("Identifique o que está em destaque nesta imagem (objeto, "
                      "lugar/ponto de referência, planta, animal, produto ou texto) e "
                      "dê uma info curta e útil, em 1-2 frases, português do Brasil. "
                      "Se houver texto importante, transcreva.")
        else:
            prompt = ("Descreva em 1 frase curta (pt-BR) o que a câmera vê agora: "
                      "objetos principais e quantas pessoas/rostos aparecem (sem "
                      "identificar quem são). Seja objetivo.")
        text = await brain.describe_image(data, f.content_type or "image/jpeg", prompt)
        return {"text": text or "(não consegui enxergar agora)"}

    @app.post("/api/scan")
    async def scan(request: Request):
        """Scan a document: OCR the frame and save the text to the knowledge base."""
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhuma imagem."}
        data = await f.read()
        text = await brain.ocr_image(data, f.content_type or "image/jpeg")
        if not text or text.strip() in ("", "(sem texto)"):
            return {"ok": False, "msg": "Não achei texto legível no documento."}
        from datetime import datetime, timezone
        title = "Documento " + datetime.now(timezone.utc).strftime("%d/%m %H:%M")
        try:
            stored = await asyncio.to_thread(
                knowledge.ingest_text, text, title, config, memory, owner)
            return {"ok": True, "msg": f"Documento salvo na Base: {title} "
                    f"({len(text)} caracteres).", "stored": stored}
        except Exception as exc:
            return {"ok": True, "msg": f"Li o documento ({len(text)} caracteres), "
                    f"mas não consegui salvar na Base ({str(exc)[:50]}).", "text": text[:300]}

    @app.post("/api/receipt")
    async def receipt(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhuma imagem enviada."}
        data = await f.read()
        if not data:
            return {"ok": False, "msg": "Imagem vazia."}
        try:
            exp = await brain.extract_receipt(data, f.content_type or "image/jpeg")
        except Exception as exc:
            return {"ok": False, "msg": f"Não consegui ler o comprovante: {exc}"}
        if not exp:
            return {"ok": False,
                    "msg": "Não consegui identificar um valor nesse comprovante."}
        return {"ok": True, **exp}

    @app.post("/api/stt")
    async def stt(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("audio")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            raise HTTPException(status_code=400, detail="no audio")
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty audio")
        text = await brain.transcribe(data, f.content_type or "audio/webm")
        return {"text": (text or "").strip()}

    @app.post("/api/email")
    async def api_email(request: Request):
        _check(request.headers.get("authorization"))
        from ...providers import tools
        d = await _body(request)
        to = (d.get("to") or "").strip()
        subject = (d.get("subject") or "").strip()
        body = (d.get("body") or "").strip()
        if not to or not body:
            return {"ok": False, "msg": "Preencha destinatário e mensagem."}
        account = (d.get("account") or "").strip() or config.default_account
        try:
            msg = await asyncio.to_thread(
                tools.send_email, config, account, to, subject, body
            )
            return {"ok": True, "msg": msg}
        except Exception as exc:
            return {"ok": False, "msg": f"Falha ao enviar o email: {exc}"}

    @app.post("/api/notify")
    async def api_notify(request: Request):
        """Send a message to the owner's own Telegram (a note to yourself)."""
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if not text:
            return {"ok": False, "msg": "Mensagem vazia."}
        if not config.telegram_token or config.owner_id is None:
            return {"ok": False, "msg": "Telegram não está configurado."}
        import httpx

        def _send():
            return httpx.post(
                f"https://api.telegram.org/bot{config.telegram_token}/sendMessage",
                data={"chat_id": config.owner_id, "text": text}, timeout=15,
            )
        try:
            r = await asyncio.to_thread(_send)
            if r.status_code == 200:
                return {"ok": True, "msg": "Mensagem enviada ao seu Telegram."}
            return {"ok": False, "msg": f"Falha ao enviar (HTTP {r.status_code})."}
        except Exception as exc:
            return {"ok": False, "msg": f"Falha ao enviar: {exc}"}

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

    @app.get("/api/gcal")
    async def gcal_list(request: Request):
        _check(request.headers.get("authorization"))
        if not config.google_ready() or not config.google_authorized():
            return {"ok": False, "events": [], "msg": "Google não autorizado."}
        start = request.query_params.get("start") or ""
        end = request.query_params.get("end") or ""
        from ...providers import tools
        try:
            events = await asyncio.to_thread(
                tools.calendar_list_range, config, config.default_account, start, end)
            return {"ok": True, "events": events}
        except Exception as exc:
            return {"ok": False, "events": [], "msg": str(exc)}

    @app.post("/api/gcal/create")
    async def gcal_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
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
        from ...providers import tools
        try:
            msg = await asyncio.to_thread(
                tools.calendar_create, config, config.default_account,
                summary, start_iso, end_iso)
            ok = "criei" in msg.lower() or "criado" in msg.lower() or "http" in msg.lower()
            return {"ok": ok, "msg": msg}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    @app.post("/api/gcal/delete")
    async def gcal_delete(request: Request):
        _check(request.headers.get("authorization"))
        eid = ((await _body(request)).get("id") or "").strip()
        if not eid:
            return {"ok": False}
        from ...providers import tools
        try:
            await asyncio.to_thread(
                tools.calendar_delete, config, config.default_account, eid)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    # --- OAuth login (Google / GitHub) -------------------------------------
    import secrets as _secrets
    from fastapi.responses import RedirectResponse
    _oauth_states: set[str] = set()
    _sp_pkce: dict = {}   # state -> code_verifier (Spotify PKCE, sem secret)

    def _base_url(request: Request) -> str:
        return config.web_base_url or str(request.base_url).rstrip("/")

    def _login_ok_html() -> HTMLResponse:
        # Passed the identity check: hand the app token to this browser and enter.
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>E.V.</title>"
            "<script>localStorage.setItem('ev_token'," + json.dumps(config.web_token)
            + ");location.replace('/');</script>"
            "<p style='font:14px system-ui;color:#888;padding:24px'>Entrando…</p>")

    def _login_denied_html(msg: str) -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>E.V.</title>"
            "<div style='font:15px system-ui;color:#d6e9fb;background:#04070c;"
            "height:100vh;display:flex;flex-direction:column;align-items:center;"
            "justify-content:center;gap:16px;text-align:center;padding:24px'>"
            "<p>" + msg + "</p><a href='/' style='color:#8ab4f8'>voltar</a></div>",
            status_code=403)

    @app.get("/auth/google")
    async def auth_google(request: Request):
        if not config.google_login_client:
            return _login_denied_html("Login com Google não configurado.")
        from urllib.parse import urlencode
        state = _secrets.token_urlsafe(16); _oauth_states.add(state)
        params = urlencode({
            "client_id": config.google_login_client,
            "redirect_uri": _base_url(request) + "/auth/google/callback",
            "response_type": "code", "scope": "openid email profile",
            "access_type": "online", "state": state, "prompt": "select_account",
        })
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + params)

    @app.get("/auth/google/callback")
    async def auth_google_cb(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in _oauth_states:
            return _login_denied_html("Sessão de login inválida. Tente de novo.")
        _oauth_states.discard(state)
        redirect = _base_url(request) + "/auth/google/callback"

        def _work():
            tok = httpx.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": config.google_login_client,
                "client_secret": config.google_login_secret,
                "redirect_uri": redirect, "grant_type": "authorization_code",
            }, timeout=15).json()
            at = tok.get("access_token")
            info = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo",
                             headers={"Authorization": "Bearer " + (at or "")},
                             timeout=15).json()
            return (info.get("email") or "").lower()
        try:
            email = await asyncio.to_thread(_work)
        except Exception as exc:
            return _login_denied_html(f"Falha no login Google: {exc}")
        if not email:
            return _login_denied_html("Não consegui obter seu email do Google.")
        allowed = memory.get_setting("login_google_email")
        if not allowed:
            memory.set_setting("login_google_email", email)  # pin the first login
        elif email != allowed:
            return _login_denied_html("Esta conta Google não tem acesso a esta E.V.")
        return _login_ok_html()

    @app.get("/auth/github")
    async def auth_github(request: Request):
        if not config.github_login_client:
            return _login_denied_html("Login com GitHub não configurado.")
        from urllib.parse import urlencode
        state = _secrets.token_urlsafe(16); _oauth_states.add(state)
        params = urlencode({
            "client_id": config.github_login_client,
            "redirect_uri": _base_url(request) + "/auth/github/callback",
            "scope": "read:user", "state": state,
        })
        return RedirectResponse("https://github.com/login/oauth/authorize?" + params)

    @app.get("/auth/github/callback")
    async def auth_github_cb(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in _oauth_states:
            return _login_denied_html("Sessão de login inválida. Tente de novo.")
        _oauth_states.discard(state)
        redirect = _base_url(request) + "/auth/github/callback"

        def _work():
            tok = httpx.post("https://github.com/login/oauth/access_token", data={
                "client_id": config.github_login_client,
                "client_secret": config.github_login_secret,
                "code": code, "redirect_uri": redirect,
            }, headers={"Accept": "application/json"}, timeout=15).json()
            at = tok.get("access_token")
            u = httpx.get("https://api.github.com/user", headers={
                "Authorization": "Bearer " + (at or ""),
                "Accept": "application/vnd.github+json"}, timeout=15).json()
            return u.get("login") or ""
        try:
            login = await asyncio.to_thread(_work)
        except Exception as exc:
            return _login_denied_html(f"Falha no login GitHub: {exc}")
        if not login:
            return _login_denied_html("Não consegui obter seu usuário do GitHub.")
        allowed = memory.get_setting("login_github_user")
        if not allowed:
            memory.set_setting("login_github_user", login)  # pin the first login
        elif login.lower() != allowed.lower():
            return _login_denied_html("Este usuário GitHub não tem acesso a esta E.V.")
        return _login_ok_html()

    return app


def run():
    import uvicorn

    config = Config.load(require_telegram=False)
    if not config.web_token:
        raise SystemExit("EV_WEB_TOKEN não configurado no .env.")
    logging.basicConfig(level=logging.INFO)
    log.info("E.V. web em http://%s:%s", config.web_host, config.web_port)
    uvicorn.run(create_app(config), host=config.web_host, port=config.web_port)
