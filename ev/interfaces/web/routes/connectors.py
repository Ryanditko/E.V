"""Self-service connectors domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio
import json
import os as _os
import re as _re

from fastapi import APIRouter, HTTPException, Request

from ....providers import connectors as conn_mod
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    def _subst(s: str) -> str:
        # replace {{SECRET_NAME}} with the value from the environment (never logged)
        return _re.sub(r"\{\{\s*([A-Z][A-Z0-9_]{1,39})\s*\}\}",
                       lambda m: _os.environ.get(m.group(1), ""), s or "")

    @router.get("/api/connectors")
    async def connectors_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_connectors(owner)}

    @router.post("/api/connectors")
    async def connectors_add(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        name = (d.get("name") or "").strip()
        url = (d.get("url") or "").strip()
        if not name or not url.startswith("https://"):
            raise HTTPException(status_code=400, detail="nome e URL https são obrigatórios")
        headers = d.get("headers") if isinstance(d.get("headers"), dict) else {}
        cid = memory.add_connector(owner, name[:60], url, headers, (d.get("path") or "").strip())
        return {"ok": True, "id": cid}

    @router.post("/api/connectors/delete")
    async def connectors_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_connector(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/connectors/run")
    async def connectors_run(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        # run either a saved connector (by name) or an ad-hoc test payload
        if d.get("name"):
            c = memory.get_connector(owner, d["name"])
            if not c:
                raise HTTPException(status_code=404, detail="conector não encontrado")
            url, headers, path = c["url"], c["headers"], c["path"]
        else:
            url = (d.get("url") or "").strip()
            headers = d.get("headers") if isinstance(d.get("headers"), dict) else {}
            path = (d.get("path") or "").strip()
        url = _subst(url)
        headers = {k: _subst(v) for k, v in (headers or {}).items()}
        val, err = await asyncio.to_thread(conn_mod.fetch, url, headers, path)
        if err:
            return {"ok": False, "error": err}
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)[:800]
        return {"ok": True, "value": str(val)[:800]}

    return router
