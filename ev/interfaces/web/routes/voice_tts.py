"""Voice/TTS settings + synthesis domain routes — Phase 6b, Group 4 route
split (external-API-dependent: edge-tts / Gemini TTS via
`ev/providers/voice.py`).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`. Shares `ctx.env_write` (persists
voice settings to .env) with the keys/custom-keys routes.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from ....providers import voice as voice_mod
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config = ctx.config

    @router.post("/api/tts")
    async def tts(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        text = (d.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="empty")
        # optional per-request overrides (voice picker previews force edge-tts)
        req_voice = d.get("voice")
        voice = req_voice if str(req_voice or "").startswith("pt-BR") else None
        audio, mime = await voice_mod.synth_web(
            config, text[:1200], voice=voice, gvoice=d.get("gvoice"),
            rate=d.get("rate"), pitch=d.get("pitch"),
            lang=ctx.memory.assistant_lang())
        return Response(content=audio, media_type=mime)

    @router.get("/api/voice")
    async def voice_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        gv = ([{"id": i, "desc": d} for i, d in voice_mod.GEMINI_VOICES]
              if config.gemini_api_key else [])
        return {"voice": config.voice, "rate": config.voice_rate,
                "pitch": config.voice_pitch,
                "voices": await voice_mod.list_ptbr_voices(),
                "engine": "gemini" if getattr(config, "gemini_tts", False) else "edge",
                "gvoice": getattr(config, "gemini_tts_voice", "Kore"),
                "gemini_voices": gv}

    @router.post("/api/voice")
    async def voice_set(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        voice = (d.get("voice") or "").strip()
        engine = (d.get("engine") or "").strip()
        gset = {i for i, _ in voice_mod.GEMINI_VOICES}
        # --- Gemini voice ---
        if engine == "gemini" or voice in gset:
            if voice not in gset:
                raise HTTPException(status_code=400, detail="invalid gemini voice")
            for f, env, val in (("gemini_tts", "EV_GEMINI_TTS", True),
                                ("gemini_tts_voice", "EV_GEMINI_VOICE", voice)):
                try:
                    object.__setattr__(config, f, val)
                except Exception:
                    pass
                try:
                    ctx.env_write(env, "1" if val is True else val)
                except Exception:
                    pass
            return {"ok": True, "engine": "gemini", "voice": voice}
        # --- edge voice (also turns Gemini off) ---
        voices = {v["id"] for v in await voice_mod.list_ptbr_voices()}
        if not voice.startswith("pt-BR") or (voices and voice not in voices):
            raise HTTPException(status_code=400, detail="invalid voice")
        rate = (d.get("rate") or "+0%").strip()
        pitch = (d.get("pitch") or "+0Hz").strip()
        for f, env, val in (("voice", "EV_VOICE", voice),
                            ("voice_rate", "EV_VOICE_RATE", rate),
                            ("voice_pitch", "EV_VOICE_PITCH", pitch),
                            ("gemini_tts", "EV_GEMINI_TTS", False)):
            try:
                object.__setattr__(config, f, val)
            except Exception:
                pass
            try:
                ctx.env_write(env, "0" if val is False else val)
            except Exception:
                pass
        return {"ok": True, "engine": "edge", "voice": voice, "rate": rate, "pitch": pitch}

    return router
