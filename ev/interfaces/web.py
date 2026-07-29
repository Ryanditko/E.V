"""E.V.'s web interface — a JARVIS-style operator console (voice + dashboard +
terminal + scoped conversations). Reuses the SAME brain/memory/tools as Telegram.

One self-contained page (no build) served by FastAPI. Auth: EV_WEB_TOKEN.
Conversations are scoped by folder -> conv_id = "web:<folder>" (own thread each,
shared data). Runs data commands AND interface commands (provedor/status/...).
"""

import asyncio
import hmac
import json
import logging

from ..config import Config
from ..core import health, knowledge
from ..core.brain import Brain
from ..core.commands import COMMAND_LIST, Commands
from ..core.memory import Memory
from ..providers import tools as tools_mod, voice as voice_mod

log = logging.getLogger("ev.web")

_DEFAULT_FOLDERS = ["geral", "work", "university", "personal"]

# Monochrome "core" mark — the E.V. identity, as an inline SVG favicon.
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#0a0a0a"/>'
    '<circle cx="32" cy="32" r="21" fill="none" stroke="#f4f3f1" stroke-opacity=".22" stroke-width="2"/>'
    '<circle cx="32" cy="32" r="12.5" fill="none" stroke="#f4f3f1" stroke-opacity=".5" stroke-width="2"/>'
    '<circle cx="32" cy="32" r="4.5" fill="#f4f3f1"/></svg>'
)

# Minimal service worker — makes the app installable (needs a fetch handler) and
# focuses/opens the app when a notification is clicked. No caching (avoids stale UI).
# Bump the version comment to force browsers to re-install the worker. v3
_SERVICE_WORKER = """
// ev-sw v3 — no caching, always network
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil((async () => {
  const keys = await caches.keys();
  await Promise.all(keys.map(k => caches.delete(k)));  // wipe any old caches
  await self.clients.claim();
})()));
self.addEventListener('fetch', e => {});  // pass-through; presence enables install
self.addEventListener('push', e => {
  let d = {title:'E.V.', body:''};
  try { d = e.data.json(); } catch(_) { if (e.data) d.body = e.data.text(); }
  e.waitUntil(self.registration.showNotification(d.title || 'E.V.', {
    body: d.body || '', icon: '/icon-192.png', badge: '/icon-192.png',
    tag: d.body || 'ev', data: { url: d.url || '/' }
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(clients.matchAll({type:'window', includeUncontrolled:true}).then(cs => {
    for (const c of cs) { if ('focus' in c) return c.focus(); }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});
"""

_ICON_CACHE: dict[int, bytes] = {}


def _icon_png(size: int) -> bytes:
    """Render the E.V. 'core' mark as a PNG (for the installable app icon)."""
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
    import io

    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22),
                        fill=(10, 10, 10, 255))
    cx = cy = size / 2
    fg = (244, 243, 241)
    w = max(2, size // 34)
    for rr, alpha in [(0.33, 150), (0.20, 235)]:
        rad = size * rr
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=fg + (alpha,), width=w)
    dot = size * 0.075
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=fg + (255,))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    _ICON_CACHE[size] = buf.getvalue()
    return _ICON_CACHE[size]


_PAGE = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>E.V.</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0a0a0a">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="E.V.">
<link rel="apple-touch-icon" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
<style>
:root{
  --ink:#0a0a0a;--panel:#0d0d0d;--elev:#141414;--surface:#101010;
  --fg:#f4f3f1;--muted:#a1a1a1;--subtle:#6b6b6b;
  --line:rgba(244,243,241,.10);--line-2:rgba(244,243,241,.20);
  --disp:'Space Grotesk',sans-serif;--body:'Inter',sans-serif;--mono:'JetBrains Mono',monospace;
}
*{box-sizing:border-box}html,body{height:100%;max-width:100%;overflow-x:hidden}
body{margin:0;background:var(--ink);color:var(--fg);font-family:var(--body);-webkit-font-smoothing:antialiased;overflow:hidden}
.topbar{min-width:0}#center{overflow:hidden}
*{scrollbar-width:thin;scrollbar-color:#242424 transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#202020;border-radius:8px;border:2px solid var(--ink);background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:#2f2f2f;background-clip:padding-box}
::-webkit-scrollbar-corner{background:transparent}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(rgba(244,243,241,.04) 1px,transparent 1px);background-size:26px 26px;mask:radial-gradient(120% 90% at 50% 0%,#000,transparent 78%)}
#app{position:relative;z-index:1;height:100%;display:grid;grid-template-columns:238px 1fr 272px;min-height:0}
.rail{display:flex;flex-direction:column;min-height:0}
#left{border-right:1px solid var(--line);padding:18px;gap:14px;overflow:auto}
#right{border-left:1px solid var(--line);padding:18px;gap:12px;overflow:auto}
#center{min-width:0;min-height:0;display:flex;flex-direction:column}
.brand .name{font-family:var(--disp);font-weight:700;font-size:26px;letter-spacing:.14em}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.26em;color:var(--subtle);text-transform:uppercase;margin:4px 2px}
.core{width:132px;height:132px;position:relative;margin:6px auto 2px}
.core .ring{position:absolute;border-radius:50%;border:1px solid var(--line-2)}
.core .ring.a{inset:0}.core .ring.b{inset:18px;border-color:var(--line)}.core .ring.c{inset:40px;border-color:var(--line-2)}
.core .arc{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 66%,rgba(244,243,241,.95) 84%,transparent 100%);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));animation:spin 7s linear infinite}
.core .arc.two{inset:18px;animation-duration:11s;animation-direction:reverse;opacity:.5}
.core .dot{position:absolute;inset:0;margin:auto;width:8px;height:8px;border-radius:50%;background:var(--fg);box-shadow:0 0 20px 4px rgba(244,243,241,.45)}
@keyframes spin{to{transform:rotate(360deg)}}
body.listening .core .arc{animation-duration:1.8s}body.thinking .core .arc{animation-duration:2.6s}
body.listening .core .dot{animation:pulse 1s infinite}@keyframes pulse{50%{transform:scale(1.9);opacity:.55}}
.state{font-family:var(--mono);font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);text-align:center}
.folder{display:flex;align-items:center;gap:9px;font-size:14px;color:var(--muted);padding:9px 11px;border:1px solid transparent;border-radius:10px;cursor:pointer;transition:.15s}
.folder:hover{background:var(--surface);color:var(--fg)}
.folder.on{background:var(--elev);color:var(--fg);border-color:var(--line-2)}
.folder.drop{border-color:var(--fg);background:var(--elev)}
.folder .fi{font-family:var(--mono);font-size:11px;color:var(--subtle)}
.newf{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--subtle);border:1px dashed var(--line);border-radius:10px;padding:8px;cursor:pointer;text-align:center}
.newf:hover{color:var(--fg);border-color:var(--line-2)}
.fx{font-family:var(--mono);font-size:11px;color:var(--subtle);opacity:0;transition:.15s;padding:0 4px}
.folder:hover .fx{opacity:1}.fx:hover{color:var(--fg)}
/* voice console overlay */
#vc{position:fixed;inset:0;z-index:20;background:radial-gradient(80% 60% at 50% 30%,#111,#060606 80%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:26px}
#vc.on{display:flex}
.bigcore{width:220px;height:220px;position:relative}
.bigcore .ring{position:absolute;border-radius:50%;border:1px solid var(--line-2)}
.bigcore .r1{inset:0}.bigcore .r2{inset:26px;border-color:var(--line)}.bigcore .r3{inset:60px;border-color:var(--line-2)}
.bigcore .arc{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 66%,rgba(244,243,241,.95) 84%,transparent 100%);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));animation:spin 8s linear infinite}
.bigcore .bdot{position:absolute;inset:0;margin:auto;width:14px;height:14px;border-radius:50%;background:var(--fg);box-shadow:0 0 40px 10px rgba(244,243,241,.4)}
body.listening .bigcore .arc{animation-duration:1.6s}
body.listening .bigcore .bdot{animation:pulse .9s infinite}
#vc-txt{font-family:var(--disp);font-size:22px;text-align:center;max-width:640px;padding:0 24px;line-height:1.4;min-height:60px}
#vc-sub{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--subtle)}
#vc-actions{display:flex;gap:12px}
.vcbtn{width:76px;height:76px;border-radius:50%;border:1px solid var(--line-2);background:var(--elev);color:var(--fg);font-size:26px;cursor:pointer;transition:.15s}
.vcbtn:hover{border-color:var(--fg);transform:translateY(-2px)}
.vcbtn.rec{background:var(--fg);color:var(--ink);border:none;animation:pulse 1.1s infinite}
#vc-x{position:absolute;top:20px;right:24px;font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
/* pomodoro focus overlay */
#pomo{position:fixed;inset:0;z-index:24;background:radial-gradient(80% 60% at 50% 32%,#111,#050505 82%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:20px}
#pomo.on{display:flex}
#pomo .bigcore{width:210px;height:210px}
#pomo.run .bigcore .arc{animation-duration:2.4s}
#pomo-timebox{display:flex;flex-direction:column;align-items:center;gap:6px}
#pomo-time{font-family:var(--mono);font-weight:600;font-size:60px;letter-spacing:.02em;line-height:1}
#pomo-label{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted)}
#pomo-ctl{display:flex;gap:10px;align-items:center}
#pomo-ctl button{font-family:var(--mono);font-size:13px;color:var(--fg);background:var(--elev);border:1px solid var(--line);border-radius:10px;padding:11px 15px;cursor:pointer;transition:.15s}
#pomo-ctl button:hover{border-color:var(--line-2)}
#pomo-toggle{width:62px!important;height:62px;border-radius:50%!important;font-size:20px!important;background:var(--fg)!important;color:var(--ink)!important;border:none!important;display:grid;place-items:center}
#pomo-toggle svg{width:24px;height:24px}
#pomo-presets{display:flex;gap:8px}
#pomo-presets button{font-family:var(--mono);font-size:11px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
#pomo-presets button:hover{color:var(--fg);border-color:var(--line-2)}
#pomo-pip{margin-top:4px;font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:999px;padding:9px 16px;cursor:pointer}
#pomo-pip:hover{color:var(--fg);border-color:var(--line-2)}
#pomo-x{position:absolute;top:20px;right:24px;font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
#login,#welcome{position:fixed;inset:0;z-index:50;background:radial-gradient(80% 60% at 50% 30%,#111,#050505 82%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:22px}
#login.on,#welcome.on{display:flex}
#login-token{background:var(--surface);border:1px solid var(--line-2);border-radius:12px;padding:13px 18px;color:var(--fg);font:inherit;font-size:15px;width:min(320px,80vw);text-align:center;outline:none}
#login-token:focus{border-color:var(--fg)}
#login-btn{min-width:170px}#login-err{font-family:var(--mono);font-size:12px;color:var(--muted);min-height:16px}
.login-or{display:flex;align-items:center;gap:10px;width:100%;max-width:230px;color:var(--muted);font-size:12px;font-family:var(--mono)}
.login-or span{flex:1;height:1px;background:var(--line)}
.login-oauth{min-width:230px;text-align:center;text-decoration:none;display:inline-flex;justify-content:center;gap:8px}
#welcome-txt{font-family:var(--disp);font-size:26px;text-align:center;max-width:600px;padding:0 24px;line-height:1.4;animation:rise .5s}
#pomo-mini{position:fixed;top:20px;right:20px;z-index:26;width:186px;background:var(--panel);border:1px solid var(--line-2);border-radius:14px;box-shadow:0 20px 60px -24px #000;display:none;flex-direction:column;overflow:hidden}
.pm-head{display:flex;align-items:center;gap:6px;padding:7px 10px;border-bottom:1px solid var(--line);cursor:move;user-select:none}
.pm-grip{color:var(--subtle);font-size:12px;letter-spacing:-3px}
.pm-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:13px;padding:2px 6px}.pm-btn:hover{color:var(--fg)}
.pm-body{padding:16px 14px;display:flex;justify-content:center;cursor:pointer}
#pomo-mini #pomo-time{font-size:36px}#pomo-mini #pomo-label{font-size:9px}
.sysbox{margin-top:auto;display:flex;flex-direction:column;gap:7px;border-top:1px solid var(--line);padding-top:12px}
.kv{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px}
.kv span{color:var(--subtle)}.kv b{font-weight:500}
.topbar{display:flex;align-items:center;gap:10px;padding:15px 22px;border-bottom:1px solid var(--line)}
.topbar .eyebrow{flex:1;margin:0}
.tbtn{font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--muted);border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:7px 12px;cursor:pointer}
.tbtn.on{color:var(--ink);background:var(--fg);border-color:var(--fg)}
.tbtn.ico{padding:7px 9px;display:inline-flex;align-items:center}.tbtn.ico svg{width:15px;height:15px}
.tbtn.ic-txt{display:inline-flex;align-items:center;gap:6px}.tbtn.ic-txt svg{width:16px;height:16px}
.tbtn.ic-txt span{display:none}  /* icon-only header buttons (minimalist, frees room for tabs) */
.icon svg{width:20px;height:20px}.mg{display:inline-flex}.vcbtn svg{width:28px;height:28px}
/* desktop-only panel hiding — must NOT apply on mobile, where the panels are
   slide-in drawers (otherwise a persisted hide-* forces display:none and the
   drawer can never open). */
