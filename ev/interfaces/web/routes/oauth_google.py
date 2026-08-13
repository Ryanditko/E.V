"""Google OAuth login domain routes — Phase 6b, Group 3 route split
(session-sensitive: this is the flow that grants access to the web console).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. Shares the OAuth CSRF-state set
(`ctx.oauth_states`) and the login success/denied HTML helpers
(`ctx.login_ok_html`/`ctx.login_denied_html`) with the GitHub and Spotify
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

    @router.get("/auth/google")
    async def auth_google(request: Request):
        if not config.google_login_client:
            return ctx.login_denied_html("Login com Google não configurado.")
        from urllib.parse import urlencode
        state = _secrets.token_urlsafe(16); ctx.oauth_states.add(state)
        params = urlencode({
            "client_id": config.google_login_client,
            "redirect_uri": ctx.base_url(request) + "/auth/google/callback",
            "response_type": "code", "scope": "openid email profile",
            "access_type": "online", "state": state, "prompt": "select_account",
        })
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + params)

    @router.get("/auth/google/callback")
    async def auth_google_cb(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in ctx.oauth_states:
            return ctx.login_denied_html("Sessão de login inválida. Tente de novo.")
        ctx.oauth_states.discard(state)
        redirect = ctx.base_url(request) + "/auth/google/callback"

        def _work():
            tok = httpx.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": config.google_login_client,
                "client_secret": config.google_login_secret,
                "redirect_uri": redirect, "grant_type": "authorization_code",
            }, timeout=15).json()
            at = tok.get("access_token")
            info = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo",
                             headers={"Authorization": "Bearer " + (at or "")},
                             timeout=15).json()
            return (info.get("email") or "").lower()
        try:
            email = await asyncio.to_thread(_work)
        except Exception as exc:
            return ctx.login_denied_html(f"Falha no login Google: {exc}")
        if not email:
            return ctx.login_denied_html("Não consegui obter seu email do Google.")
        allowed = memory.get_setting("login_google_email")
        if not allowed:
            memory.set_setting("login_google_email", email)  # pin the first login
        elif email != allowed:
            return ctx.login_denied_html("Esta conta Google não tem acesso a esta E.V.")
        return ctx.login_ok_html()

    return router
