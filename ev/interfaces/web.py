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
    '<circle cx="32" cy="32" r="21" fill="none" stroke="#35c8ff" stroke-opacity=".28" stroke-width="2"/>'
    '<circle cx="32" cy="32" r="12.5" fill="none" stroke="#35c8ff" stroke-opacity=".55" stroke-width="2"/>'
    '<circle cx="32" cy="32" r="4.5" fill="#35c8ff"/></svg>'
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
    fg = (53, 200, 255)
    w = max(2, size // 34)
    for rr, alpha in [(0.33, 71), (0.20, 140)]:
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
<meta name="theme-color" content="#04070c">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="E.V.">
<link rel="apple-touch-icon" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --ink:#04070c;--panel:#070c14;--elev:#0e1b2b;--surface:#081019;
  --fg:#d6e9fb;--muted:#7d93aa;--subtle:#44586d;
  --accent:#35c8ff;--accent-dim:#12668f;
  --line:rgba(93,178,255,.13);--line-2:rgba(93,178,255,.28);
  --glow:rgba(53,200,255,.55);
  --disp:'Space Grotesk',sans-serif;--body:'Inter',sans-serif;--mono:'JetBrains Mono',monospace;
}
*{box-sizing:border-box}html,body{height:100%;max-width:100%;overflow-x:hidden}
body{margin:0;background:var(--ink);color:var(--fg);font-family:var(--body);-webkit-font-smoothing:antialiased;overflow:hidden}
.topbar{min-width:0}#center{overflow:hidden}
*{scrollbar-width:thin;scrollbar-color:#123249 transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#123249;border-radius:8px;border:2px solid var(--ink);background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:#1c4a6b;background-clip:padding-box}
::-webkit-scrollbar-corner{background:transparent}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(rgba(93,178,255,.07) 1px,transparent 1px);background-size:26px 26px;mask:radial-gradient(120% 90% at 50% 0%,#000,transparent 78%);animation:gridpulse 7s ease-in-out infinite}
@keyframes gridpulse{0%,100%{opacity:.7}50%{opacity:1}}
/* --- camada holográfica (HUD) --- */
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:6;background:repeating-linear-gradient(0deg,rgba(120,200,255,.04) 0 1px,transparent 1px 3px);mix-blend-mode:screen;opacity:.6}
#hud-scan{position:fixed;left:0;right:0;top:0;height:200px;pointer-events:none;z-index:6;background:linear-gradient(180deg,transparent,rgba(53,200,255,.05) 55%,rgba(53,200,255,.13) 84%,rgba(53,200,255,.02));transform:translateY(-260px);animation:hscan 7.5s linear infinite;will-change:transform}
@keyframes hscan{to{transform:translateY(calc(100vh + 260px))}}
#hud-bloom{position:fixed;inset:0;pointer-events:none;z-index:0;background:radial-gradient(70% 44% at 50% -8%,rgba(53,200,255,.12),transparent 70%)}
@media(prefers-reduced-motion:reduce){body::before,#hud-scan{animation:none}}
#app{position:relative;z-index:1;height:100%;display:grid;grid-template-columns:238px 1fr 272px;min-height:0}
/* painéis de vidro + brilho interno + brackets de canto HUD */
#left,#right{background:linear-gradient(180deg,rgba(14,27,43,.5),rgba(6,12,20,.34));-webkit-backdrop-filter:blur(9px);backdrop-filter:blur(9px)}
#left{box-shadow:inset -1px 0 0 var(--line),inset 0 0 70px -34px var(--glow)}
#right{box-shadow:inset 1px 0 0 var(--line),inset 0 0 70px -34px var(--glow)}
.rail{position:relative}
.rail::before,.rail::after{content:"";position:absolute;width:15px;height:15px;border:1px solid var(--accent);opacity:.45;pointer-events:none;z-index:2}
.rail::before{top:9px;left:9px;border-right:none;border-bottom:none}
.rail::after{bottom:9px;right:9px;border-left:none;border-top:none}
/* Firefox/Zen: só o blur (backdrop-filter) e o blend travam — desligo esses e
   MANTENHO as animações holográficas (pulso do grid + barra de scan), que são baratas. */
.ff #left,.ff #right{-webkit-backdrop-filter:none;backdrop-filter:none;background:rgba(8,15,26,.94)}
/* só tira o blur das bolhas — mantém o degradê translúcido + borda que brilha (holográfico) */
.ff .msg.ev,.ff #map-results,.ff #map-route{-webkit-backdrop-filter:none;backdrop-filter:none}
.ff #map-results{background:rgba(6,12,20,.96)}.ff #map-route{background:rgba(6,12,20,.96)}
.ff body::after{mix-blend-mode:normal;opacity:.4}
.rail{display:flex;flex-direction:column;min-height:0}
#left{border-right:1px solid var(--line);padding:18px;gap:14px;overflow:auto}
#right{border-left:1px solid var(--line);padding:18px;gap:12px;overflow:auto}
#center{min-width:0;min-height:0;display:flex;flex-direction:column}
.brand .name{font-family:var(--disp);font-weight:700;font-size:26px;letter-spacing:.14em;color:var(--accent);text-shadow:0 0 20px var(--glow)}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.26em;color:#5f9fc9;text-transform:uppercase;margin:4px 2px;text-shadow:0 0 12px rgba(53,200,255,.22)}
.core{width:132px;height:132px;position:relative;margin:6px auto 2px}
.core .ring{position:absolute;border-radius:50%;border:1px solid var(--line-2)}
.core .ring.a{inset:0}.core .ring.b{inset:18px;border-color:var(--line)}.core .ring.c{inset:40px;border-color:var(--line-2)}
.core .arc{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 66%,var(--accent) 84%,transparent 100%);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));animation:spin 7s linear infinite}
.core .arc.two{inset:18px;animation-duration:11s;animation-direction:reverse;opacity:.5}
.core .dot{position:absolute;inset:0;margin:auto;width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 20px 5px var(--glow)}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes ambpulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.7)}}
body.listening .core .arc{animation-duration:1.8s}body.thinking .core .arc{animation-duration:2.6s}
body.speaking .core .arc{animation-duration:1.1s}
body.listening .core .dot{animation:pulse 1s infinite}@keyframes pulse{50%{transform:scale(1.9);opacity:.55}}
body.speaking .core .dot{animation:pulse .6s infinite}
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
#vc{position:fixed;inset:0;z-index:20;background:radial-gradient(90% 70% at 50% 26%,#0b1929,#04070c 76%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:26px;overflow:hidden}
#vc.on{display:flex}
#vc::before{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(120,200,255,.045) 0 1px,transparent 1px 3px)}
#vc::after{content:"";position:absolute;inset:16px;border-radius:16px;pointer-events:none;box-shadow:inset 0 0 0 1px rgba(53,200,255,.12),inset 0 0 90px -55px var(--glow)}
#vc>*{position:relative;z-index:1}
#vc-orb{position:relative;display:flex;align-items:center;justify-content:center}
#vc-viz{position:absolute;width:480px;height:480px;max-width:92vw;max-height:92vw;pointer-events:none;opacity:0;transition:opacity .35s;filter:drop-shadow(0 0 14px var(--glow))}
.bigcore{width:220px;height:220px;position:relative;z-index:1}
#mapview{display:none;padding:22px;overflow:auto}
#chartsview{display:none;padding:22px;overflow:auto}
.chart-card{border:1px solid var(--line-2);border-radius:13px;padding:14px 16px;margin-bottom:16px;background:linear-gradient(180deg,rgba(14,27,43,.4),rgba(6,12,20,.3));box-shadow:0 0 40px -26px var(--glow)}
.chart-t{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#6fb0da;margin-bottom:10px}
.chart-card canvas{max-height:280px}
#brainview{display:none;padding:22px;overflow:hidden;flex-direction:column;min-height:0;height:100%}
#brain-wrap{position:relative;flex:1;min-height:400px;margin-top:10px;border:1px solid var(--line-2);border-radius:13px;overflow:hidden;box-shadow:0 0 60px -20px var(--glow),inset 0 0 60px -20px var(--glow);background:radial-gradient(120% 100% at 50% 0%,rgba(53,200,255,.08),transparent 60%),radial-gradient(90% 90% at 50% 100%,rgba(53,200,255,.05),transparent 70%),#03070a}
#brain-canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab;z-index:0}
#brain-canvas.dragging{cursor:grabbing}
#brain-wrap::before{content:"";position:absolute;inset:0;pointer-events:none;z-index:1;background:repeating-linear-gradient(0deg,rgba(120,200,255,.05) 0 1px,transparent 1px 3px);mix-blend-mode:screen;opacity:.5}
#brain-wrap::after{content:"";position:absolute;left:50%;top:50%;width:150%;padding-top:150%;margin-left:-75%;margin-top:-75%;pointer-events:none;z-index:1;background:conic-gradient(from 0deg,transparent 0 91%,rgba(53,200,255,.22) 98%,transparent 100%);animation:brainsweep 6s linear infinite;mix-blend-mode:screen;opacity:.8}
@keyframes brainsweep{to{transform:rotate(360deg)}}
.brain-corner{position:absolute;width:26px;height:26px;border:2px solid var(--accent);opacity:.5;pointer-events:none;z-index:2;filter:drop-shadow(0 0 6px var(--glow))}
.brain-corner.tl{top:10px;left:10px;border-right:none;border-bottom:none;border-radius:6px 0 0 0}
.brain-corner.tr{top:10px;right:10px;border-left:none;border-bottom:none;border-radius:0 6px 0 0}
.brain-corner.bl{bottom:10px;left:10px;border-right:none;border-top:none;border-radius:0 0 0 6px}
.brain-corner.br{bottom:10px;right:10px;border-left:none;border-top:none;border-radius:0 0 6px 0}
#brain-tip{position:absolute;pointer-events:none;display:none;max-width:240px;padding:7px 10px;border-radius:9px;background:var(--elev);border:1px solid var(--accent);color:var(--fg);font-size:12px;font-family:var(--body);box-shadow:0 0 20px -4px var(--glow),0 8px 24px -12px rgba(0,0,0,.6);z-index:3}
#brain-menu{position:absolute;display:none;flex-direction:column;min-width:170px;max-width:230px;background:var(--elev);border:1px solid var(--accent);border-radius:11px;padding:8px;z-index:4;box-shadow:0 0 26px -6px var(--glow),0 12px 30px -14px rgba(0,0,0,.7)}
#brain-menu.on{display:flex}
#brain-menu .bm-t{font-size:12px;color:var(--fg);padding:2px 6px 8px;border-bottom:1px solid var(--line);margin-bottom:6px;word-break:break-word}
#brain-menu button{display:flex;align-items:center;gap:8px;font-family:var(--body);font-size:13px;color:var(--fg);background:none;border:none;border-radius:8px;padding:8px 8px;cursor:pointer;text-align:left}
#brain-menu button:hover{background:var(--surface);color:var(--accent)}
#brain-menu button svg{width:15px;height:15px}
#brain-menu button.bm-del:hover{color:#ff8a8a}
#map-wrap{position:relative;height:calc(100vh - 300px);min-height:400px}
#map{position:absolute;inset:0;border:1px solid var(--line-2);border-radius:13px;overflow:hidden;box-shadow:0 0 40px -24px var(--glow)}
#map .leaflet-container{background:#04070c;font-family:var(--body)}
#map .leaflet-control-zoom a{background:var(--elev);color:var(--accent);border-color:var(--line)}
#map .leaflet-bar{border:1px solid var(--line)}
#map .leaflet-popup-content-wrapper,#map .leaflet-popup-tip{background:var(--elev);color:var(--fg);border:1px solid var(--line-2)}
#map .leaflet-popup-content{margin:11px 13px;font-family:var(--body)}
.pop-n{font-weight:600;font-size:13px;margin-bottom:2px}.pop-d{font-family:var(--mono);font-size:10px;color:var(--subtle);margin-bottom:7px}
.pop-b{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--accent);background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:4px 8px;cursor:pointer;margin-right:5px}
.pop-b:hover{background:var(--fg);color:var(--ink)}
#map-results{position:absolute;top:12px;left:12px;width:252px;max-height:calc(100% - 24px);overflow:auto;z-index:600;background:rgba(6,12,20,.86);-webkit-backdrop-filter:blur(7px);backdrop-filter:blur(7px);border:1px solid var(--line-2);border-radius:12px;padding:8px;display:none}
#map-results.on{display:block}
#map-results .mr-h{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--subtle);padding:4px 6px 6px;display:flex;align-items:center;justify-content:space-between}
#map-results .mr-h b{cursor:pointer;color:var(--muted)}
.mres{padding:8px 9px;border-radius:8px;cursor:pointer;border-top:1px solid var(--line)}
.mres:first-of-type{border-top:none}.mres:hover{background:var(--elev)}
.mres .mr-n{font-size:13px;font-weight:600}.mres .mr-d{font-family:var(--mono);font-size:10px;color:var(--subtle);margin-top:2px}
#map-route{position:absolute;left:12px;right:12px;bottom:12px;z-index:600;background:rgba(6,12,20,.9);-webkit-backdrop-filter:blur(7px);backdrop-filter:blur(7px);border:1px solid var(--line-2);border-radius:12px;padding:9px 12px;display:none;align-items:center;gap:9px;flex-wrap:wrap}
#map-route.on{display:flex}
#map-route .rt-info{font-size:13px;font-weight:600;flex:1;min-width:120px}
#map-route .rt-b{font-size:11px;color:var(--accent);background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:5px 10px;cursor:pointer}
#map-route .rt-b.on{background:var(--accent);color:var(--ink)}#map-route .rt-b:hover{background:var(--fg);color:var(--ink)}
.bigcore .ring{position:absolute;border-radius:50%;border:1px solid var(--line-2)}
.bigcore .r1{inset:0}.bigcore .r2{inset:26px;border-color:var(--line)}.bigcore .r3{inset:60px;border-color:var(--line-2)}
.bigcore .arc{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 66%,var(--accent) 84%,transparent 100%);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));animation:spin 8s linear infinite}
.bigcore .bdot{position:absolute;inset:0;margin:auto;width:14px;height:14px;border-radius:50%;background:var(--accent);box-shadow:0 0 40px 12px var(--glow)}
body.listening .bigcore .arc{animation-duration:1.6s}body.speaking .bigcore .arc{animation-duration:1s}
body.listening .bigcore .bdot{animation:pulse .9s infinite}body.speaking .bigcore .bdot{animation:pulse .55s infinite}
body.speaking .bigcore .ring{animation:ringpulse 1.3s ease-in-out infinite}
body.speaking .bigcore .r2{animation-delay:.15s}body.speaking .bigcore .r3{animation-delay:.3s}
@keyframes ringpulse{0%,100%{transform:scale(1);border-color:var(--line-2)}50%{transform:scale(1.05);border-color:var(--accent)}}
#vc-txt{font-family:var(--disp);font-size:22px;text-align:center;max-width:640px;padding:0 24px;line-height:1.4;min-height:60px}
#vc-txt .msg{font-family:var(--body);font-size:15px;text-align:left;max-width:min(560px,92vw);margin:0 auto;max-height:52vh;overflow:auto}
#vc-sub{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:#6fb0da;text-shadow:0 0 12px rgba(53,200,255,.3)}
#vc-actions{display:flex;gap:12px}
.vcbtn{width:82px;height:82px;border-radius:50%;border:1px solid var(--accent);background:radial-gradient(circle at 50% 35%,rgba(53,200,255,.16),var(--elev) 70%);color:var(--accent);font-size:27px;cursor:pointer;transition:.15s;box-shadow:0 0 26px -6px var(--glow),inset 0 0 20px -12px var(--glow);display:inline-flex;align-items:center;justify-content:center}
.vcbtn:hover{box-shadow:0 0 40px -6px var(--glow),inset 0 0 24px -10px var(--glow);transform:translateY(-1px)}
.vcbtn svg{width:30px;height:30px}
.vcbtn:hover{border-color:var(--fg);transform:translateY(-2px)}
.vcbtn.rec{background:var(--accent);color:var(--ink);border-color:var(--accent);box-shadow:0 0 44px -4px var(--glow);animation:pulse 1.1s infinite}
.vcbtn.rec svg{color:var(--ink)}
#vc-x{position:absolute;top:20px;right:24px;z-index:2;font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--muted);background:rgba(4,7,12,.5);border:1px solid var(--line-2);border-radius:999px;padding:8px 14px;cursor:pointer}
#vc-x:hover{color:var(--accent);border-color:var(--accent)}
/* live camera overlay */
#cam{position:fixed;inset:0;z-index:22;background:#000;display:none;flex-direction:column;align-items:center;justify-content:center}
#cam.on{display:flex}
#cam-stage{position:relative;display:flex}
#cam-video{max-width:100%;max-height:78vh;object-fit:contain;background:#000;display:block}
#cam-fx{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#cam-result{position:absolute;bottom:120px;left:16px;right:16px;max-width:640px;margin:0 auto;text-align:center;font-size:14px;line-height:1.4;color:var(--fg);background:rgba(4,7,12,.66);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);border:1px solid var(--line-2);border-radius:12px;padding:10px 14px;display:none;z-index:3;box-shadow:0 0 30px -18px var(--glow)}
#cam-result.on{display:block}
#cam .vcbtn.on{background:var(--accent);color:var(--ink);border-color:var(--accent)}
#cam .vcbtn.on svg{color:var(--ink)}
#cam-hint{position:absolute;top:70px;left:0;right:0;text-align:center;font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--subtle);padding:0 20px}
#cam-actions{position:absolute;bottom:34px;left:10px;right:10px;display:flex;gap:16px;align-items:center;justify-content:center;flex-wrap:wrap}
@media(max-width:520px){#cam-actions{gap:10px}#cam .vcbtn{width:60px;height:60px}#cam .vcbtn svg{width:24px;height:24px}}
#cam-x{position:absolute;top:20px;right:24px;font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--fg);background:rgba(0,0,0,.4);border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer;z-index:2}
/* pomodoro focus overlay */
#pomo{position:fixed;inset:0;z-index:24;background:radial-gradient(90% 70% at 50% 28%,#0b1929,#04070c 78%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:20px;overflow:hidden}
#pomo.on{display:flex}
#pomo::before{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(120,200,255,.045) 0 1px,transparent 1px 3px)}
#pomo::after{content:"";position:absolute;inset:16px;border-radius:16px;pointer-events:none;box-shadow:inset 0 0 0 1px rgba(53,200,255,.12),inset 0 0 90px -55px var(--glow)}
#pomo>*{position:relative;z-index:1}
#pomo .bigcore{width:210px;height:210px}
#pomo.run .bigcore .arc{animation-duration:2.4s}
#pomo-timebox{display:flex;flex-direction:column;align-items:center;gap:6px}
#pomo-time{font-family:var(--mono);font-weight:600;font-size:60px;letter-spacing:.02em;line-height:1;color:#eaf4fb;text-shadow:0 0 24px var(--glow)}
#pomo-label{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:#6fb0da;text-shadow:0 0 12px rgba(53,200,255,.3)}
#pomo-ctl{display:flex;gap:10px;align-items:center}
#pomo-ctl button{font-family:var(--mono);font-size:13px;color:var(--fg);background:var(--elev);border:1px solid var(--line);border-radius:10px;padding:11px 15px;cursor:pointer;transition:.15s}
#pomo-ctl button:hover{border-color:var(--accent);color:var(--accent)}
#pomo-toggle{width:64px!important;height:64px;border-radius:50%!important;background:radial-gradient(circle at 50% 35%,rgba(53,200,255,.18),var(--elev) 70%)!important;color:var(--accent)!important;border:1px solid var(--accent)!important;display:grid;place-items:center;box-shadow:0 0 30px -6px var(--glow),inset 0 0 20px -12px var(--glow)}
#pomo-toggle svg{width:24px;height:24px}
#pomo-presets{display:flex;gap:8px}
#pomo-presets button{font-family:var(--mono);font-size:11px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
#pomo-presets button:hover{color:var(--fg);border-color:var(--line-2)}
#pomo-pip{margin-top:4px;font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:999px;padding:9px 16px;cursor:pointer}
#pomo-pip:hover{color:var(--fg);border-color:var(--line-2)}
#pomo-x{position:absolute;top:20px;right:24px;z-index:2;font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--muted);background:rgba(4,7,12,.5);border:1px solid var(--line-2);border-radius:999px;padding:8px 14px;cursor:pointer}
#pomo-x:hover{color:var(--accent);border-color:var(--accent)}
#pomo-presets button:hover{color:var(--accent);border-color:var(--accent)}
#pomo-pip:hover{color:var(--accent);border-color:var(--accent)}
#login,#welcome{position:fixed;inset:0;z-index:50;background:radial-gradient(90% 70% at 50% 28%,#0b1929,#04070c 78%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:22px;overflow:hidden}
#login.on,#welcome.on{display:flex}
#login::before,#welcome::before{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(120,200,255,.045) 0 1px,transparent 1px 3px)}
#login::after,#welcome::after{content:"";position:absolute;inset:16px;border-radius:16px;pointer-events:none;box-shadow:inset 0 0 0 1px rgba(53,200,255,.12),inset 0 0 90px -55px var(--glow)}
#login>*,#welcome>*{position:relative;z-index:1}
#login-token{background:var(--surface);border:1px solid var(--line-2);border-radius:12px;padding:13px 18px;color:var(--fg);font:inherit;font-size:15px;width:min(320px,80vw);text-align:center;outline:none}
#login-token:focus{border-color:var(--fg)}
#login-btn{min-width:170px}#login-err{font-family:var(--mono);font-size:12px;color:var(--muted);min-height:16px}
.login-or{display:flex;align-items:center;gap:10px;width:100%;max-width:230px;color:var(--muted);font-size:12px;font-family:var(--mono)}
.login-or span{flex:1;height:1px;background:var(--line)}
.login-oauth{min-width:230px;text-align:center;text-decoration:none;display:inline-flex;justify-content:center;gap:8px}
#welcome-txt{font-family:var(--disp);font-size:26px;text-align:center;max-width:600px;padding:0 24px;line-height:1.4;animation:rise .5s;color:#eaf4fb;text-shadow:0 0 22px rgba(53,200,255,.35)}
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
  .mnav{display:block;flex:1 1 auto;min-width:60px}
  /* declutter the phone header so the folder/panel toggles never get clipped
     (keep Terminal available on mobile; only drop search + clean-mode) */
  #gsearch,#tgl-zen,#amb{display:none}
  .tbtn.ic-txt span{display:none}
  .tbtn.ic-txt{padding:9px 10px}
  .topbar{gap:6px;padding:10px 10px}
  #tgl-left,#tgl-right,#vcopen,#voz{flex:none}
  #tgl-right{margin-left:auto}
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
.tv-h{font-family:var(--disp);font-weight:600;font-size:22px;margin-bottom:18px;color:#eaf4fb;text-shadow:0 0 16px rgba(53,200,255,.2)}
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
.msg.you{align-self:flex-end;background:var(--fg);color:var(--ink);border:none;border-bottom-right-radius:5px;font-weight:500;box-shadow:0 0 20px -13px var(--glow)}
.msg.ev{position:relative}
body:not(.term) .msg.ev::after{content:"";position:absolute;top:7px;left:7px;width:11px;height:11px;border-top:1px solid var(--accent);border-left:1px solid var(--accent);opacity:.5;pointer-events:none}
.msg.ev{align-self:flex-start;background:linear-gradient(180deg,rgba(18,34,52,.72),rgba(10,20,32,.66));-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);border-color:var(--line-2);border-bottom-left-radius:5px;box-shadow:0 0 26px -18px var(--glow),inset 0 0 0 1px rgba(53,200,255,.06)}
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
.msg .mtable{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px;display:block;overflow-x:auto}
.msg .mtable th,.msg .mtable td{border:1px solid var(--line);padding:6px 9px;text-align:left;white-space:nowrap}
.msg .mtable th{background:var(--surface);color:var(--accent);font-family:var(--mono);font-size:10px;letter-spacing:.05em;text-transform:uppercase}
.msg .mtable tr:nth-child(even) td{background:rgba(53,200,255,.045)}
.msg .mimg{max-width:100%;border-radius:12px;margin:8px 0;border:1px solid var(--line-2);display:block;box-shadow:0 4px 18px rgba(0,0,0,.35)}
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
.msg .h{font-family:var(--disp);font-weight:600;font-size:15px;margin-bottom:8px;display:block;color:#eaf4fb;text-shadow:0 0 14px rgba(53,200,255,.35)}
.msg .cat{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle);margin:8px 0 4px}
.row{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:none}
.row .id{font-family:var(--mono);font-size:11px;color:var(--ink);background:var(--fg);border-radius:6px;padding:2px 7px;flex:none;margin-top:1px}
.msg.ev .row .id{color:var(--ink)}
.row .t{flex:1}.hint{color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:8px}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
.tp{display:inline-flex;gap:5px}.tp i{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--glow);animation:td 1.1s infinite}
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
.field:focus-within{border-color:var(--accent);box-shadow:0 0 0 4px rgba(53,200,255,.10)}
#txt{flex:1;min-width:0;background:transparent;border:none;outline:none;color:var(--fg);font-family:var(--body);font-size:15px;padding:11px 0}
body.term #txt{font-family:var(--mono)}
body.term form{background:#060606}
body.term .field{background:#0a0a0a;border-color:#1c1c1c;border-radius:8px}
body.term .field:focus-within{border-color:#2a2a2a}
body.term #txt::placeholder{color:#4a4a4a}
.icon{width:44px;height:44px;flex:none;display:grid;place-items:center;border-radius:12px;border:1px solid var(--line);background:var(--elev);color:var(--fg);cursor:pointer;position:relative;overflow:hidden;transition:.14s}
.icon:hover{transform:translateY(-1px);border-color:var(--line-2)}.icon:active{transform:scale(.95)}
.icon.send{background:var(--accent);color:var(--ink);border:none;box-shadow:0 0 16px -2px var(--glow)}.icon.mic.on{background:var(--accent);color:var(--ink);border:none}
#imgprev{display:none;align-items:center;gap:12px;padding:9px 18px;border-top:1px solid var(--line);background:var(--surface)}
#imgprev img{width:48px;height:48px;object-fit:cover;border-radius:9px;border:1px solid var(--line)}
#imgprev .ip-name{flex:1;min-width:0;font-size:12px;color:var(--muted);font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#imgprev .ip-x{background:var(--elev);border:1px solid var(--line);color:var(--fg);width:30px;height:30px;flex:none;border-radius:8px;cursor:pointer;font-size:17px;line-height:1;display:inline-flex;align-items:center;justify-content:center}
#imgprev .ip-x:hover{background:var(--fg);color:var(--ink)}
#imgprev .ip-x svg{width:16px;height:16px}
.msg-img{max-width:230px;max-height:230px;border-radius:11px;display:block}
#audprev{display:none;align-items:center;gap:10px;padding:9px 18px;border-top:1px solid var(--line);background:var(--surface)}
#audprev .ap-info{flex:1;min-width:0;font-size:12.5px;color:var(--muted);font-family:var(--mono)}
#audprev button{border-radius:9px;cursor:pointer;font:inherit;font-size:13px;padding:8px 12px;border:1px solid var(--line);background:var(--elev);color:var(--fg)}
#audprev .ap-send{background:var(--fg);color:var(--ink);border:none;font-weight:600}
.wave{display:none;align-items:flex-end;gap:2px;height:16px}.icon.mic.on .mg{display:none}.icon.mic.on .wave{display:flex}
.wave b{width:2.5px;height:5px;background:var(--ink);border-radius:2px;animation:wv .9s infinite}
.wave b:nth-child(2){animation-delay:.12s}.wave b:nth-child(3){animation-delay:.24s}.wave b:nth-child(4){animation-delay:.36s}
@keyframes wv{50%{height:15px}}
.ripple{position:absolute;border-radius:50%;background:rgba(53,200,255,.3);transform:scale(0);animation:rp .5s ease-out;pointer-events:none}
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
.msg .h svg{width:19px;height:19px;vertical-align:-4px;margin-right:8px;color:var(--accent);filter:drop-shadow(0 0 6px var(--glow))}
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
  #left,#right{position:fixed;top:0;bottom:0;width:min(86vw,320px);z-index:60;background:var(--ink);-webkit-backdrop-filter:none;backdrop-filter:none;overflow:auto;transition:transform .25s ease}
  #left{left:0;transform:translateX(-106%);border-right:1px solid var(--line)}
  #right{right:0;transform:translateX(106%);border-left:1px solid var(--line)}
  body.m-left #left,body.m-right #right{transform:translateX(0);box-shadow:0 0 60px rgba(0,0,0,.7)}
  body.m-left #mbackdrop,body.m-right #mbackdrop{display:block;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:55}
  .topbar{padding:11px 12px;gap:5px}
  #slash{left:14px;right:14px}
  #taskview,#kbview,#expview,#remview,#memview,#calview,#lnkview,#habview,#jouview,#subview,#orcview,#monview,#actview,#brainview{padding:16px 14px}
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
<div id="hud-bloom"></div><div id="hud-scan"></div>
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
      <select id="mnav" class="mnav" title="Ir para"><option value="chat">Conversa</option><option value="tasks">Tarefas</option><option value="exp">Gastos</option><option value="rem">Lembretes</option><option value="cal">Agenda</option><option value="mem">Memórias</option><option value="lnk">Links</option><option value="hab">Hábitos</option><option value="jou">Diário</option><option value="sub">Assinaturas</option><option value="orc">Orçamentos</option><option value="mon">Monitores</option><option value="act">Histórico</option><option value="kb">Base</option><option value="map">Mapa</option><option value="brain">Cérebro</option><option value="graf">Gráficos</option></select>
      <span class="eyebrow" id="scope">geral</span>
      <button class="tbtn ico" id="gsearch" title="Buscar em tudo"><i data-lucide="search"></i></button>
      <button class="tbtn ic-txt" id="vcopen" title="Falar"><i data-lucide="mic"></i><span>FALAR</span></button>
      <button class="tbtn ic-txt" id="amb" title="Presença ambiente — escuta &quot;E.V. ...&quot; sempre"><i data-lucide="radio"></i><span>AMBIENTE</span></button>
      <button class="tbtn ic-txt" id="term" title="Modo terminal"><i data-lucide="square-terminal"></i><span>TERMINAL</span></button>
      <button class="tbtn ic-txt on" id="voz" title="Voz da E.V."><i data-lucide="volume-2"></i><span>VOZ</span></button>
      <button class="tbtn ico" id="tgl-right" title="Ocultar/mostrar painel"><i data-lucide="panel-right"></i></button>
      <button class="tbtn ico" id="tgl-zen" title="Modo limpo (ocultar painéis)"><i data-lucide="minimize-2"></i></button></div>
    <div id="chatview">
      <div id="log"></div>
      <div id="audprev"></div>
      <div id="imgprev"></div>
      <form id="f"><div id="slash"></div>
        <button type="button" class="icon mic" id="mic" title="Falar"><span class="mg"><i data-lucide="mic"></i></span><span class="wave"><b></b><b></b><b></b><b></b></span></button>
        <button type="button" class="icon" id="imgbtn" title="Enviar imagem"><i data-lucide="image"></i></button>
        <button type="button" class="icon" id="cambtn" title="Câmera ao vivo"><i data-lucide="camera"></i></button>
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
      <div class="tv-h">Memórias<span id="mem-count" style="font-size:13px;color:var(--subtle);margin-left:10px"></span></div>
      <form id="memform" class="tv-form"><input id="mem-text" placeholder="Algo que a E.V. deve lembrar sobre você..."><button class="mbtn" type="submit">Salvar</button></form>
      <input class="tv-search" id="mem-search" placeholder="Buscar no cérebro..." autocomplete="off">
      <div class="tv-cat" style="display:flex;justify-content:space-between;align-items:center">O que a E.V. sabe<span id="mem-clear" style="cursor:pointer;color:var(--muted);font-family:var(--mono);font-size:10px;letter-spacing:.1em">esquecer tudo</span></div>
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
    <div id="mapview">
      <div class="tv-h">Mapa · você e o que tem por perto</div>
      <div id="map-status" class="eyebrow" style="margin:0 2px 8px">toque em "Onde estou" para localizar seu dispositivo</div>
      <div id="map-chips" class="mchips"></div>
      <div class="tv-form" style="margin:6px 0 10px;gap:8px;flex-wrap:wrap">
        <input class="tv-search" id="map-q" placeholder="Buscar por perto: padaria, farmácia..." autocomplete="off" style="flex:1;min-width:170px">
        <button class="mchip" id="map-fix" type="button"><i data-lucide="crosshair"></i>Corrigir localização</button>
        <button class="mchip" id="map-mine" type="button"><i data-lucide="star"></i>Meus pontos</button>
        <button class="mchip" id="map-plan" type="button"><i data-lucide="route"></i>Tempo A→B</button>
        <button class="mchip" id="map-addr" type="button"><i data-lucide="search"></i>Adicionar endereço</button>
        <button class="mchip" id="map-add" type="button"><i data-lucide="map-pin"></i>Adicionar ponto</button>
        <button class="mchip" id="map-sat" type="button"><i data-lucide="satellite"></i>Satélite</button>
        <button class="mchip" id="map-street" type="button"><i data-lucide="eye"></i>Ver rua</button>
        <button class="mchip" id="map-ask" type="button"><i data-lucide="message-circle"></i>Perguntar à E.V.</button>
      </div>
      <div id="map-planner" style="display:none;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 10px">
        <span class="eyebrow" style="margin:0">De</span><select id="plan-from" class="tv-search" style="max-width:190px"></select>
        <span class="eyebrow" style="margin:0">para</span><select id="plan-to" class="tv-search" style="max-width:190px"></select>
        <button class="mchip" id="plan-go" type="button"><i data-lucide="clock"></i>Ver tempo</button>
      </div>
      <div id="map-wrap"><div id="map"></div><div id="map-results"></div><div id="map-route"></div></div>
    </div>
    <div id="brainview">
      <div class="tv-h">Cérebro · tudo que a E.V. sabe</div>
      <div class="tv-form" style="align-items:center;gap:10px">
        <span class="eyebrow" id="brain-count" style="margin:0"></span>
        <button class="mchip" id="brain-reset" type="button"><i data-lucide="focus"></i>Centralizar</button>
      </div>
      <div id="brain-wrap">
        <canvas id="brain-canvas"></canvas>
        <span class="brain-corner tl"></span><span class="brain-corner tr"></span><span class="brain-corner bl"></span><span class="brain-corner br"></span>
        <div id="brain-tip"></div>
        <div id="brain-menu"></div>
      </div>
    </div>
    <div id="chartsview">
      <div class="tv-h">Gráficos · seus dados</div>
      <div class="tv-form" style="gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px">
        <select id="ch-period" class="tv-search" style="max-width:190px">
          <option value="month">Este mês</option>
          <option value="30">Últimos 30 dias</option>
          <option value="90">Últimos 3 meses</option>
          <option value="180">Últimos 6 meses</option>
          <option value="year">Este ano</option>
          <option value="custom">Personalizado</option>
        </select>
        <input type="date" id="ch-from" class="tv-search" style="max-width:160px;display:none">
        <input type="date" id="ch-to" class="tv-search" style="max-width:160px;display:none">
        <span class="eyebrow" id="ch-range" style="margin:0"></span>
      </div>
      <div class="chart-card"><div class="chart-t">Gastos por categoria</div><canvas id="ch-cat"></canvas></div>
      <div class="chart-card"><div class="chart-t">Gastos ao longo do período</div><canvas id="ch-day"></canvas></div>
      <div class="chart-card"><div class="chart-t">Hábitos (dias marcados no período)</div><canvas id="ch-hab"></canvas></div>
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
  <div id="vc-orb"><canvas id="vc-viz" width="480" height="480"></canvas><div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div></div>
  <div id="vc-txt">Toque no microfone e fale.</div>
  <div id="vc-sub">voz ao vivo · português</div>
  <div id="vc-actions"><button class="vcbtn" id="vc-mic"><i data-lucide="mic"></i></button></div>
  <button id="vc-cont" class="tbtn" style="margin-top:14px"><i data-lucide="infinity"></i> Modo contínuo: off</button>
</div>
<div id="cam">
  <button id="cam-x">FECHAR</button>
  <div id="cam-stage"><video id="cam-video" autoplay playsinline muted></video><canvas id="cam-fx"></canvas></div>
  <div id="cam-result"></div>
  <div id="cam-hint">Aponte a câmera. Toque em capturar, em "o que é isso?", ou ligue o modo ao vivo.</div>
  <div id="cam-actions">
    <button class="vcbtn" id="cam-flip" title="Trocar câmera"><i data-lucide="refresh-cw"></i></button>
    <button class="vcbtn" id="cam-live" title="Ao vivo (marca rostos + narra)"><i data-lucide="scan-eye"></i></button>
    <button class="vcbtn" id="cam-what" title="O que é isso?"><i data-lucide="search"></i></button>
    <button class="vcbtn" id="cam-tr" title="Traduzir o texto"><i data-lucide="languages"></i></button>
    <button class="vcbtn" id="cam-food" title="Calorias da comida"><i data-lucide="utensils"></i></button>
    <button class="vcbtn" id="cam-qr" title="Ler QR / código de barras"><i data-lucide="qr-code"></i></button>
    <button class="vcbtn" id="cam-scan" title="Escanear documento pra Base"><i data-lucide="scan-line"></i></button>
    <button class="vcbtn" id="cam-face" title="Quem sou eu? (reconhece só você — segure para apagar)"><i data-lucide="user-round-check"></i></button>
    <button class="vcbtn" id="cam-shot" title="Capturar e perguntar no chat"><i data-lucide="camera"></i></button>
  </div>
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
// Firefox/Zen: backdrop-filter e mix-blend-mode são muito lentos nele -> versão leve.
try{if(/firefox/i.test(navigator.userAgent))document.documentElement.classList.add('ff');}catch(e){}
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
// modo limpo: esconde/mostra os dois painéis de uma vez
function syncTgl(){const b=document.body,z=b.classList.contains('hide-left')&&b.classList.contains('hide-right');
  $('#tgl-zen').classList.toggle('on',z);$('#tgl-left').classList.toggle('on',b.classList.contains('hide-left'));$('#tgl-right').classList.toggle('on',b.classList.contains('hide-right'));}
$('#tgl-zen').onclick=()=>{const b=document.body;
  if(mob()){b.classList.remove('m-left','m-right');return;}
  const z=b.classList.contains('hide-left')&&b.classList.contains('hide-right');
  b.classList.toggle('hide-left',!z);b.classList.toggle('hide-right',!z);
  localStorage.setItem('ev_hl',!z?'1':'');localStorage.setItem('ev_hr',!z?'1':'');syncTgl();};
syncTgl();
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
let _chartLibP=null,_charts={};
function loadChartLib(){if(window.Chart)return Promise.resolve();if(_chartLibP)return _chartLibP;
  _chartLibP=new Promise((res,rej)=>{const s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js';s.onload=res;s.onerror=rej;document.head.appendChild(s);});return _chartLibP;}
function chPeriodRange(){const p=($('#ch-period')||{}).value||'month';const to=new Date();let from=new Date();
  if(p==='month')from=new Date(to.getFullYear(),to.getMonth(),1);
  else if(p==='year')from=new Date(to.getFullYear(),0,1);
  else if(p==='custom')return {from:$('#ch-from').value,to:$('#ch-to').value};
  else from=new Date(to.getTime()-parseInt(p)*86400000);
  const f=d=>d.toISOString().slice(0,10);return {from:f(from),to:f(to)};}
async function loadCharts(){try{await loadChartLib();}catch(e){return;}
  const r=chPeriodRange();let url='/api/charts';if(r.from||r.to)url+='?from='+encodeURIComponent(r.from||'')+'&to='+encodeURIComponent(r.to||'');
  let d;try{d=await (await fetch(url,{headers:H()})).json();}catch(e){return;}
  if(d.range&&$('#ch-range'))$('#ch-range').textContent=d.range.from+' → '+d.range.to;
  const grid='rgba(93,178,255,.12)';Chart.defaults.color='#7d93aa';Chart.defaults.font.family='Inter, sans-serif';
  const PAL=['#35c8ff','#7fe3ff','#1f8fbf','#5aa0cf','#2bd6c0','#9d7bff','#ff8a8a','#ffd166'];
  function mk(id,cfg){if(_charts[id])_charts[id].destroy();const cx=document.getElementById(id);if(!cx)return;_charts[id]=new Chart(cx,cfg);}
  const cat=d.exp_cat||[];mk('ch-cat',{type:'doughnut',data:{labels:cat.map(x=>x.label),datasets:[{data:cat.map(x=>x.value),backgroundColor:PAL,borderColor:'#04070c',borderWidth:2}]},options:{plugins:{legend:{position:'right'}}}});
  const day=d.exp_day||[];mk('ch-day',{type:'bar',data:{labels:day.map(x=>x.label),datasets:[{data:day.map(x=>x.value),backgroundColor:'#35c8ff',borderRadius:4}]},options:{plugins:{legend:{display:false}},scales:{x:{grid:{color:grid}},y:{grid:{color:grid}}}}});
  const hab=d.habits||[];mk('ch-hab',{type:'bar',data:{labels:hab.map(x=>x.label),datasets:[{data:hab.map(x=>x.value),backgroundColor:'#7fe3ff',borderRadius:4}]},options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{grid:{color:grid}},y:{grid:{color:grid}}}}});}
(function(){const ps=document.getElementById('ch-period');if(!ps)return;
  ps.onchange=()=>{const cst=ps.value==='custom';const cf=$('#ch-from'),ct=$('#ch-to');if(cf)cf.style.display=cst?'block':'none';if(ct)ct.style.display=cst?'block':'none';if(!cst)loadCharts();};
  const cf=$('#ch-from'),ct=$('#ch-to');if(cf)cf.onchange=()=>{if(ct.value)loadCharts();};if(ct)ct.onchange=()=>{if(cf.value)loadCharts();};})();
function splitRow(r){return r.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());}
function renderTable(box,rows){const t=document.createElement('table');t.className='mtable';
  const thead=document.createElement('thead'),htr=document.createElement('tr');
  splitRow(rows[0]).forEach(h=>{const th=document.createElement('th');appendRich(th,h);htr.appendChild(th);});
  thead.appendChild(htr);t.appendChild(thead);const tb=document.createElement('tbody');
  rows.slice(2).forEach(r=>{const tr=document.createElement('tr');splitRow(r).forEach(c=>{const td=document.createElement('td');appendRich(td,c);tr.appendChild(td);});tb.appendChild(tr);});
  t.appendChild(tb);box.appendChild(t);}
function renderLine(box,s,st){let m;
  if((m=s.match(/^!\[[^\]]*\]\((https?:\/\/[^)\s]+)\)$/))){const im=document.createElement('img');im.src=m[1];im.className='mimg';im.loading='lazy';im.alt='mapa';im.onerror=()=>im.remove();box.appendChild(im);st.first=false;return;}
  if(SEPRE.test(s)){box.appendChild(el('div','sep'));return;}
  if(EMOLEAD.test(s)){
    if(st.first){const h=el('span','h');h.appendChild(ficon(iconName(s)));h.appendChild(document.createTextNode(stripEmoji(s)));box.appendChild(h);st.first=false;return;}
    const sub=el('div','sub');sub.appendChild(ficon(iconName(s)));const sp=el('span','');appendRich(sp,stripEmoji(s));sub.appendChild(sp);box.appendChild(sub);return;}
  if((m=s.match(/^\[(.+)\]$/))){box.appendChild(el('div','cat',m[1]));return;}
  if((m=s.match(/^#{1,6}\s+(.+)$/))){const h=el('div','mdh');appendRich(h,stripEmoji(m[1]).replace(/\*+/g,''));box.appendChild(h);st.first=false;return;}
  if((m=s.match(/^[-*•]\s+(.+)$/))){const b=el('div','bul');const sp=el('span','');appendRich(sp,stripEmoji(m[1]));b.appendChild(sp);box.appendChild(b);st.first=false;return;}
  if((m=s.match(/^#(\w+)\s+(.*)$/))){const r=el('div','row');r.appendChild(el('span','id','#'+m[1]));
    const t=el('span','t');const tt=stripEmoji(m[2]);const parts=tt.split(/\s+(?=\d+[.)]\s)/);
    if(parts.length>1)parts.forEach(p=>{const dv=el('div','');appendRich(dv,p);t.appendChild(dv);});else appendRich(t,tt);
    r.appendChild(t);box.appendChild(r);return;}
  if(/^(Concluir|Cancelar|Uso|Remover|Apagar):/i.test(s)||s.startsWith('/')){const hh=el('div','hint');appendRich(hh,stripEmoji(s));box.appendChild(hh);return;}
  const pp=el('p','');appendRich(pp,stripEmoji(s));box.appendChild(pp);st.first=false;}
function renderReply(box,text){box.textContent='';const lines=(text||'').split('\n');const st={first:true};
  for(let i=0;i<lines.length;i++){const s=lines[i].trim();
    if(/^\|.*\|$/.test(s)&&i+1<lines.length&&/^\|[\s:|-]+\|$/.test(lines[i+1].trim())){
      const rows=[s];let j=i+2;while(j<lines.length&&/^\|.*\|$/.test(lines[j].trim())){rows.push(lines[j].trim());j++;}
      renderTable(box,rows);i=j-1;st.first=false;continue;}
    if(!s)continue;
    renderLine(box,s,st);}
  window.lucide&&lucide.createIcons();
}
function you(t){const d=el('div','msg you',t);log.appendChild(d);log.scrollTop=log.scrollHeight;}
function ev(t){const d=el('div','msg ev');renderReply(d,t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function sys(t){const d=el('div','msg sys',t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function thinking(){const d=el('div','msg ev');d.innerHTML='<span class="tp"><i></i><i></i><i></i></span>';log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ripple(b,e){const r=el('span','ripple');const q=b.getBoundingClientRect(),s=Math.max(q.width,q.height);
  r.style.width=r.style.height=s+'px';r.style.left=((e?e.clientX:q.left+q.width/2)-q.left-s/2)+'px';
  r.style.top=((e?e.clientY:q.top+q.height/2)-q.top-s/2)+'px';b.appendChild(r);setTimeout(()=>r.remove(),500);}
let _audio=null,_audioMsg=false,_speaking=false;
function stopSpeaking(){try{if(_audio){_audio.pause();_audio.currentTime=0;}}catch(e){}_speaking=false;document.body.classList.remove('speaking');}
// audio-reactive visualizer for the live voice screen (Web Audio analyser on _audio)
let _actx=null,_analyser=null,_vizData=null,_vizSrc=null;
function ensureViz(){if(_analyser||!_audio)return;
  try{_actx=new (window.AudioContext||window.webkitAudioContext)();
    _vizSrc=_actx.createMediaElementSource(_audio);_analyser=_actx.createAnalyser();_analyser.fftSize=128;
    _vizSrc.connect(_analyser);_analyser.connect(_actx.destination);
    _vizData=new Uint8Array(_analyser.frequencyBinCount);}catch(e){_analyser=null;}}
function resumeAudioCtx(){try{if(_actx&&_actx.state==='suspended')_actx.resume();}catch(e){}}
function vizFrame(){requestAnimationFrame(vizFrame);
  const cv=document.getElementById('vc-viz');if(!cv)return;
  const open=vc&&vc.classList.contains('on');
  cv.style.opacity=(open&&_speaking)?'1':'0';
  const ctx=cv.getContext('2d');const W=cv.width,H=cv.height;ctx.clearRect(0,0,W,H);
  if(!open||!_speaking||!_analyser)return;
  _analyser.getByteFrequencyData(_vizData);
  const cx=W/2,cy=H/2,R=Math.min(W,H)*0.24,N=_vizData.length;
  ctx.lineWidth=3.4;ctx.lineCap='round';ctx.strokeStyle='rgba(53,200,255,.92)';
  for(let i=0;i<N;i++){const a=(i/N)*Math.PI*2-Math.PI/2;const v=_vizData[i]/255;const len=R*0.2+v*R*0.95;
    ctx.globalAlpha=0.3+v*0.7;
    ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*R,cy+Math.sin(a)*R);ctx.lineTo(cx+Math.cos(a)*(R+len),cy+Math.sin(a)*(R+len));ctx.stroke();}
  ctx.globalAlpha=1;}
requestAnimationFrame(vizFrame);
function unlockAudio(){if(!_audio)_audio=new Audio();ensureViz();resumeAudioCtx();try{_audio.play().catch(()=>{});}catch(e){}}
window.addEventListener('pointerdown',unlockAudio,{once:true});
async function speak(t,force){if((!voiceOn&&!force)||!t)return;try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text:t})});if(!r.ok)return;const url=URL.createObjectURL(await r.blob());if(!_audio)_audio=new Audio();ensureViz();resumeAudioCtx();_audio.src=url;_speaking=true;document.body.classList.add('speaking');_audio.onended=()=>{_speaking=false;document.body.classList.remove('speaking');};await _audio.play().catch(()=>{_speaking=false;document.body.classList.remove('speaking');if(!_audioMsg){_audioMsg=true;sys('O navegador bloqueou o áudio automático. Toque uma vez na tela e a E.V. volta a falar.');}});}catch(e){_speaking=false;document.body.classList.remove('speaking');}}

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

const CAT={plano:['Plano do dia','sunrise'],pendencias:['Pendências','bell-ring'],padroes:['Padrões','sparkles'],automacoes:['Automações','zap'],bak:['Backup','database-backup'],tarefas:['Tarefas','list-checks'],lembretes:['Lembretes','alarm-clock'],gastos:['Gastos','wallet'],memorias:['Memórias','brain'],kb:['Base','book-open'],map:['Mapa','map'],graf:['Gráficos','bar-chart-3'],brain:['Cérebro','brain-circuit'],cam:['Câmera','camera'],buscar:['Buscar web','search'],noticias:['Notícias','newspaper'],clima:['Clima','cloud-sun'],relatorio:['Relatório','bar-chart-3'],status:['Status','activity'],semana:['Semana','calendar-days'],foco:['Pomodoro','timer'],procurar:['Procurar','file-search'],calendario:['Agenda','calendar'],habitos:['Hábitos','repeat'],diario:['Diário','notebook-pen'],orcamentos:['Orçamentos','piggy-bank'],assinaturas:['Assinaturas','credit-card'],dados:['Meus dados','database'],insights:['Insights','sparkles'],quiz:['Quiz','graduation-cap']};
const SM={tasks:['Tarefas','list-checks','tarefas'],reminders:['Lembretes','alarm-clock','lembretes'],expenses:['Gastos · mês','wallet','gastos'],memories:['Memórias','brain','memorias'],kb:['Base','book-open','kb'],kbfiles:['Arquivos','file-text','kb'],links:['Links','link','links'],habits:['Hábitos','repeat','habitos'],journal:['Diário','notebook-pen','diario'],subscriptions:['Assinaturas','credit-card','assinaturas'],budgets:['Orçamentos','piggy-bank','orcamentos'],watches:['Monitores','radar','monitores'],agenda:['Agenda · 7d','calendar','calendario'],activity:['Histórico · 24h','history','status'],provider:['Provedor','cpu','status'],model:['Modelo','box','modelo'],disk:['Disco','hard-drive','status'],ram:['RAM','memory-stick','status'],uptime:['Uptime','clock','status']};
const RECUR=[{v:'',l:'Uma vez'},{v:'daily',l:'Diário'},{v:'weekly',l:'Semanal'},{v:'monthly',l:'Mensal'}];
const RECUR_LBL={daily:'repete diário',weekly:'repete semanal',monthly:'repete mensal'};
let config={actions:['plano','buscar','noticias','clima','relatorio','semana'],stats:['tasks','reminders','expenses','memories','kb']};let _counts={};
function renderStats(){const box=$('#stats');box.textContent='';config.stats.forEach(k=>{const m=SM[k];if(!m)return;
  const VMAP={tasks:'tasks',reminders:'rem',expenses:'exp',memories:'mem',kb:'kb',kbfiles:'kb',links:'lnk',habits:'hab',journal:'jou',subscriptions:'sub',budgets:'orc',watches:'mon',agenda:'cal',activity:'act'};
  const s=el('div','stat');s.onclick=()=>{if(VMAP[k])switchView(VMAP[k]);else runCmd(m[2]);};const lbl=el('span','lbl');lbl.appendChild(ficon(m[1]));lbl.appendChild(document.createTextNode(m[0]));
  const num=el('span','num');if(k==='expenses'){const rs=el('span','','R$');rs.style.cssText='font-size:12px;color:var(--subtle);margin-right:2px';num.appendChild(rs);}
  num.appendChild(document.createTextNode(_counts[k]!=null?_counts[k]:'0'));s.appendChild(lbl);s.appendChild(num);box.appendChild(s);});window.lucide&&lucide.createIcons();}
function renderActs(){const box=$('#acts');box.textContent='';config.actions.forEach(cmd=>{const m=CAT[cmd]||[cmd,'chevron-right'];
  const b=el('button','act');b.appendChild(ficon(m[1]));b.appendChild(document.createTextNode(m[0]));
  b.onclick=e=>{if(cmd==='foco'){openPomo(25);return;}ripple(b,e);if(cmd==='cam'){$('#cambtn').click();return;}if(cmd==='bak'){window.location='/api/backup?k='+encodeURIComponent(token);toast('Baixando backup cifrado…');return;}if(VIEWS[cmd]){switchView(cmd);return;}runCmd(cmd,b,e);};box.appendChild(b);});window.lucide&&lucide.createIcons();}
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
    pipWin.document.body.style.cssText='margin:0;background:#04070c;color:#d6e9fb;display:flex;align-items:center;justify-content:center;height:100vh;cursor:pointer';
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
  d.messages.forEach(m=>m.role==='user'?youHistory(m.content):ev(m.content));}catch(e){}}
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
// mostra a resposta da voz com a MESMA formatação bonita do chat (sem ** cru)
function vcShowReply(reply){vcTxt.innerHTML='';const b=el('div','msg ev');renderReply(b,reply||'(sem resposta)');vcTxt.appendChild(b);}
$('#vcopen').onclick=()=>{if(!RECOK){sys('Gravação de áudio indisponível neste navegador.');return;}vc.classList.add('on');vcTxt.textContent='Toque no microfone e fale. Toque de novo para enviar.';$('#vc-sub').textContent='pasta: '+thread+' · a conversa fica salva aqui';};
$('#vc-x').onclick=()=>{if(_recActive)stopRec();if(_hf){stopHF();renderHFBtn();}stopSpeaking();vc.classList.remove('on');setState(_ambient?'listening':'');};
vcMic.onclick=async()=>{
  if(!RECOK){vcTxt.textContent='Gravação de áudio indisponível neste navegador.';return;}
  if(_recActive){stopRec();vcTxt.textContent='transcrevendo...';return;}
  vcMic.classList.add('rec');setState('listening');vcTxt.textContent='ouvindo... (toque de novo para enviar)';
  const res=await startRec(async blob=>{vcMic.classList.remove('rec');setState('thinking');vcTxt.textContent='transcrevendo...';
    try{const t=await sttBlob(blob);if(!t){vcTxt.textContent='Não entendi. Toque no microfone e fale de novo.';setState();return;}
      vcTxt.textContent='"'+t+'"';
      const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:t,thread})});const j=await r.json();
      vcShowReply(j.reply);speak(j.reply,true);loadPanel();
    }catch(x){vcTxt.textContent='Falha ao processar o áudio. Tente de novo.';}finally{setState();}});
  if(res!==true){vcMic.classList.remove('rec');setState();vcTxt.textContent=micErrMsg(res);}};

