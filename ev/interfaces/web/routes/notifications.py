"""Notification-center domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, commands, owner = ctx.memory, ctx.commands, ctx.owner

    @router.get("/api/notifications")
    async def notifs_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        alerts = []
        for s in commands.subscriptions_due(owner):
            alerts.append({
                "id": f"sub-{s['id']}", "ephemeral": True, "kind": "sub",
                "title": "Assinatura vencendo em breve",
                "body": f"{s['description']} — R$ {s['amount']:.2f} · vence em "
                        f"{s['days_until']} dia{'s' if s['days_until'] != 1 else ''}",
            })
        for b in commands.budget_alerts(owner):
            alerts.append({
                "id": f"bud-{b['category']}", "ephemeral": True, "kind": "budget",
                "title": "Orçamento estourado" if b["level"] == "over" else "Orçamento perto do limite",
                "body": f"{b['category']}: R$ {b['spent']:.2f} de R$ {b['amount']:.2f} ({b['pct']}%)",
            })
        return {"items": alerts + memory.list_notifications(owner),
                "unread": len(alerts) + memory.unread_notifications(owner)}

    @router.post("/api/notifications/read")
    async def notifs_read(request: Request):
        ctx.check(request.headers.get("authorization"))
        nid = (await ctx.body(request)).get("id")
        memory.mark_notification_read(owner, int(nid) if nid else None)
        return {"ok": True, "unread": memory.unread_notifications(owner)}

    @router.post("/api/notifications/delete")
    async def notifs_delete(request: Request):
        ctx.check(request.headers.get("authorization"))
        memory.delete_notification(owner, int((await ctx.body(request)).get("id") or 0))
        return {"ok": True, "unread": memory.unread_notifications(owner)}

    @router.post("/api/notifications/clear")
    async def notifs_clear(request: Request):
        ctx.check(request.headers.get("authorization"))
        scope = (await ctx.body(request)).get("scope")
        memory.clear_notifications(owner, only_read=(scope == "read"))
        return {"ok": True, "unread": memory.unread_notifications(owner)}

    return router
