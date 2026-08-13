"""Backup domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio
import hmac

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory = ctx.config, ctx.memory

    @router.get("/api/backup")
    async def api_backup(request: Request):
        # On-demand off-VM pull: a browser download can't set headers, so the
        # token comes as ?k=. Returns a fresh, SQLCipher-encrypted copy of the DB.
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        from fastapi.responses import FileResponse
        from datetime import datetime
        bdir = config.db_path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        dest = bdir / f"ev_memory.{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        await asyncio.to_thread(memory.backup, dest)
        return FileResponse(str(dest), media_type="application/octet-stream",
                            filename=dest.name)

    @router.get("/api/backup/status")
    async def api_backup_status(request: Request):
        ctx.check(request.headers.get("authorization"))
        from datetime import datetime
        bdir = config.db_path.parent / "backups"
        files = sorted(bdir.glob("ev_memory*.db")) if bdir.exists() else []
        last = files[-1] if files else None
        return {
            "count": len(files),
            "last_at": datetime.fromtimestamp(last.stat().st_mtime).isoformat() if last else None,
            "last_size_kb": round(last.stat().st_size / 1024, 1) if last else None,
        }

    @router.post("/api/backup/run")
    async def api_backup_run(request: Request):
        ctx.check(request.headers.get("authorization"))
        from datetime import datetime
        bdir = config.db_path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        dest = bdir / f"ev_memory.{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        await asyncio.to_thread(memory.backup, dest)
        for f in sorted(bdir.glob("ev_memory*.db"))[:-7]:
            f.unlink()
        return {"ok": True}

    return router
