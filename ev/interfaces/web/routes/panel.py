"""Dashboard/panel domain routes — Phase 6b, Group 5 route split: system
panel stats, home overview, chart data, dashboard widget config, the
Mapillary street-view token, "modo foco" toggle, and the owner's face
descriptor (personalization at login/greeting). None of these fit any of
the other Group-5 domains cleanly, so they're bundled here as the
console/dashboard's own settings & stats surface — a judgment call, see the
Group-5 PR description.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import json
import time as _time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from ....core import health
from ..context import WebContext

_DEF_ACTIONS = ["plano", "buscar", "noticias", "clima", "relatorio", "semana"]
_DEF_STATS = ["tasks", "reminders", "expenses", "memories", "kb"]


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, brain, commands, owner = (
        ctx.config, ctx.memory, ctx.brain, ctx.commands, ctx.owner)

    def _cfg_list(key, default):
        raw = memory.get_setting(key)
        try:
            v = json.loads(raw) if raw else None
        except Exception:
            v = None
        return v if isinstance(v, list) else list(default)

    @router.get("/api/config")
    async def cfg_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"actions": _cfg_list("web_actions", _DEF_ACTIONS),
                "stats": _cfg_list("web_stats", _DEF_STATS),
                "mapillary": bool(getattr(config, "mapillary_token", ""))}

    @router.get("/api/mapillary")
    async def mapillary_token(request: Request):
        # The in-app street-level viewer runs client-side and needs the token.
        ctx.check(request.headers.get("authorization"))
        tok = getattr(config, "mapillary_token", "") or ""
        return {"enabled": bool(tok), "token": tok}

    @router.post("/api/config")
    async def cfg_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        if isinstance(data.get("actions"), list):
            memory.set_setting("web_actions", json.dumps(data["actions"][:24]))
        if isinstance(data.get("stats"), list):
            memory.set_setting("web_stats", json.dumps(data["stats"][:10]))
        return {"ok": True}

    @router.get("/api/face")
    async def face_get(request: Request):
        # Owner face descriptor (greeting/personalization only). Never other people.
        ctx.check(request.headers.get("authorization"))
        raw = memory.get_setting("face_descriptor") or ""
        try:
            desc = json.loads(raw) if raw else None
        except ValueError:
            desc = None
        return {"enrolled": bool(desc), "descriptor": desc}

    @router.post("/api/face")
    async def face_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        if data.get("clear"):
            memory.set_setting("face_descriptor", "")
            return {"ok": True, "enrolled": False}
        desc = data.get("descriptor")
        if (not isinstance(desc, list) or len(desc) != 128
                or not all(isinstance(x, (int, float)) for x in desc)):
            raise HTTPException(status_code=400, detail="invalid descriptor")
        memory.set_setting("face_descriptor", json.dumps([float(x) for x in desc]))
        return {"ok": True, "enrolled": True}

    @router.get("/api/charts")
    async def charts(request: Request):
        ctx.check(request.headers.get("authorization"))
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

        # --- new charts: same [frm, to_end) period + daily/monthly bucketing ---
        bucket_keys = list(buckets.keys())

        def _lbl(k):  # match exp_day label format (MM-DD daily, YYYY-MM monthly)
            return k if by_month else k[5:]

        def _bkey(day):  # day is "YYYY-MM-DD"
            return day[:7] if by_month else day

        labels = [_lbl(k) for k in bucket_keys]
        frm_iso = frm.isoformat()

        # 1. Interactions over time (messages per day, by role)
        inter_user = {k: 0 for k in bucket_keys}
        inter_model = {k: 0 for k in bucket_keys}
        for row in memory.messages_per_day(owner, frm_iso, to_end):
            key = _bkey(row.get("day") or "")
            if key in inter_user:
                if row.get("role") == "user":
                    inter_user[key] += row.get("n", 0)
                elif row.get("role") == "model":
                    inter_model[key] += row.get("n", 0)
        interactions = {
            "labels": labels,
            "user": [inter_user[k] for k in bucket_keys],
            "model": [inter_model[k] for k in bucket_keys],
        }

        # 2. AI-provider usage share
        prov_tot = memory.usage_between(fd, td)
        providers = [{"label": p, "value": n}
                     for p, n in sorted(prov_tot.items(), key=lambda x: -x[1])]

        # 3. Activity by type (top 8)
        activity = [{"label": r["action"], "value": r["n"]}
                    for r in memory.activity_counts(owner, frm_iso, to_end, 8)]

        # 4. Tasks created vs completed per bucket
        tpd = memory.tasks_per_day(owner, frm_iso, to_end)
        t_created = {k: 0 for k in bucket_keys}
        t_done = {k: 0 for k in bucket_keys}
        for day, n in tpd.get("created", {}).items():
            key = _bkey(day)
            if key in t_created:
                t_created[key] += n
        for day, n in tpd.get("completed", {}).items():
            key = _bkey(day)
            if key in t_done:
                t_done[key] += n
        tasks_daily = {
            "labels": labels,
            "created": [t_created[k] for k in bucket_keys],
            "completed": [t_done[k] for k in bucket_keys],
        }

        # 5. Memory growth (cumulative facts, starting from pre-period total)
        fpd = memory.facts_per_day(owner, frm_iso, to_end)
        f_new = {k: 0 for k in bucket_keys}
        for day, n in fpd.items():
            key = _bkey(day)
            if key in f_new:
                f_new[key] += n
        running = memory.facts_count_before(owner, frm_iso)
        mem_values = []
        for k in bucket_keys:
            running += f_new[k]
            mem_values.append(running)
        memory_growth = {"labels": labels, "values": mem_values}

        return {
            "exp_cat": [{"label": k, "value": round(v, 2)} for k, v in cat],
            "exp_day": series,
            "habits": habits[:10],
            "interactions": interactions,
            "providers": providers,
            "activity": activity,
            "tasks_daily": tasks_daily,
            "memory_growth": memory_growth,
            "range": {"from": fd, "to": td},
        }

    # --- modo foco (alerta vermelho) --------------------------------------
    @router.post("/api/serious")
    async def serious_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        body = await request.json()
        memory.set_setting("serious_mode", "1" if body.get("on") else "0")
        return {"ok": True, "serious": bool(body.get("on"))}

    # --- home dashboard overview -------------------------------------------
    @router.get("/api/overview")
    async def overview_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        return commands.overview(owner)

    @router.get("/api/panel")
    async def panel(request: Request):
        ctx.check(request.headers.get("authorization"))
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
        up = int(ctx.boot and (_time.monotonic() - ctx.boot) or 0)
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

    return router
