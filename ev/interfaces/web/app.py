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
from ...providers import voice as voice_mod

from .context import WebContext
from .frontend import _DEFAULT_FOLDERS, _FAVICON, _SERVICE_WORKER, _icon_png, _PAGE
from .routes import (
    activity, backup, connectors, email, expenses, facts, gcal, habits,
    journal, keys, links, location_map, music, notifications, oauth_github,
    oauth_google, pages, push, recurring, reminders, scan_receipt, spotify,
    stt, tasks, vision, voice_tts, watches, weather,
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

    for _router_mod in (
        activity, backup, connectors, email, expenses, facts, gcal, habits,
        journal, keys, links, location_map, music, notifications,
        oauth_github, oauth_google, pages, push, recurring, reminders,
        scan_receipt, spotify, stt, tasks, vision, voice_tts, watches,
        weather,
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

    # weather/astro/radar/music routes moved to .routes/ (Phase 6b, Group 4)

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

    # --- Subscriptions / Budgets / Watches CRUD ----------------------------
    # (recurring/watches CRUD, including their reunified /update, moved to
    # .routes/recurring.py and .routes/watches.py — Phase 6b, Group 2)
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

    # voice/tts, vision, location/map, scan/receipt, stt, and email routes
    # moved to .routes/ (Phase 6b, Group 4)

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

    # Google Calendar (/api/gcal*) routes moved to .routes/ (Phase 6b, Group 4)

    return app


def run():
    import uvicorn

    config = Config.load(require_telegram=False)
    if not config.web_token:
        raise SystemExit("EV_WEB_TOKEN não configurado no .env.")
    logging.basicConfig(level=logging.INFO)
    log.info("E.V. web em http://%s:%s", config.web_host, config.web_port)
    uvicorn.run(create_app(config), host=config.web_host, port=config.web_port)