// --- hands-free: escuta contínua + palavra de ativação "E.V." (Web Speech API) ---
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let _hf=false,_rec=null,_hfBusy=false,_ambient=false;
function vcOpen(){return vc.classList.contains('on');}
// aceita variações de como o STT ouve "E.V." em pt-BR (ev, eva, e vê, êvê, ei vi...)
// "E.V." é ouvido pelo STT de MUITAS formas (evee, yvee, eveee, evi, ivi, e vê...).
// Normaliza cada palavra (minúsculas, sem pontuação, colapsa letras repetidas) e
// compara com um conjunto de variações que soam como "é-vê".
const WAKESET=new Set(['ev','eve','eva','evo','evi','yve','yvi','yv','ive','ivi','ivy','iv','aivi','evie','êvê','eev','hev','hive','evee']);
function normTok(w){return (w||'').toLowerCase().replace(/[^a-zà-ÿ]/g,'').replace(/(.)\1+/g,'$1');}
function extractCommand(t){let s=(t||'').trim();
  s=s.replace(/\be[.\s]+v[êei]*(?![a-zà-ÿ])[\s.,:!?;-]*/i,' eve ');   // junta "e vê"/"e v"/"e.v."
  const words=s.split(/\s+/).filter(Boolean);
  for(let i=0;i<words.length;i++){if(WAKESET.has(normTok(words[i])))return words.slice(i+1).join(' ').trim();}
  return null;}
