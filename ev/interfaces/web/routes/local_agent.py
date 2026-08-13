"""Local execution agent domain routes — Phase 6b, Group 5 route split.
Every task requires explicit human approval — no kind auto-runs, ever.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import json

from fastapi import APIRouter, HTTPException, Request

from ..context import WebContext

_LOCAL_TASK_KINDS = {"script", "open", "browser", "shell"}

_BROWSER_AGENT_SYSTEM = (
    "Você controla um navegador de verdade para cumprir um objetivo do "
    "usuário. Responda SOMENTE com um objeto JSON compacto, sem markdown e "
    "sem texto fora do JSON. Campos: "
    "action (um de: goto, click_text, type_text, press_enter, scroll, "
    "read_more, done), "
    "value (string — URL para goto, texto visível do elemento para "
    "click_text, texto a digitar para type_text, ou o resultado final para "
    "done), "
    "risky (bool — true se esta ação específica for enviar mensagem, "
    "publicar, curtir, seguir, comprar, excluir ou qualquer coisa "
    "irreversível feita em nome do usuário), "
    "note (string curta, em português, explicando a ação para o usuário). "
    "Se a tarefa for marcada como alto risco (WhatsApp/Instagram), SEMPRE "
    "marque risky=true antes de clicar em enviar/postar ou de digitar uma "
    "mensagem que será enviada. Use 'done' assim que o objetivo estiver "
    "cumprido ou se for impossível continuar; nesse caso 'value' deve "
    "resumir o resultado para o usuário."
)


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, brain, owner = ctx.memory, ctx.brain, ctx.owner

    @router.get("/api/local-tasks")
    async def local_tasks_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        status = (request.query_params.get("status") or "").strip() or None
        return {"items": memory.list_local_tasks(owner, status)}

    @router.post("/api/local-tasks")
    async def local_tasks_create(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        kind = (d.get("kind") or "").strip().lower()
        label = (d.get("label") or "").strip()
        if kind not in _LOCAL_TASK_KINDS or not label:
            raise HTTPException(status_code=400, detail="kind/label inválidos")
        tid = memory.add_local_task(owner, kind, label[:200], {"command": d.get("command") or ""})
        return {"ok": True, "id": tid}

    @router.post("/api/local-tasks/approve")
    async def local_tasks_approve(request: Request):
        ctx.check(request.headers.get("authorization"))
        tid = int((await ctx.body(request)).get("id") or 0)
        ok = memory.set_local_task_status(owner, tid, "approved")
        return {"ok": ok}

    @router.post("/api/local-tasks/reject")
    async def local_tasks_reject(request: Request):
        ctx.check(request.headers.get("authorization"))
        tid = int((await ctx.body(request)).get("id") or 0)
        ok = memory.set_local_task_status(owner, tid, "rejected")
        return {"ok": ok}

    @router.get("/api/local-tasks/claim")
    async def local_tasks_claim(request: Request):
        # The local daemon polls this from the user's own machine using the
        # same bearer token as the web console — it only ever receives tasks
        # a human already approved.
        ctx.check(request.headers.get("authorization"))
        task = memory.claim_local_task(owner)
        return {"task": task}

    @router.post("/api/local-tasks/result")
    async def local_tasks_result(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        tid = int(d.get("id") or 0)
        ok = memory.finish_local_task(owner, tid, bool(d.get("ok")), d.get("output") or {})
        return {"ok": ok}

    @router.get("/api/local-scripts")
    async def local_scripts_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"items": memory.list_local_scripts(owner)}

    @router.post("/api/local-scripts")
    async def local_scripts_add(request: Request):
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        name = (d.get("name") or "").strip()
        command = (d.get("command") or "").strip()
        if not name or not command:
            raise HTTPException(status_code=400, detail="nome e comando obrigatórios")
        return {"ok": True, "id": memory.add_local_script(owner, name[:60], command)}

    @router.post("/api/local-scripts/delete")
    async def local_scripts_del(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_local_script(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True}

    @router.post("/api/local-tasks/decide")
    async def local_tasks_decide(request: Request):
        # Called by the local browser agent at each step of an autonomous
        # browsing task — the LLM only ever picks the NEXT action, it never
        # executes anything itself (the local daemon does that, on the user's PC).
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        goal = (d.get("goal") or "")[:2000]
        url = (d.get("url") or "")[:500]
        page_text = (d.get("page_text") or "")[:6000]
        history = d.get("history") or []
        high_risk = bool(d.get("high_risk"))
        prompt = (
            f"Objetivo: {goal}\n"
            f"Alto risco (WhatsApp/Instagram): {'sim' if high_risk else 'não'}\n"
            f"URL atual: {url}\n"
            f"Últimas ações: {json.dumps(history[-8:], ensure_ascii=False)}\n"
            f"Texto visível da página (truncado):\n{page_text}"
        )
        raw = await brain.ask(_BROWSER_AGENT_SYSTEM, prompt)
        action = {"action": "done", "value": "não consegui decidir o próximo passo",
                  "risky": False, "note": "erro ao interpretar a resposta do modelo"}
        if raw:
            text = raw.strip()
            if text.startswith("```"):
                text = text.strip("`")
                text = text.split("\n", 1)[1] if "\n" in text else text
                text = text.rsplit("```", 1)[0] if "```" in text else text
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and parsed.get("action"):
                    action = parsed
            except (ValueError, TypeError):
                pass
        return {"action": action}

    @router.post("/api/local-tasks/confirms")
    async def local_confirms_create(request: Request):
        # The local agent calls this right before a 'risky' in-flight action —
        # a SECOND, separate approval on top of the task's original approval.
        ctx.check(request.headers.get("authorization"))
        d = await ctx.body(request)
        tid = int(d.get("task_id") or 0)
        label = (d.get("label") or "ação de alto risco").strip()
        cid = memory.add_local_confirm(owner, tid, label[:200])
        return {"ok": True, "id": cid}

    @router.get("/api/local-tasks/confirms")
    async def local_confirms_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        status = (request.query_params.get("status") or "").strip() or None
        return {"items": memory.list_local_confirms(owner, status)}

    @router.get("/api/local-tasks/confirms/status")
    async def local_confirms_status(request: Request):
        ctx.check(request.headers.get("authorization"))
        cid = int(request.query_params.get("id") or 0)
        c = memory.get_local_confirm(owner, cid)
        return {"status": (c or {}).get("status") or "unknown"}

    @router.post("/api/local-tasks/confirms/approve")
    async def local_confirms_approve(request: Request):
        ctx.check(request.headers.get("authorization"))
        cid = int((await ctx.body(request)).get("id") or 0)
        ok = memory.set_local_confirm_status(owner, cid, "approved")
        return {"ok": ok}

    @router.post("/api/local-tasks/confirms/reject")
    async def local_confirms_reject(request: Request):
        ctx.check(request.headers.get("authorization"))
        cid = int((await ctx.body(request)).get("id") or 0)
        ok = memory.set_local_confirm_status(owner, cid, "rejected")
        return {"ok": ok}

    return router
