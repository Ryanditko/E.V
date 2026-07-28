"""Web Push — deliver a browser notification to the owner's subscribed devices,
even when the web app is closed. Used by the reminder scheduler and a test button.

Subscriptions are stored by the web interface (`memory.add_push_sub`) and signed
with the server's VAPID key. Best-effort: a dead subscription is pruned.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ev.push")


def send_push(config, memory, title: str, body: str, url: str = "/",
              owner: str | None = None) -> int:
    """Push `{title, body}` to every stored subscription. Returns how many sent.

    When `owner` is given, the notification is also logged to the notification
    center so it can be reviewed/dismissed later — even if no device was
    reachable or Web Push isn't configured.
    """
    if owner:
        try:
            memory.add_notification(owner, title, body, url)
        except Exception as exc:
            log.warning("notification log failed: %s", exc)
    if not (config.vapid_private and config.vapid_public):
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except Exception as exc:  # library missing -> silently no-op
        log.warning("pywebpush unavailable: %s", exc)
        return 0
    subs = memory.list_push_subs()
    if not subs:
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    for s in subs:
        try:
            webpush(
                subscription_info=json.loads(s["sub"]),
                data=payload,
                vapid_private_key=config.vapid_private,
                vapid_claims={"sub": config.vapid_subject},
            )
            sent += 1
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):  # subscription gone -> prune it
                try:
                    memory.delete_push_sub(s["endpoint"])
                except Exception:
                    pass
            log.warning("push failed (%s)", code)
        except Exception as exc:
            log.warning("push error: %s", exc)
    return sent