function hasWake(t){return extractCommand(t)!==null;}
function hfSay(t){if(vcOpen())vcTxt.textContent=t;else toast(t);}
async function processHF(text){if(_hfBusy)return;_hfBusy=true;stopSpeaking();
  setState('thinking');hfSay('"'+text+'"');
  try{const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:text,thread})});
    const j=await r.json();
    if(vcOpen())vcShowReply(j.reply);else toast((j.reply||'').slice(0,220));
    speak(j.reply,true);loadPanel();
  }catch(e){hfSay('Falha ao falar com a E.V. Tenta de novo.');}
  finally{_hfBusy=false;setState((_hf||_ambient)?'listening':'');}}
// Single SpeechRecognition shared by hands-free (voice screen) and ambient presence.
function ensureRec(){if(_rec)return true;if(!SR)return false;
  try{_rec=new SR();}catch(e){return false;}
  _rec.lang='pt-BR';_rec.continuous=true;_rec.interimResults=true;
  _rec.onresult=ev=>{for(let i=ev.resultIndex;i<ev.results.length;i++){const res=ev.results[i];
    const txt=res[0].transcript;
    // barge-in: se a E.V. está falando e o dono a chamou de novo, cala e escuta
    if(_speaking&&hasWake(txt))stopSpeaking();
    if(!res.isFinal)continue;
    const cmd=extractCommand(txt);
    if(cmd===null)continue;                 // não foi chamada pela E.V.
    if(!cmd){hfSay('Pois não, Ryan?');speak('Pois não?',true);continue;}
    processHF(cmd);}};
  _rec.onerror=e=>{if(e.error==='not-allowed'||e.error==='service-not-allowed'){
    _hf=false;_ambient=false;renderHFBtn();renderAmbBtn();hfSay('Permita o microfone para escutar por voz.');}};
  _rec.onend=()=>{if(_hf||_ambient){try{_rec.start();}catch(e){}}};   // reinicia (o SR para sozinho)
  try{_rec.start();}catch(e){}
  return true;}
