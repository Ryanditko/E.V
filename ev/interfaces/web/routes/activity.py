"""Activity (history) domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/activity")
    async def activity_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        cat = request.query_params.get("category") or None
        return {"items": ctx.memory.list_activity(ctx.owner, cat),
                "categories": ctx.memory.activity_categories(ctx.owner)}

    return router
