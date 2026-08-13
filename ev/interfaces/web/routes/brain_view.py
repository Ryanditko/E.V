""""Brain" graph-view domain routes — Phase 6b, Group 5 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    # groups shown in the "brain" graph: (key, hub label, view to jump to on
    # click, items, text-getter). Capped per group below so a heavy user's DB
    # still renders a smooth graph.
    @router.get("/api/brain")
    async def brain_graph(request: Request):
        ctx.check(request.headers.get("authorization"))
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

    @router.post("/api/brain/delete")
    async def brain_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        ref = d.get("ref")
        if ref is None:
            raise HTTPException(status_code=400, detail="no ref")
        try:
            _brain_delete(d.get("group", ""), ref)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="bad ref")
        return {"ok": True}

    @router.post("/api/brain/edit")
    async def brain_edit(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        ref = d.get("ref")
        if ref is None:
            raise HTTPException(status_code=400, detail="no ref")
        try:
            ok = _brain_edit(d.get("group", ""), ref, d.get("text", ""))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="bad ref")
        return {"ok": bool(ok)}

    return router