function maybeStopRec(){if(!_hf&&!_ambient&&_rec){try{_rec.onend=null;_rec.stop();}catch(e){}_rec=null;}}
function startHF(){if(!SR){vcTxt.textContent='Mãos-livres precisa do Chrome, Edge ou Safari. No Firefox, use o microfone manual.';return false;}
  return ensureRec();}
function stopHF(){_hf=false;maybeStopRec();}
function renderHFBtn(){const b=$('#vc-cont');b.innerHTML='';b.appendChild(ficon(_hf?'ear':'ear-off'));
  b.appendChild(document.createTextNode(' Mãos-livres: '+(_hf?'on — diga "E.V. ..."':'off')));b.classList.toggle('on',_hf);window.lucide&&lucide.createIcons();}
$('#vc-cont').onclick=()=>{if(!SR){vcTxt.textContent='Mãos-livres precisa do Chrome, Edge ou Safari. No Firefox, use o microfone manual.';return;}
  if(_hf){stopHF();setState();}else{_hf=true;if(startHF()){vcTxt.textContent='Modo mãos-livres ligado. É só dizer: "E.V., ..."';setState('listening');}else{_hf=false;}}renderHFBtn();};
renderHFBtn();
// Ambient presence — keeps listening globally so "E.V. ..." works from any screen.
function renderAmbBtn(){const b=$('#amb');if(!b)return;b.classList.toggle('on',_ambient);
  b.title=_ambient?'Presença ambiente ligada — escuta "E.V. ..." sempre':'Presença ambiente — escuta "E.V. ..." sempre';
  let d=document.getElementById('amb-dot');
  if(_ambient){if(!d){d=el('div','');d.id='amb-dot';d.style.cssText='position:fixed;bottom:22px;left:22px;display:flex;align-items:center;gap:8px;padding:7px 13px;border-radius:20px;background:rgba(4,7,12,.72);border:1px solid var(--accent);color:var(--fg);font-size:12px;letter-spacing:.06em;z-index:9998;box-shadow:0 0 18px var(--glow);backdrop-filter:blur(4px)';d.innerHTML='<span style="width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent);animation:ambpulse 1.4s infinite"></span>E.V. OUVINDO';document.body.appendChild(d);if(document.body.classList.contains('ff'))d.style.backdropFilter='none';}}
  else if(d){d.remove();}}
function toggleAmb(){if(!SR){toast('Presença ambiente precisa do Chrome, Edge ou Safari.');return;}
  if(_ambient){_ambient=false;maybeStopRec();setState((_hf)?'listening':'');}
  else{_ambient=true;if(!ensureRec()){_ambient=false;}else{toast('Presença ambiente ligada — é só dizer "E.V. ..." a qualquer momento.');setState('listening');}}
  renderAmbBtn();}
$('#amb').onclick=toggleAmb;
renderAmbBtn();
// view tabs — customizable: pick which appear in the header (minimalist)
const VIEW_LABELS={chat:'Conversa',tasks:'Tarefas',exp:'Gastos',rem:'Lembretes',cal:'Agenda',mem:'Memórias',lnk:'Links',hab:'Hábitos',jou:'Diário',sub:'Assinaturas',orc:'Orçamentos',mon:'Monitores',act:'Histórico',kb:'Base',map:'Mapa',brain:'Cérebro',graf:'Gráficos'};
let curView='chat',tabsShown;try{tabsShown=JSON.parse(localStorage.getItem('ev_tabs'));}catch(e){}
if(!Array.isArray(tabsShown)||!tabsShown.length)tabsShown=['chat','tasks','exp','rem','cal','brain'];
function renderTabs(){const box=$('#tabs');if(!box)return;box.textContent='';
  tabsShown.forEach(v=>{if(!VIEW_LABELS[v])return;const b=el('button','tab'+(v===curView?' on':''),VIEW_LABELS[v]);b.dataset.view=v;b.onclick=()=>switchView(v);box.appendChild(b);});
  const ed=el('button','tab tab-edit','+');ed.title='Escolher abas';ed.onclick=()=>openPicker('Abas do topo','Escolha quais abas aparecem no topo.',Object.keys(VIEW_LABELS).map(k=>({key:k,label:VIEW_LABELS[k]})),tabsShown,l=>{tabsShown=l.length?l:['chat'];localStorage.setItem('ev_tabs',JSON.stringify(tabsShown));renderTabs();});box.appendChild(ed);}
