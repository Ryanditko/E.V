"""Speech-to-text domain routes — Phase 6b, Group 4 route split
(external-API-dependent: audio transcription via the Brain).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    brain = ctx.brain

    @router.post("/api/stt")
    async def stt(request: Request):
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("audio")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            raise HTTPException(status_code=400, detail="no audio")
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty audio")
        text = await brain.transcribe(data, f.content_type or "audio/webm")
        return {"text": (text or "").strip()}

    return router
