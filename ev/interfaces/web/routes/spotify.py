"""Spotify OAuth + Web API domain routes — Phase 6b, Group 3 route split
(session-sensitive: links the user's Spotify account and controls playback
with the resulting tokens).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. Shares the OAuth CSRF-state set
(`ctx.oauth_states`) and the login-denied HTML helper (`ctx.login_denied_html`)
with the Google and GitHub OAuth routers — do not duplicate that state, it
must stay a single shared set recognized by all three callbacks. The Spotify
PKCE verifier map (`_sp_pkce`) is used only within this domain, so it stays
local to this router (never shared with Google/GitHub).
"""

import asyncio
import json
import secrets as _secrets
import time as _time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ....providers import spotify as _sp
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory = ctx.config, ctx.memory
    _sp_pkce: dict = {}   # state -> code_verifier (Spotify PKCE, sem secret)

    def _sp_redirect(request: Request) -> str:
        return _sp.norm_redirect(config.web_base_url or str(request.base_url))

    def _sp_save(tokens: dict):
        memory.set_setting("spotify_tokens", json.dumps(tokens))

    def _sp_tokens() -> dict:
        try:
            return json.loads(memory.get_setting("spotify_tokens") or "{}")
        except (ValueError, TypeError):
            return {}

    def _sp_access() -> str | None:
        """A valid access token, refreshing with the refresh_token if expired."""
        import httpx
        t = _sp_tokens()
        if not t.get("refresh"):
            return None
        if t.get("access") and t.get("exp", 0) > _time.time() + 30:
            return t["access"]
        try:
            data = {"grant_type": "refresh_token", "refresh_token": t["refresh"],
                    "client_id": config.spotify_client_id}
            if config.spotify_client_secret:
                data["client_secret"] = config.spotify_client_secret
            r = httpx.post("https://accounts.spotify.com/api/token",
                           data=data, timeout=15).json()
        except Exception:
            return None
        if not r.get("access_token"):
            return None
        t["access"] = r["access_token"]
        t["exp"] = _time.time() + int(r.get("expires_in", 3600))
        if r.get("refresh_token"):
            t["refresh"] = r["refresh_token"]
        _sp_save(t)
        return t["access"]

    def _sp_api(method: str, path: str, token: str, **kw):
        import httpx
        url = path if path.startswith("http") else ("https://api.spotify.com/v1" + path)
        return httpx.request(method, url, headers={"Authorization": "Bearer " + token},
                             timeout=15, **kw)

    @router.get("/spotify/connect")
    async def spotify_connect(request: Request):
        if not config.spotify_client_id:
            return ctx.login_denied_html("Configure o Spotify Client ID em Chaves de API.")
        state = _secrets.token_urlsafe(16); ctx.oauth_states.add(state)
        verifier, challenge = _sp.pkce_pair(); _sp_pkce[state] = verifier
        return RedirectResponse(_sp.auth_url(
            config.spotify_client_id, _sp_redirect(request), state, challenge))

    @router.get("/spotify/callback")
    async def spotify_callback(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in ctx.oauth_states:
            return ctx.login_denied_html("Sessão do Spotify inválida. Tente de novo.")
        ctx.oauth_states.discard(state)
        redirect = _sp_redirect(request)
        verifier = _sp_pkce.pop(state, "")

        def _work():
            data = {"grant_type": "authorization_code", "code": code,
                    "redirect_uri": redirect, "client_id": config.spotify_client_id}
            if verifier:  # PKCE — sem secret
                data["code_verifier"] = verifier
            elif config.spotify_client_secret:
                data["client_secret"] = config.spotify_client_secret
            return httpx.post("https://accounts.spotify.com/api/token",
                              data=data, timeout=15).json()
        try:
            r = await asyncio.to_thread(_work)
        except Exception as exc:
            return ctx.login_denied_html(f"Falha ao conectar o Spotify: {exc}")
        if not r.get("refresh_token"):
            return ctx.login_denied_html("Spotify não devolveu o token. Confira o Client Secret e a Redirect URI.")
        _sp_save({"access": r.get("access_token"), "refresh": r["refresh_token"],
                  "exp": _time.time() + int(r.get("expires_in", 3600))})
        return HTMLResponse("<script>location.href='/'</script>Spotify conectado! Redirecionando…")

    @router.get("/api/spotify/status")
    async def spotify_status(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"configured": bool(config.spotify_client_id),
                "connected": bool(_sp_tokens().get("refresh")),
                "redirect_uri": _sp_redirect(request)}

    @router.post("/api/spotify/disconnect")
    async def spotify_disconnect(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.set_setting("spotify_tokens", "")
        return {"ok": True}

    @router.get("/api/spotify/token")
    async def spotify_token(request: Request):
        # fresh access token for the Web Playback SDK (client-side)
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        return {"token": tok}

    @router.get("/api/spotify/playlists")
    async def spotify_playlists(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        def _work():
            r = _sp_api("GET", "/me/playlists?limit=50", tok)
            return r.json() if r.status_code == 200 else {}
        data = await asyncio.to_thread(_work)
        items = [{"name": p.get("name"), "uri": p.get("uri"), "id": (p.get("id") or ""),
                  # a API passou a devolver a contagem em items.total (antes tracks.total)
                  "tracks": ((p.get("tracks") or p.get("items") or {}).get("total", 0))}
                 for p in (data.get("items") or []) if p]
        return {"items": items}

    @router.post("/api/spotify/play")
    async def spotify_play(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        d = await ctx.body(request)
        body, dev = {}, d.get("device_id")
        if d.get("uris"):
            body["uris"] = d["uris"]
        elif d.get("uri"):
            u = d["uri"]
            if u.startswith("spotify:track:"):
                body["uris"] = [u]           # a single track
            else:
                body["context_uri"] = u      # playlist/album/artist
        if d.get("query"):                   # search then play the top track
            tk = await asyncio.to_thread(_sp.first_track_uri, tok, d["query"])
            if tk:
                body = {"uris": [tk]}
        def _work():
            path = "/me/player/play" + (f"?device_id={dev}" if dev else "")
            r = _sp_api("PUT", path, tok, json=body)
            return r.status_code
        sc = await asyncio.to_thread(_work)
        if sc == 404:
            return {"ok": False, "error": "nenhum dispositivo ativo — abra o Spotify ou use o player da E.V."}
        return {"ok": sc in (200, 202, 204)}

    @router.post("/api/spotify/transfer")
    async def spotify_transfer(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        dev = (await ctx.body(request)).get("device_id")
        if not dev:
            raise HTTPException(status_code=400, detail="sem device da E.V.")
        # move a reprodução pro device da E.V. (toca in-page -> controles do SO)
        sc = await asyncio.to_thread(lambda: _sp_api(
            "PUT", "/me/player", tok, json={"device_ids": [dev], "play": True}).status_code)
        return {"ok": sc in (200, 202, 204)}

    @router.get("/api/spotify/search")
    async def spotify_search(request: Request):
        ctx.check(request.headers.get("authorization"))
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return {"items": []}
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        return {"items": await asyncio.to_thread(_sp.search_tracks, tok, q)}

    @router.get("/api/spotify/current")
    async def spotify_current(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            return {"track": ""}
        return {"track": await asyncio.to_thread(_sp.current_track, tok)}

    @router.get("/api/spotify/nowplaying")
    async def spotify_nowplaying(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            return {"playing": False, "connected": False}
        def _work():
            r = _sp_api("GET", "/me/player", tok)
            if r.status_code != 200:
                return {"playing": False, "connected": True}
            d = r.json() or {}
            it = d.get("item") or {}
            imgs = (it.get("album") or {}).get("images") or []
            tid = it.get("id")
            liked = False
            if tid:
                try:
                    lr = _sp_api("GET", "/me/tracks/contains?ids=" + tid, tok)
                    liked = bool((lr.json() or [False])[0]) if lr.status_code == 200 else False
                except Exception:
                    pass
            dev = d.get("device") or {}
            return {"connected": True, "playing": bool(d.get("is_playing")),
                    "name": it.get("name"), "id": tid, "liked": liked,
                    "artists": ", ".join(a.get("name", "") for a in (it.get("artists") or [])),
                    "image": (imgs[0].get("url") if imgs else ""),
                    "progress": d.get("progress_ms", 0), "duration": it.get("duration_ms", 0),
                    "device": dev.get("name", ""), "volume": dev.get("volume_percent", 50)}
        return await asyncio.to_thread(_work)

    @router.post("/api/spotify/like")
    async def spotify_like(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        d = await ctx.body(request)
        tid = d.get("id")
        if not tid:
            raise HTTPException(status_code=400, detail="sem id")
        method = "PUT" if d.get("on") else "DELETE"
        sc = await asyncio.to_thread(lambda: _sp_api(method, "/me/tracks?ids=" + tid, tok).status_code)
        return {"ok": sc in (200, 201, 202, 204)}

    @router.get("/api/spotify/devices")
    async def spotify_devices(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            return {"items": []}
        def _work():
            r = _sp_api("GET", "/me/player/devices", tok)
            return (r.json().get("devices") or []) if r.status_code == 200 else []
        ds = await asyncio.to_thread(_work)
        return {"items": [{"id": x.get("id"), "name": x.get("name"),
                           "active": x.get("is_active")} for x in ds]}

    @router.post("/api/spotify/volume")
    async def spotify_volume(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        pct = max(0, min(100, int((await ctx.body(request)).get("percent") or 0)))
        sc = await asyncio.to_thread(lambda: _sp_api("PUT", f"/me/player/volume?volume_percent={pct}", tok).status_code)
        return {"ok": sc in (200, 202, 204)}

    @router.post("/api/spotify/queue")
    async def spotify_queue(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        uri = (await ctx.body(request)).get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="sem uri")
        import urllib.parse as _up
        sc = await asyncio.to_thread(lambda: _sp_api("POST", "/me/player/queue?uri=" + _up.quote(uri), tok).status_code)
        return {"ok": sc in (200, 202, 204)}

    @router.post("/api/spotify/control")
    async def spotify_control(request: Request):
        ctx.check(request.headers.get("authorization"))
        tok = await asyncio.to_thread(_sp_access)
        if not tok:
            raise HTTPException(status_code=400, detail="não conectado")
        d = await ctx.body(request)
        act = d.get("action")
        if act == "seek":   # pular pra uma posição (ms)
            ms = max(0, int(d.get("ms") or 0))
            sc = await asyncio.to_thread(
                lambda: _sp_api("PUT", f"/me/player/seek?position_ms={ms}", tok).status_code)
            return {"ok": sc in (200, 202, 204)}
        M = {"pause": ("PUT", "/me/player/pause"), "resume": ("PUT", "/me/player/play"),
             "next": ("POST", "/me/player/next"), "prev": ("POST", "/me/player/previous")}
        if act not in M:
            raise HTTPException(status_code=400, detail="ação inválida")
        method, path = M[act]
        sc = await asyncio.to_thread(lambda: _sp_api(method, path, tok).status_code)
        return {"ok": sc in (200, 202, 204)}

    return router
