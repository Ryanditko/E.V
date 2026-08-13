"""Global search domain routes — Phase 6b, Group 5 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/search")
    async def search_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
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

    return router
