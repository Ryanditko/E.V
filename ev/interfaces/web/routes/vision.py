"""Vision domain routes — Phase 6b, Group 4 route split (external-API-
dependent: image understanding via the Brain's vision model). Covers
persisted chat-image vision (`/api/vision` + `/api/chat/image`, which save
the image into the conversation so it re-appears on reload) and ephemeral
live-camera vision (`/api/see`, which never saves the frame).

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import hmac

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, brain, owner = ctx.config, ctx.memory, ctx.brain, ctx.owner

    @router.post("/api/vision")
    async def vision(request: Request):
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"reply": "Nenhuma imagem enviada."}
        data = await f.read()
        if not data:
            return {"reply": "Imagem vazia."}
        prompt = (form.get("text") or "").strip() or "O que há nesta imagem?"
        thread = (form.get("thread") or "geral").strip()
        conv = ctx.conv(thread)
        try:
            reply = await brain.respond(
                owner, conv_id=conv, text=prompt,
                image=data, image_mime=(f.content_type or "image/jpeg"))
        except Exception as exc:
            return {"reply": f"Não consegui analisar a imagem: {exc}"}
        # keep the image in the conversation so it re-appears on reload
        img_id = None
        try:
            img_id = memory.add_chat_image(conv, data, f.content_type or "image/png")
            memory.mark_last_user_image(conv, img_id)
        except Exception:
            pass
        return {"reply": reply, "img_id": img_id}

    @router.get("/api/chat/image")
    async def chat_image(request: Request):
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        img = memory.get_chat_image(int(request.query_params.get("id") or 0))
        if not img:
            raise HTTPException(status_code=404, detail="não encontrada")
        return Response(content=img["data"],
                        media_type=img["mime"] or "image/png",
                        headers={"Cache-Control": "private, max-age=86400"})

    @router.post("/api/see")
    async def see(request: Request):
        """Ephemeral vision for the live camera / 'what is this' — describes the
        frame without saving it to the conversation."""
        ctx.check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"text": ""}
        data = await f.read()
        if not data:
            return {"text": ""}
        mode = (form.get("mode") or "live").strip()
        if mode == "translate":
            prompt = ("Leia TODO o texto visível nesta imagem e traduza para "
                      "português do Brasil. Responda só com a tradução, natural e "
                      "curta. Se não houver texto legível, responda apenas: (sem texto).")
        elif mode == "food":
            prompt = ("Esta é uma foto de comida. Estime em 1-2 frases (pt-BR) o "
                      "prato/itens e as calorias aproximadas totais, e os macros se "
                      "der (proteína/carbo/gordura). Deixe claro que é estimativa. "
                      "Se não for comida, diga: (não parece comida).")
        elif mode == "what":
            prompt = ("Identifique o que está em destaque nesta imagem (objeto, "
                      "lugar/ponto de referência, planta, animal, produto ou texto) e "
                      "dê uma info curta e útil, em 1-2 frases, português do Brasil. "
                      "Se houver texto importante, transcreva.")
        else:
            prompt = ("Descreva em 1 frase curta (pt-BR) o que a câmera vê agora: "
                      "objetos principais e quantas pessoas/rostos aparecem (sem "
                      "identificar quem são). Seja objetivo.")
        text = await brain.describe_image(data, f.content_type or "image/jpeg", prompt)
        return {"text": text or "(não consegui enxergar agora)"}

    return router