renderTabs();
$('#mnav').onchange=()=>switchView($('#mnav').value);
const VIEWS={chat:'#chatview',tasks:'#taskview',exp:'#expview',rem:'#remview',cal:'#calview',mem:'#memview',lnk:'#lnkview',hab:'#habview',jou:'#jouview',sub:'#subview',orc:'#orcview',mon:'#monview',kb:'#kbview',act:'#actview',map:'#mapview',brain:'#brainview',graf:'#chartsview'};
function switchView(v){if(!VIEWS[v])v='chat';curView=v;document.querySelectorAll('#tabs .tab').forEach(t=>t.classList.toggle('on',t.dataset.view===v));
  const mn=$('#mnav');if(mn&&mn.value!==v)mn.value=v;
  document.body.classList.remove('m-left','m-right');
  Object.entries(VIEWS).forEach(([k,sel])=>{const el2=$(sel);if(el2)el2.style.display=(k===v)?((k==='chat'||k==='brain')?'flex':'block'):'none';});
  ({tasks:loadTasks,exp:loadExp,rem:loadRem,mem:loadMem,kb:loadKB,cal:loadCal,lnk:loadLinks,hab:loadHabits,jou:loadJournal,sub:loadSub,orc:loadOrc,mon:loadMon,act:loadAct,map:loadMap,brain:loadBrain,graf:loadCharts}[v]||function(){})();}
// --- Mapa + localização (Leaflet + OSM; lugares e pontos dentro da própria E.V.) ---
let _map=null,_marker=null,_loc=null,_nearLayer=null,_savedLayer=null,_addMode=false,_pendingNear=null;
let _baseDark=null,_baseSat=null,_sat=false;
const MAP_CHIPS=[['Onde estou','locate-fixed'],['Metrô','tram-front'],['Trem','train-front'],['Ônibus','bus'],['Farmácia','pill'],['Mercado','shopping-cart'],['Restaurante','utensils'],['Padaria','croissant'],['Café','coffee'],['Posto','fuel'],['Banco','landmark'],['Hospital','cross'],['Academia','dumbbell']];
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function askEV(name,lat,lng){switchView('chat');send('me conta sobre "'+name+'", que fica perto de mim.');}
function routeBtn(name,lat,lng){const b=el('span','pop-b');b.appendChild(ficon('route'));b.appendChild(document.createTextNode('Traçar rota'));b.onclick=()=>routeTo(lat,lng,name);return b;}
function poiPopup(name,lat,lng,dist){const d=document.createElement('div');
  d.innerHTML='<div class="pop-n">'+esc(name)+'</div>'+(dist!=null?'<div class="pop-d">~'+dist+' m de você</div>':'');
  const ask=el('span','pop-b');ask.appendChild(ficon('message-circle'));ask.appendChild(document.createTextNode('Perguntar à E.V.'));ask.onclick=()=>askEV(name,lat,lng);
  d.appendChild(routeBtn(name,lat,lng));d.appendChild(ask);window.lucide&&lucide.createIcons();return d;}
function renderMapChips(){const box=$('#map-chips');box.textContent='';
  MAP_CHIPS.forEach(([label,ic])=>{const b=el('button','mchip');b.type='button';b.appendChild(ficon(ic));b.appendChild(document.createTextNode(label));
    b.onclick=(e)=>{ripple(b,e);label==='Onde estou'?locateMe():showNearby(label);};box.appendChild(b);});window.lucide&&lucide.createIcons();}
let _routeLayer=null,_routeFT=null,_routeMode='car',_savedPlaces=[];
function fmtDur(s){const m=Math.round(s/60);return m>=60?Math.floor(m/60)+'h '+(m%60)+'min':m+' min';}
function fmtDist(m){return m>=1000?(m/1000).toFixed(1).replace('.',',')+' km':m+' m';}
function clearRoute(){if(_routeLayer){_routeLayer.remove();_routeLayer=null;}_routeFT=null;$('#map-route').classList.remove('on');}
function routeTo(lat,lng,name){if(!_loc){_routeFT=[null,[lat,lng],name||''];$('#map-status').textContent='Localizando pra traçar a rota...';locateMe();return;}
  drawRouteFT(_loc,[lat,lng],name||'');}
async function drawRouteFT(from,to,label){if(!from||!to)return;_routeFT=[from,to,label];
  const banner=$('#map-route');banner.classList.add('on');banner.innerHTML='';const info=el('div','rt-info','Calculando tempo...');banner.appendChild(info);
  let r=null;try{r=await (await fetch('/api/route',{method:'POST',headers:H(),body:JSON.stringify({from,to,mode:_routeMode})})).json();}catch(e){}
  if(!r||!r.ok){info.textContent='Não consegui calcular a rota agora.';return;}
  if(_routeLayer)_routeLayer.remove();
  _routeLayer=L.geoJSON(r.geometry,{style:{color:'#35c8ff',weight:5,opacity:.85}}).addTo(_map);
  try{_map.fitBounds(_routeLayer.getBounds(),{padding:[70,70]});}catch(e){}
  const mt=_routeMode==='foot'?' a pé':_routeMode==='bike'?' de bike':' de carro';
  info.textContent=(label?label+' · ':'')+'~'+fmtDur(r.duration)+' · '+fmtDist(r.distance)+mt;
  [['car','Carro'],['foot','A pé'],['bike','Bike']].forEach(a=>{const b=el('button','rt-b'+(_routeMode===a[0]?' on':''),a[1]);b.onclick=()=>{_routeMode=a[0];drawRouteFT(from,to,label);};banner.appendChild(b);});
  const clr=el('button','rt-b','Limpar');clr.onclick=clearRoute;banner.appendChild(clr);window.lucide&&lucide.createIcons();}
function planCoord(v){if(v==='me')return _loc;const p=_savedPlaces.find(x=>String(x.id)===v);return p?[p.lat,p.lng]:null;}
function refreshPlanner(){const opts=[['me','Minha localização']].concat(_savedPlaces.map(p=>[String(p.id),p.name]));
  ['plan-from','plan-to'].forEach(id=>{const s=$('#'+id);const cur=s.value;s.innerHTML='';opts.forEach(o=>{const op=document.createElement('option');op.value=o[0];op.textContent=o[1];s.appendChild(op);});if(cur)s.value=cur;});
  if($('#plan-to').value==='me'&&_savedPlaces.length)$('#plan-to').value=String(_savedPlaces[0].id);}
async function addByAddress(){const q=prompt('Endereço ou local (ex: Av. Paulista 1578, São Paulo):');if(!q)return;
  $('#map-status').textContent='Procurando "'+q+'"...';
  let g=null;try{g=await (await fetch('/api/geocode?q='+encodeURIComponent(q),{headers:H()})).json();}catch(e){}
  if(!g||!g.ok){$('#map-status').textContent='Não achei esse endereço. Tenta mais detalhado.';return;}
  const name=prompt('Nome do ponto:',(g.name||q).split(',')[0]);if(!name)return;
  const d=await (await fetch('/api/places',{method:'POST',headers:H(),body:JSON.stringify({name,lat:g.lat,lng:g.lng})})).json();
  addSavedMarker({id:d.id,name,lat:g.lat,lng:g.lng});if(_map)_map.setView([g.lat,g.lng],16);
  $('#map-status').textContent='Ponto "'+name+'" salvo';}
async function showNearby(query){if(!_loc){_pendingNear=query;$('#map-status').textContent='Preciso da sua localização — localizando...';locateMe();return;}
  $('#map-status').textContent='Buscando "'+query+'" por perto...';
  let items=[];try{const r=await fetch('/api/nearby',{method:'POST',headers:H(),body:JSON.stringify({query,lat:_loc[0],lng:_loc[1]})});items=(await r.json()).items||[];}catch(e){}
  if(_nearLayer)_nearLayer.clearLayers();else _nearLayer=L.layerGroup().addTo(_map);
  const res=$('#map-results');res.innerHTML='';
  if(!items.length){$('#map-status').textContent='Não achei "'+query+'" num raio de ~1,6 km.';res.classList.remove('on');return;}
  $('#map-status').textContent=items.length+' resultado(s) para "'+query+'"';
  const head=el('div','mr-h');head.appendChild(document.createTextNode(query.toUpperCase()));const x=document.createElement('b');x.textContent='fechar';x.onclick=()=>{res.classList.remove('on');if(_nearLayer)_nearLayer.clearLayers();};head.appendChild(x);res.appendChild(head);
  const bounds=[_loc];
  items.forEach(it=>{const m=L.circleMarker([it.lat,it.lng],{radius:7,weight:2,color:'#8fe0ff',fillColor:'#35c8ff',fillOpacity:.85}).addTo(_nearLayer);
    m.bindPopup(()=>poiPopup(it.name,it.lat,it.lng,it.dist));bounds.push([it.lat,it.lng]);
    const row=el('div','mres');row.appendChild(el('div','mr-n',it.name));row.appendChild(el('div','mr-d','~'+it.dist+' m'));
    row.onclick=()=>{_map.setView([it.lat,it.lng],16);m.openPopup();};res.appendChild(row);});
  res.classList.add('on');try{_map.fitBounds(bounds,{padding:[60,60],maxZoom:16});}catch(e){}}
let _savedMarkers={};
function addSavedMarker(p){if(!_savedLayer)_savedLayer=L.layerGroup().addTo(_map);const m=L.marker([p.lat,p.lng]).addTo(_savedLayer);_savedMarkers[p.id]=m;
  m.bindPopup(()=>{const d=document.createElement('div');d.innerHTML='<div class="pop-n">'+esc(p.name)+'</div><div class="pop-d">ponto salvo</div>';
    const ask=el('span','pop-b');ask.appendChild(ficon('message-circle'));ask.appendChild(document.createTextNode('Perguntar à E.V.'));ask.onclick=()=>askEV(p.name,p.lat,p.lng);
    const del=el('span','pop-b');del.appendChild(ficon('trash-2'));del.appendChild(document.createTextNode('Remover'));del.onclick=async()=>{await fetch('/api/places/delete',{method:'POST',headers:H(),body:JSON.stringify({id:p.id})});m.remove();delete _savedMarkers[p.id];_savedPlaces=_savedPlaces.filter(x=>x.id!==p.id);};
    d.appendChild(routeBtn(p.name,p.lat,p.lng));d.appendChild(ask);d.appendChild(del);window.lucide&&lucide.createIcons();return d;});}
function loadSavedPlaces(){fetch('/api/places',{headers:H()}).then(r=>r.json()).then(d=>{
  _savedPlaces=d.items||[];_savedMarkers={};if(_savedLayer)_savedLayer.clearLayers();_savedPlaces.forEach(addSavedMarker);}).catch(()=>{});}
function showSavedList(){const res=$('#map-results');res.innerHTML='';
  if(!_savedPlaces.length){$('#map-status').textContent='Você ainda não salvou pontos. Use "Adicionar ponto" ou "Adicionar endereço".';res.classList.remove('on');return;}
  const head=el('div','mr-h');head.appendChild(document.createTextNode('MEUS PONTOS ('+_savedPlaces.length+')'));const x=document.createElement('b');x.textContent='fechar';x.onclick=()=>res.classList.remove('on');head.appendChild(x);res.appendChild(head);
  _savedPlaces.forEach(p=>{const row=el('div','mres');row.appendChild(el('div','mr-n',p.name));
    const act=el('div','mr-d');const go=document.createElement('span');go.textContent='ver no mapa';go.style.cursor='pointer';go.onclick=(e)=>{e.stopPropagation();_map.setView([p.lat,p.lng],16);const mk=_savedMarkers[p.id];if(mk)mk.openPopup();};
    const rt=document.createElement('span');rt.textContent=' · traçar rota';rt.style.cursor='pointer';rt.onclick=(e)=>{e.stopPropagation();routeTo(p.lat,p.lng,p.name);};
    act.appendChild(go);act.appendChild(rt);row.appendChild(act);
    row.onclick=()=>{_map.setView([p.lat,p.lng],16);const mk=_savedMarkers[p.id];if(mk)mk.openPopup();};res.appendChild(row);});
  res.classList.add('on');$('#map-status').textContent=_savedPlaces.length+' ponto(s) salvo(s)';}
let _accCircle=null,_fixMode=false;
function setMyLocation(lat,lng,acc){_loc=[lat,lng];
  if(_map){_map.setView(_loc,acc&&acc>1500?14:16);
    if(_marker)_marker.setLatLng(_loc);else _marker=L.circleMarker(_loc,{radius:9,weight:3,color:'#35c8ff',fillColor:'#35c8ff',fillOpacity:.7}).addTo(_map);
    if(_accCircle){_accCircle.remove();_accCircle=null;}
    if(acc)_accCircle=L.circle(_loc,{radius:acc,color:'#35c8ff',weight:1,fillColor:'#35c8ff',fillOpacity:.07}).addTo(_map);
    setTimeout(()=>_map.invalidateSize(),80);}
  fetch('/api/location',{method:'POST',headers:H(),body:JSON.stringify({lat,lng})}).catch(()=>{});
  if(_pendingNear){const q=_pendingNear;_pendingNear=null;showNearby(q);}
  if(_routeFT&&!_routeFT[0])drawRouteFT(_loc,_routeFT[1],_routeFT[2]);}
function locateMe(){const st=$('#map-status');if(!navigator.geolocation){st.textContent='Geolocalização indisponível neste navegador.';return;}
  st.textContent='Localizando seu dispositivo...';
  navigator.geolocation.getCurrentPosition(p=>{const acc=Math.round(p.coords.accuracy||0);
    setMyLocation(p.coords.latitude,p.coords.longitude,acc);
    st.textContent=acc>1500?('Localização aproximada (~'+acc+' m) — no PC costuma errar. Use "Corrigir localização" se estiver errado.'):('Você está aqui'+(acc?' (~'+acc+' m)':'')+' · toque num tipo de lugar');
  },()=>{st.textContent='Não consegui pegar sua localização — permita o acesso e tente de novo.';},{enableHighAccuracy:true,timeout:15000,maximumAge:0});}
async function fixLocation(){const q=prompt('Seu endereço atual (ou deixe vazio pra escolher tocando no mapa):');
  if(q===null)return;
  if(q.trim()){$('#map-status').textContent='Procurando "'+q+'"...';let g=null;try{g=await (await fetch('/api/geocode?q='+encodeURIComponent(q),{headers:H()})).json();}catch(e){}
    if(!g||!g.ok){$('#map-status').textContent='Não achei esse endereço. Tenta com mais detalhe (rua, número, cidade).';return;}
    setMyLocation(g.lat,g.lng,0);$('#map-status').textContent='Localização definida por endereço.';return;}
  _fixMode=true;$('#map-status').textContent='Toque no mapa exatamente onde você está pra definir sua localização.';}