@media(min-width:981px){
  body.hide-left #left{display:none}body.hide-right #right{display:none}
  body.hide-left #app{grid-template-columns:1fr 272px}
  body.hide-right #app{grid-template-columns:238px 1fr}
  body.hide-left.hide-right #app{grid-template-columns:1fr}
}
.tabs{display:flex;gap:3px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:3px;overflow-x:auto;scrollbar-width:none;min-width:0;flex:0 1 auto}
.mnav{display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;color:var(--fg);font:inherit;font-size:14px;padding:10px 12px;font-family:var(--mono);cursor:pointer}
.tabs::-webkit-scrollbar{display:none}.tab{white-space:nowrap;flex:none}
.topbar{gap:8px}
@media(max-width:1180px){.topbar #scope{display:none}}
/* Desktop/tablet keep the scrollable tab strip. Only on phones (<=760px) swap
   it for the compact picker and shrink the labelled buttons to icons. */
@media(max-width:760px){
  .tabs{display:none}
  .mnav{display:block;flex:1 1 auto;min-width:70px}
  #gsearch{display:none}
  .tbtn.ic-txt span{display:none}
  .tbtn.ic-txt{padding:9px 10px}
}
.lnk{color:var(--fg);text-decoration:underline;text-underline-offset:2px}.lnk:hover{opacity:.75}
.tab{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--muted);border:none;background:transparent;border-radius:8px;padding:7px 13px;cursor:pointer;white-space:nowrap}
.tab-edit{opacity:.5;font-size:14px;padding:6px 11px}.tab-edit:hover{opacity:1;color:var(--fg)}
.tab.on{background:var(--fg);color:var(--ink)}
#chatview{flex:1;display:flex;flex-direction:column;min-height:0}
#taskview,#kbview,#expview,#remview,#memview,#calview,#lnkview,#habview,#jouview,#subview,#orcview,#monview,#actview{flex:1;min-height:0;overflow:auto;padding:24px;display:none}
.cal-head{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:18px}
.cal-send{display:flex;gap:8px;justify-content:center;margin:-6px 0 16px;flex-wrap:wrap}
.cal-send .mbtn2{display:inline-flex;align-items:center;gap:7px}
#calgrid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;max-width:940px;margin:0 auto}
.cal-dow{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--subtle);text-align:center;padding:4px}
.cal-cell{min-height:94px;border:1px solid var(--line);border-radius:10px;padding:7px;background:var(--surface);cursor:pointer;transition:border-color .15s;overflow:hidden}
.cal-cell:hover{border-color:var(--line-2)}.cal-cell.empty{background:transparent;border:none;cursor:default}
.cal-cell.today{border-color:var(--fg)}
.cal-num{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:5px}.cal-cell.today .cal-num{color:var(--fg);font-weight:600}
.cal-ev{font-size:11px;background:var(--elev);border-radius:5px;padding:2px 5px;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;border:1px solid transparent}
.cal-ev:hover{border-color:var(--line-2);background:var(--panel)}
.cal-ev.g{border-left:2px solid var(--fg);background:var(--panel);opacity:.92}
.heat{display:flex;flex-wrap:wrap;gap:2px;margin-top:8px;max-width:340px}
.hc{width:9px;height:9px;border-radius:2px;background:var(--surface);border:1px solid var(--line)}
.hc.on{background:var(--fg);border-color:var(--fg)}
#chatview.drag{outline:2px dashed var(--line-2);outline-offset:-8px}
.cal-more{font-family:var(--mono);font-size:10px;color:var(--subtle);cursor:pointer}
.cal-more:hover{color:var(--fg)}
.kb-add{max-width:720px;display:flex;flex-direction:column;gap:14px;margin-bottom:22px}
#kb-text{min-height:84px}
#expchart{max-width:720px;margin-bottom:10px}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:7px}
.bar-lbl{width:120px;color:var(--muted);font-family:var(--mono);font-size:12px;text-align:right;flex:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{flex:1;height:10px;background:var(--surface);border-radius:6px;overflow:hidden}
.bar-fill{height:100%;background:var(--fg);border-radius:6px;transition:width .5s}
.bar-val{width:80px;font-family:var(--mono);font-size:12px;flex:none}
.tv-cat.drop{color:var(--fg);background:var(--elev);border-radius:6px}
.tv-h{font-family:var(--disp);font-weight:600;font-size:22px;margin-bottom:18px}
.tv-form{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px;max-width:720px}
.tv-form input{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:12px 15px;color:var(--fg);font:inherit;font-size:15px}
.tv-form #task-text{flex:1}.tv-form #task-cat{width:140px;flex:none;font-family:var(--mono);font-size:13px}
.tv-form input:focus{outline:none;border-color:var(--line-2)}
.tv-form select{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:12px 15px;color:var(--fg);font:inherit;font-size:13px;font-family:var(--mono);flex:none;cursor:pointer}
.tv-form select:focus{outline:none;border-color:var(--line-2)}
.tv-cat{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--subtle);margin:20px 0 9px}
.tv-row{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;background:var(--surface);max-width:720px;transition:border-color .15s}
.tv-row:hover{border-color:var(--line-2)}.tv-row .txt{flex:1;line-height:1.4}
.tv-ic{width:34px;height:34px;flex:none;display:grid;place-items:center;border-radius:9px;border:1px solid var(--line);background:var(--elev);color:var(--muted);cursor:pointer;transition:.15s}
.tv-ic:hover{color:var(--fg);border-color:var(--line-2)}.tv-ic svg{width:16px;height:16px}
.tv-empty{color:var(--subtle);font-family:var(--mono);font-size:13px;padding:8px 2px}
.tv-search{width:100%;max-width:720px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:11px 14px;color:var(--fg);font:inherit;font-size:14px;margin-bottom:14px;display:block}
.tv-search:focus{outline:none;border-color:var(--line-2)}
#log{flex:1;min-height:0;overflow-y:auto;padding:20px 22px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:82%;padding:13px 16px;line-height:1.55;border:1px solid var(--line);border-radius:16px;animation:rise .32s cubic-bezier(.2,.7,.2,1)}
.msg.you{align-self:flex-end;background:var(--fg);color:var(--ink);border:none;border-bottom-right-radius:5px;font-weight:500}
.msg.ev{align-self:flex-start;background:var(--elev);border-bottom-left-radius:5px}
.msg.sys{align-self:center;background:transparent;border:1px dashed var(--line);color:var(--muted);font-family:var(--mono);font-size:12px}
.msg p{margin:0 0 6px}.msg p:last-child{margin:0}
.msg strong{font-weight:700;color:var(--fg)}
.msg em{font-style:italic}
.msg code{font-family:var(--mono);font-size:.88em;background:var(--elev);border:1px solid var(--line);padding:1px 6px;border-radius:6px}
.msg .mdh{font-family:var(--disp);font-weight:700;font-size:14.5px;margin:8px 0 4px;display:block}
.msg .bul{display:flex;gap:8px;margin:2px 0}.msg .bul::before{content:"·";color:var(--subtle);flex:none}
.msg .sub{font-family:var(--disp);font-weight:650;font-size:12.5px;letter-spacing:.02em;margin:11px 0 3px;display:flex;align-items:center;gap:7px;color:var(--fg)}
.msg .sub:first-child{margin-top:0}
.msg .sub svg{width:15px;height:15px;color:var(--subtle);flex:none}
.msg .sep{height:1px;background:var(--line);margin:9px 0;border:none}
.mchips{display:flex;flex-wrap:wrap;gap:7px;margin:3px 0 10px}
.mchip{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:12px;color:var(--fg);background:var(--elev);border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer;position:relative;overflow:hidden;transition:background .15s,border-color .15s,color .15s}
.mchip:hover,.mchip:active{background:var(--fg);color:var(--ink);border-color:var(--fg)}
.mchip svg{width:14px;height:14px}.mchip:hover svg{color:var(--ink)}
body.term .mchip{border-radius:4px}
.nbadge{display:none;margin-left:auto;background:var(--fg);color:var(--ink);border-radius:999px;font-family:var(--mono);font-size:10px;font-weight:600;line-height:1;padding:3px 7px}
.nbadge.on{display:inline-block}
.nlist{max-height:54vh;overflow:auto;margin:6px 0 12px;display:flex;flex-direction:column;gap:7px}
.nrow{display:flex;gap:10px;align-items:flex-start;padding:10px 11px;border:1px solid var(--line);border-radius:12px;cursor:pointer;transition:border-color .15s,background .15s}
.nrow:hover{border-color:var(--line-2)}
.nrow.unread{background:var(--elev);border-color:var(--line-2)}
.nrow .nico{width:16px;height:16px;color:var(--subtle);flex:none;margin-top:2px}
.nrow.unread .nico{color:var(--fg)}
.ncont{flex:1;min-width:0}
.ntitle{font-weight:600;font-size:13px;display:flex;align-items:center;gap:7px}
.nrow.unread .ntitle::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--fg);flex:none}
.nbody{font-size:12px;color:var(--muted);margin-top:3px;white-space:pre-wrap;word-break:break-word}
.ntime{font-family:var(--mono);font-size:10px;color:var(--subtle);margin-top:5px;letter-spacing:.05em}
.nx{background:none;border:none;color:var(--subtle);cursor:pointer;padding:2px;flex:none;border-radius:6px}
.nx:hover{color:var(--fg);background:var(--line)}.nx svg{width:15px;height:15px}
body.term .msg code{background:transparent;border:none;padding:0}
body.term .msg .mdh,body.term .msg .bul,body.term .msg .sub{all:unset;display:block}
body.term .msg .sub{font-weight:700}
body.term .msg .sep{all:unset;display:block;color:var(--subtle)}body.term .msg .sep::before{content:"─────────"}
.msg .h{font-family:var(--disp);font-weight:600;font-size:15px;margin-bottom:8px;display:block}
.msg .cat{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle);margin:8px 0 4px}
.row{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:none}
.row .id{font-family:var(--mono);font-size:11px;color:var(--ink);background:var(--fg);border-radius:6px;padding:2px 7px;flex:none;margin-top:1px}
.msg.ev .row .id{color:var(--ink)}
.row .t{flex:1}.hint{color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:8px}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
.tp{display:inline-flex;gap:5px}.tp i{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:td 1.1s infinite}
.tp i:nth-child(2){animation-delay:.15s}.tp i:nth-child(3){animation-delay:.3s}
@keyframes td{0%,60%,100%{opacity:.25}30%{opacity:1}}
/* terminal mode */
body.term #log{font-family:var(--mono);font-size:13px;gap:2px;background:#060606}
body.term .msg{max-width:100%;border:none;border-radius:0;background:transparent!important;color:var(--fg);padding:2px 0;animation:none;white-space:pre-wrap}
body.term .msg.you{color:var(--fg)}body.term .msg.you::before{content:"ryan@ev ~ $ ";color:var(--muted)}
body.term .msg.ev::before{content:"» ";color:var(--subtle)}
body.term .msg .h,body.term .msg .cat,body.term .row{all:unset;display:block}
body.term .row .id{background:transparent;color:var(--muted);padding:0 6px 0 0}
form{display:flex;align-items:center;gap:10px;padding:14px 18px;border-top:1px solid var(--line);position:relative;min-width:0}
.field{flex:1;min-width:0;display:flex;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:2px 6px 2px 16px;transition:.2s}
.field:focus-within{border-color:var(--line-2);box-shadow:0 0 0 4px rgba(244,243,241,.05)}
#txt{flex:1;min-width:0;background:transparent;border:none;outline:none;color:var(--fg);font-family:var(--body);font-size:15px;padding:11px 0}
body.term #txt{font-family:var(--mono)}
body.term form{background:#060606}
body.term .field{background:#0a0a0a;border-color:#1c1c1c;border-radius:8px}
body.term .field:focus-within{border-color:#2a2a2a}
body.term #txt::placeholder{color:#4a4a4a}
.icon{width:44px;height:44px;flex:none;display:grid;place-items:center;border-radius:12px;border:1px solid var(--line);background:var(--elev);color:var(--fg);cursor:pointer;position:relative;overflow:hidden;transition:.14s}
.icon:hover{transform:translateY(-1px);border-color:var(--line-2)}.icon:active{transform:scale(.95)}
.icon.send{background:var(--fg);color:var(--ink);border:none}.icon.mic.on{background:var(--fg);color:var(--ink);border:none}
#imgprev{display:none;align-items:center;gap:12px;padding:9px 18px;border-top:1px solid var(--line);background:var(--surface)}
#imgprev img{width:48px;height:48px;object-fit:cover;border-radius:9px;border:1px solid var(--line)}
#imgprev .ip-name{flex:1;min-width:0;font-size:12px;color:var(--muted);font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#imgprev .ip-x{background:var(--elev);border:1px solid var(--line);color:var(--fg);width:30px;height:30px;flex:none;border-radius:8px;cursor:pointer;font-size:17px;line-height:1}
.msg-img{max-width:230px;max-height:230px;border-radius:11px;display:block}
#audprev{display:none;align-items:center;gap:10px;padding:9px 18px;border-top:1px solid var(--line);background:var(--surface)}
#audprev .ap-info{flex:1;min-width:0;font-size:12.5px;color:var(--muted);font-family:var(--mono)}
#audprev button{border-radius:9px;cursor:pointer;font:inherit;font-size:13px;padding:8px 12px;border:1px solid var(--line);background:var(--elev);color:var(--fg)}
#audprev .ap-send{background:var(--fg);color:var(--ink);border:none;font-weight:600}
.wave{display:none;align-items:flex-end;gap:2px;height:16px}.icon.mic.on .mg{display:none}.icon.mic.on .wave{display:flex}
.wave b{width:2.5px;height:5px;background:var(--ink);border-radius:2px;animation:wv .9s infinite}
.wave b:nth-child(2){animation-delay:.12s}.wave b:nth-child(3){animation-delay:.24s}.wave b:nth-child(4){animation-delay:.36s}
@keyframes wv{50%{height:15px}}
.ripple{position:absolute;border-radius:50%;background:rgba(244,243,241,.3);transform:scale(0);animation:rp .5s ease-out;pointer-events:none}
.icon.send .ripple{background:rgba(10,10,10,.25)}@keyframes rp{to{transform:scale(2.4);opacity:0}}
/* slash menu */
#slash{position:absolute;left:78px;right:78px;bottom:66px;max-height:264px;overflow:auto;background:var(--panel);border:1px solid var(--line-2);border-radius:14px;box-shadow:0 20px 60px -24px #000;display:none;z-index:5}
#slash .s{display:flex;gap:12px;align-items:baseline;padding:9px 14px;cursor:pointer;border-top:1px solid var(--line)}
#slash .s:first-child{border-top:none}#slash .s.sel,#slash .s:hover{background:var(--elev)}
#slash .c{font-family:var(--mono);font-size:13px;color:var(--fg);min-width:120px}
#slash .d{font-size:12px;color:var(--muted)}
.stat{display:flex;align-items:baseline;justify-content:space-between;padding:11px 13px;border:1px solid var(--line);border-radius:12px;background:var(--surface);cursor:pointer;transition:.2s}
.stat:hover{border-color:var(--line-2);background:var(--elev)}.stat .lbl{font-size:13px;color:var(--muted)}
.stat .num{font-family:var(--mono);font-weight:600;font-size:18px}
[data-lucide],svg.lucide{width:16px;height:16px;stroke-width:1.75;vertical-align:-3px;flex:none}
.stat .lbl{display:flex;align-items:center;gap:9px}.stat .lbl svg{width:17px;height:17px;color:var(--muted)}
.act{display:flex;align-items:center;gap:8px}.act svg{width:16px;height:16px;color:var(--muted)}
.msg .h svg{width:19px;height:19px;vertical-align:-4px;margin-right:8px;color:var(--fg)}
.row .id svg,.hint svg{width:13px;height:13px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.act{font-size:13px;color:var(--fg);border:1px solid var(--line);background:var(--surface);border-radius:11px;padding:11px 10px;cursor:pointer;text-align:left;transition:.15s}
.act:hover{border-color:var(--line-2);transform:translateY(-1px);background:var(--elev)}
select{width:100%;font-family:var(--mono);font-size:12px;background:var(--surface);color:var(--fg);border:1px solid var(--line);border-radius:11px;padding:10px}
.eyebrow .mini{font-family:var(--mono);font-size:9px;letter-spacing:.1em;color:var(--subtle);cursor:pointer;float:right;border:1px solid var(--line);border-radius:6px;padding:2px 7px;text-transform:none}
.mini:hover{color:var(--fg);border-color:var(--line-2)}
.row .t div{padding:1px 0}
#modal{position:fixed;inset:0;z-index:30;background:rgba(4,4,4,.72);display:none;align-items:center;justify-content:center}
#modal.on{display:flex}
.mcard{width:min(420px,92vw);max-height:80vh;overflow:auto;background:var(--panel);border:1px solid var(--line-2);border-radius:16px;padding:18px}
.mtitle{font-family:var(--disp);font-weight:600;font-size:16px;margin-bottom:6px}.mtitle small{display:block;font-family:var(--body);font-weight:400;font-size:12px;color:var(--muted);margin-top:3px}
.mconf{font-size:14px;color:var(--fg);line-height:1.5;margin:2px 0 4px}
.mrow{display:flex;align-items:center;gap:10px;padding:9px 6px;border-top:1px solid var(--line);cursor:pointer;font-size:14px}
.mrow input{width:16px;height:16px;accent-color:var(--fg)}
.mfield{margin-bottom:13px}.mlabel{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}
.minput{width:100%;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:11px 13px;color:var(--fg);font:inherit;font-size:14px}
.minput:focus{outline:none;border-color:var(--line-2)}
select.minput{cursor:pointer}
textarea.minput{resize:vertical;min-height:74px;font-family:var(--body);line-height:1.45}
.mbar{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.mbtn{background:var(--fg);color:var(--ink);border:none;border-radius:10px;padding:9px 16px;cursor:pointer;font-weight:500}
.mbtn2{background:var(--surface);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:9px 16px;cursor:pointer}
#cmdk{position:fixed;inset:0;z-index:40;background:rgba(4,4,4,.6);display:none;align-items:flex-start;justify-content:center;padding-top:12vh}
#cmdk.on{display:flex}
.ck-card{width:min(560px,92vw);background:var(--panel);border:1px solid var(--line-2);border-radius:16px;box-shadow:0 30px 80px -30px #000;overflow:hidden}
#ck-input{width:100%;background:transparent;border:none;border-bottom:1px solid var(--line);color:var(--fg);font:inherit;font-size:16px;padding:16px 18px;outline:none}
#ck-list{max-height:52vh;overflow:auto}
.ck-item{display:flex;gap:12px;align-items:center;padding:11px 18px;cursor:pointer;font-size:14px;border-top:1px solid var(--line)}
.ck-item:first-child{border-top:none}.ck-item.sel,.ck-item:hover{background:var(--elev)}
.ck-item .ck-k{font-family:var(--mono);font-size:12px;color:var(--muted);min-width:104px}
.ck-item .ck-d{color:var(--subtle);font-size:12px;margin-left:auto}
#mbackdrop{display:none}
@media(max-width:980px){
  #app{grid-template-columns:1fr!important}
  #left,#right{position:fixed;top:0;bottom:0;width:min(86vw,320px);z-index:60;background:var(--ink);overflow:auto;transition:transform .25s ease}
  #left{left:0;transform:translateX(-106%);border-right:1px solid var(--line)}
  #right{right:0;transform:translateX(106%);border-left:1px solid var(--line)}
  body.m-left #left,body.m-right #right{transform:translateX(0);box-shadow:0 0 60px rgba(0,0,0,.7)}
  body.m-left #mbackdrop,body.m-right #mbackdrop{display:block;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:55}
  .topbar{padding:11px 12px;gap:5px}
  #slash{left:14px;right:14px}
  #taskview,#kbview,#expview,#remview,#memview,#calview,#lnkview,#habview,#jouview,#subview,#orcview,#monview,#actview{padding:16px 14px}
  #log{padding:14px 14px}
  .msg{max-width:92%!important}
  #calgrid{gap:3px}.cal-cell{min-height:62px;padding:4px}
}
@media(max-width:520px){
  .topbar{padding:9px 10px;gap:5px}
  .tab{padding:6px 10px;font-size:10px}
  .icon{width:40px;height:40px}
  .tv-h{font-size:19px}
  .cal-ev{font-size:10px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
<div id="app">
  <aside id="left" class="rail">
    <div class="brand"><div class="name">E.V.</div><div class="eyebrow">Personal Intelligence</div></div>
    <div class="core"><div class="ring a"></div><div class="ring b"></div><div class="ring c"></div><div class="arc"></div><div class="arc two"></div><div class="dot"></div></div>
    <div class="state" id="state">em espera</div>
    <div class="eyebrow">Conversas</div>
    <div id="folders"></div>
    <div class="newf" id="newf">+ nova pasta</div>
    <div class="sysbox">
      <div class="kv"><span>PROVEDOR</span><b id="s-prov">—</b></div>
      <div class="kv"><span>MODELO</span><b id="s-model">—</b></div>
      <div class="kv"><span>HORA</span><b id="s-clock">—</b></div>
    </div>
  </aside>
  <main id="center">
    <div class="topbar">
      <button class="tbtn ico" id="tgl-left" title="Ocultar/mostrar pastas"><i data-lucide="panel-left"></i></button>
      <div class="tabs" id="tabs"></div>
      <select id="mnav" class="mnav" title="Ir para"><option value="chat">Conversa</option><option value="tasks">Tarefas</option><option value="exp">Gastos</option><option value="rem">Lembretes</option><option value="cal">Agenda</option><option value="mem">Memórias</option><option value="lnk">Links</option><option value="hab">Hábitos</option><option value="jou">Diário</option><option value="sub">Assinaturas</option><option value="orc">Orçamentos</option><option value="mon">Monitores</option><option value="act">Histórico</option><option value="kb">Base</option></select>
      <span class="eyebrow" id="scope">geral</span>
      <button class="tbtn ico" id="gsearch" title="Buscar em tudo"><i data-lucide="search"></i></button>
      <button class="tbtn ic-txt" id="vcopen" title="Falar"><i data-lucide="mic"></i><span>FALAR</span></button>
      <button class="tbtn ic-txt" id="term" title="Modo terminal"><i data-lucide="square-terminal"></i><span>TERMINAL</span></button>
      <button class="tbtn ic-txt on" id="voz" title="Voz da E.V."><i data-lucide="volume-2"></i><span>VOZ</span></button>
      <button class="tbtn ico" id="tgl-right" title="Ocultar/mostrar painel"><i data-lucide="panel-right"></i></button></div>
    <div id="chatview">
      <div id="log"></div>
      <div id="audprev"></div>
      <div id="imgprev"></div>
      <form id="f"><div id="slash"></div>
        <button type="button" class="icon mic" id="mic" title="Falar"><span class="mg"><i data-lucide="mic"></i></span><span class="wave"><b></b><b></b><b></b><b></b></span></button>
        <button type="button" class="icon" id="imgbtn" title="Enviar imagem"><i data-lucide="image"></i></button>
        <input type="file" id="imgfile" accept="image/*" style="display:none">
        <div class="field"><input id="txt" placeholder="Fala com a E.V.  ·  digite / para comandos" autocomplete="off"></div>
        <button class="icon send" id="send" title="Enviar"><i data-lucide="arrow-up"></i></button></form>
    </div>
    <div id="taskview">
      <div class="tv-h">Tarefas</div>
      <form id="taskform" class="tv-form">
        <input id="task-text" placeholder="Nova tarefa..." autocomplete="off">
        <input id="task-cat" placeholder="categoria" value="geral" autocomplete="off">
        <input id="task-due" type="datetime-local" title="Vencimento (opcional)" style="flex:none">
        <select id="task-recur" title="Repetir"><option value="">Uma vez</option><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option></select>
        <button class="mbtn" type="submit">Adicionar</button>
      </form>
      <input class="tv-search" id="tasks-search" placeholder="Buscar tarefas..." autocomplete="off">
      <div id="tasklist"></div>
    </div>
    <div id="kbview">
      <div class="tv-h">Base de conhecimento</div>
      <div class="kb-add">
        <form id="kb-urlf" class="tv-form"><input id="kb-url" placeholder="https://...  (indexar uma página)"><button class="mbtn" type="submit">Indexar URL</button></form>
        <div class="tv-form" style="align-items:center"><label class="mbtn2" for="kb-file" style="cursor:pointer">⭱ Enviar arquivo (PDF / Word / txt)</label><input id="kb-file" type="file" accept=".pdf,.docx,.txt,.md" style="display:none"><span id="kb-fmsg" class="tv-empty"></span></div>
        <form id="kb-textf"><input id="kb-title" class="minput" placeholder="Título da nota" style="margin-bottom:8px"><textarea id="kb-text" class="minput" placeholder="Cole um texto pra E.V. aprender e responder com base nele..."></textarea><button class="mbtn" type="submit" style="margin-top:8px">Adicionar texto</button></form>
      </div>
      <input class="tv-search" id="kb-search" placeholder="Buscar na base..." autocomplete="off">
      <div class="tv-cat">Documentos indexados</div>
      <div id="kblist"></div>
    </div>
    <div id="expview">
      <div class="tv-h">Gastos</div>
      <form id="expform" class="tv-form"><input id="exp-amt" placeholder="Valor" style="width:110px;flex:none"><input id="exp-desc" placeholder="Descrição"><input id="exp-cat" placeholder="categoria" value="geral" style="width:140px;flex:none"><button class="mbtn" type="submit">Registrar</button></form>
      <div id="expchart"></div>
      <input class="tv-search" id="exp-search" placeholder="Buscar gastos..." autocomplete="off">
      <div class="tv-cat">Últimos 60 dias</div>
      <div id="explist"></div>
    </div>
    <div id="remview">
      <div class="tv-h">Lembretes</div>
      <form id="remform" class="tv-form"><input id="rem-text" placeholder="Lembrar de..."><input id="rem-when" type="datetime-local" style="flex:none"><select id="rem-recur" title="Repetir"><option value="">Uma vez</option><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option></select><button class="mbtn" type="submit">Criar</button></form>
      <input class="tv-search" id="rem-search" placeholder="Buscar lembretes..." autocomplete="off">
      <div class="tv-cat">Em aberto</div>
      <div id="remlist"></div>
    </div>
    <div id="calview">
      <div class="cal-head"><button class="tbtn" id="cal-prev">‹</button><div class="tv-h" id="cal-title" style="margin:0;min-width:200px;text-align:center"></div><button class="tbtn" id="cal-next">›</button></div>
      <div class="cal-send"><button class="mbtn2" id="cal-email">Enviar email</button><button class="mbtn2" id="cal-msg">Mensagem no Telegram</button></div>
      <div id="calgrid"></div>
    </div>
    <div id="memview">
      <div class="tv-h">Memórias</div>
      <form id="memform" class="tv-form"><input id="mem-text" placeholder="Algo que a E.V. deve lembrar sobre você..."><button class="mbtn" type="submit">Salvar</button></form>
      <input class="tv-search" id="mem-search" placeholder="Buscar memórias..." autocomplete="off">
      <div class="tv-cat">O que a E.V. sabe</div>
      <div id="memlist"></div>
    </div>
    <div id="lnkview">
      <div class="tv-h">Links</div>
      <form id="lnkform" class="tv-form"><input id="lnk-name" placeholder="Nome"><input id="lnk-url" placeholder="https://..."><input id="lnk-cat" placeholder="categoria" value="geral" style="width:150px;flex:none"><button class="mbtn" type="submit">Salvar</button></form>
      <input class="tv-search" id="lnk-search" placeholder="Buscar links..." autocomplete="off">
      <div id="lnklist"></div>
    </div>
    <div id="habview">
      <div class="tv-h">Hábitos</div>
      <form id="habform" class="tv-form"><input id="hab-name" placeholder="Novo hábito (ex: treino)"><button class="mbtn" type="submit">Criar</button></form>
      <input class="tv-search" id="hab-search" placeholder="Buscar hábitos..." autocomplete="off">
      <div id="hablist"></div>
    </div>
    <div id="jouview">
      <div class="tv-h">Diário</div>
      <form id="jouform" class="tv-form"><input id="jou-text" placeholder="Como foi seu dia?"><button class="mbtn" type="submit">Registrar</button></form>
      <input class="tv-search" id="jou-search" placeholder="Buscar no diário..." autocomplete="off">
      <div id="joulist"></div>
    </div>
    <div id="subview">
      <div class="tv-h">Assinaturas</div>
      <form id="subform" class="tv-form"><input id="sub-amt" placeholder="Valor" style="width:100px;flex:none"><input id="sub-desc" placeholder="Ex: Netflix"><input id="sub-day" type="number" min="1" max="28" value="1" title="dia do mês" style="width:70px;flex:none"><button class="mbtn" type="submit">Salvar</button></form>
      <input class="tv-search" id="sub-search" placeholder="Buscar assinaturas..." autocomplete="off">
      <div id="sublist"></div>
    </div>
    <div id="orcview">
      <div class="tv-h">Orçamentos</div>
      <form id="orcform" class="tv-form"><input id="orc-cat" placeholder="Categoria (ex: comida)"><input id="orc-amt" placeholder="Limite/mês" style="width:130px;flex:none"><button class="mbtn" type="submit">Definir</button></form>
      <input class="tv-search" id="orc-search" placeholder="Buscar orçamentos..." autocomplete="off">
      <div id="orclist"></div>
    </div>
    <div id="monview">
      <div class="tv-h">Monitores web</div>
      <form id="monform" class="tv-form"><input id="mon-url" placeholder="https://... (página a vigiar)"><input id="mon-kw" placeholder="palavra (opcional)" style="width:160px;flex:none"><button class="mbtn" type="submit">Vigiar</button></form>
      <input class="tv-search" id="mon-search" placeholder="Buscar monitores..." autocomplete="off">
      <div id="monlist"></div>
    </div>
    <div id="actview">
      <div class="tv-h">Histórico de atividade</div>
      <div class="tv-form" style="align-items:center">
        <select id="act-cat" class="tv-search" style="max-width:260px"><option value="">Todas as categorias</option></select>
      </div>
      <input class="tv-search" id="act-search" placeholder="Buscar no histórico..." autocomplete="off">
      <div id="actlist"></div>
    </div>
  </main>
  <aside id="right" class="rail">
    <div class="eyebrow">Sistema <span class="mini" id="edit-stats">editar</span></div>
    <div id="stats"></div>
    <div class="eyebrow">Ações rápidas <span class="mini" id="edit-acts">editar</span></div>
    <div class="grid2" id="acts"></div>
    <div class="eyebrow">Provedor de IA</div>
    <select id="prov"><option>auto</option><option>gemini</option><option>groq</option><option>openrouter</option><option>ollama</option></select>
    <button class="act" id="btn-keys" style="margin-top:12px;width:100%"><i data-lucide="key-round"></i>Chaves de API</button>
    <button class="act" id="btn-notifs" style="margin-top:8px;width:100%"><i data-lucide="bell"></i>Notificações<span id="notif-badge" class="nbadge"></span></button>
  </aside>
</div>
<div id="mbackdrop"></div>
<div id="vc">
  <button id="vc-x">FECHAR</button>
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="vc-txt">Toque no microfone e fale.</div>
  <div id="vc-sub">voz ao vivo · português</div>
  <div id="vc-actions"><button class="vcbtn" id="vc-mic"><i data-lucide="mic"></i></button></div>
  <button id="vc-cont" class="tbtn" style="margin-top:14px"><i data-lucide="infinity"></i> Modo contínuo: off</button>
</div>
<div id="pomo">
  <button id="pomo-x">FECHAR</button>
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="pomo-timebox"><div id="pomo-time">25:00</div><div id="pomo-label">Foco</div></div>
  <div id="pomo-ctl"><button data-m="-5">−5</button><button id="pomo-toggle"><i data-lucide="play"></i></button><button data-m="5">+5</button><button id="pomo-reset">reset</button></div>
  <div id="pomo-presets"><button data-set="15">15 min</button><button data-set="25">25 min</button><button data-set="50">50 min</button></div>
  <button id="pomo-pip">⧉ minimizar</button>
</div>
<div id="pomo-mini">
  <div class="pm-head"><span class="pm-grip">⋮⋮</span><span style="flex:1"></span><button class="pm-btn" id="pm-open" title="expandir">⤢</button><button class="pm-btn" id="pm-close" title="fechar">✕</button></div>
  <div class="pm-body"></div>
</div>
<div id="modal"></div>
<div id="cmdk"><div class="ck-card"><input id="ck-input" placeholder="Buscar ação ou comando...  (Esc pra fechar)" autocomplete="off"><div id="ck-list"></div></div></div>
<div id="login">
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div class="brand" style="text-align:center"><div class="name" style="font-size:38px">E.V.</div><div class="eyebrow">Personal Intelligence</div></div>
  <input id="login-token" type="password" placeholder="Token de acesso" autocomplete="off">
  <button id="login-btn" class="mbtn">Entrar</button>
  <div class="login-or"><span></span>ou<span></span></div>
  <a id="login-google" class="mbtn2 login-oauth" href="/auth/google">Entrar com Google</a>
  <a id="login-github" class="mbtn2 login-oauth" href="/auth/github">Entrar com GitHub</a>
  <div id="login-err"></div>
</div>
<div id="welcome">
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="welcome-txt"></div>
</div>
<script>
let token=localStorage.getItem('ev_token')||'';
let voiceOn=localStorage.getItem('ev_voice')!=='off';
let thread=localStorage.getItem('ev_thread')||'geral';
let COMMANDS=[];
const H=()=>({'Content-Type':'application/json','Authorization':'Bearer '+token});
const $=s=>document.querySelector(s), log=$('#log'), txt=$('#txt'), f=$('#f'), micBtn=$('#mic'),
  vozBtn=$('#voz'), termBtn=$('#term'), stateEl=$('#state'), slash=$('#slash'), scopeEl=$('#scope');
function setState(s){document.body.classList.remove('listening','thinking');if(s)document.body.classList.add(s);
  stateEl.textContent=s==='listening'?'ouvindo':s==='thinking'?'processando':'em espera';}
vozBtn.classList.toggle('on',voiceOn);
vozBtn.onclick=()=>{voiceOn=!voiceOn;localStorage.setItem('ev_voice',voiceOn?'on':'off');vozBtn.classList.toggle('on',voiceOn);};
termBtn.onclick=()=>{document.body.classList.toggle('term');termBtn.classList.toggle('on',document.body.classList.contains('term'));};
// hide/show side panels (focus mode), persisted
function mob(){return window.matchMedia('(max-width:980px)').matches;}
if(localStorage.getItem('ev_hl'))document.body.classList.add('hide-left');
if(localStorage.getItem('ev_hr'))document.body.classList.add('hide-right');
$('#tgl-left').onclick=()=>{if(mob()){document.body.classList.remove('m-right');document.body.classList.toggle('m-left');return;}document.body.classList.toggle('hide-left');localStorage.setItem('ev_hl',document.body.classList.contains('hide-left')?'1':'');$('#tgl-left').classList.toggle('on',document.body.classList.contains('hide-left'));};
$('#tgl-right').onclick=()=>{if(mob()){document.body.classList.remove('m-left');document.body.classList.toggle('m-right');return;}document.body.classList.toggle('hide-right');localStorage.setItem('ev_hr',document.body.classList.contains('hide-right')?'1':'');$('#tgl-right').classList.toggle('on',document.body.classList.contains('hide-right'));};
$('#tgl-left').classList.toggle('on',document.body.classList.contains('hide-left'));$('#tgl-right').classList.toggle('on',document.body.classList.contains('hide-right'));
$('#mbackdrop').onclick=()=>document.body.classList.remove('m-left','m-right');
// mobile: open/close the side panels by swiping from the screen edges
(function(){let sx=0,sy=0,edge=0,track=false;
  addEventListener('touchstart',e=>{if(!mob()||e.touches.length!==1)return;const t=e.touches[0];sx=t.clientX;sy=t.clientY;
    const open=document.body.classList.contains('m-left')||document.body.classList.contains('m-right');
    edge = sx<30?1 : sx>innerWidth-30?-1 : open?9 : 0; track=edge!==0;},{passive:true});
  addEventListener('touchend',e=>{if(!track)return;track=false;const t=e.changedTouches[0];const dx=t.clientX-sx,dy=t.clientY-sy;
    if(Math.abs(dx)<45||Math.abs(dy)>Math.abs(dx))return;   // needs a clear horizontal swipe
    const cl=document.body.classList;
    if(cl.contains('m-left')||cl.contains('m-right')){if((cl.contains('m-left')&&dx<0)||(cl.contains('m-right')&&dx>0))cl.remove('m-left','m-right');return;}
    if(edge===1&&dx>0){cl.remove('m-right');cl.add('m-left');}
    else if(edge===-1&&dx<0){cl.remove('m-left');cl.add('m-right');}
  },{passive:true});})();

function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;}
const HASEMO=/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{2300}-\u{23FF}\u{20E3}]/u;
// a line that LEADS with a pictographic emoji is a section header (excludes arrows/tech symbols)
const EMOLEAD=/^\s*[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{20E3}]/u;
const SEPRE=/^[─-╿=_·—–-]{3,}$/;
const EMOG=/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{2300}-\u{23FF}️‍\u{20E3}]/gu;
const IC={'📋':'list-checks','📝':'file-pen','✅':'check-circle-2','⏰':'alarm-clock','💰':'wallet','🧠':'brain','📄':'file-text','📰':'newspaper','☀':'sun','🌧':'cloud-rain','🩺':'activity','🔎':'search','📊':'bar-chart-3','📚':'book-open','🍅':'timer','⚠':'triangle-alert','🔕':'bell-off','🔔':'bell','🗄':'database','📅':'calendar-days','🔗':'link','📌':'pin','🌐':'globe','🎧':'headphones','📥':'download','🧽':'eraser','🧹':'trash-2','🔀':'shuffle','▶':'play','⏸':'pause','⏹':'square','💧':'droplet','🕷':'sparkles','🗓':'calendar-clock','📔':'notebook-pen','☕':'coffee'};
function stripEmoji(s){return s.replace(EMOG,'').replace(/\s{2,}/g,' ').trim();}
function iconName(s){for(const ch of s){if(IC[ch])return IC[ch];}return 'sparkles';}
function ficon(n){const i=document.createElement('i');i.setAttribute('data-lucide',n);return i;}
const URLRE=/(https?:\/\/[^\s)]+)/g;
function appendLinked(parent,text){let last=0,m;URLRE.lastIndex=0;while((m=URLRE.exec(text))){if(m.index>last)parent.appendChild(document.createTextNode(text.slice(last,m.index)));
  const a=document.createElement('a');a.href=m[0];a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=m[0];parent.appendChild(a);last=m.index+m[0].length;}
  if(last<text.length)parent.appendChild(document.createTextNode(text.slice(last)));}
// inline markdown: **bold**, *italic*, `code`, and links — so /menu & voice replies
// render formatted instead of showing raw ** and * characters.
const MDRE=/\*\*([^*]+)\*\*|`([^`]+)`|\*([^*\n]+)\*|(https?:\/\/[^\s)]+)/g;
function appendRich(parent,text){let last=0,m;MDRE.lastIndex=0;
  while((m=MDRE.exec(text))){if(m.index>last)parent.appendChild(document.createTextNode(text.slice(last,m.index)));
    if(m[1]!=null)parent.appendChild(el('strong',null,m[1]));
    else if(m[2]!=null)parent.appendChild(el('code',null,m[2]));
    else if(m[3]!=null)parent.appendChild(el('em',null,m[3]));
    else{const a=document.createElement('a');a.href=m[4];a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=m[4];parent.appendChild(a);}
    last=m.index+m[0].length;}
  if(last<text.length)parent.appendChild(document.createTextNode(text.slice(last)));}
// structured, monochrome rendering with Lucide icons (no emoji read-out)
function renderReply(box,text){box.textContent='';const lines=(text||'').split('\n');let first=true;
  lines.forEach(ln=>{const s=ln.trim();if(!s)return;let m;
    if(SEPRE.test(s)){box.appendChild(el('div','sep'));return;}
    if(EMOLEAD.test(s)){
      if(first){const h=el('span','h');h.appendChild(ficon(iconName(s)));h.appendChild(document.createTextNode(stripEmoji(s)));box.appendChild(h);first=false;return;}
      const sub=el('div','sub');sub.appendChild(ficon(iconName(s)));const sp=el('span','');appendRich(sp,stripEmoji(s));sub.appendChild(sp);box.appendChild(sub);return;}
    if((m=s.match(/^\[(.+)\]$/))){box.appendChild(el('div','cat',m[1]));return;}
    if((m=s.match(/^#{1,6}\s+(.+)$/))){const h=el('div','mdh');appendRich(h,stripEmoji(m[1]).replace(/\*+/g,''));box.appendChild(h);first=false;return;}
    if((m=s.match(/^[-*•]\s+(.+)$/))){const b=el('div','bul');const sp=el('span','');appendRich(sp,stripEmoji(m[1]));b.appendChild(sp);box.appendChild(b);first=false;return;}
    if((m=s.match(/^#(\w+)\s+(.*)$/))){const r=el('div','row');r.appendChild(el('span','id','#'+m[1]));
      const t=el('span','t');const tt=stripEmoji(m[2]);const parts=tt.split(/\s+(?=\d+[.)]\s)/);
      if(parts.length>1)parts.forEach(p=>{const dv=el('div','');appendRich(dv,p);t.appendChild(dv);});else appendRich(t,tt);
      r.appendChild(t);box.appendChild(r);return;}
    if(/^(Concluir|Cancelar|Uso|Remover|Apagar):/i.test(s)||s.startsWith('/')){const hh=el('div','hint');appendRich(hh,stripEmoji(s));box.appendChild(hh);return;}
    const pp=el('p','');appendRich(pp,stripEmoji(s));box.appendChild(pp);first=false;});
  window.lucide&&lucide.createIcons();
}
function you(t){const d=el('div','msg you',t);log.appendChild(d);log.scrollTop=log.scrollHeight;}
function ev(t){const d=el('div','msg ev');renderReply(d,t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function sys(t){const d=el('div','msg sys',t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function thinking(){const d=el('div','msg ev');d.innerHTML='<span class="tp"><i></i><i></i><i></i></span>';log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ripple(b,e){const r=el('span','ripple');const q=b.getBoundingClientRect(),s=Math.max(q.width,q.height);
  r.style.width=r.style.height=s+'px';r.style.left=((e?e.clientX:q.left+q.width/2)-q.left-s/2)+'px';
  r.style.top=((e?e.clientY:q.top+q.height/2)-q.top-s/2)+'px';b.appendChild(r);setTimeout(()=>r.remove(),500);}
let _audio=null,_audioMsg=false;
function unlockAudio(){if(!_audio)_audio=new Audio();try{_audio.play().catch(()=>{});}catch(e){}}
window.addEventListener('pointerdown',unlockAudio,{once:true});
async function speak(t,force){if((!voiceOn&&!force)||!t)return;try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text:t})});if(!r.ok)return;const url=URL.createObjectURL(await r.blob());if(!_audio)_audio=new Audio();_audio.src=url;await _audio.play().catch(()=>{if(!_audioMsg){_audioMsg=true;sys('O navegador bloqueou o áudio automático. Toque uma vez na tela e a E.V. volta a falar.');}});}catch(e){}}

async function send(msg){if(!msg)return;you(msg);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/chat/stream',{method:'POST',headers:H(),body:JSON.stringify({message:msg,thread})});
    if(r.status===401){p.remove();sys('Token inválido — recarregue e informe o token certo.');localStorage.removeItem('ev_token');return;}
    p.remove();
    if(!r.body){const t=await r.text();ev(t);speak(t);loadPanel();return;}          // fallback: no streaming
    const bubble=ev('');const reader=r.body.getReader();const dec=new TextDecoder();let full='';
    while(true){const{done,value}=await reader.read();if(done)break;full+=dec.decode(value,{stream:true});renderReply(bubble,full);log.scrollTop=log.scrollHeight;}
    speak(full);loadPanel();
  }catch(e){p.remove();sys('Sem conexão com a E.V. — '+e);}finally{setState();}}
// interactive /menu — tappable chips grouped by area (like the Telegram button menu)
const MENU=[
  {h:'Ver',gi:'eye',items:[
    {c:'/tarefas',l:'Tarefas',i:'list-checks'},{c:'/lembretes',l:'Lembretes',i:'alarm-clock'},
    {c:'/gastos',l:'Gastos',i:'wallet'},{c:'/calendario',l:'Agenda',i:'calendar'},
    {c:'/habitos',l:'Hábitos',i:'repeat'},{c:'/diario',l:'Diário',i:'notebook-pen'},
    {c:'/memorias',l:'Memórias',i:'brain'},{c:'/links',l:'Links',i:'link'},
    {c:'/relatorio',l:'Relatório',i:'bar-chart-3'},{c:'/semana',l:'Semana',i:'calendar-days'},
    {c:'/emails',l:'E-mails',i:'mail'},
    {c:'/status',l:'Status',i:'activity'},{c:'/dados',l:'Meus dados',i:'database'}]},
  {h:'Criar',gi:'plus-circle',items:[
    {c:'/tarefa',l:'Tarefa',i:'plus',fill:1},{c:'/lembrete',l:'Lembrete',i:'alarm-clock',fill:1},
    {c:'/gasto',l:'Gasto',i:'wallet',fill:1},{c:'/evento',l:'Evento',i:'calendar-plus',fill:1},
    {c:'/email',l:'E-mail',i:'mail',fill:1},{c:'/link',l:'Link',i:'link',fill:1},
    {c:'/kb',l:'Nota na base',i:'book-open',fill:1}]},
  {h:'Ferramentas',gi:'wand-2',items:[
    {c:'/foco',l:'Pomodoro',i:'timer',pomo:1},{c:'/buscar',l:'Buscar web',i:'search',fill:1},
    {c:'/procurar',l:'Procurar',i:'file-search',fill:1},{c:'/resumir',l:'Resumir link',i:'link',fill:1},
    {c:'/noticias',l:'Notícias',i:'newspaper'},{c:'/clima',l:'Clima',i:'cloud-sun',fill:1},
    {c:'/quiz',l:'Quiz',i:'graduation-cap'}]},
  {h:'Ajustes',gi:'settings',items:[
    {c:'/provedor',l:'Provedor',i:'server',fill:1},{c:'/modelo',l:'Modelo',i:'cpu'},
    {c:'/silenciar',l:'Silenciar',i:'bell-off',fill:1},{c:'/ajuda',l:'Ajuda',i:'help-circle'}]},
];
function showMenu(){const d=el('div','msg ev');
  const h=el('span','h');h.appendChild(ficon('layout-grid'));h.appendChild(document.createTextNode('Menu — toque para abrir ou preencher'));d.appendChild(h);
  MENU.forEach(g=>{const sub=el('div','sub');sub.appendChild(ficon(g.gi));const sp=el('span','');sp.textContent=g.h;sub.appendChild(sp);d.appendChild(sub);
    const wrap=el('div','mchips');
    g.items.forEach(it=>{const b=el('button','mchip');b.type='button';b.appendChild(ficon(it.i));b.appendChild(document.createTextNode(it.l));
      b.onclick=(ev)=>{if(it.fill){ripple(b,ev);txt.value=it.c+' ';txt.focus();return;}
        if(it.pomo){ripple(b,ev);openPomo();return;}
        runCmd(it.c,b,ev);};
      wrap.appendChild(b);});
    d.appendChild(wrap);});
  log.appendChild(d);log.scrollTop=log.scrollHeight;window.lucide&&lucide.createIcons();}
async function runCmd(cmd,btn,e){const nm=cmd.trim().replace(/^\//,'').split(/\s+/)[0].toLowerCase();
  if(nm==='menu'){if(btn)ripple(btn,e);showMenu();return;}
  if(nm==='foco'){if(btn)ripple(btn,e);const n=cmd.match(/\d+/g)||[];openPomo(parseInt(n[0])||25,parseInt(n[1])||5);return;}
  if(btn)ripple(btn,e);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/cmd',{method:'POST',headers:H(),body:JSON.stringify({command:cmd,thread})});
    const j=await r.json();
    if(/^\/?limpar(chat)?\b/.test(cmd.trim())){log.textContent='';sys(j.reply);}
    else{p.remove();ev(j.reply);}
    loadPanel();}catch(err){p.remove();sys('Erro — '+err);}finally{setState();}}
f.onsubmit=e=>{e.preventDefault();if(slash.style.display==='block'&&slSel>=0){pickSlash();return;}
  ripple($('#send'));const m=txt.value.trim();
  if(_pendingImg){const img=_pendingImg;setPendingImg(null);txt.value='';hideSlash();sendImage(img,m);return;}
  txt.value='';hideSlash();if(!m)return;
  if(m.startsWith('/'))runCmd(m.slice(1));else send(m);};

const CAT={tarefas:['Tarefas','list-checks'],lembretes:['Lembretes','alarm-clock'],gastos:['Gastos','wallet'],memorias:['Memórias','brain'],kb:['Base','book-open'],buscar:['Buscar web','search'],noticias:['Notícias','newspaper'],clima:['Clima','cloud-sun'],relatorio:['Relatório','bar-chart-3'],status:['Status','activity'],semana:['Semana','calendar-days'],foco:['Pomodoro','timer'],procurar:['Procurar','file-search'],calendario:['Agenda','calendar'],habitos:['Hábitos','repeat'],diario:['Diário','notebook-pen'],orcamentos:['Orçamentos','piggy-bank'],assinaturas:['Assinaturas','credit-card'],dados:['Meus dados','database'],insights:['Insights','sparkles'],quiz:['Quiz','graduation-cap']};
const SM={tasks:['Tarefas','list-checks','tarefas'],reminders:['Lembretes','alarm-clock','lembretes'],expenses:['Gastos · mês','wallet','gastos'],memories:['Memórias','brain','memorias'],kb:['Base','book-open','kb'],kbfiles:['Arquivos','file-text','kb'],links:['Links','link','links'],habits:['Hábitos','repeat','habitos'],journal:['Diário','notebook-pen','diario'],subscriptions:['Assinaturas','credit-card','assinaturas'],budgets:['Orçamentos','piggy-bank','orcamentos'],watches:['Monitores','radar','monitores'],agenda:['Agenda · 7d','calendar','calendario'],activity:['Histórico · 24h','history','status'],provider:['Provedor','cpu','status'],model:['Modelo','box','modelo'],disk:['Disco','hard-drive','status'],ram:['RAM','memory-stick','status'],uptime:['Uptime','clock','status']};
const RECUR=[{v:'',l:'Uma vez'},{v:'daily',l:'Diário'},{v:'weekly',l:'Semanal'},{v:'monthly',l:'Mensal'}];
const RECUR_LBL={daily:'repete diário',weekly:'repete semanal',monthly:'repete mensal'};
let config={actions:['buscar','noticias','clima','relatorio','status','semana'],stats:['tasks','reminders','expenses','memories','kb']};let _counts={};
function renderStats(){const box=$('#stats');box.textContent='';config.stats.forEach(k=>{const m=SM[k];if(!m)return;
  const VMAP={tasks:'tasks',reminders:'rem',expenses:'exp',memories:'mem',kb:'kb',kbfiles:'kb',links:'lnk',habits:'hab',journal:'jou',subscriptions:'sub',budgets:'orc',watches:'mon',agenda:'cal',activity:'act'};
  const s=el('div','stat');s.onclick=()=>{if(VMAP[k])switchView(VMAP[k]);else runCmd(m[2]);};const lbl=el('span','lbl');lbl.appendChild(ficon(m[1]));lbl.appendChild(document.createTextNode(m[0]));
  const num=el('span','num');if(k==='expenses'){const rs=el('span','','R$');rs.style.cssText='font-size:12px;color:var(--subtle);margin-right:2px';num.appendChild(rs);}
  num.appendChild(document.createTextNode(_counts[k]!=null?_counts[k]:'0'));s.appendChild(lbl);s.appendChild(num);box.appendChild(s);});window.lucide&&lucide.createIcons();}
function renderActs(){const box=$('#acts');box.textContent='';config.actions.forEach(cmd=>{const m=CAT[cmd]||[cmd,'chevron-right'];
  const b=el('button','act');b.appendChild(ficon(m[1]));b.appendChild(document.createTextNode(m[0]));
  b.onclick=e=>{if(cmd==='foco')openPomo(25);else runCmd(cmd,b,e);};box.appendChild(b);});window.lucide&&lucide.createIcons();}
async function loadPanel(){try{const r=await fetch('/api/panel',{headers:H()});if(!r.ok)return;_counts=await r.json();
  renderStats();$('#s-prov').textContent=_counts.provider;$('#s-model').textContent=_counts.model;$('#prov').value=_counts.provider;updateNBadge(_counts.notifs);}catch(e){}}
async function loadConfig(){try{config=await (await fetch('/api/config',{headers:H()})).json();}catch(e){}renderActs();}
async function saveConfig(){try{await fetch('/api/config',{method:'POST',headers:H(),body:JSON.stringify(config)});}catch(e){}}
$('#prov').onchange=()=>runCmd('provedor '+$('#prov').value);
async function openKeys(){let d;try{d=await (await fetch('/api/keys',{headers:H()})).json();}catch(e){return;}
  const fields=d.keys.map(k=>({key:k.field,label:k.label,type:'password',placeholder:k.set?'definida — deixe em branco pra manter':'não definida'}));
  openForm('Chaves de API',fields,async v=>{const body={};Object.keys(v).forEach(k=>{if(v[k])body[k]=v[k];});
    if(Object.keys(body).length){const r=await (await fetch('/api/keys',{method:'POST',headers:H(),body:JSON.stringify(body)})).json();sys('Chaves atualizadas: '+(r.changed||[]).join(', '));loadPanel();}});}
$('#btn-keys').onclick=openKeys;
function updateNBadge(n){const b=$('#notif-badge');if(!b)return;n=n||0;b.textContent=n>99?'99+':n;b.classList.toggle('on',n>0);}
function nfmt(iso){try{const d=new Date(iso);const now=new Date();const diff=(now-d)/1000;
  if(diff<60)return 'agora';if(diff<3600)return Math.floor(diff/60)+'min';
  if(d.toDateString()===now.toDateString())return 'hoje '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})+' '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});}catch(e){return '';}}
async function openNotifs(){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle','Notificações'));
  const list=el('div','nlist');card.appendChild(list);
  async function refresh(){let d;try{d=await (await fetch('/api/notifications',{headers:H()})).json();}catch(e){return;}
    updateNBadge(d.unread);list.textContent='';
    if(!d.items||!d.items.length){list.appendChild(el('div','tv-empty','Nenhuma notificação. Lembretes e alertas aparecem aqui.'));return;}
    d.items.forEach(it=>{const row=el('div','nrow'+(it.read?'':' unread'));
      const ico=ficon('bell');ico.classList.add('nico');row.appendChild(ico);
      const c=el('div','ncont');c.appendChild(el('div','ntitle',it.title));
      if(it.body)c.appendChild(el('div','nbody',it.body));
      c.appendChild(el('div','ntime',nfmt(it.created)));row.appendChild(c);
      const x=el('button','nx');x.appendChild(ficon('x'));x.title='Apagar';
      x.onclick=async(e)=>{e.stopPropagation();await fetch('/api/notifications/delete',{method:'POST',headers:H(),body:JSON.stringify({id:it.id})});refresh();};
      row.appendChild(x);
      row.onclick=async()=>{if(!it.read){await fetch('/api/notifications/read',{method:'POST',headers:H(),body:JSON.stringify({id:it.id})});refresh();}};
      list.appendChild(row);});
    window.lucide&&lucide.createIcons();}
  const bar=el('div','mbar');
  const rd=el('button','mbtn2','Marcar todas lidas');rd.onclick=async()=>{await fetch('/api/notifications/read',{method:'POST',headers:H(),body:JSON.stringify({})});refresh();};
  const cl=el('button','mbtn2','Limpar lidas');cl.onclick=async()=>{await fetch('/api/notifications/clear',{method:'POST',headers:H(),body:JSON.stringify({scope:'read'})});refresh();};
  const ok=el('button','mbtn','Fechar');ok.onclick=()=>m.classList.remove('on');
  bar.appendChild(rd);bar.appendChild(cl);bar.appendChild(ok);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');refresh();}
$('#btn-notifs').onclick=openNotifs;
function openPicker(title,sub,items,selected,onSave){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  const tt=el('div','mtitle',title);tt.appendChild(el('small','',sub));card.appendChild(tt);const sel=new Set(selected);
  items.forEach(it=>{const row=el('label','mrow');const cb=document.createElement('input');cb.type='checkbox';cb.checked=sel.has(it.key);
    cb.onchange=()=>cb.checked?sel.add(it.key):sel.delete(it.key);row.appendChild(cb);row.appendChild(el('span','',it.label));card.appendChild(row);});
  const bar=el('div','mbar');const c=el('button','mbtn2','Cancelar');c.onclick=()=>m.classList.remove('on');
  const sv=el('button','mbtn','Salvar');sv.onclick=()=>{onSave([...sel]);m.classList.remove('on');};bar.appendChild(c);bar.appendChild(sv);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');}
function confirmDialog(msg){return new Promise(res=>{const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle','Confirmar'));card.appendChild(el('div','mconf',msg));
  const bar=el('div','mbar');const c=el('button','mbtn2','Cancelar');c.onclick=()=>{m.classList.remove('on');res(false);};
  const s=el('button','mbtn','Confirmar');s.onclick=()=>{m.classList.remove('on');res(true);};
  bar.appendChild(c);bar.appendChild(s);card.appendChild(bar);m.appendChild(card);m.classList.add('on');setTimeout(()=>s.focus(),50);});}
function openForm(title,fields,onSave,onDelete){const m=$('#modal');m.textContent='';const card=el('div','mcard');card.appendChild(el('div','mtitle',title));
  const inp={};fields.forEach(fd=>{const w=el('div','mfield');w.appendChild(el('label','mlabel',fd.label));
    let i;
    if(fd.type==='textarea'){i=document.createElement('textarea');}
    else if(fd.select){i=document.createElement('select');fd.select.forEach(o=>{const op=document.createElement('option');op.value=o.v;op.textContent=o.l;i.appendChild(op);});}
    else{i=document.createElement('input');i.type=fd.type==='password'?'password':fd.type==='datetime'?'datetime-local':'text';}
    i.className='minput';i.value=fd.value||'';if(fd.placeholder)i.placeholder=fd.placeholder;
    if(fd.options&&fd.options.length){const dl=document.createElement('datalist');dl.id='dl_'+fd.key;fd.options.forEach(o=>{const op=document.createElement('option');op.value=o;dl.appendChild(op);});w.appendChild(dl);i.setAttribute('list','dl_'+fd.key);}
    w.appendChild(i);card.appendChild(w);inp[fd.key]=i;});
  const bar=el('div','mbar');
  if(onDelete){const d=el('button','mbtn2','Apagar');d.style.marginRight='auto';d.onclick=()=>{m.classList.remove('on');onDelete();};bar.appendChild(d);}
  const c=el('button','mbtn2','Cancelar');c.onclick=()=>m.classList.remove('on');
  const s=el('button','mbtn','Salvar');s.onclick=()=>{const v={};Object.keys(inp).forEach(k=>v[k]=inp[k].value.trim());m.classList.remove('on');onSave(v);};
  bar.appendChild(c);bar.appendChild(s);card.appendChild(bar);m.appendChild(card);m.classList.add('on');
  setTimeout(()=>{const f=inp[fields[0].key];f.focus();if(f.select)f.select();},60);}
$('#edit-acts').onclick=()=>openPicker('Ações rápidas','Escolha os atalhos do painel.',Object.keys(CAT).map(k=>({key:k,label:CAT[k][0]})),config.actions,async l=>{config.actions=l;await saveConfig();renderActs();});
$('#edit-stats').onclick=()=>openPicker('Sistema','Escolha os indicadores exibidos.',Object.keys(SM).map(k=>({key:k,label:SM[k][0]})),config.stats,async l=>{config.stats=l;await saveConfig();renderStats();});
const PT=$('#pomo-time'),PL=$('#pomo-label'),PG=$('#pomo-toggle'),PBOX=$('#pomo-timebox'),PW=$('#pomo');
let pomo={rem:1500,total:1500,brk:300,phase:'focus',run:false,timer:null};
function pfmt(){const s=Math.max(0,pomo.rem);return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
function pIcon(){PG.innerHTML='';PG.appendChild(ficon(pomo.run?'pause':'play'));window.lucide&&lucide.createIcons();}
function prender(){PT.textContent=pfmt();PW.classList.toggle('run',pomo.run);PW.classList.toggle('brk',pomo.phase==='break');}
function ptick(){if(!pomo.run)return;pomo.rem--;
  if(pomo.rem<=0){
    if(pomo.phase==='focus'){pomo.phase='break';pomo.total=pomo.brk;pomo.rem=pomo.brk;PL.textContent='Pausa';speak('Foco concluído, hora da pausa.',true);}
    else{pomo.rem=0;pstop();PL.textContent='Ciclo concluído';speak('Pausa concluída. Bora pro próximo ciclo.',true);}
  }prender();}
function pstart(){if(pomo.timer)clearInterval(pomo.timer);pomo.run=true;pomo.timer=setInterval(ptick,1000);prender();pIcon();}
function pstop(){pomo.run=false;if(pomo.timer){clearInterval(pomo.timer);pomo.timer=null;}prender();pIcon();}
function openPomo(mins,brk){mins=mins||25;brk=brk||5;pomo.phase='focus';pomo.brk=brk*60;pomo.total=mins*60;pomo.rem=mins*60;PL.textContent='Foco';PW.classList.add('on');pstart();speak('Iniciando o foco. '+mins+' minutos, vamos nessa, Ryan.',true);}
$('#pomo-x').onclick=()=>{pstop();PW.classList.remove('on');};
PG.onclick=()=>pomo.run?pstop():pstart();
$('#pomo-reset').onclick=()=>{pomo.rem=pomo.total;prender();};
document.querySelectorAll('#pomo-ctl [data-m]').forEach(b=>b.onclick=()=>{pomo.rem=Math.max(30,pomo.rem+parseInt(b.dataset.m)*60);pomo.total=Math.max(pomo.total,pomo.rem);prender();});
document.querySelectorAll('#pomo-presets [data-set]').forEach(b=>b.onclick=()=>openPomo(parseInt(b.dataset.set)));
const MINI=$('#pomo-mini'),MBODY=MINI.querySelector('.pm-body');let pipWin=null;
function restorePBOX(){if(!PW.contains(PBOX))PW.insertBefore(PBOX,$('#pomo-ctl'));}
function minimizeInPage(){PW.classList.remove('on');MBODY.appendChild(PBOX);MINI.style.display='flex';}
$('#pomo-pip').onclick=async()=>{
  if(window.documentPictureInPicture){try{pipWin=await documentPictureInPicture.requestWindow({width:240,height:160});
    document.querySelectorAll('style').forEach(n=>pipWin.document.head.appendChild(n.cloneNode(true)));
    pipWin.document.body.style.cssText='margin:0;background:#0a0a0a;color:#f4f3f1;display:flex;align-items:center;justify-content:center;height:100vh;cursor:pointer';
    pipWin.document.body.appendChild(PBOX);pipWin.document.body.onclick=()=>pomo.run?pstop():pstart();PW.classList.remove('on');
    pipWin.addEventListener('pagehide',()=>{restorePBOX();PW.classList.add('on');pipWin=null;});return;
  }catch(e){}}
  minimizeInPage();}; // fallback (funciona no HTTP): janelinha flutuante na própria página
$('#pm-open').onclick=()=>{restorePBOX();MINI.style.display='none';PW.classList.add('on');};
$('#pm-close').onclick=()=>{pstop();MINI.style.display='none';restorePBOX();};
MBODY.onclick=()=>pomo.run?pstop():pstart();
(function(){let dx=0,dy=0,drag=false;const h=MINI.querySelector('.pm-head');
  h.onmousedown=e=>{drag=true;const r=MINI.getBoundingClientRect();dx=e.clientX-r.left;dy=e.clientY-r.top;MINI.style.right='auto';e.preventDefault();};
  window.addEventListener('mousemove',e=>{if(!drag)return;MINI.style.left=Math.max(0,e.clientX-dx)+'px';MINI.style.top=Math.max(0,e.clientY-dy)+'px';});
  window.addEventListener('mouseup',()=>drag=false);})();

// folders
async function loadFolders(){try{const r=await fetch('/api/threads',{headers:H()});const d=await r.json();
  const box=$('#folders');box.textContent='';
  d.threads.slice().sort().forEach(path=>{const seg=path.split('/');const depth=seg.length-1;const label=seg[seg.length-1];
    const f=el('div','folder'+(path===thread?' on':''));f.style.paddingLeft=(11+depth*15)+'px';
    f.appendChild(el('span','fi',depth?'└':'▚'));const nm=el('span','fn',label);nm.style.flex='1';f.appendChild(nm);
    const add=el('span','fx','+');add.title='subpasta';add.onclick=e=>{e.stopPropagation();childFolder(path);};f.appendChild(add);
    if(depth>0){const up=el('span','fx','↑');up.title='mover para a raiz';up.onclick=async e=>{e.stopPropagation();
      await fetch('/api/threads/move',{method:'POST',headers:H(),body:JSON.stringify({path,parent:''})});
      if(thread===path||thread.startsWith(path+'/')){thread=thread.replace(path,label);localStorage.setItem('ev_thread',thread);}
      await switchThread(thread);};f.appendChild(up);}
    if(path!=='geral'){const x=el('span','fx','✕');x.title='apagar';x.onclick=e=>{e.stopPropagation();delFolder(path);};f.appendChild(x);}
    f.onclick=()=>switchThread(path);f.ondblclick=()=>renameFolder(path);
    f.draggable=true;
    f.ondragstart=e=>{e.dataTransfer.setData('text/plain',path);e.dataTransfer.effectAllowed='move';};
    f.ondragover=e=>{e.preventDefault();f.classList.add('drop');};
    f.ondragleave=()=>f.classList.remove('drop');
    f.ondrop=async e=>{e.preventDefault();f.classList.remove('drop');const src=e.dataTransfer.getData('text/plain');
      if(src&&src!==path&&!path.startsWith(src+'/')){await fetch('/api/threads/move',{method:'POST',headers:H(),body:JSON.stringify({path:src,parent:path})});
        const leaf=src.split('/').pop(),np=path+'/'+leaf;
        if(thread===src||thread.startsWith(src+'/')){thread=thread.replace(src,np);localStorage.setItem('ev_thread',thread);}
        await switchThread(thread);}};
    box.appendChild(f);});
  // drop on empty area -> move to root
  const bx=$('#folders');bx.ondragover=e=>e.preventDefault();
  bx.ondrop=async e=>{if(e.target!==bx)return;e.preventDefault();const src=e.dataTransfer.getData('text/plain');
    if(src){await fetch('/api/threads/move',{method:'POST',headers:H(),body:JSON.stringify({path:src,parent:''})});await switchThread(thread);}};
}catch(e){}}
function childFolder(parent){openForm('Nova subpasta em "'+parent+'"',[{key:'name',label:'Nome',placeholder:'ex: projetos'}],async v=>{
  const name=(v.name||'').toLowerCase().replace(/\s+/g,'-').replace(/\//g,'-');if(!name)return;
  await fetch('/api/threads',{method:'POST',headers:H(),body:JSON.stringify({name,parent})});await switchThread(parent+'/'+name);});}
async function delFolder(path){if(!(await confirmDialog('Apagar "'+path+'" (e subpastas/conversas)? Não dá pra desfazer.')))return;
  await fetch('/api/threads/delete',{method:'POST',headers:H(),body:JSON.stringify({name:path})});
  if(thread===path||thread.startsWith(path+'/'))await switchThread('geral');else loadFolders();}
function renameFolder(path){if(path==='geral')return;const seg=path.split('/');const leaf=seg[seg.length-1];
  openForm('Renomear pasta',[{key:'name',label:'Novo nome',value:leaf}],async v=>{const nv=(v.name||'').toLowerCase().replace(/\s+/g,'-').replace(/\//g,'-');if(!nv||nv===leaf)return;
    await fetch('/api/threads/rename',{method:'POST',headers:H(),body:JSON.stringify({old:path,new:nv})});
    const np=(seg.slice(0,-1).join('/')?seg.slice(0,-1).join('/')+'/':'')+nv;
    if(thread===path||thread.startsWith(path+'/')){thread=thread.replace(path,np);localStorage.setItem('ev_thread',thread);}
    await switchThread(thread);});}
async function switchThread(name){thread=name;localStorage.setItem('ev_thread',name);scopeEl.textContent='Conversa · '+name;
  document.body.classList.remove('m-left','m-right');
  loadFolders();log.textContent='';await loadHistory();}
async function loadHistory(){try{const r=await fetch('/api/history?thread='+encodeURIComponent(thread),{headers:H()});const d=await r.json();
  if(!d.messages.length){sys('Pasta "'+thread+'" — comece a conversa.');return;}
  d.messages.forEach(m=>m.role==='user'?you(m.content):ev(m.content));}catch(e){}}
$('#newf').onclick=()=>openForm('Nova pasta',[{key:'name',label:'Nome',placeholder:'ex: projetos'}],async v=>{
  const name=(v.name||'').toLowerCase().replace(/\s+/g,'-').replace(/\//g,'-');if(!name)return;
  await fetch('/api/threads',{method:'POST',headers:H(),body:JSON.stringify({name})});await switchThread(name);});

// slash autocomplete
let slSel=-1,slList=[];
function showSlash(q){slList=COMMANDS.filter(c=>c.name.startsWith(q));if(!slList.length){hideSlash();return;}
  slash.textContent='';slList.forEach((c,i)=>{const s=el('div','s'+(i===0?' sel':''));s.appendChild(el('span','c','/'+c.name));s.appendChild(el('span','d',c.desc));
    s.onclick=()=>{slSel=i;pickSlash();};slash.appendChild(s);});slSel=0;slash.style.display='block';}
function hideSlash(){slash.style.display='none';slSel=-1;}
function pickSlash(){const c=slList[slSel];if(!c)return;txt.value='/'+c.name+' ';hideSlash();txt.focus();}
txt.addEventListener('input',()=>{const v=txt.value;if(v.startsWith('/')&&!v.includes(' '))showSlash(v.slice(1).toLowerCase());else hideSlash();});
txt.addEventListener('keydown',e=>{if(slash.style.display!=='block')return;
  if(e.key==='ArrowDown'){e.preventDefault();slSel=Math.min(slList.length-1,slSel+1);}
  else if(e.key==='ArrowUp'){e.preventDefault();slSel=Math.max(0,slSel-1);}
  else if(e.key==='Escape'){hideSlash();return;}else if(e.key==='Tab'){e.preventDefault();pickSlash();return;}else return;
  [...slash.children].forEach((c,i)=>c.classList.toggle('sel',i===slSel));slash.children[slSel].scrollIntoView({block:'nearest'});});

// voice input — grava com MediaRecorder e transcreve no servidor (Whisper).
// Funciona em qualquer navegador (Firefox, Chrome, Safari), não só Chrome.
const RECOK=!!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia&&window.MediaRecorder);
let _mrec=null,_mstream=null,_mchunks=[],_recActive=false;
function micErrMsg(e){const n=(e&&e.name)||'';return {'NotAllowedError':'Permissão do microfone negada. Toque no ícone de cadeado/site na barra de endereço e habilite o microfone para este site.','NotFoundError':'Nenhum microfone encontrado no aparelho.','NotReadableError':'O microfone está sendo usado por outro app. Feche-o e tente de novo.','SecurityError':'O microfone exige HTTPS.'}[n]||('Não consegui acessar o microfone: '+((e&&e.message)||e));}
async function startRec(onBlob){
  try{_mstream=await navigator.mediaDevices.getUserMedia({audio:true});}catch(e){return e;}
  _mchunks=[];const mr=new MediaRecorder(_mstream);
  mr.ondataavailable=e=>{if(e.data&&e.data.size)_mchunks.push(e.data);};
  mr.onstop=()=>{if(_mstream){_mstream.getTracks().forEach(t=>t.stop());_mstream=null;}
    const blob=new Blob(_mchunks,{type:mr.mimeType||'audio/webm'});_recActive=false;onBlob(blob);};
  mr.start();_mrec=mr;_recActive=true;return true;
}
function stopRec(){if(_mrec&&_mrec.state!=='inactive')_mrec.stop();_recActive=false;}
async function sttBlob(blob){const ext=(blob.type||'').includes('mp4')?'mp4':(blob.type||'').includes('ogg')?'ogg':'webm';
  const fd=new FormData();fd.append('audio',blob,'rec.'+ext);
  const r=await fetch('/api/stt',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd});
  if(!r.ok)throw new Error('stt '+r.status);return ((await r.json()).text||'').trim();}
// botão de microfone no chat
let _audA=null;
function audioConfirm(blob){const p=$('#audprev');p.innerHTML='';if(!blob||!blob.size){p.style.display='none';return;}
  if(_audA){try{_audA.pause();}catch(e){}}_audA=new Audio(URL.createObjectURL(blob));
  const play=el('button','ap-play','▶ ouvir');play.onclick=()=>{try{_audA.currentTime=0;_audA.play();}catch(e){}};
  const info=el('span','ap-info','Áudio gravado — confira antes de enviar (transcrever custa tokens).');
  const cancel=el('button','ap-cancel','Cancelar');cancel.onclick=()=>{p.style.display='none';if(_audA){try{_audA.pause();}catch(e){}}};
  const sendb=el('button','ap-send','Enviar');sendb.onclick=async()=>{p.style.display='none';setState('thinking');
    try{const t=await sttBlob(blob);if(t)send(t);else sys('Não entendi o áudio — fale mais perto e tente de novo.');}
    catch(x){sys('Falha ao transcrever o áudio. Tente de novo.');}finally{setState();}};
  p.appendChild(play);p.appendChild(info);p.appendChild(cancel);p.appendChild(sendb);p.style.display='flex';}
micBtn.onclick=async e=>{ripple(micBtn,e);
  if(!RECOK){sys('Gravação de áudio indisponível neste navegador.');return;}
  if(_recActive){stopRec();return;}
  $('#audprev').style.display='none';micBtn.classList.add('on');setState('listening');
  const res=await startRec(blob=>{micBtn.classList.remove('on');setState();audioConfirm(blob);});
  if(res!==true){micBtn.classList.remove('on');setState();sys(micErrMsg(res));}};

// live voice console
const vc=$('#vc'),vcTxt=$('#vc-txt'),vcMic=$('#vc-mic');
$('#vcopen').onclick=()=>{if(!RECOK){sys('Gravação de áudio indisponível neste navegador.');return;}vc.classList.add('on');vcTxt.textContent='Toque no microfone e fale. Toque de novo para enviar.';$('#vc-sub').textContent='pasta: '+thread+' · a conversa fica salva aqui';};
$('#vc-x').onclick=()=>{if(_recActive)stopRec();vc.classList.remove('on');setState();};
vcMic.onclick=async()=>{
  if(!RECOK){vcTxt.textContent='Gravação de áudio indisponível neste navegador.';return;}
  if(_recActive){stopRec();vcTxt.textContent='transcrevendo...';return;}
  vcMic.classList.add('rec');setState('listening');vcTxt.textContent='ouvindo... (toque de novo para enviar)';
  const res=await startRec(async blob=>{vcMic.classList.remove('rec');setState('thinking');vcTxt.textContent='transcrevendo...';
    try{const t=await sttBlob(blob);if(!t){vcTxt.textContent='Não entendi. Toque no microfone e fale de novo.';setState();return;}
      vcTxt.textContent='"'+t+'"';
      const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:t,thread})});const j=await r.json();
      vcTxt.textContent=j.reply||'(sem resposta)';speak(j.reply,true);loadPanel();
      if(_vcCont&&vc.classList.contains('on'))setTimeout(()=>{if(!_recActive&&vc.classList.contains('on'))vcMic.click();},2200);
    }catch(x){vcTxt.textContent='Falha ao processar o áudio. Tente de novo.';}finally{setState();}});
  if(res!==true){vcMic.classList.remove('rec');setState();vcTxt.textContent=micErrMsg(res);}};
let _vcCont=false;
$('#vc-cont').onclick=()=>{_vcCont=!_vcCont;$('#vc-cont').innerHTML='';$('#vc-cont').appendChild(ficon('infinity'));$('#vc-cont').appendChild(document.createTextNode(' Modo contínuo: '+(_vcCont?'on':'off')));window.lucide&&lucide.createIcons();if(_vcCont&&!_recActive)vcMic.click();};
// view tabs — customizable: pick which appear in the header (minimalist)
const VIEW_LABELS={chat:'Conversa',tasks:'Tarefas',exp:'Gastos',rem:'Lembretes',cal:'Agenda',mem:'Memórias',lnk:'Links',hab:'Hábitos',jou:'Diário',sub:'Assinaturas',orc:'Orçamentos',mon:'Monitores',act:'Histórico',kb:'Base'};
let curView='chat',tabsShown;try{tabsShown=JSON.parse(localStorage.getItem('ev_tabs'));}catch(e){}
if(!Array.isArray(tabsShown)||!tabsShown.length)tabsShown=['chat','tasks','exp','rem','cal'];
function renderTabs(){const box=$('#tabs');if(!box)return;box.textContent='';
  tabsShown.forEach(v=>{if(!VIEW_LABELS[v])return;const b=el('button','tab'+(v===curView?' on':''),VIEW_LABELS[v]);b.dataset.view=v;b.onclick=()=>switchView(v);box.appendChild(b);});
  const ed=el('button','tab tab-edit','+');ed.title='Escolher abas';ed.onclick=()=>openPicker('Abas do topo','Escolha quais abas aparecem no topo.',Object.keys(VIEW_LABELS).map(k=>({key:k,label:VIEW_LABELS[k]})),tabsShown,l=>{tabsShown=l.length?l:['chat'];localStorage.setItem('ev_tabs',JSON.stringify(tabsShown));renderTabs();});box.appendChild(ed);}
renderTabs();
$('#mnav').onchange=()=>switchView($('#mnav').value);
const VIEWS={chat:'#chatview',tasks:'#taskview',exp:'#expview',rem:'#remview',cal:'#calview',mem:'#memview',lnk:'#lnkview',hab:'#habview',jou:'#jouview',sub:'#subview',orc:'#orcview',mon:'#monview',kb:'#kbview',act:'#actview'};
function switchView(v){if(!VIEWS[v])v='chat';curView=v;document.querySelectorAll('#tabs .tab').forEach(t=>t.classList.toggle('on',t.dataset.view===v));
  const mn=$('#mnav');if(mn&&mn.value!==v)mn.value=v;
  document.body.classList.remove('m-left','m-right');
  Object.entries(VIEWS).forEach(([k,sel])=>{const el2=$(sel);if(el2)el2.style.display=(k===v)?(k==='chat'?'flex':'block'):'none';});
  ({tasks:loadTasks,exp:loadExp,rem:loadRem,mem:loadMem,kb:loadKB,cal:loadCal,lnk:loadLinks,hab:loadHabits,jou:loadJournal,sub:loadSub,orc:loadOrc,mon:loadMon,act:loadAct}[v]||function(){})();}
const ACT_ICON={'task.new':['plus','tarefa criada'],'task.done':['check-check','tarefa concluída'],'task.del':['trash-2','tarefa apagada'],'reminder.new':['alarm-clock','lembrete criado'],'reminder.done':['bell-ring','lembrete disparado'],'reminder.cancel':['bell-off','lembrete cancelado'],'expense.new':['wallet','gasto adicionado'],'expense.del':['trash-2','gasto apagado'],'habit.done':['repeat','hábito feito']};
async function loadAct(){try{const cat=$('#act-cat').value;
  const d=await (await fetch('/api/activity'+(cat?'?category='+encodeURIComponent(cat):''),{headers:H()})).json();
  const sel=$('#act-cat');sel.innerHTML='<option value="">Todas as categorias</option>'+(d.categories||[]).map(c=>'<option'+(c===cat?' selected':'')+'>'+c+'</option>').join('');
  const box=$('#actlist');box.textContent='';const items=d.items||[];
  if(!items.length){box.appendChild(el('div','tv-empty','Nada registrado ainda. Suas ações (criar, concluir, apagar) aparecem aqui — do Telegram e da web.'));return;}
  items.forEach(a=>{const meta=ACT_ICON[a.action]||['activity',a.action];const row=el('div','tv-row');
    const ic=el('div','tv-ic');ic.appendChild(ficon(meta[0]));ic.style.cursor='default';
    const t=el('div','txt');t.appendChild(el('div','',meta[1]+': '+a.label));
    const w=a.created?new Date(a.created):null;
    const sub=((w&&!isNaN(w))?w.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'')+(a.category?' · '+a.category:'');
    t.appendChild(subline(sub));row.appendChild(ic);row.appendChild(t);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
$('#act-cat').onchange=()=>loadAct();
async function loadSub(){try{const items=(await (await fetch('/api/recurring',{headers:H()})).json()).items||[];const box=$('#sublist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhuma assinatura.'));return;}
  items.forEach(x=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',x.description));t.appendChild(subline(x.category+' · dia '+x.day));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+x.amount.toFixed(0);
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editSub(x);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog('Remover assinatura?'))recDel('/api/recurring/delete',x.id,loadSub);};
    row.appendChild(t);row.appendChild(val);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editSub(x){openForm('Editar assinatura',[
  {key:'amount',label:'Valor (R$)',value:String(x.amount)},
  {key:'description',label:'Descrição',value:x.description},
  {key:'category',label:'Categoria',value:x.category},
  {key:'day',label:'Dia do mês',value:String(x.day)}],
  async v=>{await fetch('/api/recurring/update',{method:'POST',headers:H(),body:JSON.stringify({id:x.id,amount:v.amount,description:v.description,category:v.category,day:v.day})});loadSub();});}
$('#subform').onsubmit=async e=>{e.preventDefault();const amount=$('#sub-amt').value.trim();if(!amount)return;
  await fetch('/api/recurring',{method:'POST',headers:H(),body:JSON.stringify({amount,description:$('#sub-desc').value.trim(),day:$('#sub-day').value})});$('#sub-amt').value='';$('#sub-desc').value='';loadSub();};
async function loadOrc(){try{const items=(await (await fetch('/api/budgets',{headers:H()})).json()).items||[];const box=$('#orclist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhum orçamento definido.'));return;}
  items.forEach(b=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',b.category));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+b.amount.toFixed(0)+'/mês';
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editOrc(b);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog('Remover orçamento?')){await fetch('/api/budgets/delete',{method:'POST',headers:H(),body:JSON.stringify({category:b.category})});loadOrc();loadPanel();}};
    row.appendChild(t);row.appendChild(val);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editOrc(b){openForm('Editar orçamento · '+b.category,[
  {key:'amount',label:'Valor mensal (R$)',value:String(b.amount)}],
  async v=>{if(!v.amount)return;await fetch('/api/budgets',{method:'POST',headers:H(),body:JSON.stringify({category:b.category,amount:v.amount})});loadOrc();loadPanel();});}
$('#orcform').onsubmit=async e=>{e.preventDefault();const cat=$('#orc-cat').value.trim(),amount=$('#orc-amt').value.trim();if(!cat||!amount)return;
  await fetch('/api/budgets',{method:'POST',headers:H(),body:JSON.stringify({category:cat,amount})});$('#orc-cat').value='';$('#orc-amt').value='';loadOrc();};
async function loadMon(){try{const items=(await (await fetch('/api/watches',{headers:H()})).json()).items||[];const box=$('#monlist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhum monitor.'));return;}
  items.forEach(w=>{const row=el('div','tv-row');const t=el('div','txt');const a=document.createElement('a');a.href=w.url;a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=w.url;t.appendChild(a);if(w.keyword)t.appendChild(subline('palavra: '+w.keyword));
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editMon(w);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog('Remover monitor?'))recDel('/api/watches/delete',w.id,loadMon);};
    row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editMon(w){openForm('Editar monitor',[
  {key:'url',label:'URL',value:w.url},
  {key:'keyword',label:'Palavra-chave',value:w.keyword||''}],
  async v=>{if(!v.url)return;await fetch('/api/watches/update',{method:'POST',headers:H(),body:JSON.stringify({id:w.id,url:v.url,keyword:v.keyword})});loadMon();});}
$('#monform').onsubmit=async e=>{e.preventDefault();const url=$('#mon-url').value.trim();if(!url)return;
  await fetch('/api/watches',{method:'POST',headers:H(),body:JSON.stringify({url,keyword:$('#mon-kw').value.trim()})});$('#mon-url').value='';$('#mon-kw').value='';loadMon();};
async function loadLinks(){try{const items=(await (await fetch('/api/links',{headers:H()})).json()).items||[];const box=$('#lnklist');box.textContent='';
  window._lcats=[...new Set(items.map(l=>l.category))];
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhum link salvo.'));return;}
  const g={};items.forEach(l=>{(g[l.category]=g[l.category]||[]).push(l);});
  Object.keys(g).sort().forEach(cat=>{box.appendChild(el('div','tv-cat',cat));
    g[cat].forEach(l=>{const row=el('div','tv-row');const t=el('div','txt');const a=document.createElement('a');a.href=l.url;a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=l.name;t.appendChild(a);t.appendChild(subline(l.url));
      const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editLink(l);
      const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/links/delete',{id:l.id},'/api/links',{name:l.name,url:l.url,category:l.category},loadLinks,'Link');
      row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});});window.lucide&&lucide.createIcons();}catch(e){}}
function editLink(l){openForm('Editar link',[
  {key:'name',label:'Nome',value:l.name},
  {key:'url',label:'URL',value:l.url},
  {key:'category',label:'Categoria',value:l.category,options:window._lcats||[]}],
  async v=>{if(!v.name||!v.url)return;await fetch('/api/links/update',{method:'POST',headers:H(),body:JSON.stringify({id:l.id,name:v.name,url:v.url,category:v.category})});loadLinks();});}
$('#lnkform').onsubmit=async e=>{e.preventDefault();const name=$('#lnk-name').value.trim(),url=$('#lnk-url').value.trim(),cat=$('#lnk-cat').value.trim()||'geral';if(!name||!url)return;
  await fetch('/api/links',{method:'POST',headers:H(),body:JSON.stringify({name,url,category:cat})});$('#lnk-name').value='';$('#lnk-url').value='';loadLinks();};
async function loadHabits(){try{const items=(await (await fetch('/api/habits',{headers:H()})).json()).items||[];const box=$('#hablist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhum hábito. Crie um acima.'));return;}
  items.forEach(h=>{const row=el('div','tv-row');const done=el('button','tv-ic');done.title=h.done_today?'feito hoje':'marcar feito';done.appendChild(ficon(h.done_today?'check-check':'check'));if(h.done_today)done.style.color='var(--fg)';
    done.onclick=async()=>{await fetch('/api/habits/done',{method:'POST',headers:H(),body:JSON.stringify({id:h.id})});loadHabits();};
    const t=el('div','txt');t.appendChild(el('div','',h.name));t.appendChild(subline(h.total+' dias'+(h.done_today?' · feito hoje':'')));t.appendChild(habHeat(h.days));
    const ed=el('button','tv-ic');ed.title='renomear';ed.appendChild(ficon('pencil'));ed.onclick=()=>editHab(h);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog('Apagar hábito?'))recDel('/api/habits/delete',h.id,loadHabits);};
    row.appendChild(done);row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function habHeat(days){const set=new Set(days||[]);const wrap=el('div','heat');const today=new Date();
  for(let i=111;i>=0;i--){const d=new Date(today);d.setDate(today.getDate()-i);const ds=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');const c=el('span','hc'+(set.has(ds)?' on':''));c.title=ds;wrap.appendChild(c);}
  return wrap;}
function editHab(h){openForm('Renomear hábito',[
  {key:'name',label:'Nome',value:h.name}],
  async v=>{if(!v.name)return;await fetch('/api/habits/update',{method:'POST',headers:H(),body:JSON.stringify({id:h.id,name:v.name})});loadHabits();});}
$('#habform').onsubmit=async e=>{e.preventDefault();const name=$('#hab-name').value.trim();if(!name)return;await fetch('/api/habits',{method:'POST',headers:H(),body:JSON.stringify({name})});$('#hab-name').value='';loadHabits();};
async function loadJournal(){try{const items=(await (await fetch('/api/journal',{headers:H()})).json()).items||[];const box=$('#joulist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Diário vazio.'));return;}
  items.slice().reverse().forEach(j=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',j.text));if(j.created)t.appendChild(subline(j.created.slice(0,10)));
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editJou(j);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/journal/delete',{id:j.id},'/api/journal',{text:j.text},loadJournal,'Entrada');
    row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editJou(j){openForm('Editar entrada',[
  {key:'text',label:'Texto',value:j.text,type:'textarea'}],
  async v=>{if(!v.text)return;await fetch('/api/journal/update',{method:'POST',headers:H(),body:JSON.stringify({id:j.id,text:v.text})});loadJournal();});}
$('#jouform').onsubmit=async e=>{e.preventDefault();const text=$('#jou-text').value.trim();if(!text)return;await fetch('/api/journal',{method:'POST',headers:H(),body:JSON.stringify({text})});$('#jou-text').value='';loadJournal();};
let calY=null,calM=null;
function ymd(y,m,d){return y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');}
async function loadCal(){const now=new Date();if(calY==null){calY=now.getFullYear();calM=now.getMonth();}
  const items=(await (await fetch('/api/reminders',{headers:H()})).json()).items||[];
  const byDay={};items.forEach(r=>{if(r.when_iso){const d=r.when_iso.slice(0,10);(byDay[d]=byDay[d]||[]).push(r);}});
  // merge Google Calendar events for the visible month (if authorized)
  try{const ms=ymd(calY,calM,1),me=ymd(calM===11?calY+1:calY,(calM+1)%12,1);
    const gj=await (await fetch('/api/gcal?start='+ms+'T00:00:00Z&end='+me+'T00:00:00Z',{headers:H()})).json();
    (gj.events||[]).forEach(e=>{const st=e.start||'';const d=st.slice(0,10);if(!d)return;
      (byDay[d]=byDay[d]||[]).push({when_iso:st.includes('T')?st:(d+'T00:00'),text:e.summary,_g:true,gid:e.id,link:e.link,all_day:e.all_day});});
  }catch(e){}
  const MONTHS=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  $('#cal-title').textContent=MONTHS[calM]+' '+calY;const grid=$('#calgrid');grid.textContent='';
  ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'].forEach(d=>grid.appendChild(el('div','cal-dow',d)));
  const first=new Date(calY,calM,1).getDay(),days=new Date(calY,calM+1,0).getDate();
  const tn=new Date(),tstr=ymd(tn.getFullYear(),tn.getMonth(),tn.getDate());
  for(let i=0;i<first;i++)grid.appendChild(el('div','cal-cell empty'));
  for(let d=1;d<=days;d++){const ds=ymd(calY,calM,d);const cell=el('div','cal-cell'+(ds===tstr?' today':''));
    cell.appendChild(el('div','cal-num',String(d)));const list=(byDay[ds]||[]).slice().sort((a,b)=>a.when_iso.localeCompare(b.when_iso));
    list.slice(0,3).forEach(r=>{const lbl=(r._g&&r.all_day)?'dia todo':r.when_iso.slice(11,16);const ev=el('div','cal-ev'+(r._g?' g':''),lbl+' '+r.text);ev.title=(r._g?'Google · ':'')+r.text;ev.onclick=e=>{e.stopPropagation();r._g?calGoogle(r):calEdit(r);};cell.appendChild(ev);});
    if(list.length>3){const mo=el('div','cal-more','+'+(list.length-3)+' mais');mo.onclick=e=>{e.stopPropagation();calList(ds,list);};cell.appendChild(mo);}
    cell.onclick=()=>calAdd(ds);grid.appendChild(cell);}}
function calFmtDay(ds){return ds.split('-').reverse().join('/');}
function calAdd(ds){openForm('Novo evento · '+calFmtDay(ds),[
    {key:'text',label:'Evento',placeholder:'...'},
    {key:'time',label:'Hora',value:'09:00'},
    {key:'where',label:'Onde',select:[{v:'ev',l:'Lembrete da E.V.'},{v:'g',l:'Google Calendar'}],value:'ev'},
    {key:'recur',label:'Repetir (só na E.V.)',select:RECUR,value:''}],
  async v=>{if(!v.text)return;
    if(v.where==='g'){toast('Criando no Google...');const j=await (await fetch('/api/gcal/create',{method:'POST',headers:H(),body:JSON.stringify({summary:v.text,start:ds+'T'+(v.time||'09:00')})})).json();toast(j.ok?'Evento criado no Google Calendar.':(j.msg||'Falha ao criar.'));loadCal();return;}
    await fetch('/api/reminders',{method:'POST',headers:H(),body:JSON.stringify({text:v.text,when:ds+'T'+(v.time||'09:00'),recur:v.recur})});loadCal();loadRem();loadPanel();});}
function calGoogle(r){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle','Evento do Google'));
  card.appendChild(el('div','mconf',r.text));
  const when=el('div','');when.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:12px;margin:4px 0 2px';
  when.textContent=r.all_day?'dia todo':r.when_iso.replace('T',' ').slice(0,16);card.appendChild(when);
  const bar=el('div','mbar');
  const del=el('button','mbtn2','Apagar');del.style.marginRight='auto';del.onclick=async()=>{m.classList.remove('on');if(await confirmDialog('Apagar este evento do Google Calendar?')){const j=await (await fetch('/api/gcal/delete',{method:'POST',headers:H(),body:JSON.stringify({id:r.gid})})).json();toast(j.ok?'Evento apagado.':'Falha ao apagar.');loadCal();}};
  bar.appendChild(del);
  if(r.link){const op=el('button','mbtn2','Abrir no Google');op.onclick=()=>window.open(r.link,'_blank');bar.appendChild(op);}
  const c=el('button','mbtn','Fechar');c.onclick=()=>m.classList.remove('on');bar.appendChild(c);
  card.appendChild(bar);m.appendChild(card);m.classList.add('on');}
function calEdit(r){const ds=r.when_iso.slice(0,10),tm=r.when_iso.slice(11,16)||'09:00';
  openForm('Editar evento',[
    {key:'text',label:'Evento',value:r.text},
    {key:'date',label:'Data (AAAA-MM-DD)',value:ds},
    {key:'time',label:'Hora',value:tm},
    {key:'recur',label:'Repetir',select:RECUR,value:r.recur||''}],
  async v=>{if(!v.text)return;await fetch('/api/reminders/update',{method:'POST',headers:H(),body:JSON.stringify({id:r.id,text:v.text,when:(v.date||ds)+'T'+(v.time||'09:00'),recur:v.recur})});loadCal();loadRem();loadPanel();},
  async()=>{if(await confirmDialog('Apagar este evento?')){await fetch('/api/reminders/delete',{method:'POST',headers:H(),body:JSON.stringify({id:r.id})});loadCal();loadRem();loadPanel();}});}
function calList(ds,list){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle','Eventos · '+calFmtDay(ds)));
  list.forEach(r=>{const row=el('label','mrow');row.style.cursor='pointer';
    const lbl=(r._g&&r.all_day)?'dia todo':r.when_iso.slice(11,16);
    row.appendChild(el('span','',lbl+' · '+(r._g?'Google · ':'')+r.text));
    row.onclick=()=>{m.classList.remove('on');r._g?calGoogle(r):calEdit(r);};card.appendChild(row);});
  const bar=el('div','mbar');const c=el('button','mbtn2','Fechar');c.onclick=()=>m.classList.remove('on');
  const add=el('button','mbtn','Novo evento');add.onclick=()=>{m.classList.remove('on');calAdd(ds);};
  bar.appendChild(c);bar.appendChild(add);card.appendChild(bar);m.appendChild(card);m.classList.add('on');}
$('#cal-prev').onclick=()=>{calM--;if(calM<0){calM=11;calY--;}loadCal();};
$('#cal-next').onclick=()=>{calM++;if(calM>11){calM=0;calY++;}loadCal();};
function toast(msg){let t=document.getElementById('_toast');if(!t){t=el('div','');t.id='_toast';t.style.cssText='position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:var(--elev);border:1px solid var(--line-2);color:var(--fg);padding:11px 17px;border-radius:11px;font-size:13px;z-index:9999;box-shadow:0 8px 30px rgba(0,0,0,.45);max-width:82vw;text-align:center;transition:opacity .3s';document.body.appendChild(t);}
  t.textContent=msg;t.style.opacity='1';clearTimeout(t._h);t._h=setTimeout(()=>{t.style.opacity='0';},4000);}
function openEmail(){openForm('Enviar email',[
  {key:'to',label:'Para',placeholder:'fulano@email.com'},
  {key:'subject',label:'Assunto'},
  {key:'body',label:'Mensagem',type:'textarea'}],
  async v=>{if(!v.to||!v.body){toast('Preencha destinatário e mensagem.');return;}
    toast('Enviando email...');
    try{const j=await (await fetch('/api/email',{method:'POST',headers:H(),body:JSON.stringify({to:v.to,subject:v.subject,body:v.body})})).json();
      toast(j.msg||(j.ok?'Email enviado.':'Falha ao enviar.'));}catch(e){toast('Sem conexão ao enviar o email.');}});}
function openMsg(){openForm('Mensagem no meu Telegram',[
  {key:'text',label:'Mensagem',type:'textarea',placeholder:'texto que chega no seu Telegram'}],
  async v=>{if(!v.text)return;
    try{const j=await (await fetch('/api/notify',{method:'POST',headers:H(),body:JSON.stringify({text:v.text})})).json();
      toast(j.msg||(j.ok?'Mensagem enviada.':'Falha ao enviar.'));}catch(e){toast('Sem conexão ao enviar a mensagem.');}});}
$('#cal-email').onclick=()=>openEmail();
$('#cal-msg').onclick=()=>openMsg();
$('#cal-email').prepend(ficon('mail'));$('#cal-msg').prepend(ficon('send'));window.lucide&&lucide.createIcons();
async function recDel(url,id,reload){await fetch(url,{method:'POST',headers:H(),body:JSON.stringify({id})});reload();loadPanel();}
function subline(txt){const d=el('div','',txt);d.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:2px';return d;}
async function loadExp(){try{const items=(await (await fetch('/api/expenses',{headers:H()})).json()).items||[];
  window._ecats=[...new Set(items.map(x=>x.category))];
  const by={};let tot=0;items.forEach(x=>{by[x.category]=(by[x.category]||0)+x.amount;tot+=x.amount;});
  const ch=$('#expchart');ch.textContent='';const cats=Object.entries(by).sort((a,b)=>b[1]-a[1]);const mx=Math.max(1,...cats.map(c=>c[1]));
  cats.forEach(([c,v])=>{const row=el('div','bar-row');row.appendChild(el('div','bar-lbl',c));const tr=el('div','bar-track');const fl=el('div','bar-fill');fl.style.width=(v/mx*100)+'%';tr.appendChild(fl);row.appendChild(tr);row.appendChild(el('div','bar-val','R$'+v.toFixed(0)));ch.appendChild(row);});
  if(cats.length)ch.appendChild(el('div','tv-empty','Total (60d): R$'+tot.toFixed(2)));
  const box=$('#explist');box.textContent='';if(!items.length){box.appendChild(el('div','tv-empty','Nenhum gasto registrado.'));return;}
  items.slice().reverse().forEach(x=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',x.description));t.appendChild(subline(x.category+' · '+((x.created||'').slice(0,10))));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+x.amount.toFixed(0);
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editExp(x);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/expenses/delete',{id:x.id},'/api/expenses',{amount:x.amount,description:x.description,category:x.category},loadExp,'Gasto');
    row.appendChild(t);row.appendChild(val);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editExp(x){openForm('Editar gasto',[
  {key:'amount',label:'Valor (R$)',value:String(x.amount)},
  {key:'description',label:'Descrição',value:x.description},
  {key:'category',label:'Categoria',value:x.category,options:window._ecats||[]}],
  async v=>{await fetch('/api/expenses/update',{method:'POST',headers:H(),body:JSON.stringify({id:x.id,amount:v.amount,description:v.description,category:v.category})});loadExp();loadPanel();});}
$('#expform').onsubmit=async e=>{e.preventDefault();const amount=$('#exp-amt').value.trim();if(!amount)return;
  await fetch('/api/expenses',{method:'POST',headers:H(),body:JSON.stringify({amount,description:$('#exp-desc').value.trim(),category:$('#exp-cat').value.trim()||'geral'})});
  $('#exp-amt').value='';$('#exp-desc').value='';loadExp();loadPanel();};
async function loadRem(){try{const items=(await (await fetch('/api/reminders',{headers:H()})).json()).items||[];const box=$('#remlist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhum lembrete em aberto.'));return;}
  items.forEach(r=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',r.text));
    const meta=(r.when_iso?r.when_iso.replace('T',' ').slice(0,16):'')+(r.recur?((r.when_iso?' · ':'')+'repete '+recurShort(r.recur)):'');
    if(meta)t.appendChild(subline(meta));
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editRem(r);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/reminders/delete',{id:r.id},'/api/reminders',{text:r.text,when:r.when_iso||'',recur:r.recur||''},loadRem,'Lembrete');
    row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function recurShort(r){return {daily:'diário',weekly:'semanal',monthly:'mensal'}[r]||r;}
function editRem(r){openForm('Editar lembrete',[
  {key:'text',label:'Lembrar de',value:r.text},
  {key:'when',label:'Quando (AAAA-MM-DDTHH:MM)',value:r.when_iso||''},
  {key:'recur',label:'Repetir',select:RECUR,value:r.recur||''}],
  async v=>{if(!v.text)return;await fetch('/api/reminders/update',{method:'POST',headers:H(),body:JSON.stringify({id:r.id,text:v.text,when:v.when,recur:v.recur})});loadRem();loadCal();loadPanel();});}
$('#remform').onsubmit=async e=>{e.preventDefault();const text=$('#rem-text').value.trim();if(!text)return;
  await fetch('/api/reminders',{method:'POST',headers:H(),body:JSON.stringify({text,when:$('#rem-when').value||'',recur:$('#rem-recur').value})});$('#rem-text').value='';$('#rem-when').value='';$('#rem-recur').value='';loadRem();loadPanel();};
async function loadMem(){try{const items=(await (await fetch('/api/facts',{headers:H()})).json()).items||[];const box=$('#memlist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhuma memória ainda.'));return;}
  items.forEach(f=>{const row=el('div','tv-row');row.appendChild(el('div','txt',f.fact));
    const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editMem(f);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/facts/delete',{id:f.id},'/api/facts',{text:f.fact},loadMem,'Memória');
    row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editMem(f){openForm('Editar memória',[
  {key:'text',label:'Memória',value:f.fact,type:'textarea'}],
  async v=>{if(!v.text)return;await fetch('/api/facts/update',{method:'POST',headers:H(),body:JSON.stringify({id:f.id,text:v.text})});loadMem();});}
$('#memform').onsubmit=async e=>{e.preventDefault();const text=$('#mem-text').value.trim();if(!text)return;
  await fetch('/api/facts',{method:'POST',headers:H(),body:JSON.stringify({text})});$('#mem-text').value='';loadMem();loadPanel();};
async function loadKB(){try{const d=await (await fetch('/api/kb',{headers:H()})).json();const box=$('#kblist');box.textContent='';
  if(!d.sources||!d.sources.length){box.appendChild(el('div','tv-empty','Nada na base ainda. Adicione uma URL, arquivo ou texto acima.'));return;}
  const files=new Set(d.files||[]);
  d.sources.forEach(s=>{const row=el('div','tv-row');const t=el('div','txt');
    if(/^https?:\/\//.test(s.source)){const a=document.createElement('a');a.href=s.source;a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=s.source;t.appendChild(a);}else t.appendChild(el('div','',s.source));
    const sub=el('div','');sub.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:2px';sub.textContent=s.chunks+' trechos'+(files.has(s.source)?' · arquivo':'');t.appendChild(sub);
    row.appendChild(t);
    if(files.has(s.source)){const op=el('button','tv-ic');op.title='abrir';op.appendChild(ficon('external-link'));op.onclick=()=>kbOpen(s.source,false);
      const dw=el('button','tv-ic');dw.title='baixar';dw.appendChild(ficon('download'));dw.onclick=()=>kbOpen(s.source,true);row.appendChild(op);row.appendChild(dw);}
    const dl=el('button','tv-ic');dl.title='remover';dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog('Remover "'+s.source+'" da base?'))kbDel(s.source);};
    row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
async function kbOpen(source,download){try{const r=await fetch('/api/kb/file?source='+encodeURIComponent(source),{headers:H()});if(!r.ok){sys('Arquivo não encontrado.');return;}
  const url=URL.createObjectURL(await r.blob());
  if(download){const a=document.createElement('a');a.href=url;a.download=source;document.body.appendChild(a);a.click();a.remove();}else window.open(url,'_blank');
  setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){sys('Não consegui abrir o arquivo.');}}
async function kbDel(source){await fetch('/api/kb/delete',{method:'POST',headers:H(),body:JSON.stringify({source})});loadKB();loadPanel();}
$('#kb-urlf').onsubmit=e=>{e.preventDefault();const url=$('#kb-url').value.trim();if(!url)return;
  const def=url.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,50);
  openForm('Indexar página',[{key:'name',label:'Nome (pra identificar)',value:def},{key:'url',label:'URL',value:url}],async v=>{
    if(!v.url)return;$('#kb-fmsg').textContent='indexando...';
    const j=await (await fetch('/api/kb/url',{method:'POST',headers:H(),body:JSON.stringify({url:v.url,name:v.name})})).json();
    $('#kb-fmsg').textContent=j.msg||'';$('#kb-url').value='';loadKB();loadPanel();});};
$('#kb-textf').onsubmit=async e=>{e.preventDefault();const title=$('#kb-title').value.trim()||'Nota';const text=$('#kb-text').value.trim();if(!text)return;$('#kb-fmsg').textContent='indexando...';
  const j=await (await fetch('/api/kb/text',{method:'POST',headers:H(),body:JSON.stringify({title,text})})).json();$('#kb-fmsg').textContent=j.msg||'';$('#kb-title').value='';$('#kb-text').value='';loadKB();loadPanel();};
$('#kb-file').onchange=e=>{const f=e.target.files[0];if(!f)return;e.target.value='';
  openForm('Nomear arquivo',[{key:'name',label:'Nome (pra identificar)',value:f.name}],async v=>{
    $('#kb-fmsg').textContent='enviando...';const fd=new FormData();fd.append('file',f);if(v.name)fd.append('title',v.name);
    try{const j=await (await fetch('/api/kb/upload',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();$('#kb-fmsg').textContent=j.msg||'ok';}catch(x){$('#kb-fmsg').textContent='erro no upload';}
    loadKB();loadPanel();});};
async function loadTasks(){try{const d=await (await fetch('/api/tasks',{headers:H()})).json();const box=$('#tasklist');box.textContent='';
  window._cats=[...new Set((d.tasks||[]).map(t=>t.category))];
  const g={};(d.tasks||[]).forEach(t=>{(g[t.category]=g[t.category]||[]).push(t);});
  if(!d.tasks||!d.tasks.length){box.appendChild(el('div','tv-empty','Nenhuma tarefa em aberto. Crie uma acima.'));return;}
  Object.keys(g).sort().forEach(cat=>{const chd=el('div','tv-cat',cat);
    chd.ondragover=e=>{e.preventDefault();chd.classList.add('drop');};chd.ondragleave=()=>chd.classList.remove('drop');
    chd.ondrop=async e=>{e.preventDefault();chd.classList.remove('drop');const id=e.dataTransfer.getData('text/plain');
      if(id){await fetch('/api/tasks/update',{method:'POST',headers:H(),body:JSON.stringify({id:+id,category:cat})});loadTasks();loadPanel();}};
    box.appendChild(chd);
    g[cat].forEach(t=>{const row=el('div','tv-row');row.draggable=true;row.ondragstart=e=>e.dataTransfer.setData('text/plain',String(t.id));
      const done=el('button','tv-ic');done.title='concluir';done.appendChild(ficon('check'));done.onclick=()=>taskAction('complete',t.id);
      const txt=el('div','txt');const parts=t.text.split(/\s+(?=\d+[.)]\s)/);if(parts.length>1)parts.forEach(p=>txt.appendChild(el('div','',p)));else txt.appendChild(el('div','',t.text));
      const metas=[];if(t.recur)metas.push('repete '+recurShort(t.recur));
      const overdue=t.due&&new Date(t.due)<new Date();
      if(t.due)metas.push((t.recur?'próxima ':(overdue?'atrasada · ':'vence '))+fmtDue(t.due));
      if(metas.length){const s=subline(metas.join(' · '));if(overdue&&!t.recur){s.style.color='var(--fg)';s.style.fontWeight='600';}txt.appendChild(s);}
      const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editTask(t);
      const dl=el('button','tv-ic');dl.title='apagar';dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/tasks/delete',{id:t.id},'/api/tasks',{text:t.text,category:t.category,recur:t.recur||'',due:t.due||''},loadTasks,'Tarefa');
      row.appendChild(done);row.appendChild(txt);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});});
  window.lucide&&lucide.createIcons();}catch(e){}}
async function taskAction(op,id){await fetch('/api/tasks/'+op,{method:'POST',headers:H(),body:JSON.stringify({id})});loadTasks();loadPanel();}
function fmtDue(iso){const d=new Date(iso);if(isNaN(d))return iso;return d.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});}
function editTask(t){openForm('Editar tarefa',[
  {key:'text',label:'Descrição',value:t.text,type:'textarea'},
  {key:'category',label:'Categoria',value:t.category,options:window._cats||[],placeholder:'ex: faculdade'},
  {key:'due',label:'Vencimento (opcional)',value:(t.due||'').slice(0,16),type:'datetime'},
  {key:'recur',label:'Repetir',select:RECUR,value:t.recur||''}],
  async v=>{if(!v.text)return;await fetch('/api/tasks/update',{method:'POST',headers:H(),body:JSON.stringify({id:t.id,text:v.text,category:v.category||t.category,due:v.due,recur:v.recur})});loadTasks();loadPanel();});}
$('#taskform').onsubmit=async e=>{e.preventDefault();const text=$('#task-text').value.trim();const cat=$('#task-cat').value.trim()||'geral';const recur=$('#task-recur').value;const due=$('#task-due').value;
  if(!text)return;await fetch('/api/tasks',{method:'POST',headers:H(),body:JSON.stringify({text,category:cat,recur,due})});$('#task-text').value='';$('#task-due').value='';$('#task-recur').value='';loadTasks();loadPanel();};
// per-tab search filter
function filterRows(box,q){if(!box)return;q=(q||'').trim().toLowerCase();let cur=null,shown=0;
  [...box.children].forEach(k=>{
    if(k.classList.contains('tv-cat')){if(cur)cur.style.display=shown?'':'none';cur=k;shown=0;}
    else if(k.classList.contains('tv-row')){const m=k.textContent.toLowerCase().includes(q);k.style.display=m?'':'none';if(m)shown++;}
  });if(cur)cur.style.display=shown?'':'none';}
[['tasks-search','tasklist'],['exp-search','explist'],['rem-search','remlist'],['mem-search','memlist'],['kb-search','kblist'],['lnk-search','lnklist'],['hab-search','hablist'],['jou-search','joulist'],['sub-search','sublist'],['orc-search','orclist'],['mon-search','monlist'],['act-search','actlist']].forEach(p=>{const inp=document.getElementById(p[0]);if(inp)inp.oninput=()=>filterRows(document.getElementById(p[1]),inp.value);});
// command palette (Ctrl/Cmd+K)
const CK=$('#cmdk'),CKI=$('#ck-input'),CKL=$('#ck-list');let ckItems=[],ckSel=0;
function ckBuild(){const nav=[['Conversa',()=>switchView('chat')],['Tarefas',()=>switchView('tasks')],['Gastos',()=>switchView('exp')],['Lembretes',()=>switchView('rem')],['Agenda',()=>switchView('cal')],['Memórias',()=>switchView('mem')],['Links',()=>switchView('lnk')],['Hábitos',()=>switchView('hab')],['Diário',()=>switchView('jou')],['Assinaturas',()=>switchView('sub')],['Orçamentos',()=>switchView('orc')],['Monitores',()=>switchView('mon')],['Base',()=>switchView('kb')],['Pomodoro',()=>openPomo(25)],['Voz ao vivo',()=>$('#vcopen').click()],['Chaves de API',()=>openKeys()]];
  return nav.map(n=>({k:'ir',label:n[0],desc:'abrir',run:n[1]})).concat((COMMANDS||[]).map(c=>({k:'/'+c.name,label:c.name,desc:c.desc,run:()=>runCmd(c.name)})));}
function ckRender(q){ckItems=ckBuild().filter(i=>(i.label+' '+i.k+' '+i.desc).toLowerCase().includes((q||'').toLowerCase())).slice(0,40);ckSel=0;CKL.textContent='';
  ckItems.forEach((i,ix)=>{const r=el('div','ck-item'+(ix===0?' sel':''));r.appendChild(el('span','ck-k',i.k));r.appendChild(el('span','',i.label));r.appendChild(el('span','ck-d',i.desc||''));r.onclick=()=>{ckClose();i.run();};CKL.appendChild(r);});}
function ckOpen(){CK.classList.add('on');CKI.value='';ckRender('');setTimeout(()=>CKI.focus(),40);}
function ckClose(){CK.classList.remove('on');}
CKI.addEventListener('input',()=>ckRender(CKI.value));
CKI.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();ckSel=Math.min(ckItems.length-1,ckSel+1);}else if(e.key==='ArrowUp'){e.preventDefault();ckSel=Math.max(0,ckSel-1);}else if(e.key==='Enter'){e.preventDefault();const it=ckItems[ckSel];if(it){ckClose();it.run();}return;}else if(e.key==='Escape'){ckClose();return;}else return;
  [...CKL.children].forEach((c,i)=>c.classList.toggle('sel',i===ckSel));CKL.children[ckSel]&&CKL.children[ckSel].scrollIntoView({block:'nearest'});});
CK.onclick=e=>{if(e.target===CK)ckClose();};
window.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();CK.classList.contains('on')?ckClose():ckOpen();}});
setInterval(()=>{$('#s-clock').textContent=new Date().toTimeString().slice(0,8);},1000);
const GREETING='Bem-vindo de volta, Ryan. Sistemas online, tudo pronto pra você.';
async function validate(tok){try{return (await fetch('/api/panel',{headers:{'Authorization':'Bearer '+tok}})).status===200;}catch(e){return false;}}
function welcome(){$('#welcome-txt').textContent=GREETING;$('#welcome').classList.add('on');window.lucide&&lucide.createIcons();
  fetch('/api/greeting',{headers:H()}).then(r=>r.ok?r.blob():null).then(b=>{if(b&&b.size>0)new Audio(URL.createObjectURL(b)).play().catch(()=>{});}).catch(()=>{});
  setTimeout(()=>$('#welcome').classList.remove('on'),3200);}
// --- PWA + notifications + live sync (Lote A) ---
async function initPWA(){
  try{if('serviceWorker' in navigator)await navigator.serviceWorker.register('/sw.js');}catch(e){}
  if('Notification' in window&&Notification.permission==='granted')subscribePush();
  // ask for notification permission on the first tap (a gesture — browsers require it)
  window.addEventListener('pointerdown',()=>{try{if('Notification' in window&&Notification.permission==='default')Notification.requestPermission().then(p=>{if(p==='granted')subscribePush();});}catch(e){}},{once:true});
}
function urlB64ToUint8(b){const pad='='.repeat((4-b.length%4)%4);const s=(b+pad).replace(/-/g,'+').replace(/_/g,'/');const raw=atob(s);return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)));}
async function subscribePush(){try{
  if(!('serviceWorker' in navigator)||!('PushManager' in window))return;
  if(Notification.permission!=='granted')return;
  const reg=await navigator.serviceWorker.ready;
  let sub=await reg.pushManager.getSubscription();
  if(!sub){const k=await (await fetch('/api/push/key',{headers:H()})).json();if(!k.key)return;
    sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlB64ToUint8(k.key)});}
  await fetch('/api/push/subscribe',{method:'POST',headers:H(),body:JSON.stringify(sub)});
}catch(e){}}
let _notified=new Set();try{_notified=new Set(JSON.parse(localStorage.getItem('ev_notified')||'[]'));}catch(e){}
function _saveNotified(){try{localStorage.setItem('ev_notified',JSON.stringify([..._notified].slice(-200)));}catch(e){}}
function notify(title,body){try{
  if(!('Notification' in window)||Notification.permission!=='granted')return;
  if(navigator.serviceWorker&&navigator.serviceWorker.ready){navigator.serviceWorker.ready.then(r=>r.showNotification(title,{body,icon:'/favicon.svg',badge:'/favicon.svg',tag:body})).catch(()=>{try{new Notification(title,{body});}catch(e){}});}
  else new Notification(title,{body});
}catch(e){}}
const _VLOAD={tasks:()=>loadTasks(),exp:()=>loadExp(),rem:()=>loadRem(),mem:()=>loadMem(),kb:()=>loadKB(),cal:()=>loadCal(),lnk:()=>loadLinks(),hab:()=>loadHabits(),jou:()=>loadJournal(),sub:()=>loadSub(),orc:()=>loadOrc(),mon:()=>loadMon(),act:()=>loadAct()};
async function pollTick(){try{
  const items=(await (await fetch('/api/reminders',{headers:H()})).json()).items||[];
  const now=Date.now();
  items.forEach(r=>{if(!r.when_iso)return;const due=new Date(r.when_iso).getTime();const key=r.id+'@'+r.when_iso;
    if(due<=now&&(now-due)<3600000&&!_notified.has(key)){_notified.add(key);_saveNotified();notify('⏰ Lembrete',r.text);}});
  loadPanel();
  // live sync: refresh the current data view, unless a modal is open or the user is typing
  const modalOpen=$('#modal').classList.contains('on');
  const typing=['INPUT','TEXTAREA','SELECT'].includes((document.activeElement||{}).tagName);
  if(!modalOpen&&!typing&&curView&&_VLOAD[curView])_VLOAD[curView]();
}catch(e){}}
let _pollTimer=null;
function startPoll(){if(_pollTimer)return;_pollTimer=setInterval(pollTick,90000);pollTick();}  // fallback; SSE drives instant updates
let _es=null;
function startEvents(){try{if(_es)_es.close();
  _es=new EventSource('/api/events?k='+encodeURIComponent(token));
  _es.onmessage=()=>pollTick();   // any DB change (incl. from Telegram) -> refresh now
}catch(e){}}
// --- Batch C: image in chat, global search, undo ---
function youImg(caption,url){const d=el('div','msg you');const img=document.createElement('img');img.className='msg-img';img.src=url;d.appendChild(img);if(caption){const c=el('div','',caption);c.style.marginTop='6px';d.appendChild(c);}log.appendChild(d);log.scrollTop=log.scrollHeight;}
let _pendingImg=null;
function setPendingImg(f){_pendingImg=f;const p=$('#imgprev');p.innerHTML='';if(!f){p.style.display='none';return;}
  const img=document.createElement('img');img.src=URL.createObjectURL(f);
  const x=el('button','ip-x','×');x.title='remover';x.onclick=()=>setPendingImg(null);
  p.appendChild(img);p.appendChild(el('span','ip-name',f.name+' — escreva algo (opcional) e envie'));p.appendChild(x);p.style.display='flex';if(txt)txt.focus();}
async function sendImage(file,caption){if(!file)return;youImg(caption,URL.createObjectURL(file));const p=thinking();setState('thinking');
  try{const fd=new FormData();fd.append('image',file);if(caption)fd.append('text',caption);fd.append('thread',thread);
    const j=await (await fetch('/api/vision',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    p.remove();ev(j.reply||'(sem resposta)');speak(j.reply);}catch(e){p.remove();sys('Falha ao enviar a imagem.');}finally{setState();}}
$('#imgbtn').onclick=()=>$('#imgfile').click();
$('#imgfile').onchange=e=>{const f=e.target.files[0];if(f)setPendingImg(f);e.target.value='';};
(function(){const cv=$('#chatview');if(!cv)return;
  ['dragover','dragenter'].forEach(n=>cv.addEventListener(n,e=>{e.preventDefault();cv.classList.add('drag');}));
  ['dragleave','drop'].forEach(n=>cv.addEventListener(n,e=>{e.preventDefault();cv.classList.remove('drag');}));
  cv.addEventListener('drop',e=>{const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f&&f.type.startsWith('image/'))setPendingImg(f);});})();
$('#gsearch').onclick=()=>openForm('Buscar em tudo',[{key:'q',label:'Buscar',placeholder:'tarefas, gastos, memórias, base...'}],v=>{if(!v.q)return;switchView('chat');runCmd('procurar '+v.q);});
function toastUndo(msg,onUndo){let t=document.getElementById('_toast');if(!t){t=el('div','');t.id='_toast';t.style.cssText='position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:var(--elev);border:1px solid var(--line-2);color:var(--fg);padding:11px 17px;border-radius:11px;font-size:13px;z-index:9999;box-shadow:0 8px 30px rgba(0,0,0,.45);display:flex;align-items:center;gap:14px;transition:opacity .3s';document.body.appendChild(t);}
  t.textContent='';t.appendChild(document.createTextNode(msg));const b=el('button','','Desfazer');b.style.cssText='background:none;border:none;color:var(--fg);font:inherit;font-weight:700;cursor:pointer;text-decoration:underline';b.onclick=()=>{clearTimeout(t._h);t.style.opacity='0';onUndo();};t.appendChild(b);
  t.style.opacity='1';clearTimeout(t._h);t._h=setTimeout(()=>t.style.opacity='0',6000);}
async function delU(delUrl,delBody,recUrl,recBody,reload,label){await fetch(delUrl,{method:'POST',headers:H(),body:JSON.stringify(delBody)});reload();loadPanel();
  toastUndo((label||'Item')+' apagado',async()=>{await fetch(recUrl,{method:'POST',headers:H(),body:JSON.stringify(recBody)});reload();loadPanel();});}
async function startApp(){try{COMMANDS=(await (await fetch('/api/commands',{headers:H()})).json()).commands;}catch(e){}
  scopeEl.textContent='Conversa · '+thread;await loadFolders();await loadHistory();await loadConfig();loadPanel();
  initPWA();startPoll();startEvents();window.lucide&&lucide.createIcons();}
function enter(){$('#login').classList.remove('on');startApp();welcome();}
async function doLogin(){const inp=$('#login-token');const tok=((inp&&inp.value.trim())||token);if(!tok){$('#login-err').textContent='Informe o token.';if(inp)inp.style.display='block';return;}
  $('#login-err').textContent='verificando...';if(!(await validate(tok))){$('#login-err').textContent='Token inválido.';token='';localStorage.removeItem('ev_token');if(inp)inp.style.display='block';return;}
  token=tok;localStorage.setItem('ev_token',tok);enter();}
(async function boot(){
  if(token && await validate(token)){enter();return;}          // já logado -> entra direto
  token='';const inp=$('#login-token');if(inp)inp.style.display='block';$('#login').classList.add('on');window.lucide&&lucide.createIcons();
  $('#login-btn').onclick=doLogin;if(inp)inp.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});setTimeout(()=>{$('#login-btn').focus();},60);})();
</script></body></html>"""


def create_app(config: Config, brain: Brain | None = None):
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import HTMLResponse

    import time as _time
    boot = _time.monotonic()
    memory = Memory(config.db_path)
    brain = brain or Brain(config, memory)
    commands = Commands(config, memory)
    owner = str(config.owner_id) if config.owner_id is not None else "web"
    app = FastAPI(title="E.V.")

    def _check(auth):
        tok = (auth or "").removeprefix("Bearer ").strip()
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")

    async def _body(request):
        try:
            return await request.json()
        except Exception:
            return {}

    def _recurval(v, allow_clear=False):
        """Normalize a recurrence value to 'daily'/'weekly'/'monthly'. Returns
        None (skip) for invalid/absent, or '' to clear when allow_clear."""
        v = (v or "").strip()
        if v in ("daily", "weekly", "monthly"):
            return v
        return "" if allow_clear else None

    def _folders():
        raw = memory.get_setting("web_folders")
        try:
            fs = json.loads(raw) if raw else None
        except Exception:
            fs = None
        return fs if isinstance(fs, list) and fs else list(_DEFAULT_FOLDERS)

    def _conv(thread):
        t = (thread or "geral").strip() or "geral"
        return f"web:{t}"

    def _status_text():
        rep = health.system_report(config, memory)
        keys = health.keys_status(config)
        out = ["🩺 Status da E.V.", ""]
        if "disk_used_pct" in rep:
            out.append(f"Disco: {rep['disk_used_pct']}% · {rep.get('disk_free_gb','?')} GB livres")
        if "mem_used_pct" in rep:
            out.append(f"Memória: {rep['mem_used_pct']}%")
        out.append(f"Banco: {'ok' if rep.get('db_query_ok') else 'erro'} ({rep.get('db_size_mb',0)} MB)")
        out.append("")
        out.append("Chaves / integrações:")
        for k in keys:
            mark = "ok" if k["ok"] else (k["note"] or "não")
            out.append(f"- {k['name']}: {mark}")
        return "\n".join(out)

    async def run_command(cmd_str: str, thread=None) -> str:
        """Run a slash command from the web (data + interface commands)."""
        parts = (cmd_str or "").strip().split(None, 1)
        if not parts:
            return "Digite um comando."
        name = parts[0].lstrip("/").lower()
        rest = parts[1] if len(parts) > 1 else ""
        if name in ("limpar", "limparchat"):  # clear THIS folder's conversation
            memory.clear_conversation(_conv(thread))
            return "Conversa limpa nesta pasta."
        if name in commands.runnable():
            return commands.run(owner, name, rest)
        if name == "provedor":
            v = rest.strip().lower()
            if v in ("", "auto", "gemini", "groq", "openrouter", "ollama"):
                memory.set_setting("force_provider", "" if v in ("", "auto") else v)
                return f"Provedor: {v or 'auto'}." if v else "Provedor: automático."
            return "Uso: /provedor auto|gemini|groq|openrouter|ollama"
        if name == "status":
            return _status_text()
        if name == "modelo":
            from datetime import datetime, timezone
            usage = memory.usage_for_day(datetime.now(timezone.utc).date().isoformat())
            caps = {"gemini": 20, "groq": 1000, "openrouter": 1000}
            forced = memory.get_setting("force_provider") or "auto"
            out = [f"🧠 Principal: {brain.current_model()} (Gemini)"]
            if config.groq_api_key:
                out.append(f"Fallback: {config.groq_model} (Groq)")
            if config.openrouter_api_key:
                out.append(f"Fallback: {config.openrouter_model} (OpenRouter)")
            out.append(f"Provedor ativo: {forced}")
            out.append("")
            out.append("📊 Uso hoje (zera à meia-noite UTC):")
            for prov in ("gemini", "groq", "openrouter", "ollama"):
                used = usage.get(prov, 0)
                cap = caps.get(prov)
                if cap:
                    out.append(f"- {prov}: {used} usados · ~{max(0, cap - used)} restantes (de ~{cap})")
                elif prov == "ollama" and config.ollama_enabled:
                    out.append(f"- ollama: {used} usados · ilimitado")
            return "\n".join(out)
        if name == "ajuda":
            return commands.help()
        if name == "dados":
            summ = memory.storage_summary(owner)
            out = ["🗄️ Seus dados guardados:", ""]
            out += [f"- {s['label']}: {s['count']}" for s in summ]
            out.append("\nPra apagar por categoria, use as abas (Tarefas/Gastos/...) "
                       "ou o /dados no Telegram (com dupla confirmação pra apagar tudo).")
            return "\n".join(out)
        if name == "resumir":
            if not rest.lower().startswith("http"):
                return "Uso: /resumir <url>"
            try:
                text = await asyncio.to_thread(tools_mod.fetch_text, rest)
            except Exception as e:
                return f"Não consegui abrir a página ({str(e)[:80]})."
            if not text or len(text.strip()) < 80:
                return "Não achei texto útil nessa página."
            s = await brain.ask(
                "Você é a E.V. Resuma o artigo em português: um parágrafo de contexto "
                "e depois 3 a 6 bullets com os pontos principais.",
                f"Conteúdo de {rest}:\n\n{text[:12000]}")
            return s or "Não consegui resumir agora, tenta de novo?"
        if name == "quiz":
            chunk = memory.random_chunk(owner, rest or None)
            if not chunk:
                return "Base de conhecimento vazia. Adicione algo na aba Base primeiro."
            out = await brain.ask(
                "Você é um tutor. Com base no trecho, crie UMA pergunta de estudo "
                "objetiva e a resposta. Formato:\nPERGUNTA: <pergunta>\nRESPOSTA: <resposta>",
                f"Trecho de [{chunk['source']}]:\n{chunk['chunk']}")
            return out or "Não consegui gerar a pergunta agora."
        if name in ("foco", "exportar", "transcrever", "documento", "insights", "menu"):
            return (f"O /{name} é melhor no Telegram ou pela interface: use a aba/botão "
                    "correspondente (ex: Pomodoro, exportar no painel).")
        return commands.run(owner, name, rest)  # -> "não conheço"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        # never cache the HTML shell, so updates land immediately (no stale UI)
        return HTMLResponse(_PAGE, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    @app.get("/favicon.svg")
    async def favicon_svg():
        return Response(content=_FAVICON, media_type="image/svg+xml")

    @app.get("/favicon.ico")
    async def favicon_ico():
        return Response(content=_FAVICON, media_type="image/svg+xml")

    @app.get("/icon-192.png")
    async def icon192():
        return Response(content=_icon_png(192), media_type="image/png")

    @app.get("/icon-512.png")
    async def icon512():
        return Response(content=_icon_png(512), media_type="image/png")

    @app.get("/manifest.webmanifest")
    async def manifest():
        data = {
            "name": "E.V. — assistente pessoal", "short_name": "E.V.",
            "description": "Sua assistente E.V. — chat, voz, tarefas e agenda.",
            "start_url": "/", "scope": "/", "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#0a0a0a", "theme_color": "#0a0a0a",
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
                {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
            ],
        }
        return Response(content=json.dumps(data),
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    async def service_worker():
        return Response(content=_SERVICE_WORKER, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    _greet = []  # cache the welcome audio (edge-tts, no LLM) for the server's life

    @app.get("/api/greeting")
    async def greeting(request: Request):
        from fastapi import Response as R
        _check(request.headers.get("authorization"))
        if not _greet:
            phrase = "Bem-vindo de volta, Ryan. Sistemas online, tudo pronto pra você."
            try:
                mp3 = await voice_mod.synthesize(
                    phrase, config.voice, rate=config.voice_rate,
                    pitch=config.voice_pitch, fixes=config.voice_fixes)
                _greet.append(mp3)
            except Exception:
                _greet.append(b"")
        return R(content=_greet[0], media_type="audio/mpeg")

    @app.get("/api/health")
    async def health_ep():
        return {"ok": True}

    @app.get("/api/commands")
    async def commands_ep(request: Request):
        _check(request.headers.get("authorization"))
        return {"commands": [{"name": n, "desc": d} for n, d in COMMAND_LIST]}

    @app.get("/api/threads")
    async def threads_get(request: Request):
        _check(request.headers.get("authorization"))
        return {"threads": _folders()}

    @app.post("/api/threads")
    async def threads_post(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        name = (data.get("name") or "").strip().lower().replace(" ", "-").replace("/", "-")
        parent = (data.get("parent") or "").strip().lower()
        if name:
            path = f"{parent}/{name}" if parent else name
            fs = _folders()
            if path not in fs:
                fs.append(path)
                memory.set_setting("web_folders", json.dumps(fs))
        return {"threads": _folders()}

    @app.post("/api/threads/move")
    async def threads_move(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        path = (data.get("path") or "").strip().lower()
        parent = (data.get("parent") or "").strip().lower()  # "" = to root
        if not path or path == "geral" or parent == path or parent.startswith(path + "/"):
            return {"threads": _folders()}  # can't move into itself/descendant
        leaf = path.rsplit("/", 1)[-1]
        newpath = f"{parent}/{leaf}" if parent else leaf
        fs = _folders()
        if newpath != path and path in fs and newpath not in fs:
            out = []
            for f in fs:
                if f == path or f.startswith(path + "/"):
                    nf = newpath + f[len(path):]
                    memory.rename_conversation(_conv(f), _conv(nf))
                    out.append(nf)
                else:
                    out.append(f)
            memory.set_setting("web_folders", json.dumps(out))
        return {"threads": _folders()}

    @app.get("/api/history")
    async def history_ep(request: Request):
        _check(request.headers.get("authorization"))
        thread = request.query_params.get("thread", "geral")
        msgs = memory.recent_messages(_conv(thread), limit=50)
        return {"messages": msgs}

    @app.post("/api/chat")
    async def chat(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo. 🙂"}
        reply = await brain.respond(owner, conv_id=_conv(data.get("thread")), text=text)
        brain.pop_documents()
        brain.pop_actions()
        return {"reply": reply}

    @app.post("/api/chat/stream")
    async def chat_stream(request: Request):
        _check(request.headers.get("authorization"))
        from fastapi.responses import StreamingResponse
        import re as _re
        data = await _body(request)
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo."}
        reply = await brain.respond(owner, conv_id=_conv(data.get("thread")), text=text)
        brain.pop_documents()
        brain.pop_actions()

        async def gen():
            # progressive reveal of the computed reply (live-typing feel)
            for w in (_re.findall(r"\S+\s*", reply) or [reply]):
                yield w
                await asyncio.sleep(0.015)
        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    @app.post("/api/cmd")
    async def cmd(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        command = (data.get("command") or "").strip()
        thread = data.get("thread")
        reply = await run_command(command, thread)
        name = command.lstrip("/").split()[0].lower() if command else ""
        if name not in ("limpar", "limparchat"):  # don't re-log after clearing
            conv = _conv(thread)
            memory.add_message(conv, "user", "/" + command)
            memory.add_message(conv, "model", reply)
        return {"reply": reply}

    @app.post("/api/threads/delete")
    async def threads_delete(request: Request):
        _check(request.headers.get("authorization"))
        name = ((await _body(request)).get("name") or "").strip().lower()
        if name and name != "geral":
            fs = _folders()
            victims = [f for f in fs if f == name or f.startswith(name + "/")]
            if victims:
                memory.set_setting(
                    "web_folders", json.dumps([f for f in fs if f not in victims]))
                for v in victims:  # drop the folder and its subfolders' conversations
                    memory.clear_conversation(_conv(v))
        return {"threads": _folders()}

    @app.post("/api/threads/rename")
    async def threads_rename(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        old = (data.get("old") or "").strip().lower()
        new = (data.get("new") or "").strip().lower().replace(" ", "-").replace("/", "-")
        if old and new and old != "geral":
            parent = old.rsplit("/", 1)[0] if "/" in old else ""
            newpath = f"{parent}/{new}" if parent else new
            fs = _folders()
            if old in fs and newpath not in fs:
                out = []
                for f in fs:  # rename the folder AND all its descendants
                    if f == old or f.startswith(old + "/"):
                        nf = newpath + f[len(old):]
                        memory.rename_conversation(_conv(f), _conv(nf))
                        out.append(nf)
                    else:
                        out.append(f)
                memory.set_setting("web_folders", json.dumps(out))
        return {"threads": _folders()}

    _DEF_ACTIONS = ["buscar", "noticias", "clima", "relatorio", "status", "semana"]
    _DEF_STATS = ["tasks", "reminders", "expenses", "memories", "kb"]

    def _cfg_list(key, default):
        raw = memory.get_setting(key)
        try:
            v = json.loads(raw) if raw else None
        except Exception:
            v = None
        return v if isinstance(v, list) else list(default)

    @app.get("/api/config")
    async def cfg_get(request: Request):
        _check(request.headers.get("authorization"))
        return {"actions": _cfg_list("web_actions", _DEF_ACTIONS),
                "stats": _cfg_list("web_stats", _DEF_STATS)}

    @app.post("/api/config")
    async def cfg_set(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        if isinstance(data.get("actions"), list):
            memory.set_setting("web_actions", json.dumps(data["actions"][:24]))
        if isinstance(data.get("stats"), list):
            memory.set_setting("web_stats", json.dumps(data["stats"][:10]))
        return {"ok": True}

    # --- Tasks CRUD (dedicated panel) --------------------------------------
    @app.get("/api/tasks")
    async def tasks_get(request: Request):
        _check(request.headers.get("authorization"))
        memory.roll_due_tasks()  # keep recurring tasks rolled to their next occurrence
        return {"tasks": memory.open_tasks(owner)}

    @app.get("/api/activity")
    async def activity_get(request: Request):
        _check(request.headers.get("authorization"))
        cat = request.query_params.get("category") or None
        return {"items": memory.list_activity(owner, cat),
                "categories": memory.activity_categories(owner)}

    @app.get("/api/events")
    async def events(request: Request):
        # SSE — the browser's EventSource can't set headers, so the token comes as
        # a query param. Streams a tick whenever the DB is changed by ANY process
        # (e.g. the Telegram bot), so the web reflects it near-instantly.
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        from fastapi.responses import StreamingResponse
        import os as _os

        async def gen():
            # same open path as Memory (handles SQLCipher when EV_DB_KEY is set)
            conn, _row = Memory._connect(config.db_path, _os.getenv("EV_DB_KEY", "").strip())

            def _rev():
                return conn.execute("PRAGMA data_version").fetchone()[0]
            try:
                last = _rev()   # fast read, no thread hop needed
                yield "retry: 4000\n\ndata: ready\n\n"
                while True:
                    await asyncio.sleep(2)
                    try:
                        dv = _rev()
                    except Exception:
                        continue
                    if dv != last:
                        last = dv
                        yield f"data: {dv}\n\n"
                    else:
                        yield ": ping\n\n"   # keepalive; also detects client disconnect
            finally:
                conn.close()
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.get("/api/push/key")
    async def push_key(request: Request):
        _check(request.headers.get("authorization"))
        return {"key": config.vapid_public}

    @app.post("/api/push/subscribe")
    async def push_subscribe(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        ep = d.get("endpoint")
        if not ep:
            return {"ok": False}
        memory.add_push_sub(ep, json.dumps(d))
        return {"ok": True}

    @app.post("/api/push/unsubscribe")
    async def push_unsubscribe(request: Request):
        _check(request.headers.get("authorization"))
        ep = (await _body(request)).get("endpoint")
        if ep:
            memory.delete_push_sub(ep)
        return {"ok": True}

    @app.post("/api/push/test")
    async def push_test(request: Request):
        _check(request.headers.get("authorization"))
        from ..providers import push
        # owner passed so the test also shows up in the notification center
        n = await asyncio.to_thread(push.send_push, config, memory,
                                    "E.V.", "Notificação de teste funcionando.", "/", owner)
        return {"ok": n > 0, "sent": n}

    # --- notification center -----------------------------------------------
    @app.get("/api/notifications")
    async def notifs_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_notifications(owner),
                "unread": memory.unread_notifications(owner)}

    @app.post("/api/notifications/read")
    async def notifs_read(request: Request):
        _check(request.headers.get("authorization"))
        nid = (await _body(request)).get("id")
        memory.mark_notification_read(owner, int(nid) if nid else None)
        return {"ok": True, "unread": memory.unread_notifications(owner)}

    @app.post("/api/notifications/delete")
    async def notifs_delete(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_notification(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True, "unread": memory.unread_notifications(owner)}

    @app.post("/api/notifications/clear")
    async def notifs_clear(request: Request):
        _check(request.headers.get("authorization"))
        scope = (await _body(request)).get("scope")
        memory.clear_notifications(owner, only_read=(scope == "read"))
        return {"ok": True, "unread": memory.unread_notifications(owner)}

    @app.post("/api/tasks")
    async def tasks_create(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        text = (data.get("text") or "").strip()
        cat = (data.get("category") or "geral").strip() or "geral"
        if text:
            memory.add_task(owner, text, cat, recur=_recurval(data.get("recur")),
                            due=(data.get("due") or "").strip() or None)
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/update")
    async def tasks_update(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        recur = _recurval(data.get("recur"), allow_clear=True) if "recur" in data else None
        due = (data.get("due") or "").strip() if "due" in data else None
        memory.update_task(owner, int(data.get("id") or 0),
                           text=(data.get("text") or None),
                           category=(data.get("category") or None),
                           recur=recur, due=due)
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/complete")
    async def tasks_complete(request: Request):
        _check(request.headers.get("authorization"))
        memory.complete_task(owner, int((await _body(request)).get("id") or 0))
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/delete")
    async def tasks_delete(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_task(owner, int((await _body(request)).get("id") or 0))
        return {"tasks": memory.open_tasks(owner)}

    # --- Knowledge base ----------------------------------------------------
    @app.get("/api/kb")
    async def kb_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"sources": memory.list_sources(owner),
                "files": memory.kb_file_sources(owner)}

    @app.get("/api/kb/file")
    async def kb_file(request: Request):
        from urllib.parse import quote
        _check(request.headers.get("authorization"))
        f = memory.get_kb_file(owner, request.query_params.get("source", ""))
        if not f:
            raise HTTPException(status_code=404, detail="arquivo não encontrado")
        fn = f["filename"] or "arquivo"
        return Response(
            content=f["data"], media_type=f["mime"] or "application/octet-stream",
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(fn)}"},
        )

    @app.post("/api/kb/url")
    async def kb_url(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        url = (d.get("url") or "").strip()
        name = (d.get("name") or "").strip() or None
        if not url.lower().startswith("http"):
            return {"ok": False, "msg": "Informe uma URL válida (http...)."}
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_url, url, config, memory, owner, name)
            msg = f"{stored} trechos indexados" + (" (parcial)" if trunc else "") if stored else "Não achei texto útil."
            return {"ok": stored > 0, "msg": msg, "sources": memory.list_sources(owner)}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:120]}

    @app.post("/api/kb/text")
    async def kb_text(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        title = (d.get("title") or "Nota").strip()
        text = (d.get("text") or "").strip()
        if not text:
            return {"ok": False, "msg": "Texto vazio."}
        stored, trunc = await asyncio.to_thread(
            knowledge.ingest_text, text, title, config, memory, owner)
        return {"ok": stored > 0, "msg": f"{stored} trechos indexados",
                "sources": memory.list_sources(owner)}

    @app.post("/api/kb/upload")
    async def kb_upload(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("file")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhum arquivo enviado."}
        fname = f.filename or "arquivo"
        if not fname.lower().endswith(knowledge.READABLE_EXTS):
            return {"ok": False, "msg": "Só PDF, Word (.docx) ou texto (.txt/.md)."}
        title = (form.get("title") or "").strip() or None
        data = await f.read()
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_file, data, fname, config, memory, owner, title)
            label = title or fname
            if stored and len(data) <= 25_000_000:  # keep the original for download/open
                mime = getattr(f, "content_type", None) or "application/octet-stream"
                memory.save_kb_file(owner, label, fname, mime, data)
            msg = f"'{label}': {stored} trechos" if stored else "Sem texto extraível."
            return {"ok": stored > 0, "msg": msg, "sources": memory.list_sources(owner)}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:120]}

    @app.post("/api/kb/delete")
    async def kb_delete(request: Request):
        _check(request.headers.get("authorization"))
        source = ((await _body(request)).get("source") or "").strip()
        n = memory.delete_source(owner, source) if source else 0
        return {"ok": n > 0, "sources": memory.list_sources(owner)}

    # --- Expenses / Reminders / Memories CRUD ------------------------------
    @app.get("/api/expenses")
    async def exp_list(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        return {"items": memory.expenses_since(owner, since)}

    @app.post("/api/expenses")
    async def exp_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
        except Exception:
            return {"ok": False}
        memory.add_expense(owner, amount, (d.get("description") or "").strip() or "gasto",
                           (d.get("category") or "geral").strip() or "geral")
        return {"ok": True}

    @app.post("/api/expenses/delete")
    async def exp_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_expense(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/reminders")
    async def rem_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.open_reminders(owner)}

    @app.post("/api/reminders")
    async def rem_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        text = (d.get("text") or "").strip()
        when = (d.get("when") or "").strip() or None
        if text:
            memory.add_reminder(owner, text, when, _recurval(d.get("recur")))
        return {"ok": bool(text)}

    @app.post("/api/reminders/delete")
    async def rem_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.cancel_reminder(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/facts")
    async def fact_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_facts(owner)}

    @app.post("/api/facts")
    async def fact_create(request: Request):
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if text:
            memory.add_fact(owner, text)
        return {"ok": bool(text)}

    @app.post("/api/facts/delete")
    async def fact_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_fact(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    # --- API keys management -----------------------------------------------
    _KEY_FIELDS = [
        ("gemini_api_key", "GEMINI_API_KEY", "Gemini (IA principal)"),
        ("groq_api_key", "GROQ_API_KEY", "Groq (fallback + voz→texto)"),
        ("openrouter_api_key", "OPENROUTER_API_KEY", "OpenRouter (fallback)"),
        ("tavily_api_key", "TAVILY_API_KEY", "Tavily (busca web)"),
        ("brave_api_key", "BRAVE_API_KEY", "Brave (busca web)"),
        ("imap_address", "EV_IMAP_ADDRESS", "E-mail Gmail (leitura)"),
        ("imap_password", "EV_IMAP_PASSWORD", "Senha de app Gmail (leitura)"),
    ]

    def _env_write(var, value):
        import re
        p = config.db_path.parent / ".env"
        try:
            s = p.read_text() if p.exists() else ""
        except Exception:
            s = ""
        line = f"{var}={value}"
        if re.search(rf"(?m)^{re.escape(var)}=", s):
            s = re.sub(rf"(?m)^{re.escape(var)}=.*$", line, s)
        else:
            s = (s.rstrip("\n") + "\n" + line + "\n") if s else line + "\n"
        p.write_text(s)

    def _keys_state():
        return [{"field": f, "label": lbl, "set": bool(getattr(config, f, ""))}
                for f, env, lbl in _KEY_FIELDS]

    @app.get("/api/keys")
    async def keys_get(request: Request):
        _check(request.headers.get("authorization"))
        return {"keys": _keys_state()}

    @app.post("/api/keys")
    async def keys_set(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        changed = []
        for f, env, lbl in _KEY_FIELDS:
            v = (d.get(f) or "").strip()
            if v:
                try:  # frozen dataclass -> update in place so the web uses it now
                    object.__setattr__(config, f, v)
                except Exception:
                    pass
                try:  # persist to .env (survives restart; Telegram picks it up too)
                    _env_write(env, v)
                    changed.append(lbl)
                except Exception:
                    pass
        return {"ok": bool(changed), "changed": changed, "keys": _keys_state()}

    # --- Links / Habits / Journal CRUD -------------------------------------
    @app.get("/api/links")
    async def links_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_links(owner)}

    @app.post("/api/links")
    async def links_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        name = (d.get("name") or "").strip()
        url = (d.get("url") or "").strip()
        cat = (d.get("category") or "geral").strip() or "geral"
        if name and url:
            memory.add_link(owner, cat, name, url)
        return {"ok": bool(name and url)}

    @app.post("/api/links/delete")
    async def links_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_link(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/habits")
    async def habits_list(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import date
        today = date.today().isoformat()
        out = []
        for h in memory.list_habits(owner):
            days = memory.habit_days(h["id"])
            out.append({"id": h["id"], "name": h["name"],
                        "done_today": today in days, "total": len(days),
                        "days": sorted(days)[-180:]})  # recent days for the heatmap
        return {"items": out}

    @app.post("/api/habits")
    async def habits_create(request: Request):
        _check(request.headers.get("authorization"))
        name = ((await _body(request)).get("name") or "").strip()
        if name:
            memory.add_habit(owner, name)
        return {"ok": bool(name)}

    @app.post("/api/habits/done")
    async def habits_done(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import date
        memory.log_habit(int((await _body(request)).get("id") or 0), date.today().isoformat())
        return {"ok": True}

    @app.post("/api/habits/delete")
    async def habits_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_habit(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/journal")
    async def journal_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.recent_journal(owner, 60)}

    @app.post("/api/journal")
    async def journal_create(request: Request):
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if text:
            memory.add_journal(owner, text)
        return {"ok": bool(text)}

    @app.post("/api/journal/delete")
    async def journal_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_journal(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    # --- Subscriptions / Budgets / Watches CRUD ----------------------------
    @app.get("/api/recurring")
    async def rec_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_recurring(owner)}

    @app.post("/api/recurring")
    async def rec_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
            day = max(1, min(28, int(d.get("day") or 1)))
        except Exception:
            return {"ok": False}
        memory.add_recurring(owner, amount, (d.get("description") or "assinatura").strip(),
                             (d.get("category") or "assinatura").strip() or "assinatura", day)
        return {"ok": True}

    @app.post("/api/recurring/delete")
    async def rec_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_recurring(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    @app.get("/api/budgets")
    async def bud_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_budgets(owner)}

    @app.post("/api/budgets")
    async def bud_set(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        cat = (d.get("category") or "").strip()
        try:
            amount = float(str(d.get("amount", "")).replace(",", "."))
        except Exception:
            return {"ok": False}
        if cat:
            memory.set_budget(owner, cat, amount)
        return {"ok": bool(cat)}

    @app.post("/api/budgets/delete")
    async def bud_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_budget(owner, ((await _body(request)).get("category") or "").strip())
        return {"ok": True}

    @app.get("/api/watches")
    async def wat_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_watches(owner)}

    @app.post("/api/watches")
    async def wat_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        url = (d.get("url") or "").strip()
        kw = (d.get("keyword") or "").strip() or None
        if url:
            memory.add_watch(owner, url, kw)
        return {"ok": bool(url)}

    @app.post("/api/watches/delete")
    async def wat_del(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_watch(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True}

    def _num(v):
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return None

    @app.post("/api/expenses/update")
    async def exp_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.update_expense(owner, int(d.get("id") or 0), amount=_num(d.get("amount")),
                              description=(d.get("description") or None), category=(d.get("category") or None))
        return {"ok": True}

    @app.post("/api/reminders/update")
    async def rem_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        recur = _recurval(d.get("recur"), allow_clear=True) if "recur" in d else None
        memory.update_reminder(owner, int(d.get("id") or 0), text=(d.get("text") or None),
                               when_iso=(d.get("when") or None), recur=recur)
        return {"ok": True}

    @app.post("/api/facts/update")
    async def fact_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        t = (d.get("text") or "").strip()
        if t:
            memory.update_fact(owner, int(d.get("id") or 0), t)
        return {"ok": bool(t)}

    @app.post("/api/links/update")
    async def link_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.update_link(owner, int(d.get("id") or 0), category=(d.get("category") or None),
                           name=(d.get("name") or None), url=(d.get("url") or None))
        return {"ok": True}

    @app.post("/api/journal/update")
    async def jou_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        t = (d.get("text") or "").strip()
        if t:
            memory.update_journal(owner, int(d.get("id") or 0), t)
        return {"ok": bool(t)}

    @app.post("/api/habits/update")
    async def hab_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        n = (d.get("name") or "").strip()
        if n:
            memory.rename_habit(owner, int(d.get("id") or 0), n)
        return {"ok": bool(n)}

    @app.post("/api/recurring/update")
    async def rec_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            day = int(d.get("day")) if d.get("day") else None
        except Exception:
            day = None
        memory.update_recurring(owner, int(d.get("id") or 0), amount=_num(d.get("amount")),
                                description=(d.get("description") or None),
                                category=(d.get("category") or None), day=day)
        return {"ok": True}

    @app.post("/api/watches/update")
    async def wat_update(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        memory.update_watch(owner, int(d.get("id") or 0), url=(d.get("url") or None),
                            keyword=(d.get("keyword") or None))
        return {"ok": True}

    @app.get("/api/panel")
    async def panel(request: Request):
        _check(request.headers.get("authorization"))
        # "Gastos · mês" = current calendar month in the user's timezone.
        _, since, _ = commands._month_bounds(0)
        exp = memory.expenses_since(owner, since)
        prov = memory.get_setting("force_provider") or "auto"
        # the model that actually answers depends on the forced provider
        model = {
            "groq": config.groq_model,
            "openrouter": config.openrouter_model,
            "ollama": config.ollama_model,
        }.get(prov) or brain.current_model()
        # extra system indicators (pinnable in the "Sistema" panel)
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        rems = memory.open_reminders(owner)
        soon = now + timedelta(days=7)
        agenda = 0
        for r in rems:
            w = r.get("when_iso") or ""
            try:
                dt = datetime.fromisoformat(w)
                if dt.tzinfo is None:  # older rows may be tz-naive -> assume UTC
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt <= soon:
                    agenda += 1
            except ValueError:
                pass
        # activity in the last 24h (created is UTC ISO -> lexical compare is chronological)
        cutoff = (now - timedelta(hours=24)).isoformat()
        acts_24h = sum(1 for a in memory.list_activity(owner, limit=300)
                       if (a.get("created") or "") >= cutoff)
        rep = health.system_report(config, memory)
        up = int(boot and (_time.monotonic() - boot) or 0)
        uptime = (f"{up // 86400}d" if up >= 86400
                  else f"{up // 3600}h" if up >= 3600
                  else f"{up // 60}m")
        return {
            "tasks": len(memory.open_tasks(owner)),
            "reminders": len(rems),
            "expenses": round(sum(e.get("amount", 0) for e in exp)),
            "memories": len(memory.all_facts(owner)),
            "kb": len(memory.list_sources(owner)),
            "kbfiles": len(memory.kb_file_sources(owner)),
            "links": len(memory.list_links(owner)),
            "habits": len(memory.list_habits(owner)),
            "journal": len(memory.recent_journal(owner, 9999)),
            "subscriptions": len(memory.list_recurring(owner)),
            "budgets": len(memory.list_budgets(owner)),
            "watches": len(memory.list_watches(owner)),
            "agenda": agenda,
            "activity": acts_24h,
            "disk": (f"{rep['disk_used_pct']}%" if "disk_used_pct" in rep else "—"),
            "ram": (f"{rep['mem_used_pct']}%" if "mem_used_pct" in rep else "—"),
            "uptime": uptime,
            "notifs": memory.unread_notifications(owner),
            "provider": prov,
            "model": model,
        }

    @app.post("/api/tts")
    async def tts(request: Request):
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="empty")
        mp3 = await voice_mod.synthesize(
            text[:1200], config.voice, rate=config.voice_rate,
            pitch=config.voice_pitch, fixes=config.voice_fixes,
        )
        return Response(content=mp3, media_type="audio/mpeg")

    @app.post("/api/vision")
    async def vision(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"reply": "Nenhuma imagem enviada."}
        data = await f.read()
        if not data:
            return {"reply": "Imagem vazia."}
        prompt = (form.get("text") or "").strip() or "O que há nesta imagem?"
        thread = (form.get("thread") or "geral").strip()
        try:
            reply = await brain.respond(
                owner, conv_id=_conv(thread), text=prompt,
                image=data, image_mime=(f.content_type or "image/jpeg"))
        except Exception as exc:
            return {"reply": f"Não consegui analisar a imagem: {exc}"}
        return {"reply": reply}

    @app.post("/api/stt")
    async def stt(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("audio")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            raise HTTPException(status_code=400, detail="no audio")
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty audio")
        text = await brain.transcribe(data, f.content_type or "audio/webm")
        return {"text": (text or "").strip()}

    @app.post("/api/email")
    async def api_email(request: Request):
        _check(request.headers.get("authorization"))
        from ..providers import tools
        d = await _body(request)
        to = (d.get("to") or "").strip()
        subject = (d.get("subject") or "").strip()
        body = (d.get("body") or "").strip()
        if not to or not body:
            return {"ok": False, "msg": "Preencha destinatário e mensagem."}
        account = (d.get("account") or "").strip() or config.default_account
        try:
            msg = await asyncio.to_thread(
                tools.send_email, config, account, to, subject, body
            )
            return {"ok": True, "msg": msg}
        except Exception as exc:
            return {"ok": False, "msg": f"Falha ao enviar o email: {exc}"}

    @app.post("/api/notify")
    async def api_notify(request: Request):
        """Send a message to the owner's own Telegram (a note to yourself)."""
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("text") or "").strip()
        if not text:
            return {"ok": False, "msg": "Mensagem vazia."}
        if not config.telegram_token or config.owner_id is None:
            return {"ok": False, "msg": "Telegram não está configurado."}
        import httpx

        def _send():
            return httpx.post(
                f"https://api.telegram.org/bot{config.telegram_token}/sendMessage",
                data={"chat_id": config.owner_id, "text": text}, timeout=15,
            )
        try:
            r = await asyncio.to_thread(_send)
            if r.status_code == 200:
                return {"ok": True, "msg": "Mensagem enviada ao seu Telegram."}
            return {"ok": False, "msg": f"Falha ao enviar (HTTP {r.status_code})."}
        except Exception as exc:
            return {"ok": False, "msg": f"Falha ao enviar: {exc}"}

    def _tz_iso(v: str) -> str:
        """A naive datetime-local value -> ISO with the configured tz offset."""
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(config.timezone))
            return dt.isoformat()
        except Exception:
            return v

    @app.get("/api/gcal")
    async def gcal_list(request: Request):
        _check(request.headers.get("authorization"))
        if not config.google_ready() or not config.google_authorized():
            return {"ok": False, "events": [], "msg": "Google não autorizado."}
        start = request.query_params.get("start") or ""
        end = request.query_params.get("end") or ""
        from ..providers import tools
        try:
            events = await asyncio.to_thread(
                tools.calendar_list_range, config, config.default_account, start, end)
            return {"ok": True, "events": events}
        except Exception as exc:
            return {"ok": False, "events": [], "msg": str(exc)}

    @app.post("/api/gcal/create")
    async def gcal_create(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        summary = (d.get("summary") or "").strip()
        start = (d.get("start") or "").strip()
        end = (d.get("end") or "").strip()
        if not summary or not start:
            return {"ok": False, "msg": "Faltou título ou início."}
        start_iso = _tz_iso(start)
        if end:
            end_iso = _tz_iso(end)
        else:
            from datetime import datetime, timedelta
            try:
                end_iso = (datetime.fromisoformat(start_iso) + timedelta(hours=1)).isoformat()
            except Exception:
                end_iso = start_iso
        from ..providers import tools
        try:
            msg = await asyncio.to_thread(
                tools.calendar_create, config, config.default_account,
                summary, start_iso, end_iso)
            ok = "criei" in msg.lower() or "criado" in msg.lower() or "http" in msg.lower()
            return {"ok": ok, "msg": msg}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    @app.post("/api/gcal/delete")
    async def gcal_delete(request: Request):
        _check(request.headers.get("authorization"))
        eid = ((await _body(request)).get("id") or "").strip()
        if not eid:
            return {"ok": False}
        from ..providers import tools
        try:
            await asyncio.to_thread(
                tools.calendar_delete, config, config.default_account, eid)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    # --- OAuth login (Google / GitHub) -------------------------------------
    import secrets as _secrets
    from fastapi.responses import RedirectResponse
    _oauth_states: set[str] = set()

    def _base_url(request: Request) -> str:
        return config.web_base_url or str(request.base_url).rstrip("/")

    def _login_ok_html() -> HTMLResponse:
        # Passed the identity check: hand the app token to this browser and enter.
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>E.V.</title>"
            "<script>localStorage.setItem('ev_token'," + json.dumps(config.web_token)
            + ");location.replace('/');</script>"
            "<p style='font:14px system-ui;color:#888;padding:24px'>Entrando…</p>")

    def _login_denied_html(msg: str) -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>E.V.</title>"
            "<div style='font:15px system-ui;color:#f4f3f1;background:#0a0a0a;"
            "height:100vh;display:flex;flex-direction:column;align-items:center;"
            "justify-content:center;gap:16px;text-align:center;padding:24px'>"
            "<p>" + msg + "</p><a href='/' style='color:#8ab4f8'>voltar</a></div>",
            status_code=403)

    @app.get("/auth/google")
    async def auth_google(request: Request):
        if not config.google_login_client:
            return _login_denied_html("Login com Google não configurado.")
        from urllib.parse import urlencode
        state = _secrets.token_urlsafe(16); _oauth_states.add(state)
        params = urlencode({
            "client_id": config.google_login_client,
            "redirect_uri": _base_url(request) + "/auth/google/callback",
            "response_type": "code", "scope": "openid email profile",
            "access_type": "online", "state": state, "prompt": "select_account",
        })
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + params)

    @app.get("/auth/google/callback")
    async def auth_google_cb(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in _oauth_states:
            return _login_denied_html("Sessão de login inválida. Tente de novo.")
        _oauth_states.discard(state)
        redirect = _base_url(request) + "/auth/google/callback"

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
            return _login_denied_html(f"Falha no login Google: {exc}")
        if not email:
            return _login_denied_html("Não consegui obter seu email do Google.")
        allowed = memory.get_setting("login_google_email")
        if not allowed:
            memory.set_setting("login_google_email", email)  # pin the first login
        elif email != allowed:
            return _login_denied_html("Esta conta Google não tem acesso a esta E.V.")
        return _login_ok_html()

    @app.get("/auth/github")
    async def auth_github(request: Request):
        if not config.github_login_client:
            return _login_denied_html("Login com GitHub não configurado.")
        from urllib.parse import urlencode
        state = _secrets.token_urlsafe(16); _oauth_states.add(state)
        params = urlencode({
            "client_id": config.github_login_client,
            "redirect_uri": _base_url(request) + "/auth/github/callback",
            "scope": "read:user", "state": state,
        })
        return RedirectResponse("https://github.com/login/oauth/authorize?" + params)

    @app.get("/auth/github/callback")
    async def auth_github_cb(request: Request):
        import httpx
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or state not in _oauth_states:
            return _login_denied_html("Sessão de login inválida. Tente de novo.")
        _oauth_states.discard(state)
        redirect = _base_url(request) + "/auth/github/callback"

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
            return _login_denied_html(f"Falha no login GitHub: {exc}")
        if not login:
            return _login_denied_html("Não consegui obter seu usuário do GitHub.")
        allowed = memory.get_setting("login_github_user")
        if not allowed:
            memory.set_setting("login_github_user", login)  # pin the first login
        elif login.lower() != allowed.lower():
            return _login_denied_html("Este usuário GitHub não tem acesso a esta E.V.")
        return _login_ok_html()

    return app


def run():
    import uvicorn

    config = Config.load(require_telegram=False)
    if not config.web_token:
        raise SystemExit("EV_WEB_TOKEN não configurado no .env.")
    logging.basicConfig(level=logging.INFO)
    log.info("E.V. web em http://%s:%s", config.web_host, config.web_port)
    uvicorn.run(create_app(config), host=config.web_host, port=config.web_port)
