"""GitHub OAuth login domain routes — Phase 6b, Group 3 route split
(session-sensitive: this is the flow that grants access to the web console).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. Shares the OAuth CSRF-state set
(`ctx.oauth_states`) and the login success/denied HTML helpers
(`ctx.login_ok_html`/`ctx.login_denied_html`) with the Google and Spotify
OAuth routers — do not duplicate that state, it must stay a single shared set
recognized by all three callbacks.
"""

import asyncio
import secrets as _secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory = ctx.config, ctx.memory

    @router.get("/auth/github")
    async def auth_github(request: Request):
        if not config.github_login_client:
            return ctx.login_denied_html("Login com GitHub não configurado.")
        from urllib.parse import urlencode
        state = _secrets.token_urlsafe(16); ctx.oauth_states.add(state)
        params = urlencode({
            "client_id": config.github_login_client,
            "redirect_uri": ctx.base_url(request) + "/auth/github/callback",
            "scope": "read:user", "state": state,
        })
        return RedirectResponse("https://github.com/login/oauth/authorize?" + params)

    @router.get("/auth/github/callback")
    async def auth_github_cb(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in ctx.oauth_states:
            return ctx.login_denied_html("Sessão de login inválida. Tente de novo.")
        ctx.oauth_states.discard(state)
        redirect = ctx.base_url(request) + "/auth/github/callback"

        def _work():
            tok = httpx.post("https://github.com/login/oauth/access_token", data={
                "client_id": config.github_login_client,
                "client_secret": config.github_login_secret,
                "code": code, "redirect_uri": redirect,
            }, headers={"Accept": "application/json"}, timeout=15).json()
            at = tok.get("access_token")
            u = httpx.get("https://api.github.com/user", headers={
                "Authorization": "Bearer " + (at or ""),
                "Accept": "application/vnd.github+json"}, timeout=15).json()
            return u.get("login") or ""
        try:
            login = await asyncio.to_thread(_work)
        except Exception as exc:
            return ctx.login_denied_html(f"Falha no login GitHub: {exc}")
        if not login:
            return ctx.login_denied_html("Não consegui obter seu usuário do GitHub.")
        allowed = memory.get_setting("login_github_user")
        if not allowed:
            memory.set_setting("login_github_user", login)  # pin the first login
        elif login.lower() != allowed.lower():
            return ctx.login_denied_html("Este usuário GitHub não tem acesso a esta E.V.")
        return ctx.login_ok_html()

    return router
