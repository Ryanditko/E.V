"""Chat/console domain routes — Phase 6b, Group 5 route split.

Not one of the domains named in the Group-5 list (search, panel, brain_view,
health_saude, vault, local_agent, calendar, kb, subscriptions, budgets,
goals, notify) — this is a judgment call: the boot briefing/greeting, the
command list, folder ("thread") CRUD, chat history, and the /api/chat,
/api/chat/stream and /api/cmd endpoints are all leftover domain routes that
don't fit any named Group-5 domain. Since app.py must end this phase with
zero domain routes, they're grouped here as the console's own chat/command
surface rather than left inline. See the Group-5 PR description for the
full rationale.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

import asyncio
import json
import re as _re

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ....core.commands import command_list
from ....core.i18n import t as _t
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    config, memory, brain, commands, owner = (
        ctx.config, ctx.memory, ctx.brain, ctx.commands, ctx.owner)

    @router.get("/api/briefing")
    async def briefing(request: Request):
        # A live spoken boot briefing (deterministic status). Shown + spoken.
        ctx.check(request.headers.get("authorization"))
        try:
            return {"text": commands.spoken_status(owner)}
        except Exception:
            return {"text": _t(memory.assistant_lang(), "greeting.welcome_back", name="Ryan")}

    @router.get("/api/greeting")
    async def greeting(request: Request):
        from fastapi import Response as R
        from ....providers import voice as voice_mod
        ctx.check(request.headers.get("authorization"))
        try:
            phrase = commands.spoken_status(owner)
        except Exception:
            phrase = _t(memory.assistant_lang(), "greeting.welcome_back", name="Ryan")
        try:
            # Pass the assistant language so the boot briefing is SPOKEN in the
            # right voice (en-US when English) — the phrase text already honors
            # it via spoken_status; without this it fell back to the pt-BR voice.
            audio, mime = await voice_mod.synth_web(
                config, phrase, lang=memory.assistant_lang())
        except Exception:
            audio, mime = b"", "audio/mpeg"
        return R(content=audio, media_type=mime)

    @router.get("/api/commands")
    async def commands_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"commands": [{"name": n, "desc": d}
                             for n, d in command_list(memory.assistant_lang())]}

    @router.get("/api/threads")
    async def threads_get(request: Request):
        ctx.check(request.headers.get("authorization"))
        return {"threads": ctx.folders()}

    @router.post("/api/threads")
    async def threads_post(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        name = (data.get("name") or "").strip().lower().replace(" ", "-").replace("/", "-")
        parent = (data.get("parent") or "").strip().lower()
        if name:
            path = f"{parent}/{name}" if parent else name
            fs = ctx.folders()
            if path not in fs:
                fs.append(path)
                memory.set_setting("web_folders", json.dumps(fs))
        return {"threads": ctx.folders()}

    @router.post("/api/threads/move")
    async def threads_move(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        path = (data.get("path") or "").strip().lower()
        parent = (data.get("parent") or "").strip().lower()  # "" = to root
        if not path or path == "geral" or parent == path or parent.startswith(path + "/"):
            return {"threads": ctx.folders()}  # can't move into itself/descendant
        leaf = path.rsplit("/", 1)[-1]
        newpath = f"{parent}/{leaf}" if parent else leaf
        fs = ctx.folders()
        if newpath != path and path in fs and newpath not in fs:
            out = []
            for f in fs:
                if f == path or f.startswith(path + "/"):
                    nf = newpath + f[len(path):]
                    memory.rename_conversation(ctx.conv(f), ctx.conv(nf))
                    out.append(nf)
                else:
                    out.append(f)
            memory.set_setting("web_folders", json.dumps(out))
        return {"threads": ctx.folders()}

    @router.get("/api/history")
    async def history_ep(request: Request):
        ctx.check(request.headers.get("authorization"))
        thread = request.query_params.get("thread", "geral")
        msgs = memory.recent_messages(ctx.conv(thread), limit=50)
        return {"messages": msgs}

    @router.post("/api/chat")
    async def chat(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo. 🙂"}
        reply = await brain.respond(owner, conv_id=ctx.conv(data.get("thread")), text=text)
        brain.pop_documents()
        brain.pop_actions()
        steps = brain.pop_steps() if hasattr(brain, "pop_steps") else []
        return {"reply": reply, "steps": steps}

    @router.post("/api/chat/stream")
    async def chat_stream(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo."}
        reply = await brain.respond(owner, conv_id=ctx.conv(data.get("thread")), text=text)
        brain.pop_documents()
        brain.pop_actions()

        async def gen():
            # progressive reveal of the computed reply (live-typing feel)
            for w in (_re.findall(r"\S+\s*", reply) or [reply]):
                yield w
                await asyncio.sleep(0.015)
        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    @router.post("/api/cmd")
    async def cmd(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        command = (data.get("command") or "").strip()
        thread = data.get("thread")
        reply = await ctx.run_command(command, thread)
        name = command.lstrip("/").split()[0].lower() if command else ""
        if name not in ("limpar", "limparchat"):  # don't re-log after clearing
            conv = ctx.conv(thread)
            memory.add_message(conv, "user", "/" + command)
            memory.add_message(conv, "model", reply)
        return {"reply": reply}

    @router.post("/api/threads/delete")
    async def threads_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        name = ((await ctx.body(request)).get("name") or "").strip().lower()
        if name and name != "geral":
            fs = ctx.folders()
            victims = [f for f in fs if f == name or f.startswith(name + "/")]
            if victims:
                memory.set_setting(
                    "web_folders", json.dumps([f for f in fs if f not in victims]))
                for v in victims:  # drop the folder and its subfolders' conversations
                    memory.clear_conversation(ctx.conv(v))
        return {"threads": ctx.folders()}

    @router.post("/api/threads/rename")
    async def threads_rename(request: Request):
        ctx.check(request.headers.get("authorization"))
        data = await ctx.body(request)
        old = (data.get("old") or "").strip().lower()
        new = (data.get("new") or "").strip().lower().replace(" ", "-").replace("/", "-")
        if old and new and old != "geral":
            parent = old.rsplit("/", 1)[0] if "/" in old else ""
            newpath = f"{parent}/{new}" if parent else new
            fs = ctx.folders()
            if old in fs and newpath not in fs:
                out = []
                for f in fs:  # rename the folder AND all its descendants
                    if f == old or f.startswith(old + "/"):
                        nf = newpath + f[len(old):]
                        memory.rename_conversation(ctx.conv(f), ctx.conv(nf))
                        out.append(nf)
                    else:
                        out.append(f)
                memory.set_setting("web_folders", json.dumps(out))
        return {"threads": ctx.folders()}

    return router
