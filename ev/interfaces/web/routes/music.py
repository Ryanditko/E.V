"""Music (Spotify embed player) domain routes — Phase 6b, Group 4 route
split. Distinct from `.routes/spotify.py` (Group 3): this domain stores
user-picked Spotify links (playlist/track/album/...) and renders them via
the public embed player, with no OAuth/account tokens involved.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, HTTPException, Request

from ....providers import spotify as _sp
from ..context import WebContext

_SP_PT = {"playlist": "Playlist", "track": "Faixa", "album": "Álbum",
          "artist": "Artista", "show": "Podcast", "episode": "Episódio"}


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, owner = ctx.memory, ctx.owner

    @router.get("/api/music")
    async def music_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        items = memory.list_music(owner)
        for it in items:
            it["embed"] = _sp.embed_url(it["kind"], it["ref"])
        return {"items": items}

    @router.post("/api/music")
    async def music_add(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        parsed = _sp.parse(d.get("url") or "")
        if not parsed:
            raise HTTPException(status_code=400, detail=(
                "link não suportado — cole uma playlist, faixa, álbum, artista, "
                "podcast ou episódio do Spotify (perfil não tem player)"))
        kind, ref = parsed
        label = (d.get("label") or "").strip() or _SP_PT.get(kind, kind)
        mid = memory.add_music(owner, label[:80], kind, ref)
        return {"ok": True, "id": mid, "embed": _sp.embed_url(kind, ref)}

    @router.post("/api/music/delete")
    async def music_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_music(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    return router
