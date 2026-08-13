"""Custom pages (declarative dashboards) domain routes — Phase 6b, Group 1
route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext

_WIDGET_TYPES = {"note", "tasks", "connector", "command", "chart", "spotify"}


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    def _clean_widgets(raw):
        from ....providers import spotify as _sp2
        out = []
        for w in (raw or [])[:20]:
            if not isinstance(w, dict) or w.get("type") not in _WIDGET_TYPES:
                continue
            ww = {k: v for k, v in w.items()
                  if k in ("type", "text", "category", "name", "cmd", "label", "icon", "kind", "ref")}
            if ww.get("type") == "spotify":
                if w.get("url"):
                    p = _sp2.parse(w["url"])
                    if not p:
                        continue
                    ww["kind"], ww["ref"] = p
                if not ww.get("kind") or not ww.get("ref"):
                    continue
            out.append(ww)
        return out

    @router.get("/api/pages")
    async def pages_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_pages(owner)}

    @router.post("/api/pages")
    async def pages_save(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        name = (d.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="nome obrigatório")
        widgets = _clean_widgets(d.get("widgets"))
        if d.get("id"):
            memory.update_page(owner, int(d["id"]), name=name, widgets=widgets)
            return {"ok": True, "id": int(d["id"])}
        return {"ok": True, "id": memory.add_page(owner, name[:60], widgets)}

    @router.post("/api/pages/delete")
    async def pages_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_page(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    return router