function loadMap(){
  if(!window.L){$('#map').innerHTML='<div class="tv-empty" style="padding:20px">Mapa indisponível (sem conexão com o Leaflet).</div>';return;}
  if(!_map){_map=L.map('map',{zoomControl:false,attributionControl:false}).setView([-23.5505,-46.6333],12);
    L.control.zoom({position:'topright'}).addTo(_map);
    _baseDark=L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:20,subdomains:'abcd'}).addTo(_map);
    // Real-world aerial imagery (Esri World Imagery, free) + street labels overlay,
    // so "zooming in" shows the world as it actually looks — streets and buildings.
    _baseSat=L.layerGroup([
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:20,maxNativeZoom:19}),
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png',{maxZoom:20,subdomains:'abcd',opacity:.9})
    ]);
    $('#map-sat').onclick=()=>{_sat=!_sat;const b=$('#map-sat');b.classList.toggle('on',_sat);
      if(_sat){_map.removeLayer(_baseDark);_baseSat.addTo(_map);}else{_map.removeLayer(_baseSat);_baseDark.addTo(_map);}
      b.lastChild&&(b.lastChild.textContent=_sat?'Mapa':'Satélite');};
    $('#map-street').onclick=()=>{const c=(_loc?{lat:_loc[0],lng:_loc[1]}:_map.getCenter());
      window.open('https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='+c.lat+','+c.lng,'_blank','noopener');
      $('#map-status').textContent='Abrindo a rua no Street View (vista de quem está lá).';};
    renderMapChips();loadSavedPlaces();
    const q=$('#map-q');if(q)q.addEventListener('keydown',e=>{if(e.key==='Enter'&&q.value.trim())showNearby(q.value.trim());});
    $('#map-add').onclick=()=>{_addMode=!_addMode;$('#map-add').classList.toggle('on',_addMode);$('#map-status').textContent=_addMode?'Modo adicionar: toque no mapa pra criar um ponto':'Você está aqui';};
    $('#map-addr').onclick=addByAddress;
    $('#map-fix').onclick=fixLocation;
    $('#map-mine').onclick=showSavedList;
    $('#map-plan').onclick=()=>{const pl=$('#map-planner');const show=pl.style.display==='none';pl.style.display=show?'flex':'none';if(show)refreshPlanner();};
    $('#plan-go').onclick=()=>{const f=planCoord($('#plan-from').value),t=planCoord($('#plan-to').value);
      if(!f){$('#map-status').textContent='Sua localização não foi definida — toque em "Onde estou".';return;}
      if(!t){$('#map-status').textContent='Escolha o destino.';return;}
      if($('#plan-from').value===$('#plan-to').value){$('#map-status').textContent='Escolha origem e destino diferentes.';return;}
      drawRouteFT(f,t,$('#plan-to').selectedOptions[0].textContent);};
    $('#map-ask').onclick=()=>{switchView('chat');send('E.V., o que tem de útil perto de mim agora?');};
    _map.on('click',ev=>{if(_fixMode){_fixMode=false;setMyLocation(ev.latlng.lat,ev.latlng.lng,0);$('#map-status').textContent='Localização definida no mapa. É daqui que as buscas e rotas vão partir.';return;}
      if(!_addMode)return;const name=prompt('Nome do ponto (ex: Casa, Trabalho):');if(!name)return;
      fetch('/api/places',{method:'POST',headers:H(),body:JSON.stringify({name,lat:ev.latlng.lat,lng:ev.latlng.lng})}).then(r=>r.json()).then(d=>addSavedMarker({id:d.id,name,lat:ev.latlng.lat,lng:ev.latlng.lng}));
      _addMode=false;$('#map-add').classList.remove('on');$('#map-status').textContent='Ponto "'+name+'" salvo';});}
  setTimeout(()=>{if(_map)_map.invalidateSize();},120);
  if(!_loc)locateMe();}
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
async function loadMem(){try{const items=(await (await fetch('/api/facts',{headers:H()})).json()).items||[];
  const cnt=$('#mem-count');if(cnt)cnt.textContent=items.length?('· '+items.length+' memória'+(items.length>1?'s':'')):'';
  const box=$('#memlist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Cérebro vazio. Adicione acima, ou diga à E.V. o que lembrar.'));return;}
  items.forEach(f=>{const row=el('div','tv-row');
    const t=el('div','txt',f.fact);t.title='clique para editar';t.style.cursor='text';t.onclick=()=>startMemEdit(t,f);
    row.appendChild(t);
    const dl=el('button','tv-ic');dl.title='esquecer';dl.appendChild(ficon('trash-2'));dl.onclick=e=>{e.stopPropagation();delU('/api/facts/delete',{id:f.id},'/api/facts',{text:f.fact},loadMem,'Memória');};
    row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function startMemEdit(t,f){const orig=f.fact;const inp=document.createElement('input');inp.className='tv-search';inp.value=orig;inp.style.margin='0';inp.style.flex='1';
  t.replaceWith(inp);inp.focus();inp.select();let done=false;
  const save=async()=>{if(done)return;done=true;const v=inp.value.trim();
    if(v&&v!==orig){await fetch('/api/facts/update',{method:'POST',headers:H(),body:JSON.stringify({id:f.id,text:v})});}
    loadMem();};
  inp.onblur=save;inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();save();}else if(e.key==='Escape'){done=true;loadMem();}};}
$('#memform').onsubmit=async e=>{e.preventDefault();const text=$('#mem-text').value.trim();if(!text)return;
  await fetch('/api/facts',{method:'POST',headers:H(),body:JSON.stringify({text})});$('#mem-text').value='';loadMem();loadPanel();};
