"""API-keys management domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import json
import os as _os
import re as _re

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext

_KEY_FIELDS = [
    ("gemini_api_key", "GEMINI_API_KEY", "Gemini (IA principal)"),
    ("groq_api_key", "GROQ_API_KEY", "Groq (fallback + voz→texto)"),
    ("openrouter_api_key", "OPENROUTER_API_KEY", "OpenRouter (fallback)"),
    ("tavily_api_key", "TAVILY_API_KEY", "Tavily (busca web)"),
    ("brave_api_key", "BRAVE_API_KEY", "Brave (busca web)"),
    ("imap_address", "EV_IMAP_ADDRESS", "E-mail Gmail (leitura)"),
    ("imap_password", "EV_IMAP_PASSWORD", "Senha de app Gmail (leitura)"),
    ("mapillary_token", "EV_MAPILLARY_TOKEN", "Mapillary (ver rua integrado)"),
    ("spotify_client_id", "EV_SPOTIFY_CLIENT_ID", "Spotify Client ID"),
    ("spotify_client_secret", "EV_SPOTIFY_CLIENT_SECRET", "Spotify Client Secret"),
]


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory = ctx.config, ctx.memory

    def _keys_state():
        return [{"field": f, "label": lbl, "set": bool(getattr(config, f, ""))}
                for f, env, lbl in _KEY_FIELDS]

    def _custom_keys():
        try:
            return json.loads(memory.get_setting("custom_keys") or "[]")
        except (ValueError, TypeError):
            return []

    @router.get("/api/keys")
    async def keys_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"keys": _keys_state()}

    @router.post("/api/keys")
    async def keys_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        changed = []
        for f, env, lbl in _KEY_FIELDS:
            v = (d.get(f) or "").strip()
            if v:
                try:  # frozen dataclass -> update in place so the web uses it now
                    object.__setattr__(config, f, v)
                except Exception:
                    pass
                try:  # persist to .env (survives restart; Telegram picks it up too)
                    ctx.env_write(env, v)
                    changed.append(lbl)
                except Exception:
                    pass
        return {"ok": bool(changed), "changed": changed, "keys": _keys_state()}

    @router.get("/api/keys/custom")
    async def custom_keys_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        names = _custom_keys()
        return {"keys": [{"name": n, "set": bool(_os.environ.get(n))} for n in names]}

    @router.post("/api/keys/custom")
    async def custom_keys_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        name = (d.get("name") or "").strip().upper()
        if not _re.match(r"^[A-Z][A-Z0-9_]{1,39}$", name):
            raise HTTPException(status_code=400, detail="nome inválido (use MAIÚSCULAS_E_UNDERSCORE)")
        names = _custom_keys()
        if d.get("clear"):
            _os.environ.pop(name, None)
            try:
                ctx.env_write(name, "")
            except Exception:
                pass
            names = [n for n in names if n != name]
            memory.set_setting("custom_keys", json.dumps(names))
            return {"ok": True, "removed": name}
        val = (d.get("value") or "").strip()
        if not val:
            raise HTTPException(status_code=400, detail="valor vazio")
        _os.environ[name] = val                      # live for connectors, no restart
        try:
            ctx.env_write(name, val)                  # persist to .env
        except Exception:
            pass
        if name not in names:
            names.append(name)
            memory.set_setting("custom_keys", json.dumps(names))
        return {"ok": True, "name": name}

    return router
