"""Notification-center domain routes — Phase 6b, Group 1 route split.

Extract-and-recompose: logic moved verbatim from
`ev/interfaces/web/app.py`'s `create_app()`.
"""

from fastapi import APIRouter, Request

from ....core.i18n import plural as _plural
from ....core.i18n import t as _t
from ..context import WebContext


def build_router(ctx: WebContext) -> APIRouter:
    router = APIRouter()
    memory, commands, owner = ctx.memory, ctx.commands, ctx.owner

    @router.get("/api/notifications")
    async def notifs_list(request: Request):
        ctx.check(request.headers.get("authorization"))
        lang = memory.assistant_lang()
        alerts = []
        for s in commands.subscriptions_due(owner):
            alerts.append({
                "id": f"sub-{s['id']}", "ephemeral": True, "kind": "sub",
                "title": _t(lang, "notif.sub_due_title"),
                "body": _t(lang, "notif.sub_due_body",
                           description=s["description"], amount=f"{s['amount']:.2f}",
                           days=_plural(lang, "count.days", s["days_until"])),
            })
        for b in commands.budget_alerts(owner):
            alerts.append({
                "id": f"bud-{b['category']}", "ephemeral": True, "kind": "budget",
                "title": _t(lang, "notif.budget_over_title") if b["level"] == "over"
                else _t(lang, "notif.budget_warn_title"),
                "body": _t(lang, "notif.budget_body", category=b["category"],
                           spent=f"{b['spent']:.2f}", amount=f"{b['amount']:.2f}",
                           pct=b["pct"]),
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