$('#mem-clear').onclick=async()=>{if(!(await confirmDialog('Esquecer TODAS as memórias da E.V.? Isso apaga tudo que ela sabe sobre você (não afeta tarefas, gastos etc).')))return;
  await fetch('/api/facts/clear',{method:'POST',headers:H()});loadMem();loadPanel();};
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
function ckBuild(){const nav=[['Conversa',()=>switchView('chat')],['Tarefas',()=>switchView('tasks')],['Gastos',()=>switchView('exp')],['Lembretes',()=>switchView('rem')],['Agenda',()=>switchView('cal')],['Memórias',()=>switchView('mem')],['Links',()=>switchView('lnk')],['Hábitos',()=>switchView('hab')],['Diário',()=>switchView('jou')],['Assinaturas',()=>switchView('sub')],['Orçamentos',()=>switchView('orc')],['Monitores',()=>switchView('mon')],['Base',()=>switchView('kb')],['Cérebro',()=>switchView('brain')],['Pomodoro',()=>openPomo(25)],['Voz ao vivo',()=>$('#vcopen').click()],['Chaves de API',()=>openKeys()]];
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
// --- Cérebro: grafo interativo (força) com tudo que a E.V. sabe, estilo Obsidian ---
const BRAIN_COLORS={core:'#f4f3f1',mem:'#35c8ff',tasks:'#5ee6a3',rem:'#ffb35e',people:'#ff6ec7',links:'#8f7bff',kb:'#ffe066',hab:'#4dd0e1',jou:'#ff8a65',sub:'#c792ea',orc:'#82e0aa',mon:'#ef5350',places:'#64b5f6'};
let brainNodes=[],brainLinks=[],brainLoaded=false,brainRAF=null,brainAlpha=1;
let brainScale=1,brainOffX=0,brainOffY=0,brainDrag=null,brainPan=null,brainMoved=false,brainHoverId=null;
function brainMouse(e){const cv=$('#brain-canvas');const r=cv.getBoundingClientRect();return{mx:e.clientX-r.left,my:e.clientY-r.top};}
function brainToWorld(mx,my){const cv=$('#brain-canvas');const w=cv.width,h=cv.height;
  return{x:(mx*devicePixelRatio-w/2-brainOffX*devicePixelRatio)/(brainScale*devicePixelRatio),
         y:(my*devicePixelRatio-h/2-brainOffY*devicePixelRatio)/(brainScale*devicePixelRatio)};}
function brainNodeAt(mx,my){const {x,y}=brainToWorld(mx,my);let best=null,bd=1e9;
  brainNodes.forEach(node=>{const r=Math.sqrt(node.val)*2.4+5;const d=(node.x-x)**2+(node.y-y)**2;if(d<r*r&&d<bd){bd=d;best=node;}});
  return best;}
function resizeBrainCanvas(){const cv=$('#brain-canvas');if(!cv)return;const r=cv.parentElement.getBoundingClientRect();
  cv.width=Math.max(1,Math.round(r.width*devicePixelRatio));cv.height=Math.max(1,Math.round(r.height*devicePixelRatio));
  cv.style.width=r.width+'px';cv.style.height=r.height+'px';}
window.addEventListener('resize',()=>{if(curView==='brain'){resizeBrainCanvas();brainDraw();}});
async function loadBrain(){
  const cv=$('#brain-canvas');if(!cv)return;
  resizeBrainCanvas();
  if(!brainLoaded){
    try{
      const d=await (await fetch('/api/brain',{headers:H()})).json();
      const idx={};
      brainNodes=(d.nodes||[]).map(n=>{const o=Object.assign({},n,{x:(Math.random()-0.5)*320,y:(Math.random()-0.5)*320,vx:0,vy:0});idx[n.id]=o;return o;});
      brainLinks=(d.links||[]).map(l=>({source:idx[l.source],target:idx[l.target]})).filter(l=>l.source&&l.target);
      brainLoaded=true;
      const cnt=$('#brain-count');if(cnt)cnt.textContent=Math.max(0,brainNodes.length-1)+' pontos · '+brainLinks.length+' conexões';
    }catch(e){return;}
  }
  brainAlpha=1;
  if(!brainRAF)brainRAF=requestAnimationFrame(brainTick);
}
function reloadBrain(){brainLoaded=false;loadBrain();}
function brainNodeMenu(node,mx,my){const m=$('#brain-menu');m.innerHTML='';
  const grp=node.group,hasRef=node.ref!==undefined&&node.ref!==null;
  m.appendChild(el('div','bm-t',node.label));
  const ob=el('button','');ob.appendChild(ficon('external-link'));ob.appendChild(document.createTextNode('Abrir'+(node.view?' ('+(VIEW_LABELS[node.view]||node.view)+')':'')));ob.onclick=()=>{m.classList.remove('on');if(node.view)switchView(node.view);};m.appendChild(ob);
  if(hasRef&&node.editable){const eb=el('button','');eb.appendChild(ficon('pencil'));eb.appendChild(document.createTextNode('Editar'));eb.onclick=async()=>{m.classList.remove('on');
    const cur=node.full||node.label;const v=prompt('Editar:',cur);if(v==null)return;const t=v.trim();if(!t||t===cur)return;
    try{await fetch('/api/brain/edit',{method:'POST',headers:H(),body:JSON.stringify({group:grp,ref:node.ref,text:t})});}catch(e){}reloadBrain();loadPanel();};m.appendChild(eb);}
  if(hasRef){const db=el('button','bm-del');db.appendChild(ficon('trash-2'));db.appendChild(document.createTextNode('Apagar do cérebro'));db.onclick=async()=>{m.classList.remove('on');
    if(!(await confirmDialog('Apagar "'+node.label+'"? Isso remove o item de verdade da E.V.')))return;
    try{await fetch('/api/brain/delete',{method:'POST',headers:H(),body:JSON.stringify({group:grp,ref:node.ref})});}catch(e){}reloadBrain();loadPanel();};m.appendChild(db);}
  const wrap=$('#brain-wrap');m.style.left=Math.max(6,Math.min(mx,wrap.clientWidth-236))+'px';m.style.top=Math.min(my+8,wrap.clientHeight-140)+'px';m.classList.add('on');window.lucide&&lucide.createIcons();}
function brainStep(){
  const n=brainNodes.length;if(!n)return;
  for(let i=0;i<n;i++){const a=brainNodes[i];
    for(let j=i+1;j<n;j++){const b=brainNodes[j];
      let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy;if(d2<1)d2=1;
      const d=Math.sqrt(d2),force=850/d2,fx=dx/d*force,fy=dy/d*force;
      a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;}}
  brainLinks.forEach(l=>{const a=l.source,b=l.target,dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||0.01;
    const target=(a.group==='core'||b.group==='core')?115:((a.val>=12||b.val>=12)?68:34);
    const force=(d-target)*0.02,fx=dx/d*force,fy=dy/d*force;
    a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;});
  brainNodes.forEach(node=>{if(node===brainDrag)return;
    node.vx-=node.x*0.005;node.vy-=node.y*0.005;node.vx*=0.8;node.vy*=0.8;
    node.x+=node.vx*brainAlpha;node.y+=node.vy*brainAlpha;});
  brainAlpha=Math.max(0.015,brainAlpha*0.99);
}
function brainDraw(t){
  t=t||0;
  const cv=$('#brain-canvas');if(!cv)return;const ctx=cv.getContext('2d');
  const reduced=window.matchMedia&&window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  const pulse=reduced?0:0.5+0.5*Math.sin(t*2);
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.save();ctx.translate(cv.width/2+brainOffX*devicePixelRatio,cv.height/2+brainOffY*devicePixelRatio);
  ctx.scale(brainScale*devicePixelRatio,brainScale*devicePixelRatio);
  ctx.lineWidth=1/brainScale;
  brainLinks.forEach(l=>{const hi=brainHoverId&&(l.source.id===brainHoverId||l.target.id===brainHoverId);
    ctx.beginPath();ctx.moveTo(l.source.x,l.source.y);ctx.lineTo(l.target.x,l.target.y);
    if(hi){ctx.save();ctx.strokeStyle='rgba(53,200,255,.85)';ctx.shadowBlur=8;ctx.shadowColor='#35c8ff';
      ctx.setLineDash([5/brainScale,4/brainScale]);ctx.lineDashOffset=reduced?0:-t*36;ctx.lineWidth=1.4/brainScale;
      ctx.stroke();ctx.restore();}
    else{ctx.strokeStyle='rgba(125,147,170,.16)';ctx.stroke();}});
  brainNodes.forEach(node=>{const r=Math.sqrt(node.val)*2.4,hi=node.id===brainHoverId,color=BRAIN_COLORS[node.group]||'#7d93aa';
    if(node.id==='core'){
      ctx.save();ctx.lineWidth=1.4/brainScale;ctx.strokeStyle='rgba(53,200,255,.35)';
      ctx.beginPath();ctx.arc(node.x,node.y,r+9+pulse*5,0,Math.PI*2);ctx.globalAlpha=.5+.25*pulse;ctx.stroke();
      ctx.beginPath();ctx.arc(node.x,node.y,r+20+pulse*9,0,Math.PI*2);ctx.globalAlpha=.22+.14*pulse;ctx.stroke();
      ctx.restore();
    }
    ctx.save();ctx.shadowBlur=(hi?20:10)/1;ctx.shadowColor=color;
    ctx.beginPath();ctx.arc(node.x,node.y,hi?r+2:r,0,Math.PI*2);
    ctx.fillStyle=color;ctx.globalAlpha=hi?1:.88;ctx.fill();ctx.globalAlpha=1;
    if(hi){ctx.shadowBlur=0;ctx.lineWidth=2/brainScale;ctx.strokeStyle='#fff';ctx.stroke();}
    ctx.restore();
    if(node.val>=12||brainScale>1.5){ctx.fillStyle='rgba(214,233,251,.9)';ctx.font=(11/brainScale)+'px Inter, sans-serif';
      ctx.fillText(node.label,node.x+r+4,node.y+3);}});
  ctx.restore();
}
let brainT0=null;
function brainTick(ts){
  if(curView!=='brain'){brainRAF=null;brainT0=null;return;}
  if(brainT0===null)brainT0=ts;
  const t=(ts-brainT0)/1000;
  if(brainAlpha>0.016||brainDrag||brainPan)brainStep();
  brainDraw(t);
  brainRAF=requestAnimationFrame(brainTick);
}
(function initBrainCanvas(){
  const cv=$('#brain-canvas');if(!cv)return;
  cv.addEventListener('pointerdown',e=>{
    const {mx,my}=brainMouse(e);const node=brainNodeAt(mx,my);
    const bm=$('#brain-menu');if(bm)bm.classList.remove('on');
    brainMoved=false;cv.setPointerCapture(e.pointerId);
    if(node&&node.group!=='core'){brainDrag=node;cv.classList.add('dragging');brainAlpha=Math.max(brainAlpha,0.3);if(!brainRAF)brainRAF=requestAnimationFrame(brainTick);}
    else{brainPan={x:e.clientX,y:e.clientY,offX:brainOffX,offY:brainOffY};cv.classList.add('dragging');}
  });
  cv.addEventListener('pointermove',e=>{
    const {mx,my}=brainMouse(e);
    if(brainDrag){brainMoved=true;const w=brainToWorld(mx,my);brainDrag.x=w.x;brainDrag.y=w.y;brainDrag.vx=0;brainDrag.vy=0;return;}
    if(brainPan){const dx=e.clientX-brainPan.x,dy=e.clientY-brainPan.y;if(Math.abs(dx)+Math.abs(dy)>3)brainMoved=true;
      brainOffX=brainPan.offX+dx;brainOffY=brainPan.offY+dy;brainDraw();return;}
    if(curView!=='brain')return;
    const node=brainNodeAt(mx,my);brainHoverId=node?node.id:null;cv.style.cursor=node?'pointer':'grab';
    const tip=$('#brain-tip');
    if(node){tip.style.display='block';tip.style.left=(mx+14)+'px';tip.style.top=(my+10)+'px';tip.textContent=node.label;}
    else if(tip)tip.style.display='none';
    brainDraw();
  });
  function endPointer(){brainDrag=null;brainPan=null;cv.classList.remove('dragging');}
  cv.addEventListener('pointerup',endPointer);
  cv.addEventListener('pointercancel',endPointer);
  cv.addEventListener('click',e=>{
    if(brainMoved){brainMoved=false;return;}
    const {mx,my}=brainMouse(e);const node=brainNodeAt(mx,my);
    if(!node){$('#brain-menu').classList.remove('on');return;}
    const leaf=node.id.indexOf(':')>0&&!node.id.startsWith('g:')&&node.id!=='core'&&!node.id.endsWith(':more');
    if(leaf)brainNodeMenu(node,mx,my);
    else if(node.view)switchView(node.view);
  });
  cv.addEventListener('wheel',e=>{e.preventDefault();
    const {mx,my}=brainMouse(e);const before=brainScale;
    brainScale=Math.min(3,Math.max(0.35,brainScale*(e.deltaY<0?1.1:0.9)));
    brainOffX-=(mx-cv.clientWidth/2-brainOffX)*(brainScale/before-1);
    brainOffY-=(my-cv.clientHeight/2-brainOffY)*(brainScale/before-1);
    brainDraw();
  },{passive:false});
})();
document.getElementById('brain-reset')?.addEventListener('click',()=>{
  brainScale=1;brainOffX=0;brainOffY=0;brainAlpha=Math.max(brainAlpha,0.6);if(!brainRAF)brainRAF=requestAnimationFrame(brainTick);});
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
// render a persisted user message that may carry [img:ID] markers
const IMGMARK=/\[img:(\d+)\]/g;
function youHistory(content){const ids=[];let m;IMGMARK.lastIndex=0;while((m=IMGMARK.exec(content||'')))ids.push(m[1]);
  if(!ids.length){you(content);return;}
  let txt=(content||'').replace(IMGMARK,'').trim();if(txt==='O que há nesta imagem?')txt='';
  const d=el('div','msg you');
  ids.forEach(id=>{const img=document.createElement('img');img.className='msg-img';img.src='/api/chat/image?id='+id+'&k='+encodeURIComponent(token);d.appendChild(img);});
  if(txt){const c=el('div','',txt);c.style.marginTop='6px';d.appendChild(c);}
  log.appendChild(d);log.scrollTop=log.scrollHeight;}
// paste an image straight from the clipboard (no need to save it first)
window.addEventListener('paste',e=>{const items=(e.clipboardData&&e.clipboardData.items)||[];
  for(const it of items){if(it.type&&it.type.indexOf('image/')===0){const f=it.getAsFile();if(f){setPendingImg(f);e.preventDefault();break;}}}});
let _pendingImg=null;
function setPendingImg(f){_pendingImg=f;const p=$('#imgprev');p.innerHTML='';if(!f){p.style.display='none';return;}
  const img=document.createElement('img');img.src=URL.createObjectURL(f);
  const rc=el('button','ip-x');rc.title='Lançar como gasto';rc.appendChild(ficon('wallet'));rc.onclick=()=>receiptFromImage(f);
  const x=el('button','ip-x','×');x.title='remover';x.onclick=()=>setPendingImg(null);
  p.appendChild(img);p.appendChild(el('span','ip-name',f.name+' — envie, ou toque na carteira pra lançar gasto'));p.appendChild(rc);p.appendChild(x);p.style.display='flex';window.lucide&&lucide.createIcons();if(txt)txt.focus();}
async function receiptFromImage(file){if(!file)return;const p=thinking();setState('thinking');
  try{const fd=new FormData();fd.append('image',file);
    const j=await (await fetch('/api/receipt',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    p.remove();
    if(!j.ok){sys(j.msg||'Não consegui identificar um valor nesse comprovante.');return;}
    const ok=await confirmDialog('Lançar R$ '+Number(j.amount).toFixed(2)+' — '+j.description+' (#'+j.category+')?');
    if(ok){setPendingImg(null);switchView('chat');runCmd('gasto '+Number(j.amount).toFixed(2)+' '+j.description+' #'+j.category);}
  }catch(e){p.remove();sys('Falha ao ler o comprovante.');}finally{setState();}}
async function sendImage(file,caption){if(!file)return;youImg(caption,URL.createObjectURL(file));const p=thinking();setState('thinking');
  try{const fd=new FormData();fd.append('image',file,file.name||'imagem.jpg');if(caption)fd.append('text',caption);fd.append('thread',thread);
    const j=await (await fetch('/api/vision',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    p.remove();ev(j.reply||'(sem resposta)');speak(j.reply);}catch(e){p.remove();sys('Falha ao enviar a imagem.');}finally{setState();}}
$('#imgbtn').onclick=()=>$('#imgfile').click();
// live camera — aponta e pergunta ("olha isso")
let _camStream=null,_camFacing='environment';
function stopCam(){if(_camStream){_camStream.getTracks().forEach(t=>t.stop());_camStream=null;}}
async function startCam(){stopCam();
  try{_camStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:_camFacing}});$('#cam-video').srcObject=_camStream;}
  catch(e){$('#cam-hint').textContent='Não consegui abrir a câmera: '+((e&&e.message)||e);}}
$('#cambtn').onclick=async()=>{
  if(!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia)){sys('Câmera indisponível neste navegador.');return;}
  $('#cam').classList.add('on');$('#cam-hint').textContent='Aponte a câmera e toque para capturar — a E.V. analisa o que vê.';await startCam();};
$('#cam-x').onclick=()=>{stopQR();stopCamLive();stopCam();$('#cam').classList.remove('on');};
$('#cam-flip').onclick=()=>{_camFacing=_camFacing==='environment'?'user':'environment';startCam();};
// --- câmera ao vivo: caixas de rosto (MediaPipe) + narração por movimento + "o que é isso" ---
let _camLive=false,_faceDet=null,_faceRAF=0,_motionPrev=null,_lastSee=0,_camBusy=false;
const _mCv=document.createElement('canvas');_mCv.width=48;_mCv.height=36;const _mCtx=_mCv.getContext('2d',{willReadFrequently:true});
function camResult(t){const r=$('#cam-result');if(!t){r.classList.remove('on');return;}r.textContent=t;r.classList.add('on');}
function camFrameBlob(cb){const v=$('#cam-video');if(!v||!v.videoWidth)return cb(null);const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);c.toBlob(cb,'image/jpeg',0.82);}
function camSee(mode){if(_camBusy)return;_camBusy=true;if(mode==='what')camResult('Analisando...');
  camFrameBlob(async b=>{if(!b){_camBusy=false;return;}
    try{const fd=new FormData();fd.append('image',b,'frame.jpg');fd.append('mode',mode);
      const j=await (await fetch('/api/see',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
      const t=(j.text||'').trim();if(t){camResult(t);const od=mode!=='live';if(od||voiceOn)speak(t,od);}
    }catch(e){}finally{_camBusy=false;}});}
let _objDet=null;
const OBJ_PT={person:'pessoa',cup:'copo',bottle:'garrafa','cell phone':'celular',laptop:'notebook',keyboard:'teclado',mouse:'mouse',book:'livro',chair:'cadeira','dining table':'mesa',tv:'TV',remote:'controle',clock:'relógio','potted plant':'planta',backpack:'mochila',handbag:'bolsa',car:'carro',bicycle:'bicicleta',dog:'cachorro',cat:'gato',bird:'pássaro','wine glass':'taça',fork:'garfo',knife:'faca',spoon:'colher',bowl:'tigela',banana:'banana',apple:'maçã',orange:'laranja',pizza:'pizza',cake:'bolo',scissors:'tesoura',umbrella:'guarda-chuva',couch:'sofá',bed:'cama'};
let _detInit=false,_gestDet=null,_gestLast='',_gestN=0,_gestFired=0;
const GEMOJI={Thumb_Up:'👍',Thumb_Down:'👎',Victory:'✌️',Open_Palm:'✋',Closed_Fist:'✊',Pointing_Up:'☝️',ILoveYou:'🤟'};
function handleGesture(name){$('#cam-hint').textContent='Gesto: '+(GEMOJI[name]||name);
  if(name==='Thumb_Up')camSee('what');
  else if(name==='Victory')camSee('translate');
  else if(name==='Open_Palm')$('#cam-x').click();}
async function initDetectors(){if(_detInit)return;_detInit=true;
  try{const V=await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs');
    const fs=await V.FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
    try{_faceDet=await V.FaceDetector.createFromOptions(fs,{baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite'},runningMode:'VIDEO'});}catch(e){_faceDet=null;}
    try{_objDet=await V.ObjectDetector.createFromOptions(fs,{baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite'},runningMode:'VIDEO',scoreThreshold:0.45,maxResults:6});}catch(e){_objDet=null;}
    try{_gestDet=await V.GestureRecognizer.createFromOptions(fs,{baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task'},runningMode:'VIDEO',numHands:1});}catch(e){_gestDet=null;}
  }catch(e){_detInit=false;}}
function ovCtx(){const v=$('#cam-video'),cv=$('#cam-fx');if(!cv||!v)return null;const W=v.clientWidth||1,H=v.clientHeight||1;if(cv.width!==W)cv.width=W;if(cv.height!==H)cv.height=H;const ctx=cv.getContext('2d');ctx.clearRect(0,0,W,H);ctx._sx=W/(v.videoWidth||W);ctx._sy=H/(v.videoHeight||H);return ctx;}
function drawBox(ctx,bb,color,label){const x=bb.originX*ctx._sx,y=bb.originY*ctx._sy,w=bb.width*ctx._sx,h=bb.height*ctx._sy;
  ctx.strokeStyle=color;ctx.lineWidth=2;ctx.shadowColor=color;ctx.shadowBlur=8;ctx.strokeRect(x,y,w,h);ctx.shadowBlur=0;
  if(label){ctx.font='12px Inter, sans-serif';const tw=ctx.measureText(label).width+10;ctx.fillStyle='rgba(4,7,12,.82)';ctx.fillRect(x,Math.max(0,y-18),tw,18);ctx.fillStyle=color;ctx.fillText(label,x+5,Math.max(11,y-5));}}
function faceLoop(){if(!_camLive)return;const v=$('#cam-video');
  if(v&&v.videoWidth){const ctx=ovCtx();let nf=0,no=0;const ts=performance.now();
    if(ctx&&_faceDet){try{(_faceDet.detectForVideo(v,ts).detections||[]).forEach(d=>{if(d.boundingBox){drawBox(ctx,d.boundingBox,'#35c8ff','rosto');nf++;}});}catch(e){}}
    if(ctx&&_objDet){try{(_objDet.detectForVideo(v,ts).detections||[]).forEach(d=>{const c=(d.categories&&d.categories[0])||{};const nm=OBJ_PT[c.categoryName]||c.categoryName||'objeto';if(nm==='pessoa')return;if(d.boundingBox){drawBox(ctx,d.boundingBox,'#7fe3ff',nm);no++;}});}catch(e){}}
    if(ctx&&_gestDet&&!_camBusy){try{const gr=_gestDet.recognizeForVideo(v,ts);const g=(gr.gestures&&gr.gestures[0]&&gr.gestures[0][0])||null;const nm=(g&&g.score>0.55)?g.categoryName:'';
      if(nm&&nm!=='None'){if(nm===_gestLast)_gestN++;else{_gestLast=nm;_gestN=1;}if(_gestN===5&&performance.now()-_gestFired>2800){_gestFired=performance.now();handleGesture(nm);}}
      else{_gestLast='';_gestN=0;}}catch(e){}}
    if(ctx)$('#cam-hint').textContent=(nf?nf+' rosto(s) · ':'')+(no?no+' objeto(s) · ':'')+'👍 o que é · ✌️ traduzir · ✋ fechar';}
  if(v&&v.videoWidth){try{_mCtx.drawImage(v,0,0,48,36);const cur=_mCtx.getImageData(0,0,48,36).data;
    if(_motionPrev){let diff=0,n=0;for(let i=0;i<cur.length;i+=16){diff+=Math.abs(cur[i]-_motionPrev[i]);n++;}diff/=n;
      const now=performance.now();if(diff>18&&now-_lastSee>6500&&!_camBusy){_lastSee=now;camSee('live');}}
    _motionPrev=cur;}catch(e){}}
  _faceRAF=requestAnimationFrame(faceLoop);}
async function startCamLive(){_camLive=true;$('#cam-live').classList.add('on');$('#cam-hint').textContent='Modo ao vivo: preparando visão...';
  await initDetectors();$('#cam-hint').textContent=(_faceDet||_objDet)?'Ao vivo: rostos e objetos marcados + movimento narrado':'Ao vivo: narração por movimento (detecção indisponível neste navegador)';
  _motionPrev=null;_lastSee=performance.now();cancelAnimationFrame(_faceRAF);faceLoop();}
function stopCamLive(){_camLive=false;const lb=$('#cam-live');if(lb)lb.classList.remove('on');cancelAnimationFrame(_faceRAF);const cv=$('#cam-fx');if(cv&&cv.getContext)cv.getContext('2d').clearRect(0,0,cv.width,cv.height);camResult('');}
$('#cam-live').onclick=()=>{_camLive?stopCamLive():startCamLive();};
$('#cam-what').onclick=()=>camSee('what');
$('#cam-tr').onclick=()=>{camResult('Traduzindo...');camSee('translate');};
$('#cam-food').onclick=()=>{camResult('Estimando calorias...');camSee('food');};
$('#cam-scan').onclick=()=>{camResult('Lendo o documento...');camFrameBlob(async b=>{if(!b)return;
  try{const fd=new FormData();fd.append('image',b,'doc.jpg');const j=await (await fetch('/api/scan',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    camResult(j.msg||'Pronto.');speak(j.msg||'',true);loadPanel();}catch(e){camResult('Falha ao escanear o documento.');}});};
// QR / código de barras (client-side, grátis, via BarcodeDetector)
let _qrScan=false,_qrDet=null,_qrRAF=0;
function stopQR(){_qrScan=false;const b=$('#cam-qr');if(b)b.classList.remove('on');cancelAnimationFrame(_qrRAF);}
async function qrLoop(){if(!_qrScan)return;const v=$('#cam-video');
  if(v&&v.videoWidth){try{const codes=await _qrDet.detect(v);if(codes&&codes.length){const val=(codes[0].rawValue||'').trim();stopQR();
    if(/^https?:\/\//i.test(val)){camResult('Link: '+val);window.open(val,'_blank','noopener');}
    else if(val){camResult('Código lido: '+val);speak('Código: '+val,true);}else camResult('Não consegui ler.');return;}}catch(e){}}
  _qrRAF=requestAnimationFrame(qrLoop);}
$('#cam-qr').onclick=()=>{if(_qrScan){stopQR();camResult('');return;}
  if(!('BarcodeDetector' in window)){camResult('Leitura de QR/código precisa do Chrome ou Edge.');return;}
  try{if(!_qrDet)_qrDet=new BarcodeDetector();}catch(e){camResult('Leitura de código indisponível.');return;}
  _qrScan=true;$('#cam-qr').classList.add('on');camResult('Aponte para um QR ou código de barras...');qrLoop();};
$('#cam-shot').onclick=()=>{const v=$('#cam-video');if(!v||!v.videoWidth){$('#cam-hint').textContent='Espere a câmera carregar...';return;}
  const cv=document.createElement('canvas');cv.width=v.videoWidth;cv.height=v.videoHeight;cv.getContext('2d').drawImage(v,0,0);
  cv.toBlob(b=>{if(!b)return;const cap=(txt.value||'').trim();txt.value='';
    stopQR();stopCamLive();stopCam();$('#cam').classList.remove('on');switchView('chat');sendImage(b,cap);},'image/jpeg',0.85);};
// --- Owner face recognition (client-side, greeting only — token stays the gate) ---
// Recognizes ONLY the enrolled owner; anyone else = "não reconhecido". Never IDs
// strangers. Stores a 128-d math descriptor (not photos), encrypted server-side.
let _fapi=null,_fapiBusy=false;
async function loadFaceApi(){if(_fapi)return _fapi;
  const B='https://cdn.jsdelivr.net/npm/@vladmandic/face-api';
  const fa=await import(B+'/dist/face-api.esm.js');
  await fa.nets.tinyFaceDetector.loadFromUri(B+'/model');
  await fa.nets.faceLandmark68Net.loadFromUri(B+'/model');
  await fa.nets.faceRecognitionNet.loadFromUri(B+'/model');
  _fapi=fa;return fa;}
async function faceDescriptor(){const v=$('#cam-video');if(!v||!v.videoWidth)return null;
  const fa=await loadFaceApi();
  const r=await fa.detectSingleFace(v,new fa.TinyFaceDetectorOptions()).withFaceLandmarks().withFaceDescriptor();
  return r?Array.from(r.descriptor):null;}
function faceDist(a,b){let s=0;for(let i=0;i<a.length;i++){const d=a[i]-b[i];s+=d*d;}return Math.sqrt(s);}
async function camFace(){if(_fapiBusy)return;_fapiBusy=true;camResult('Analisando seu rosto…');
  try{const desc=await faceDescriptor();
    if(!desc){camResult('Não achei um rosto nítido — chega mais perto, com luz.');return;}
    const st=await (await fetch('/api/face',{headers:H()})).json();
    if(!st.enrolled){
      if(!confirm('Ainda não reconheço você. Cadastrar SEU rosto agora? (fica só pra te cumprimentar; o token continua sendo a segurança)')){camResult('');return;}
      await fetch('/api/face',{method:'POST',headers:H(),body:JSON.stringify({descriptor:desc})});
      camResult('Rosto cadastrado! Da próxima vez eu te reconheço, Ryan. 👋');speak('Rosto cadastrado. Da próxima vez eu te reconheço.',true);return;}
    const d=faceDist(desc,st.descriptor);
    if(d<0.52){camResult('Olá, Ryan! 👋 Reconheci você.');speak('Olá, Ryan! Reconheci você.',true);}
    else{camResult('Não reconheço quem está na câmera. 🔒');}
  }catch(e){camResult('Reconhecimento facial indisponível neste navegador.');}
  finally{_fapiBusy=false;}}
$('#cam-face').onclick=camFace;
$('#cam-face').oncontextmenu=async e=>{e.preventDefault();
  if(!confirm('Apagar seu rosto cadastrado da E.V.?'))return;
  await fetch('/api/face',{method:'POST',headers:H(),body:JSON.stringify({clear:true})});
  camResult('Rosto apagado. Nenhuma biometria fica guardada.');};
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
        if name in ("plano", "manha", "manhã"):  # agentic day plan
            return await brain.plan_day(owner)
        if name in ("pendencias", "pendências", "cobrar"):  # proactive open loops
            return commands.nudge_text(owner) or "Tudo em dia, Ryan — nada atrasado. 👌"
        if name in ("padroes", "padrões", "aprendi"):  # continuous learning view
            return commands.learned_text(owner)
        if name in ("automacoes", "automações", "automacao", "automação"):
            return commands.automacoes(owner)
        if name == "automacaorm":
            return commands.automacao_rm(owner, rest)
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
            "background_color": "#04070c", "theme_color": "#04070c",
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

    _DEF_ACTIONS = ["plano", "buscar", "noticias", "clima", "relatorio", "semana"]
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

    @app.get("/api/backup")
    async def api_backup(request: Request):
        # On-demand off-VM pull: a browser download can't set headers, so the
        # token comes as ?k=. Returns a fresh, SQLCipher-encrypted copy of the DB.
        tok = request.query_params.get("k", "")
        if not config.web_token or not hmac.compare_digest(tok, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        from fastapi.responses import FileResponse
        from datetime import datetime
        bdir = config.db_path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        dest = bdir / f"ev_memory.{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        await asyncio.to_thread(memory.backup, dest)
        return FileResponse(str(dest), media_type="application/octet-stream",
                            filename=dest.name)

    @app.get("/api/face")
    async def face_get(request: Request):
        # Owner face descriptor (greeting/personalization only). Never other people.
        _check(request.headers.get("authorization"))
        raw = memory.get_setting("face_descriptor") or ""
        try:
            desc = json.loads(raw) if raw else None
        except ValueError:
            desc = None
        return {"enrolled": bool(desc), "descriptor": desc}

    @app.post("/api/face")
    async def face_set(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        if data.get("clear"):
            memory.set_setting("face_descriptor", "")
            return {"ok": True, "enrolled": False}
        desc = data.get("descriptor")
        if (not isinstance(desc, list) or len(desc) != 128
                or not all(isinstance(x, (int, float)) for x in desc)):
            raise HTTPException(status_code=400, detail="invalid descriptor")
        memory.set_setting("face_descriptor", json.dumps([float(x) for x in desc]))
        return {"ok": True, "enrolled": True}

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

    @app.post("/api/facts/clear")
    async def fact_clear(request: Request):
        _check(request.headers.get("authorization"))
        n = memory.clear_facts(owner)
        return {"ok": True, "cleared": n}

    @app.get("/api/charts")
    async def charts(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        qp = request.query_params

        def _pd(s):
            try:
                return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return None
        frm = _pd(qp.get("from", ""))
        to = _pd(qp.get("to", ""))
        if not frm:  # default = current month
            _, since, _ = commands._month_bounds(0)
            frm = datetime.fromisoformat(since)
        if not to:
            to = datetime.now(timezone.utc)
        to_end = (to.replace(hour=0, minute=0, second=0, microsecond=0)
                  + timedelta(days=1)).isoformat()
        exps = [e for e in memory.expenses_since(owner, frm.isoformat())
                if (e.get("created") or "") < to_end]

        bycat: dict = {}
        for e in exps:
            bycat[e["category"]] = bycat.get(e["category"], 0) + e.get("amount", 0)
        cat = sorted(bycat.items(), key=lambda x: -x[1])[:8]

        span = max(1, (to.date() - frm.date()).days)
        by_month = span > 62
        buckets: dict = {}
        d = frm.date()
        while d <= to.date():
            key = d.strftime("%Y-%m") if by_month else d.isoformat()
            buckets.setdefault(key, 0)
            d += timedelta(days=1)
        for e in exps:
            c = (e.get("created") or "")[:10]
            key = c[:7] if by_month else c
            if key in buckets:
                buckets[key] += e.get("amount", 0)
        series = [{"label": (k[5:] if not by_month else k),
                   "value": round(v, 2)} for k, v in buckets.items()]

        fd, td = frm.date().isoformat(), to.date().isoformat()
        habits = []
        for h in memory.list_habits(owner):
            try:
                done = sum(1 for x in memory.habit_days(h["id"]) if fd <= x <= td)
            except Exception:
                done = 0
            habits.append({"label": h["name"], "value": done})
        return {
            "exp_cat": [{"label": k, "value": round(v, 2)} for k, v in cat],
            "exp_day": series,
            "habits": habits[:10],
            "range": {"from": fd, "to": td},
        }

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

    # groups shown in the "brain" graph: (key, hub label, view to jump to on
    # click, items, text-getter). Capped per group below so a heavy user's DB
    # still renders a smooth graph.
    @app.get("/api/brain")
    async def brain_graph(request: Request):
        _check(request.headers.get("authorization"))
        # idfn: the stable identifier used to edit/delete the item (id for most;
        # name/source/category for the string-keyed tables). editable: shows "Editar".
        groups = [
            ("mem", "Memórias", "mem", memory.list_facts(owner), lambda r: r["fact"], lambda r: r["id"], True),
            ("tasks", "Tarefas", "tasks", memory.open_tasks(owner), lambda r: r["text"], lambda r: r["id"], True),
            ("rem", "Lembretes", "rem", memory.open_reminders(owner), lambda r: r["text"], lambda r: r["id"], True),
            ("people", "Pessoas", "chat", memory.list_people(owner), lambda r: r["name"], lambda r: r["id"], True),
            ("links", "Links", "lnk", memory.list_links(owner), lambda r: r["name"], lambda r: r["id"], True),
            ("kb", "Base", "kb", memory.list_sources(owner), lambda r: r["source"], lambda r: r["source"], False),
            ("hab", "Hábitos", "hab", memory.list_habits(owner), lambda r: r["name"], lambda r: r["id"], True),
            ("jou", "Diário", "jou", memory.recent_journal(owner, 40), lambda r: r["text"], lambda r: r["id"], True),
            ("sub", "Assinaturas", "sub", memory.list_recurring(owner), lambda r: r["description"], lambda r: r["id"], True),
            ("orc", "Orçamentos", "orc", memory.list_budgets(owner), lambda r: r["category"], lambda r: r["category"], False),
            ("mon", "Monitores", "mon", memory.list_watches(owner), lambda r: r["url"], lambda r: r["id"], True),
            ("places", "Lugares", "map", memory.list_places(owner), lambda r: r["name"], lambda r: r["id"], True),
        ]
        nodes = [{"id": "core", "label": "E.V.", "group": "core", "val": 22, "view": "chat"}]
        edges = []
        CAP = 40
        for key, label, view, items, textfn, idfn, editable in groups:
            if not items:
                continue
            hub = f"g:{key}"
            nodes.append({"id": hub, "label": label, "group": key, "val": 12, "view": view})
            edges.append({"source": "core", "target": hub})
            for i, item in enumerate(items[:CAP]):
                nid = f"{key}:{item.get('id', i)}"
                txt = (textfn(item) or "").strip().replace("\n", " ")
                nodes.append({
                    "id": nid, "label": (txt[:60] or "—"), "group": key, "val": 4,
                    "view": view, "ref": idfn(item), "full": txt[:400], "editable": editable,
                })
                edges.append({"source": hub, "target": nid})
            extra = len(items) - CAP
            if extra > 0:
                more_id = f"{key}:more"
                nodes.append({"id": more_id, "label": f"+{extra} mais", "group": key,
                              "val": 5, "view": view})
                edges.append({"source": hub, "target": more_id})
        return {"nodes": nodes, "links": edges}

    def _brain_delete(group: str, ref) -> bool:
        """Delete an item of any brain group by its ref (id, or name/source/category)."""
        if group == "rem":
            return memory.cancel_reminder(owner, int(ref)) or True
        if group == "kb":
            return memory.delete_source(owner, str(ref)) > 0
        if group == "orc":
            return memory.delete_budget(owner, str(ref))
        if group == "hab":
            return memory.delete_habit(owner, int(ref))          # cascades habit_logs
        if group == "people":
            return memory.delete_person_by_id(owner, int(ref))
        byid = {"mem": memory.delete_fact, "tasks": memory.delete_task,
                "links": memory.delete_link, "jou": memory.delete_journal,
                "sub": memory.delete_recurring, "mon": memory.delete_watch,
                "places": memory.delete_place}.get(group)
        if byid:
            return byid(owner, int(ref))
        raise HTTPException(status_code=400, detail="unknown group")

    def _brain_edit(group: str, ref, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        editors = {
            "mem": lambda: memory.update_fact(owner, int(ref), text),
            "tasks": lambda: memory.update_task(owner, int(ref), text=text),
            "rem": lambda: memory.update_reminder(owner, int(ref), text=text),
            "links": lambda: memory.update_link(owner, int(ref), name=text),
            "jou": lambda: memory.update_journal(owner, int(ref), text),
            "sub": lambda: memory.update_recurring(owner, int(ref), description=text),
            "mon": lambda: memory.update_watch(owner, int(ref), url=text),
            "hab": lambda: memory.update_habit(owner, int(ref), text),
            "people": lambda: memory.update_person(owner, int(ref), text),
            "places": lambda: memory.update_place(owner, int(ref), text),
        }.get(group)
        if not editors:
            raise HTTPException(status_code=400, detail="group not editable")
        return editors()

    @app.post("/api/brain/delete")
    async def brain_delete(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        ref = d.get("ref")
        if ref is None:
            raise HTTPException(status_code=400, detail="no ref")
        try:
            _brain_delete(d.get("group", ""), ref)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="bad ref")
        return {"ok": True}

    @app.post("/api/brain/edit")
    async def brain_edit(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        ref = d.get("ref")
        if ref is None:
            raise HTTPException(status_code=400, detail="no ref")
        try:
            ok = _brain_edit(d.get("group", ""), ref, d.get("text", ""))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="bad ref")
        return {"ok": bool(ok)}

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
        conv = _conv(thread)
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

    @app.get("/api/chat/image")
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

    @app.post("/api/location")
    async def set_location(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"ok": False}
        from datetime import datetime, timezone
        memory.set_setting("loc_lat", f"{lat:.6f}")
        memory.set_setting("loc_lng", f"{lng:.6f}")
        memory.set_setting("loc_time", datetime.now(timezone.utc).isoformat())
        try:  # best-effort readable address so E.V. can say where you are
            addr = await asyncio.to_thread(tools_mod.reverse_geocode, lat, lng)
            if addr:
                memory.set_setting("loc_addr", addr)
        except Exception:
            pass
        return {"ok": True}

    @app.post("/api/nearby")
    async def nearby(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"items": [], "msg": "sem localização"}
        query = (d.get("query") or "").strip()
        items = await asyncio.to_thread(tools_mod.nearby_places, lat, lng, query)
        return {"items": items}

    @app.get("/api/places")
    async def places_list(request: Request):
        _check(request.headers.get("authorization"))
        return {"items": memory.list_places(owner)}

    @app.post("/api/places")
    async def places_add(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return {"ok": False}
        name = (d.get("name") or "Ponto").strip()
        pid = memory.add_place(owner, name, lat, lng)
        return {"ok": True, "id": pid, "items": memory.list_places(owner)}

    @app.post("/api/places/delete")
    async def places_delete(request: Request):
        _check(request.headers.get("authorization"))
        memory.delete_place(owner, int((await _body(request)).get("id") or 0))
        return {"ok": True, "items": memory.list_places(owner)}

    @app.get("/api/geocode")
    async def geocode_ep(request: Request):
        _check(request.headers.get("authorization"))
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return {"ok": False}
        g = await asyncio.to_thread(tools_mod.geocode, q)
        return {"ok": bool(g), **(g or {})}

    @app.post("/api/route")
    async def route_ep(request: Request):
        _check(request.headers.get("authorization"))
        d = await _body(request)
        try:
            fr, to = d.get("from"), d.get("to")
            fl, fg = float(fr[0]), float(fr[1])
            tl, tg = float(to[0]), float(to[1])
        except (TypeError, ValueError, IndexError):
            return {"ok": False}
        r = await asyncio.to_thread(
            tools_mod.route, fl, fg, tl, tg, (d.get("mode") or "car"))
        return {"ok": bool(r), **(r or {})}

    @app.post("/api/see")
    async def see(request: Request):
        """Ephemeral vision for the live camera / 'what is this' — describes the
        frame without saving it to the conversation."""
        _check(request.headers.get("authorization"))
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

    @app.post("/api/scan")
    async def scan(request: Request):
        """Scan a document: OCR the frame and save the text to the knowledge base."""
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhuma imagem."}
        data = await f.read()
        text = await brain.ocr_image(data, f.content_type or "image/jpeg")
        if not text or text.strip() in ("", "(sem texto)"):
            return {"ok": False, "msg": "Não achei texto legível no documento."}
        from datetime import datetime, timezone
        title = "Documento " + datetime.now(timezone.utc).strftime("%d/%m %H:%M")
        try:
            stored = await asyncio.to_thread(
                knowledge.ingest_text, text, title, config, memory, owner)
            return {"ok": True, "msg": f"Documento salvo na Base: {title} "
                    f"({len(text)} caracteres).", "stored": stored}
        except Exception as exc:
            return {"ok": True, "msg": f"Li o documento ({len(text)} caracteres), "
                    f"mas não consegui salvar na Base ({str(exc)[:50]}).", "text": text[:300]}

    @app.post("/api/receipt")
    async def receipt(request: Request):
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("image")
        if f is None or isinstance(f, str) or not hasattr(f, "read"):
            return {"ok": False, "msg": "Nenhuma imagem enviada."}
        data = await f.read()
        if not data:
            return {"ok": False, "msg": "Imagem vazia."}
        try:
            exp = await brain.extract_receipt(data, f.content_type or "image/jpeg")
        except Exception as exc:
            return {"ok": False, "msg": f"Não consegui ler o comprovante: {exc}"}
        if not exp:
            return {"ok": False,
                    "msg": "Não consegui identificar um valor nesse comprovante."}
        return {"ok": True, **exp}

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
            "<div style='font:15px system-ui;color:#d6e9fb;background:#04070c;"
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
