"""Static frontend for E.V.'s web interface — the single-page app (HTML+CSS+JS),
favicon, service worker, and installable-icon renderer.

Pure, self-contained content: no project imports. Extracted from the original
monolithic ev/interfaces/web.py (frontend/backend split, Phase 6a).
"""

_DEFAULT_FOLDERS = ["geral", "work", "university", "personal"]

# Monochrome "core" mark — the E.V. identity, as an inline SVG favicon.
# Single arc-reactor design, shared 1:1 with the PIL-rendered PNG in _icon_png()
# below so the browser-tab favicon and the installed app icon always match.
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><radialGradient id="ec" cx="50%" cy="50%" r="50%">'
    '<stop offset="0" stop-color="#e8fbff"/><stop offset="1" stop-color="#35c8ff"/>'
    '</radialGradient></defs>'
    '<rect width="64" height="64" rx="15" fill="#060c14"/>'
    # base ring
    '<circle cx="32" cy="32" r="21.5" fill="none" stroke="#35c8ff" stroke-width="1.8"/>'
    # two bright reactor arc segments, opposite each other
    '<circle cx="32" cy="32" r="21.5" fill="none" stroke="#5ee6ff" stroke-width="3.2"'
    ' stroke-linecap="round" stroke-dasharray="30 200" transform="rotate(-90 32 32)"/>'
    '<circle cx="32" cy="32" r="21.5" fill="none" stroke="#5ee6ff" stroke-width="3.2"'
    ' stroke-linecap="round" stroke-dasharray="30 200" transform="rotate(90 32 32)"/>'
    # layered diamond core
    '<path d="M32 21 L43 32 L32 43 L21 32 Z" fill="#f2fdff"/>'
    '<path d="M32 26.5 L37.5 32 L32 37.5 L26.5 32 Z" fill="url(#ec)"/></svg>'
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
    """Render the E.V. 'core' mark as a PNG (for the installable app icon).

    Same arc-reactor + diamond design as the _FAVICON SVG above, redrawn with
    PIL so both surfaces show one consistent mark.
    """
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
    import io

    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22),
                        fill=(6, 12, 20, 255))
    cx = cy = size / 2
    fg = (53, 200, 255)
    fg_soft = (94, 230, 255)
    r = size * 0.336
    bbox = [cx - r, cy - r, cx + r, cy + r]
    d.ellipse(bbox, outline=fg, width=max(2, round(size * 0.028)))
    arc_w = max(3, round(size * 0.05))
    d.arc(bbox, start=-40, end=40, fill=fg_soft, width=arc_w)
    d.arc(bbox, start=140, end=220, fill=fg_soft, width=arc_w)
    r1 = size * 0.17
    d.polygon([(cx, cy - r1), (cx + r1, cy), (cx, cy + r1), (cx - r1, cy)],
              fill=(242, 253, 255, 255))
    r2 = size * 0.085
    d.polygon([(cx, cy - r2), (cx + r2, cy), (cx, cy + r2), (cx - r2, cy)],
              fill=fg + (255,))
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
  --accent:#35c8ff;--accent-rgb:53,200,255;--line-rgb:93,178,255;--accent-dim:#12668f;
  --line:rgba(var(--line-rgb),.13);--line-2:rgba(var(--line-rgb),.28);
  --glow:rgba(var(--accent-rgb),.55);
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
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(rgba(var(--line-rgb),.07) 1px,transparent 1px);background-size:26px 26px;mask:radial-gradient(120% 90% at 50% 0%,#000,transparent 78%);animation:gridpulse 7s ease-in-out infinite}
@keyframes gridpulse{0%,100%{opacity:.7}50%{opacity:1}}
/* --- camada holográfica (HUD) --- */
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:6;background:repeating-linear-gradient(0deg,rgba(var(--accent-rgb),.04) 0 1px,transparent 1px 3px);mix-blend-mode:screen;opacity:.6}
#hud-scan{position:fixed;left:0;right:0;top:0;height:200px;pointer-events:none;z-index:6;background:linear-gradient(180deg,transparent,rgba(var(--accent-rgb),.05) 55%,rgba(var(--accent-rgb),.13) 84%,rgba(var(--accent-rgb),.02));transform:translateY(-260px);animation:hscan 7.5s linear infinite;will-change:transform}
@keyframes hscan{to{transform:translateY(calc(100vh + 260px))}}
#hud-bloom{position:fixed;inset:0;pointer-events:none;z-index:0;background:radial-gradient(70% 44% at 50% -8%,rgba(var(--accent-rgb),.12),transparent 70%)}
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
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.26em;color:#5f9fc9;text-transform:uppercase;margin:4px 2px;text-shadow:0 0 12px rgba(var(--accent-rgb),.22)}
.core{width:132px;height:132px;position:relative;margin:6px auto 2px}
.core .ring{position:absolute;border-radius:50%;border:1px solid var(--line-2)}
.core .ring.a{inset:0}.core .ring.b{inset:18px;border-color:var(--line)}.core .ring.c{inset:40px;border-color:var(--line-2)}
.core .arc{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 66%,var(--accent) 84%,transparent 100%);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));animation:spin 7s linear infinite}
.core .arc.two{inset:18px;animation-duration:11s;animation-direction:reverse;opacity:.5}
.core .dot{position:absolute;inset:0;margin:auto;width:9px;height:9px;border-radius:2px;background:var(--accent);box-shadow:0 0 20px 5px var(--glow);transform:rotate(45deg)}
.core::before{content:"";position:absolute;inset:2px;border-radius:50%;background:repeating-conic-gradient(from 0deg,var(--accent) 0 1deg,transparent 1deg 11.25deg);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 7px),#000 calc(100% - 6px));mask:radial-gradient(farthest-side,transparent calc(100% - 7px),#000 calc(100% - 6px));opacity:.38;pointer-events:none;animation:spin 60s linear infinite}
.core .ring.c{inset:33px;border:0;background:repeating-conic-gradient(from 0deg,var(--accent) 0 2deg,transparent 2deg 30deg);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 6px),#000 calc(100% - 5px));mask:radial-gradient(farthest-side,transparent calc(100% - 6px),#000 calc(100% - 5px));opacity:.55;animation:spin 26s linear infinite reverse}
.core .arc,.bigcore .arc{filter:drop-shadow(0 0 5px var(--glow))}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes ambpulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.7)}}
body.listening .core .arc{animation-duration:1.8s}body.thinking .core .arc{animation-duration:2.6s}
body.speaking .core .arc{animation-duration:1.1s}
body.speaking .core .ring{animation:ringpulse 1.15s ease-in-out infinite}body.speaking .core .ring.b{animation-delay:.12s}body.speaking .core .ring.c{animation-delay:.24s}
body.listening .core .dot{animation:pulsed 1s infinite}@keyframes pulse{50%{transform:scale(1.9);opacity:.55}}
@keyframes pulsed{50%{transform:rotate(45deg) scale(1.9);opacity:.55}}
body.speaking .core .dot{animation:pulsed .6s infinite}
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
#vc::before{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(var(--accent-rgb),.045) 0 1px,transparent 1px 3px)}
#vc::after{content:"";position:absolute;inset:16px;border-radius:16px;pointer-events:none;box-shadow:inset 0 0 0 1px rgba(var(--accent-rgb),.12),inset 0 0 90px -55px var(--glow)}
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
#brain-wrap{position:relative;flex:1;min-height:400px;margin-top:10px;border:1px solid var(--line-2);border-radius:13px;overflow:hidden;box-shadow:0 0 60px -20px var(--glow),inset 0 0 60px -20px var(--glow);background:radial-gradient(120% 100% at 50% 0%,rgba(var(--accent-rgb),.08),transparent 60%),radial-gradient(90% 90% at 50% 100%,rgba(var(--accent-rgb),.05),transparent 70%),#03070a}
#brain-canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab;z-index:0}
#brain-labels{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:2}
#brain-labels .blab{position:absolute;left:0;top:0;font-size:9px;line-height:1;color:#bfe6ff;text-shadow:0 0 5px #04070c,0 0 3px #04070c,0 1px 2px #000;white-space:nowrap;letter-spacing:.02em;will-change:transform,opacity}
#brain-labels .blab.hub{font-size:11px;color:#eaf4fb;font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase}
#brain-canvas.dragging{cursor:grabbing}
#brain-wrap::before{content:"";position:absolute;inset:0;pointer-events:none;z-index:1;background:repeating-linear-gradient(0deg,rgba(var(--accent-rgb),.05) 0 1px,transparent 1px 3px);mix-blend-mode:screen;opacity:.5}
#brain-wrap::after{content:"";position:absolute;left:50%;top:50%;width:150%;padding-top:150%;margin-left:-75%;margin-top:-75%;pointer-events:none;z-index:1;background:conic-gradient(from 0deg,transparent 0 91%,rgba(var(--accent-rgb),.22) 98%,transparent 100%);animation:brainsweep 6s linear infinite;mix-blend-mode:screen;opacity:.8}
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
/* color-theme picker popover (mirrors #brain-menu; anchored to the palette icon via JS) */
#theme-menu,#lang-menu{position:fixed;display:none;flex-direction:column;min-width:190px;background:var(--elev);border:1px solid var(--accent);border-radius:11px;padding:8px;z-index:60;box-shadow:0 0 26px -6px var(--glow),0 12px 30px -14px rgba(0,0,0,.7)}
#theme-menu.on,#lang-menu.on{display:flex}
#theme-menu button,#lang-menu button{display:flex;align-items:center;gap:9px;font-family:var(--body);font-size:13px;color:var(--fg);background:none;border:none;border-radius:8px;padding:9px 9px;cursor:pointer;text-align:left}
#theme-menu button:hover,#lang-menu button:hover{background:var(--surface);color:var(--accent)}
#theme-menu button svg,#lang-menu button svg{width:15px;height:15px}
#theme-menu button .tm-lbl,#lang-menu button .tm-lbl{flex:1}
#theme-menu button .tm-ck,#lang-menu button .tm-ck{display:none;color:var(--accent)}
#theme-menu button.on .tm-ck,#lang-menu button.on .tm-ck{display:block}
#theme-menu button.on,#lang-menu button.on{color:var(--accent)}
#map-wrap{position:relative;height:calc(100vh - 300px);min-height:400px}
#street{position:fixed;inset:0;z-index:120;background:#04070c;display:none;flex-direction:column}
#street.on{display:flex}
#street-view{flex:1;min-height:0;background:#04070c}
#street-x{position:absolute;top:14px;left:14px;z-index:6;background:rgba(4,7,12,.72);border:1px solid var(--accent);color:var(--fg);padding:9px 15px;border-radius:20px;font-family:var(--mono);font-size:12px;letter-spacing:.08em;cursor:pointer;box-shadow:0 0 16px var(--glow)}
#street-hint{position:absolute;bottom:18px;left:50%;transform:translateX(-50%);background:rgba(4,7,12,.74);border:1px solid var(--line-2);color:var(--fg);padding:8px 15px;border-radius:12px;font-size:12px;z-index:6}
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
.bigcore .bdot{position:absolute;inset:0;margin:auto;width:15px;height:15px;border-radius:3px;background:var(--accent);box-shadow:0 0 40px 12px var(--glow);transform:rotate(45deg)}
.bigcore::before{content:"";position:absolute;inset:4px;border-radius:50%;background:repeating-conic-gradient(from 0deg,var(--accent) 0 .9deg,transparent .9deg 9deg);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 11px),#000 calc(100% - 10px));mask:radial-gradient(farthest-side,transparent calc(100% - 11px),#000 calc(100% - 10px));opacity:.34;pointer-events:none;animation:spin 80s linear infinite}
.bigcore .r3{inset:48px;border:0;background:repeating-conic-gradient(from 0deg,var(--accent) 0 1.8deg,transparent 1.8deg 30deg);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 9px),#000 calc(100% - 8px));mask:radial-gradient(farthest-side,transparent calc(100% - 9px),#000 calc(100% - 8px));opacity:.5;animation:spin 30s linear infinite reverse}
body.listening .bigcore .arc{animation-duration:1.6s}body.speaking .bigcore .arc{animation-duration:1s}
body.listening .bigcore .bdot{animation:pulsed .9s infinite}body.speaking .bigcore .bdot{animation:pulsed .55s infinite}
body.speaking .bigcore .ring{animation:ringpulse 1.3s ease-in-out infinite}
body.speaking .bigcore .r2{animation-delay:.15s}body.speaking .bigcore .r3{animation-delay:.3s}
@keyframes ringpulse{0%,100%{transform:scale(1);border-color:var(--line-2)}50%{transform:scale(1.05);border-color:var(--accent)}}
#vc-txt{font-family:var(--disp);font-size:22px;text-align:center;max-width:640px;padding:0 24px;line-height:1.4;min-height:60px}
#vc-txt .msg{font-family:var(--body);font-size:15px;text-align:left;max-width:min(560px,92vw);margin:0 auto;max-height:52vh;overflow:auto}
#vc-sub{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:#6fb0da;text-shadow:0 0 12px rgba(var(--accent-rgb),.3)}
#vc-actions{display:flex;gap:12px}
.vcbtn{width:82px;height:82px;border-radius:50%;border:1px solid var(--accent);background:radial-gradient(circle at 50% 35%,rgba(var(--accent-rgb),.16),var(--elev) 70%);color:var(--accent);font-size:27px;cursor:pointer;transition:.15s;box-shadow:0 0 26px -6px var(--glow),inset 0 0 20px -12px var(--glow);display:inline-flex;align-items:center;justify-content:center}
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
#pomo::before{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(var(--accent-rgb),.045) 0 1px,transparent 1px 3px)}
#pomo::after{content:"";position:absolute;inset:16px;border-radius:16px;pointer-events:none;box-shadow:inset 0 0 0 1px rgba(var(--accent-rgb),.12),inset 0 0 90px -55px var(--glow)}
#pomo>*{position:relative;z-index:1}
#pomo .bigcore{width:210px;height:210px}
#pomo.run .bigcore .arc{animation-duration:2.4s}
#pomo-timebox{display:flex;flex-direction:column;align-items:center;gap:6px}
#pomo-time{font-family:var(--mono);font-weight:600;font-size:60px;letter-spacing:.02em;line-height:1;color:#eaf4fb;text-shadow:0 0 24px var(--glow)}
#pomo-label{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:#6fb0da;text-shadow:0 0 12px rgba(var(--accent-rgb),.3)}
#pomo-ctl{display:flex;gap:10px;align-items:center}
#pomo-ctl button{font-family:var(--mono);font-size:13px;color:var(--fg);background:var(--elev);border:1px solid var(--line);border-radius:10px;padding:11px 15px;cursor:pointer;transition:.15s}
#pomo-ctl button:hover{border-color:var(--accent);color:var(--accent)}
#pomo-toggle{width:64px!important;height:64px;border-radius:50%!important;background:radial-gradient(circle at 50% 35%,rgba(var(--accent-rgb),.18),var(--elev) 70%)!important;color:var(--accent)!important;border:1px solid var(--accent)!important;display:grid;place-items:center;box-shadow:0 0 30px -6px var(--glow),inset 0 0 20px -12px var(--glow)}
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
#login::before,#welcome::before{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(var(--accent-rgb),.045) 0 1px,transparent 1px 3px)}
#login::after,#welcome::after{content:"";position:absolute;inset:16px;border-radius:16px;pointer-events:none;box-shadow:inset 0 0 0 1px rgba(var(--accent-rgb),.12),inset 0 0 90px -55px var(--glow)}
#login>*,#welcome>*{position:relative;z-index:1}
#login-token{background:var(--surface);border:1px solid var(--line-2);border-radius:12px;padding:13px 18px;color:var(--fg);font:inherit;font-size:15px;width:min(320px,80vw);text-align:center;outline:none}
#login-token:focus{border-color:var(--fg)}
#login-btn{min-width:170px}#login-err{font-family:var(--mono);font-size:12px;color:var(--muted);min-height:16px}
.login-or{display:flex;align-items:center;gap:10px;width:100%;max-width:230px;color:var(--muted);font-size:12px;font-family:var(--mono)}
.login-or span{flex:1;height:1px;background:var(--line)}
.login-oauth{min-width:230px;text-align:center;text-decoration:none;display:inline-flex;justify-content:center;gap:8px}
#welcome-txt{font-family:var(--disp);font-size:27px;text-align:center;max-width:620px;padding:0 24px;line-height:1.4;color:#eaf4fb;text-shadow:0 0 22px rgba(var(--accent-rgb),.4)}
/* elegant power-up entrance: the core boots, a pulse rings out, greeting materializes */
#welcome.on .bigcore{animation:coreboot 1s cubic-bezier(.2,.8,.2,1)}
#welcome.on .bigcore::after{content:"";position:absolute;inset:0;border-radius:50%;border:1px solid var(--accent);box-shadow:0 0 18px var(--glow);animation:pulseout 1.5s ease-out .25s both;pointer-events:none}
#welcome.on #welcome-txt{animation:wtxtin 1s .55s both}
@keyframes coreboot{0%{transform:scale(.55);opacity:0;filter:blur(7px)}55%{opacity:1}100%{transform:scale(1);opacity:1;filter:none}}
@keyframes pulseout{0%{transform:scale(.55);opacity:.75}100%{transform:scale(2.3);opacity:0}}
@keyframes wtxtin{0%{opacity:0;transform:translateY(16px);letter-spacing:.34em;filter:blur(5px)}100%{opacity:1;transform:none;letter-spacing:normal;filter:none}}
/* standby / ambient HUD (idle) */
#standby{position:fixed;inset:0;z-index:46;background:radial-gradient(90% 70% at 50% 32%,#0a1826,#04070c 82%);display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;overflow:hidden;cursor:pointer;animation:sbfade .8s}
#standby.on{display:flex}
@keyframes sbfade{from{opacity:0}to{opacity:1}}
#standby .sb-top{position:absolute;top:26px;font-family:var(--mono);letter-spacing:.24em;color:var(--accent);font-size:12px}
#standby .sb-top b{color:#5ee6a3}
#standby .bigcore{transform:scale(.85);margin-bottom:2px}
#sb-clock{font-family:var(--disp);font-size:min(14vw,120px);line-height:1;color:#eaf4fb;text-shadow:0 0 36px rgba(var(--accent-rgb),.42);letter-spacing:.02em}
#sb-date{font-family:var(--mono);letter-spacing:.2em;color:var(--muted);text-transform:uppercase;font-size:13px}
#sb-status{font-family:var(--body);color:var(--fg);font-size:16px;text-align:center;max-width:82vw;text-shadow:0 0 16px rgba(var(--accent-rgb),.3)}
#standby .sb-load{width:min(320px,60vw);height:4px;background:var(--surface);border-radius:3px;overflow:hidden;margin-top:6px}
#standby .sb-load i{display:block;height:100%;width:28%;background:linear-gradient(90deg,transparent,var(--accent),transparent);box-shadow:0 0 8px var(--glow);animation:coreload 2.4s linear infinite}
#standby .sb-hint{position:absolute;bottom:30px;font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--subtle);animation:pulse2 2.6s infinite}
@media(prefers-reduced-motion:reduce){#standby{animation:none}#standby .sb-load i,#standby .sb-hint{animation:none}}
@media(prefers-reduced-motion:reduce){#welcome.on .bigcore,#welcome.on .bigcore::after,#welcome.on #welcome-txt{animation:none}}
#pomo-mini{position:fixed;top:20px;right:20px;z-index:26;width:186px;background:var(--panel);border:1px solid var(--line-2);border-radius:14px;box-shadow:0 20px 60px -24px #000;display:none;flex-direction:column;overflow:hidden}
.pm-head{display:flex;align-items:center;gap:6px;padding:7px 10px;border-bottom:1px solid var(--line);cursor:move;user-select:none}
.pm-grip{color:var(--subtle);font-size:12px;letter-spacing:-3px}
.pm-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:13px;padding:2px 6px}.pm-btn:hover{color:var(--fg)}
.pm-body{padding:16px 14px;display:flex;justify-content:center;cursor:pointer}
#pomo-mini #pomo-time{font-size:36px}#pomo-mini #pomo-label{font-size:9px}
.sysbox{margin-top:auto;position:relative;display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--line);padding:12px 8px 6px}
.kv{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px}
.kv span{color:var(--subtle)}.kv b{font-weight:500}
.sysbox .hud-c{position:absolute;width:7px;height:7px;border:1px solid var(--accent);opacity:.55;pointer-events:none}
.sysbox .hud-c.tl{top:6px;left:-1px;border-right:0;border-bottom:0}
.sysbox .hud-c.tr{top:6px;right:-1px;border-left:0;border-bottom:0}
.sysbox .hud-c.bl{bottom:-1px;left:-1px;border-right:0;border-top:0}
.sysbox .hud-c.br{bottom:-1px;right:-1px;border-left:0;border-top:0}
.sysbox .load{height:4px;background:var(--surface);border-radius:3px;overflow:hidden;margin:1px 0 3px}
.sysbox .load i{display:block;height:100%;width:26%;background:linear-gradient(90deg,transparent,var(--accent),transparent);box-shadow:0 0 8px var(--glow);animation:coreload 2.2s linear infinite}
@keyframes coreload{from{transform:translateX(-130%)}to{transform:translateX(460%)}}
#s-status.on-dot::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:#5ee6a3;box-shadow:0 0 7px #5ee6a3;margin-right:5px;vertical-align:middle;animation:pulse2 1.6s infinite}
#s-status{color:#5ee6a3}#s-status:not(.on-dot){color:#ffb35e}
@keyframes pulse2{0%,100%{opacity:1}50%{opacity:.3}}
@media(prefers-reduced-motion:reduce){.sysbox .load i,#s-status.on-dot::before{animation:none}}
.topbar{display:flex;align-items:center;gap:10px;padding:15px 22px;border-bottom:1px solid var(--line)}
.topbar .eyebrow{flex:1;margin:0}
.mm-badge{display:none;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;letter-spacing:.12em;color:var(--accent);border:1px solid var(--accent);border-radius:999px;padding:5px 11px;cursor:pointer;flex:none;animation:mmpulse 1.8s ease-in-out infinite}
.mm-badge svg{width:12px;height:12px}
body.serious .mm-badge{display:flex}
@keyframes mmpulse{0%,100%{opacity:1}50%{opacity:.5}}
@media(prefers-reduced-motion:reduce){.mm-badge{animation:none}}
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
.tabs{display:flex;gap:3px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:3px 3px 7px;overflow-x:auto;scrollbar-width:thin;scrollbar-color:rgba(var(--accent-rgb),.55) transparent;min-width:0;flex:0 1 auto}
.mnav{display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;color:var(--fg);font:inherit;font-size:14px;padding:10px 12px;font-family:var(--mono);cursor:pointer;align-items:center;justify-content:space-between;gap:8px}
.mnav i{width:15px;height:15px;opacity:.6;flex:none}
.msheet-label{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);opacity:.6;margin:14px 0 4px;padding:0 2px}
.msheet-label:first-child{margin-top:2px}
.msheet-row{display:flex;align-items:center;gap:11px;width:100%;text-align:left;background:transparent;border:none;color:var(--fg);font:inherit;font-size:14px;padding:10px 8px;border-radius:9px;cursor:pointer}
.msheet-row:hover,.msheet-row.on{background:var(--surface)}
.msheet-row.on{color:var(--accent)}
.msheet-row i{width:17px;height:17px;flex:none;opacity:.8}
/* visible horizontal scrollbar — all sections stay reachable by scrolling
   the strip instead of having to hide/remove tabs for space. */
.tabs::-webkit-scrollbar{height:6px}
.tabs::-webkit-scrollbar-track{background:transparent}
.tabs::-webkit-scrollbar-thumb{background:rgba(var(--accent-rgb),.55);border-radius:4px}
.tabs::-webkit-scrollbar-thumb:hover{background:var(--accent)}
.tab{white-space:nowrap;flex:none}
.topbar{gap:8px}
@media(max-width:1180px){.topbar #scope{display:none}}
/* Desktop/tablet keep the scrollable tab strip. Only on phones (<=760px) swap
   it for the compact picker and shrink the labelled buttons to icons. */
/* base: attach "+" and bottom-nav are phone-only (media rules below turn them on) */
#attach{display:none}#bnav{display:none}
/* mini-player global do Spotify — aparece em qualquer tela quando algo toca */
#np-mini{position:fixed;right:18px;bottom:18px;z-index:44;display:none;flex-direction:column;gap:9px;
  cursor:grab;touch-action:none;user-select:none;-webkit-user-select:none;
  width:320px;max-width:calc(100vw - 24px);padding:9px 12px 11px 9px;border:1px solid var(--line-2);border-radius:14px;
  background:linear-gradient(160deg,rgba(18,34,52,.92),rgba(9,17,28,.94));backdrop-filter:blur(9px);
  box-shadow:0 16px 40px -22px #000,0 0 30px -20px var(--glow)}
#np-mini.on{display:flex;animation:sbfade .35s}
#qc-fab{position:fixed;left:18px;bottom:18px;z-index:44;width:50px;height:50px;border-radius:50%;
  border:1px solid var(--line-2);background:linear-gradient(150deg,rgba(24,44,68,.9),rgba(10,20,32,.92));
  color:var(--accent);cursor:pointer;display:flex;align-items:center;justify-content:center;
  box-shadow:0 8px 26px -8px var(--glow);transition:transform .15s}
#qc-fab:hover{transform:scale(1.06)}
#qc-fab svg{width:22px;height:22px}
body.v-chat #qc-fab{display:none}
.npm-top{display:flex;align-items:center;gap:11px}
#npm-bar{height:6px;border-radius:4px;background:var(--elev);cursor:pointer;position:relative;overflow:hidden;flex:none}
#npm-bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),#5ee6a3);border-radius:4px;pointer-events:none}
/* --- Terminal de ação da E.V. (janela flutuante, movível/redimensionável, SÓ DESKTOP) --- */
.eterm{position:fixed;z-index:45;width:520px;height:360px;min-width:320px;min-height:220px;max-width:96vw;max-height:88vh;
  display:flex;flex-direction:column;overflow:hidden;resize:both;font-family:var(--mono);
  background:linear-gradient(180deg,rgba(10,16,24,.97),rgba(6,10,16,.98));
  border:1px solid var(--line-2);border-radius:12px;box-shadow:0 30px 80px -30px #000,0 0 40px -26px var(--glow)}
.eterm .et-head{display:flex;align-items:center;gap:7px;padding:8px 10px;border-bottom:1px solid var(--line);cursor:grab;background:rgba(var(--accent-rgb),.06);flex:none}
.eterm .et-head svg{width:14px;height:14px;color:var(--accent)}
.eterm .et-title{font-size:11px;letter-spacing:.12em;color:var(--accent);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.eterm .et-head button{width:26px;height:26px;border-radius:7px;border:1px solid var(--line);background:var(--surface);color:var(--muted);cursor:pointer;display:grid;place-items:center;flex:none}
.eterm .et-head button:hover{color:var(--accent);border-color:var(--accent)}.eterm .et-head button svg{width:12px;height:12px;color:inherit}
.eterm .et-body{flex:1;min-height:0;overflow:auto;padding:12px 13px;font-size:12.5px;line-height:1.55;color:#cfe3f2;white-space:pre-wrap;word-break:break-word}
.eterm .et-line{padding:1px 0}
.eterm .et-user{color:#eaf4fb}.eterm .et-think{color:var(--muted)}
.eterm .et-act{color:var(--accent)}.eterm .et-act b{color:#eaf4fb;font-weight:600}
.eterm .et-res{color:#dfeaf5;margin-top:5px}.eterm .et-err{color:#ff6b6b}
.eterm .et-form{display:flex;gap:7px;padding:9px 10px;border-top:1px solid var(--line);flex:none}
.eterm .et-form input{flex:1;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;color:#eaf4fb;padding:8px 10px;font-family:var(--mono);font-size:12.5px}
.eterm .et-form input:focus{outline:none;border-color:var(--accent)}
.eterm .et-form button{background:var(--accent);border:0;border-radius:8px;color:#04121e;padding:0 13px;cursor:pointer;font-weight:700}
@media(max-width:760px){.eterm{display:none !important}}
#npm-art{width:44px;height:44px;border-radius:9px;object-fit:cover;flex:none;background:var(--elev)}
.npm-i{min-width:0;flex:1;cursor:pointer}
.npm-t{font-size:13px;color:#eaf4fb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
.npm-a{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
.npm-c{display:flex;gap:4px;flex:none}
.npm-c button{width:30px;height:30px;border-radius:50%;border:1px solid var(--line);background:var(--surface);color:var(--accent);cursor:pointer;display:grid;place-items:center}
.npm-c button:hover{border-color:var(--accent)}.npm-c button svg{width:14px;height:14px}
/* --- MODO FOCO (alerta vermelho) — recolore tudo que usa --accent/--glow --- */
/* MODO FOCO: um filtro de matiz recolore TUDO (azul->vermelho), inclusive os
   navy hardcoded e as superfícies em canvas. Imagens/vídeo e o efeito de alerta
   são contra-rotacionados para não distorcer. */
body.serious{filter:hue-rotate(163deg) saturate(1.12);transition:filter .5s}
body.serious img,body.serious video,body.serious #serfx{filter:hue-rotate(-163deg) saturate(.89)}
/* embed do Spotify (iframe cross-origin) não é alcançado pelo filtro do body;
   aplico um filtro direto pra levar o verde do player -> vermelho */
body.serious iframe[src*="spotify"]{filter:hue-rotate(-140deg) saturate(1.15)}
/* verdes de status/sucesso -> vermelho (usam o accent, que o filtro leva a
   vermelho); evita o magenta E o verde destoante no modo foco */
body.serious #s-status,body.serious .ov-tel .t.on b,body.serious #standby .sb-top b{color:var(--accent)}
body.serious #s-status::before,body.serious .ov-tel .t.on::before{background:var(--accent);box-shadow:0 0 7px var(--glow)}
body.serious .spark .b.today{background:linear-gradient(180deg,var(--accent),rgba(var(--accent-rgb),.28))}
body.serious .ov-hab .c.done{background:rgba(var(--accent-rgb),.14);border-color:var(--accent);color:#f4d7d9}
body.serious .ov-card .obar i,body.serious .ov-sp-bar i,body.serious .goal .gbar i{background:var(--accent)}
#serfx{position:fixed;inset:0;pointer-events:none;z-index:38;opacity:0;transition:opacity .5s;border:1px solid transparent}
body.serious #serfx{opacity:1;box-shadow:inset 0 0 150px -50px rgba(255,45,55,.6);border-color:rgba(255,60,70,.12)}
#serfx.sweep{animation:seriousSweep 1.15s ease-out}
@keyframes seriousSweep{0%{background:radial-gradient(circle at 50% 46%,rgba(255,55,66,.75),transparent 6%)}
  45%{background:radial-gradient(circle at 50% 46%,rgba(255,55,66,.45),rgba(255,40,50,.18) 55%,transparent 100%)}
  100%{background:radial-gradient(circle,transparent,transparent)}}
/* --- BRAND NEW DAY (tema cinematográfico arc-reactor azul elétrico/royal) —
   override das custom props (NÃO é hue-rotate); terceiro estado opt-in via body.bnd.
   Ativa/desativa client-side; persiste em localStorage.ev_theme. --- */
body.bnd{
  /* mesmo fundo escuro do tema tradicional (:root) — só recolore os DESTAQUES
     (accent/bordas/brilho) para o ciano-aqua Brand New Day */
  --accent:#85dbe1;--accent-rgb:133,219,225;--line-rgb:133,219,225;--accent-dim:#1f5e78;
  --glow:rgba(var(--accent-rgb),.6);
}
/* retinta os cyans hardcoded que não seguem as variáveis (só sob body.bnd) — tons ice-blue */
body.bnd *{scrollbar-color:#2a5f64 transparent}
body.bnd ::-webkit-scrollbar-thumb{background:#2a5f64}
body.bnd ::-webkit-scrollbar-thumb:hover{background:#3f9199}
body.bnd .eyebrow{color:#a8e6e9}
body.bnd .chart-t,body.bnd #vc-sub,body.bnd #pomo-label{color:#b8ecef}
@media(max-width:760px){
  .tabs{display:none}
  .tabs-nav{display:none}
  .mnav{display:flex;flex:1 1 auto;min-width:60px}
  /* declutter the phone header so the folder/panel toggles never get clipped
     (keep Terminal available on mobile; only drop search + clean-mode) */
  #gsearch,#tgl-zen,#amb,#sfx{display:none}
  /* Modo Foco vira icon-only no celular pra não dominar a barra */
  .mm-badge .mm-lbl{display:none}
  .mm-badge{padding:6px 8px;gap:0}
  .tbtn.ic-txt span{display:none}
  .tbtn.ic-txt{padding:9px 10px}
  .topbar{gap:6px;padding:10px 10px}
  #tgl-left,#tgl-right{display:none}   /* barras laterais viram o Menu (botão "Mais" da barra de baixo) */
  #vcopen,#voz{flex:none}
  #mnav{margin-left:0}
  /* --- composer declutter: hide media buttons behind the "+" (attach) --- */
  #attach{display:grid}
  #imgbtn,#cambtn{display:none}
  body.attach-open #imgbtn,body.attach-open #cambtn{display:grid}
  form{padding-bottom:calc(14px + env(safe-area-inset-bottom))}
  /* --- bottom tab bar (thumb-reachable nav) --- */
  #bnav{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:40;
    background:linear-gradient(180deg,rgba(9,16,26,.82),rgba(6,11,18,.97));
    -webkit-backdrop-filter:blur(9px);backdrop-filter:blur(9px);
    border-top:1px solid var(--line);padding:6px 4px calc(6px + env(safe-area-inset-bottom))}
  #bnav button{flex:1;background:none;border:0;color:var(--muted);cursor:pointer;
    display:flex;flex-direction:column;align-items:center;gap:3px;
    font-family:var(--mono);font-size:9px;letter-spacing:.04em;padding:5px 2px}
  #bnav button svg{width:21px;height:21px}
  #bnav button.on{color:var(--accent)}
  #bnav button.on svg{filter:drop-shadow(0 0 6px var(--glow))}
  body.v-chat #bnav{display:none}   /* na conversa, o composer já ocupa a base */
  #np-mini{right:10px;left:auto;max-width:calc(100vw - 20px);bottom:calc(72px + env(safe-area-inset-bottom))}
  body.v-chat #np-mini{bottom:calc(16px + env(safe-area-inset-bottom))}
  #qc-fab{left:14px;bottom:calc(72px + env(safe-area-inset-bottom))}
  /* espaço p/ o conteúdo não ficar atrás da barra */
  #taskview,#kbview,#expview,#remview,#memview,#calview,#lnkview,#habview,#jouview,#subview,#orcview,#monview,#actview,#pageview,#musicview,#climaview,#metasview,#saudeview,#cofreview,#painelview,#inicioview,#locview{padding-bottom:80px}
}
.lnk{color:var(--fg);text-decoration:underline;text-underline-offset:2px}.lnk:hover{opacity:.75}
.tab{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--muted);border:none;background:transparent;border-radius:8px;padding:7px 13px;cursor:pointer;white-space:nowrap}
.tab-edit{opacity:.5;font-size:14px;padding:6px 11px}.tab-edit:hover{opacity:1;color:var(--fg)}
.tab.on{background:var(--fg);color:var(--ink)}
.tab-group-label{flex:none;align-self:center;font-family:var(--mono);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);opacity:.45;padding:0 6px 0 9px;white-space:nowrap;pointer-events:none;border-left:1px solid var(--line);margin-left:2px}
.tab-group-label:first-child{border-left:none;margin-left:0;padding-left:2px}
/* click-to-scroll arrows for the tab strip — a scrollbar affordance that
   doesn't depend on the browser/OS's own (often near-invisible) scrollbar
   rendering. Shown/hidden and enabled/disabled from JS based on scroll pos. */
.tabs-nav{flex:none;display:none;transition:opacity .15s}
.tabs-nav.show{display:flex}
.tabs-nav:disabled{opacity:.25;cursor:default}
#chatview{flex:1;display:flex;flex-direction:column;min-height:0}
#taskview,#kbview,#expview,#remview,#memview,#calview,#lnkview,#habview,#jouview,#subview,#orcview,#monview,#actview,#pageview,#musicview,#climaview,#metasview,#saudeview,#cofreview,#painelview,#inicioview,#locview{flex:1;min-height:0;overflow:auto;padding:24px;display:none}
.ov-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;max-width:1500px;grid-auto-rows:minmax(58px,auto);grid-auto-flow:row dense}
.sp3{grid-column:span 3}.sp4{grid-column:span 4}.sp5{grid-column:span 5}.sp6{grid-column:span 6}.sp7{grid-column:span 7}.sp8{grid-column:span 8}.sp12{grid-column:span 12}.rw2{grid-row:span 2}
@media(max-width:1100px){.sp3,.sp4,.sp5,.sp7,.sp8{grid-column:span 6}}
@media(max-width:760px){
  #ov-grid{grid-template-columns:1fr !important}
  #ov-grid>*{grid-column:1 / -1 !important;grid-row:auto !important}
  .ov-hero{flex-direction:column;align-items:flex-start;gap:12px}.ov-ask{max-width:none;width:100%}}
.ov-card{position:relative;border:1px solid var(--line);border-radius:14px;background:linear-gradient(160deg,rgba(18,34,52,.42),rgba(9,17,28,.4));padding:15px 17px;transition:border-color .15s,box-shadow .15s;overflow:hidden}
.ov-card::before,.ov-card::after{content:"";position:absolute;width:11px;height:11px;border:1px solid var(--accent);opacity:.4;pointer-events:none}
.ov-card::before{top:7px;left:7px;border-right:0;border-bottom:0}.ov-card::after{bottom:7px;right:7px;border-left:0;border-top:0}
.ov-card:hover{border-color:var(--accent);box-shadow:0 10px 30px -20px var(--glow),inset 0 0 44px -34px var(--glow)}
.ov-card .h{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle);margin-bottom:10px;display:flex;align-items:center;gap:7px}
.ov-card .h svg{width:14px;height:14px;color:var(--accent)}
.ov-card .h .go{margin-left:auto;cursor:pointer;color:var(--muted);display:flex;opacity:.55}.ov-card .h .go:hover{color:var(--accent);opacity:1}
.ov-card .h .grip{margin-left:auto;cursor:grab;color:var(--muted);display:flex;opacity:.4;touch-action:none}.ov-card .h .grip:hover{color:var(--accent);opacity:1}
.ov-card.dragging{opacity:.45;box-shadow:0 0 0 2px var(--accent) inset;cursor:grabbing}
@media(max-width:760px){.ov-card .h .grip{display:none}}
.ov-card .big{font-family:var(--disp);font-size:29px;color:#eaf4fb;line-height:1.05}.ov-card .big small{font-size:13px;color:var(--muted)}
.ov-li{font-size:13px;color:var(--muted);padding:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-card .obar{height:6px;background:var(--elev);border-radius:4px;overflow:hidden;margin:5px 0}.ov-card .obar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#5ee6a3)}
.ov-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}.ov-chip{font-family:var(--mono);font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:8px;padding:3px 8px}
.ov-hero{grid-column:span 12;display:flex;align-items:center;gap:18px;flex-wrap:wrap;border:1px solid var(--line);border-radius:16px;background:radial-gradient(120% 200% at 0% 0%,rgba(18,40,60,.55),rgba(9,16,26,.4));padding:16px 20px;position:relative;overflow:hidden}
.ov-hero .core{width:52px;height:52px;flex:none;border-radius:50%;background:radial-gradient(circle,var(--accent),transparent 62%);animation:corepulse 3.5s ease-in-out infinite}
.ov-hero .hz{flex:1;min-width:210px}.ov-hero .hz .g{font-family:var(--disp);font-size:20px;color:#eaf4fb}.ov-hero .hz .s{font-size:13px;color:var(--muted);margin-top:3px}
.ov-hero .hz .ov-today{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.ov-hero .hz .ov-today span{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--accent);background:rgba(var(--accent-rgb),.08);border:1px solid var(--line);border-radius:8px;padding:4px 9px}
.ov-hero .hz .ov-today span svg{width:12px;height:12px}
.ov-hero .customize{position:absolute;top:14px;right:16px;cursor:pointer;color:var(--muted);opacity:.6;display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase}
.ov-hero .customize:hover{opacity:1;color:var(--accent)}
.ov-hero .customize svg{width:13px;height:13px}
.ov-insight{display:flex;align-items:center;gap:8px;margin-top:8px;padding:7px 12px;border-radius:9px;border:1px solid rgba(255,184,92,.35);background:rgba(255,184,92,.08);color:#ffcf8a;font-size:12.5px;cursor:pointer;width:fit-content;max-width:100%}
.ov-insight:hover{background:rgba(255,184,92,.14)}
.ov-insight svg{width:14px;height:14px;flex:none}
@media(max-width:760px){.ov-hero .customize{position:static;margin-left:auto;opacity:.8}}
.ov-ask{display:flex;gap:8px;flex:1;min-width:230px;max-width:440px}
.ov-ask input{flex:1;background:var(--surface);border:1px solid var(--line);border-radius:10px;color:#eaf4fb;padding:9px 12px;font-size:14px}.ov-ask input:focus{border-color:var(--accent);outline:none}
.ov-ask button{background:var(--accent);border:0;border-radius:10px;color:#04121e;padding:0 14px;cursor:pointer;font-weight:600}
@keyframes corepulse{0%,100%{box-shadow:0 0 22px -6px var(--glow)}50%{box-shadow:0 0 34px 2px var(--glow)}}
.ov-tel{display:flex;gap:6px;flex-wrap:wrap;width:100%;margin-top:2px}
.ov-tel .t{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;color:var(--subtle);border:1px solid var(--line);border-radius:7px;padding:4px 8px;display:flex;gap:6px;align-items:center}
.ov-tel .t b{color:var(--accent);font-weight:600}.ov-tel .t.on b{color:#5ee6a3}
.ov-tel .t.on::before{content:"";width:6px;height:6px;border-radius:50%;background:#5ee6a3;box-shadow:0 0 6px #5ee6a3;animation:pulse2 2s infinite}
.ovr{width:72px;height:72px;flex:none;border-radius:50%;background:conic-gradient(var(--accent) calc(var(--p,0)*1%),var(--elev) 0);display:flex;align-items:center;justify-content:center;position:relative}
.ovr::before{content:"";position:absolute;inset:7px;border-radius:50%;background:#0a1420}.ovr .rv{position:relative;font-family:var(--disp);font-size:16px;color:#eaf4fb;text-align:center;line-height:1}.ovr .rv small{font-size:9px;color:var(--muted)}
.ov-row2{display:flex;align-items:center;gap:14px}
.spark{display:flex;align-items:flex-end;gap:5px;height:54px;margin:10px 0 16px}
.spark .b{flex:1;background:linear-gradient(180deg,var(--accent),rgba(77,208,225,.22));border-radius:3px 3px 0 0;min-height:3px;position:relative}
.spark .b span{position:absolute;bottom:-15px;left:0;right:0;text-align:center;font-family:var(--mono);font-size:9px;color:var(--subtle)}
.spark .b.today{background:linear-gradient(180deg,#5ee6a3,rgba(94,230,163,.28))}
.ov-task{display:flex;align-items:center;gap:9px;padding:5px 0;font-size:13.5px;color:#cfe3f2}
.ov-task .ck{width:18px;height:18px;border:1.5px solid var(--line-2);border-radius:6px;flex:none;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.15s}.ov-task .ck:hover{border-color:var(--accent)}
.ov-task .ck svg{width:12px;height:12px;color:#04121e;opacity:0}.ov-task.done .ck{background:var(--accent);border-color:var(--accent)}.ov-task.done .ck svg{opacity:1}.ov-task.done .tx{text-decoration:line-through;color:var(--subtle)}
.ov-hab{display:flex;flex-wrap:wrap;gap:7px;margin-top:4px}
.ov-hab .c{font-size:12.5px;color:var(--muted);border:1px solid var(--line);border-radius:20px;padding:5px 11px;cursor:pointer;display:flex;gap:6px;align-items:center;transition:.15s}.ov-hab .c:hover{border-color:var(--accent);color:#cfe3f2}
.ov-hab .c.done{background:rgba(94,230,163,.14);border-color:#5ee6a3;color:#bff3d6}.ov-hab .c svg{width:13px;height:13px}
.ov-mini{display:flex;gap:7px;flex-wrap:wrap}.ov-mini button{background:var(--surface);border:1px solid var(--line);border-radius:9px;color:#cfe3f2;padding:8px 11px;font-size:12.5px;cursor:pointer;display:flex;gap:7px;align-items:center;transition:.15s}.ov-mini button:hover{border-color:var(--accent);color:#eaf4fb}.ov-mini button svg{width:14px;height:14px;color:var(--accent)}
.ov-add{display:flex;gap:7px;margin-top:9px}.ov-add input{flex:1;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:9px;color:#eaf4fb;padding:7px 10px;font-size:13px}.ov-add input:focus{border-color:var(--accent);outline:none}
.ov-add button{background:var(--surface);border:1px solid var(--line);border-radius:9px;color:var(--accent);padding:0 12px;cursor:pointer}
.ov-hours{display:flex;gap:10px;overflow:auto;margin-top:8px}.ov-hours .hh{flex:none;text-align:center;font-size:11px;color:var(--muted)}.ov-hours .hh svg{width:20px;height:20px;color:var(--accent);margin:3px 0}.ov-hours .hh b{color:#eaf4fb;font-weight:600}
.ov-feed{max-height:190px;overflow:auto}.ov-feed .f{display:flex;gap:9px;align-items:center;padding:5px 0;font-size:12.5px;color:var(--muted)}.ov-feed .f svg{width:14px;height:14px;color:var(--accent);flex:none}.ov-feed .f .w{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--subtle);flex:none}
.ov-ask .mic{flex:none;background:var(--surface);border:1px solid var(--line);color:var(--accent);border-radius:10px;padding:0 12px;cursor:pointer;display:flex;align-items:center}.ov-ask .mic:hover{border-color:var(--accent)}.ov-ask .mic svg{width:16px;height:16px}
.ov-ask .mic.rec{background:var(--accent);color:#04121e;animation:pulse 1.1s infinite}
.ov-sugg{display:flex;flex-wrap:wrap;gap:7px;width:100%;margin-top:2px}
.ov-sugg button{font-family:var(--mono);font-size:11px;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:20px;padding:5px 11px;cursor:pointer;transition:.15s}.ov-sugg button:hover{border-color:var(--accent);color:#cfe3f2}
.ov-task .when{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--subtle);flex:none}
.ov-sp{display:flex;gap:11px;align-items:center;margin-top:2px}
.ov-sp-art{width:52px;height:52px;border-radius:9px;object-fit:cover;flex:none;background:var(--elev);box-shadow:0 0 16px -8px var(--glow)}
.ov-sp-info{flex:1;min-width:0}.ov-sp-info .t{color:#eaf4fb;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ov-sp-info .a{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-sp-ctl{display:flex;gap:8px;margin-top:11px}.ov-sp-ctl button{width:34px;height:34px;border-radius:50%;border:1px solid var(--line);background:var(--surface);color:var(--accent);cursor:pointer;display:grid;place-items:center}.ov-sp-ctl button:hover{border-color:var(--accent)}.ov-sp-ctl button svg{width:15px;height:15px}
.ov-sp-bar{height:4px;background:var(--elev);border-radius:3px;overflow:hidden;margin-top:11px}.ov-sp-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#5ee6a3)}
.ov-astro{display:flex;gap:14px;align-items:center;margin-top:2px}
.ov-moon{width:58px;height:58px;border-radius:50%;flex:none;background:radial-gradient(circle at 32% 38%,#eef6ff,#a9c0d4 62%,#2f4256);box-shadow:0 0 22px -6px var(--glow),inset -10px -6px 16px -8px #060c14}
.ov-money{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}.ov-money:last-child{border-bottom:0}.ov-money b{color:#eaf4fb;font-family:var(--disp);font-size:16px}
.rd-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:1400px}
@media(max-width:820px){.rd-grid{grid-template-columns:1fr}}
.rd-half{min-width:0}
.rd-full{min-width:0;grid-column:1/-1}
.pd-t{font-family:var(--disp);font-size:16px;color:#eaf4fb;margin-bottom:12px;text-shadow:0 0 14px rgba(var(--accent-rgb),.25)}
.pd-card{border:1px solid var(--line);border-radius:14px;background:var(--surface);padding:15px 17px;margin-bottom:12px}
.pd-card-row{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.pd-card .l{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle);margin-bottom:8px;display:flex;align-items:center;gap:6px}
.pd-card .l svg{width:13px;height:13px}
.pd-moon{display:flex;align-items:center;gap:16px}
.pd-moon .disc{width:64px;height:64px;border-radius:50%;flex:none;background:radial-gradient(circle at 35% 35%,#eaf4fb,#7d93aa);box-shadow:0 0 22px -4px var(--glow),inset -14px 0 16px -6px rgba(4,7,12,.85)}
.pd-moon .big{font-family:var(--disp);font-size:26px;color:#eaf4fb}.pd-moon .sub{color:var(--muted);font-size:13px}
.pd-sun{display:flex;justify-content:space-between}.pd-sun .v{font-family:var(--disp);font-size:24px;color:#eaf4fb}.pd-sun .k{font-size:11px;color:var(--muted)}
.pd-clocks{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.pd-clock{display:flex;justify-content:space-between;align-items:baseline;padding:7px 11px;border:1px solid var(--line);border-radius:10px;background:var(--elev)}
.pd-clock .c{font-family:var(--mono);letter-spacing:.1em;color:var(--subtle);font-size:11px}.pd-clock .h{font-family:var(--disp);font-size:18px;color:#eaf4fb}
.pd-rate{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line);font-family:var(--mono);font-size:14px}.pd-rate b{color:var(--accent)}
.pd-hl a{display:block;padding:6px 0;border-bottom:1px solid var(--line);color:var(--fg);font-size:13px;text-decoration:none;line-height:1.4}.pd-hl a:hover{color:var(--accent)}
.goal{max-width:640px;border:1px solid var(--line);border-radius:14px;background:var(--surface);padding:15px 18px;margin-bottom:12px}
.goal .gh{display:flex;justify-content:space-between;align-items:baseline}.goal .gn{font-size:16px;color:#eaf4fb}.goal .gv{font-family:var(--mono);font-size:13px;color:var(--accent)}
.goal .gbar{height:9px;background:var(--elev);border-radius:5px;overflow:hidden;margin:9px 0}.goal .gbar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#5ee6a3);box-shadow:0 0 8px var(--glow)}
.goal .ga{display:flex;gap:8px;align-items:center;margin-top:4px}.goal .ga input{width:110px}
.sa-card{max-width:640px;border:1px solid var(--line);border-radius:14px;background:var(--surface);padding:16px 18px;margin-bottom:12px}
.sa-card .t{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle);margin-bottom:10px}
.sa-water{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.sa-drop{width:26px;height:32px;color:var(--line-2);cursor:default}.sa-drop.on{color:var(--accent);filter:drop-shadow(0 0 5px var(--glow))}
.sa-mood{display:flex;gap:8px}.sa-mood button{font-size:22px;background:none;border:1px solid var(--line);border-radius:10px;width:44px;height:44px;cursor:pointer}.sa-mood button.on{border-color:var(--accent);box-shadow:0 0 12px -4px var(--glow)}
.cf-row{display:flex;align-items:center;gap:12px;padding:11px 14px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;background:var(--surface);max-width:720px}
.cf-row .n{flex:1}.cf-row .sz{font-family:var(--mono);font-size:11px;color:var(--subtle)}
#wx-body{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;align-items:start;max-width:1500px}
.wx-cur{grid-column:1/-1;display:flex;align-items:center;gap:24px;border:1px solid var(--line-2);border-radius:18px;padding:26px 30px;background:linear-gradient(150deg,rgba(24,44,68,.6),rgba(10,20,32,.5));box-shadow:0 0 44px -22px var(--glow);min-width:0}
.wx-cur .ic{flex:none}
.wx-cur .ic svg{width:80px;height:80px;color:var(--accent);filter:drop-shadow(0 0 14px var(--glow))}
.wx-info{flex:1;min-width:0}
.wx-loc{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle)}
.wx-temp{font-family:var(--disp);font-size:72px;line-height:1;color:#eaf4fb;text-shadow:0 0 22px rgba(var(--accent-rgb),.3)}
.wx-desc{color:var(--fg);margin-top:2px;font-size:17px;overflow-wrap:anywhere}.wx-hl{color:var(--muted);font-family:var(--mono);font-size:12px;margin-top:5px;overflow-wrap:anywhere}
.wx-card{border:1px solid var(--line);border-radius:14px;background:var(--surface);padding:14px 16px;min-width:0}
.wx-card.wide{grid-column:1/-1}.wx-card.span2{grid-column:span 2}
.wx-ct{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--subtle);margin-bottom:10px;display:flex;align-items:center;gap:6px}
.wx-ct svg{width:13px;height:13px}
.wx-hours{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}.wx-hours::-webkit-scrollbar{display:none}
.wx-h{flex:none;width:66px;text-align:center;padding:8px 0;border:1px solid var(--line);border-radius:12px;background:var(--elev)}
.wx-h .t{font-family:var(--mono);font-size:11px;color:var(--muted)}.wx-h svg{width:22px;height:22px;color:var(--accent);margin:6px 0}.wx-h .d{font-size:14px;color:#eaf4fb}.wx-h .p{font-size:10px;color:#5ec8ff}
.wx-d{display:flex;align-items:center;gap:12px;padding:7px 0;border-bottom:1px solid var(--line)}
.wx-d .dn{width:52px;color:var(--fg)}.wx-d svg{width:20px;height:20px;color:var(--accent);flex:none}
.wx-d .mn{width:38px;text-align:right;color:var(--muted);font-family:var(--mono);font-size:13px}
.wx-d .mx{width:38px;color:#eaf4fb;font-family:var(--mono);font-size:13px}
.wx-track{flex:1;height:6px;background:var(--elev);border-radius:4px;position:relative}
.wx-track i{position:absolute;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--accent),#ffb35e)}
.wx-m .big{font-family:var(--disp);font-size:32px;color:#eaf4fb;line-height:1.1;margin-top:2px}
.wx-m .sub{color:var(--muted);font-size:12px;margin-top:6px}
.wx-m .bar{height:5px;background:var(--elev);border-radius:3px;overflow:hidden;margin-top:8px}
.wx-m .bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent));box-shadow:0 0 6px var(--glow)}
.wx-sun{display:flex;justify-content:space-between;margin-top:4px}.wx-sun .v{font-family:var(--disp);font-size:24px;color:#eaf4fb}.wx-sun .l{font-size:11px;color:var(--muted)}
.wx-compass{width:64px;height:64px;border-radius:50%;border:1px solid var(--line-2);position:relative;margin-top:4px}
.wx-compass .nd{position:absolute;top:2px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--subtle)}
.wx-compass .ar{position:absolute;top:50%;left:50%;width:2px;height:26px;background:var(--accent);transform-origin:bottom center;box-shadow:0 0 6px var(--glow)}
@media(max-width:600px){
  /* the desktop sizing (80px icon, 72px temp, fixed 220px grid columns) doesn't
     scale down on phones — force a single column and shrink everything to fit */
  #wx-body{grid-template-columns:1fr;gap:10px}
  .wx-card.wide,.wx-card.span2{grid-column:1/-1}
  .wx-cur{flex-wrap:wrap;gap:14px;padding:18px 16px}
  .wx-cur .ic svg{width:52px;height:52px}
  .wx-temp{font-size:44px}
  .wx-desc{font-size:15px}
  .wx-hl{font-size:11px}
  .wx-h{width:56px}
  .wx-h svg{width:18px;height:18px;margin:4px 0}
  .wx-d{gap:8px}
  .wx-d .dn{width:40px;font-size:13px}
  .wx-d .mn,.wx-d .mx{width:30px;font-size:12px}
  .wx-m .big{font-size:26px}
  .wx-compass{width:52px;height:52px}
}
#mu-player{max-width:760px;margin-bottom:16px}
#mu-player iframe{width:100%;height:352px;border:0;border-radius:14px;box-shadow:0 0 30px -18px var(--glow)}
#mu-player.compact iframe{height:152px}
.mu-row{display:flex;align-items:center;gap:10px;padding:10px 14px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;background:var(--surface);max-width:760px;cursor:pointer;transition:border-color .15s}
.mu-row:hover{border-color:var(--line-2)}.mu-row.on{border-color:var(--accent);box-shadow:0 0 16px -8px var(--glow)}
.mu-row .n{flex:1}.mu-row .k{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--subtle)}
.sp-np{display:flex;gap:14px;align-items:center;border:1px solid var(--line-2);border-radius:16px;padding:14px;background:linear-gradient(180deg,rgba(18,34,52,.5),rgba(10,20,32,.4))}
.sp-np img{width:92px;height:92px;border-radius:10px;object-fit:cover;flex:none;display:none;box-shadow:0 0 20px -8px var(--glow)}
.sp-info{flex:1;min-width:0}
.sp-tt{font-family:var(--disp);font-size:18px;color:#eaf4fb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-ar{color:var(--muted);font-size:13px;margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-prog{height:4px;background:var(--surface);border-radius:3px;overflow:hidden;margin-bottom:10px}
.sp-prog i{display:block;height:100%;background:var(--accent);box-shadow:0 0 8px var(--glow);width:0;transition:width .6s linear}
.sp-ctl{display:flex;gap:8px;align-items:center}
.sp-ctl .vcbtn{width:40px;height:40px}
.sp-ctl #sp-like.on{color:#ff6ec7;border-color:#ff6ec7;box-shadow:0 0 12px -4px #ff6ec7}
.pg-card{max-width:760px;border:1px solid var(--line);border-radius:14px;background:var(--surface);padding:16px 18px;margin-bottom:14px}
.pg-wt{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--subtle);margin-bottom:9px}
.pg-li{padding:5px 0;line-height:1.4;border-bottom:1px solid var(--line)}
.pg-big{font-family:var(--disp);font-size:30px;color:#eaf4fb;text-shadow:0 0 18px rgba(var(--accent-rgb),.3)}
.pg-bar{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.pg-bar .l{width:120px;font-family:var(--mono);font-size:11px;color:var(--muted);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:none}
.pg-bar .t{flex:1;height:9px;background:var(--elev);border-radius:5px;overflow:hidden}
.pg-bar .t i{display:block;height:100%;background:var(--accent);box-shadow:0 0 8px var(--glow)}
.pg-bar .v{width:74px;font-family:var(--mono);font-size:11px;flex:none}
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
.tv-h{font-family:var(--disp);font-weight:600;font-size:22px;margin-bottom:18px;color:#eaf4fb;text-shadow:0 0 16px rgba(var(--accent-rgb),.2);position:relative;padding-left:15px}
.tv-h::before{content:"";position:absolute;left:0;top:2px;bottom:2px;width:3px;border-radius:2px;background:linear-gradient(180deg,var(--accent),transparent);box-shadow:0 0 10px var(--glow)}
.tv-form{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px;max-width:720px}
.tv-form input{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:12px 15px;color:var(--fg);font:inherit;font-size:15px}
.tv-form #task-text{flex:1}.tv-form #task-cat{width:140px;flex:none;font-family:var(--mono);font-size:13px}
.tv-form input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(var(--accent-rgb),.12)}
.tv-form select{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:12px 15px;color:var(--fg);font:inherit;font-size:13px;font-family:var(--mono);flex:none;cursor:pointer}
.tv-form select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(var(--accent-rgb),.12)}
.tv-cat{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--subtle);margin:20px 0 9px}
.tv-row{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;background:linear-gradient(160deg,rgba(18,34,52,.34),rgba(9,17,28,.32));max-width:720px;transition:border-color .15s,box-shadow .15s,transform .15s}
.tv-row:hover{border-color:var(--accent);box-shadow:0 6px 20px -16px var(--glow);transform:translateX(2px)}.tv-row .txt{flex:1;line-height:1.4}
.tv-ic{width:34px;height:34px;flex:none;display:grid;place-items:center;border-radius:9px;border:1px solid var(--line);background:var(--elev);color:var(--muted);cursor:pointer;transition:.15s}
.tv-ic:hover{color:var(--accent);border-color:var(--accent)}.tv-ic svg{width:16px;height:16px}
.tv-empty{color:var(--subtle);font-family:var(--mono);font-size:13px;padding:22px 18px;border:1px dashed var(--line);border-radius:12px;max-width:720px;text-align:center;background:linear-gradient(160deg,rgba(18,34,52,.16),transparent)}
.tv-empty-ic{padding:34px 22px}
.tv-empty-icon{width:44px;height:44px;margin:0 auto 14px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--elev);color:var(--accent)}
.tv-empty-icon svg{width:20px;height:20px}
.tv-empty-title{font-family:var(--body);font-size:14px;color:var(--fg)}
.tv-empty-hint{margin-top:6px;font-size:12px;color:var(--subtle)}
.tv-search{width:100%;max-width:720px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:11px 14px;color:var(--fg);font:inherit;font-size:14px;margin-bottom:14px;display:block}
.tv-search:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(var(--accent-rgb),.12)}
.tv-search:focus{outline:none;border-color:var(--line-2)}
#log{flex:1;min-height:0;overflow-y:auto;padding:20px 22px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:82%;padding:13px 16px;line-height:1.55;border:1px solid var(--line);border-radius:16px;animation:rise .32s cubic-bezier(.2,.7,.2,1)}
.msg.you{align-self:flex-end;background:var(--fg);color:var(--ink);border:none;border-bottom-right-radius:5px;font-weight:500;box-shadow:0 0 20px -13px var(--glow)}
.msg.ev{position:relative}
body:not(.term) .msg.ev::after{content:"";position:absolute;top:7px;left:7px;width:11px;height:11px;border-top:1px solid var(--accent);border-left:1px solid var(--accent);opacity:.5;pointer-events:none}
.msg.ev{align-self:flex-start;background:linear-gradient(180deg,rgba(18,34,52,.72),rgba(10,20,32,.66));-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);border-color:var(--line-2);border-bottom-left-radius:5px;box-shadow:0 0 26px -18px var(--glow),inset 0 0 0 1px rgba(var(--accent-rgb),.06)}
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
.msg .mtable tr:nth-child(even) td{background:rgba(var(--accent-rgb),.045)}
.msg .mimg{max-width:100%;border-radius:12px;margin:8px 0;border:1px solid var(--line-2);display:block;box-shadow:0 4px 18px rgba(0,0,0,.35)}
.msg.ev .decoding{white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12.5px;line-height:1.5;color:var(--accent);text-shadow:0 0 6px var(--glow)}
/* reactive presence orb — the left core reacts to E.V.'s voice amplitude */
body.talking .core{filter:drop-shadow(0 0 calc(4px + var(--talk,0)*30px) var(--glow))}
body.talking .core .dot{transform:scale(calc(1 + var(--talk,0)*0.7))}
body.talking .core .arc,body.talking .core .arc.two{opacity:calc(.4 + var(--talk,0)*0.6)}
/* she heard her name — one-shot orb flash */
body.heard .core{animation:heardpulse .66s ease-out}
@keyframes heardpulse{0%{filter:drop-shadow(0 0 4px var(--glow))}35%{filter:drop-shadow(0 0 34px var(--glow)) brightness(1.5)}100%{filter:drop-shadow(0 0 4px var(--glow))}}
.mchips{display:flex;flex-wrap:wrap;gap:7px;margin:3px 0 10px}
.mchip{display:inline-flex;align-items:center;align-self:center;gap:6px;font-family:var(--mono);font-size:12px;color:var(--fg);background:var(--elev);border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer;position:relative;overflow:hidden;transition:background .15s,border-color .15s,color .15s}
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
.nrow.nproac{border-color:rgba(255,180,80,.5);background:rgba(255,180,80,.06)}
.nrow.nproac .nico{color:#ffb450}.nrow.nproac .ntitle::before{background:#ffb450}
.nx{background:none;border:none;color:var(--subtle);cursor:pointer;padding:2px;flex:none;border-radius:6px}
.nx:hover{color:var(--fg);background:var(--line)}.nx svg{width:15px;height:15px}
body.term .msg code{background:transparent;border:none;padding:0}
body.term .msg .mdh,body.term .msg .bul,body.term .msg .sub{all:unset;display:block}
body.term .msg .sub{font-weight:700}
body.term .msg .sep{all:unset;display:block;color:var(--subtle)}body.term .msg .sep::before{content:"─────────"}
.msg .h{font-family:var(--disp);font-weight:600;font-size:15px;margin-bottom:8px;display:block;color:#eaf4fb;text-shadow:0 0 14px rgba(var(--accent-rgb),.35)}
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
.field:focus-within{border-color:var(--accent);box-shadow:0 0 0 4px rgba(var(--accent-rgb),.10)}
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
.ripple{position:absolute;border-radius:50%;background:rgba(var(--accent-rgb),.3);transform:scale(0);animation:rp .5s ease-out;pointer-events:none}
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
.vlist{display:flex;flex-direction:column;gap:6px;margin:10px 0;max-height:38vh;overflow:auto}
.vrow{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 13px;border:1px solid var(--line);border-radius:11px;background:var(--surface);cursor:pointer;transition:.15s}
.vrow:hover{border-color:var(--line-2)}
.vrow.on{border-color:var(--accent);background:linear-gradient(90deg,rgba(var(--accent-rgb),.12),transparent);box-shadow:0 0 16px -8px var(--glow)}
.vname{font-size:14px;color:var(--fg)}
.vgroup{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--subtle);margin:8px 2px 2px}.vgroup:first-child{margin-top:0}
.vplay{width:34px;height:34px;flex:none;display:grid;place-items:center;border-radius:9px;border:1px solid var(--line-2);background:var(--elev);color:var(--accent);cursor:pointer}
.vplay:hover{box-shadow:0 0 12px -4px var(--glow)}.vplay.busy{opacity:.5}.vplay svg{width:15px;height:15px}
.vrange{margin:8px 0}.vrange .vval{float:right;color:var(--accent);font-family:var(--mono);font-size:11px}
.vrange input[type=range]{width:100%;accent-color:var(--accent)}
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
  #taskview,#kbview,#expview,#remview,#memview,#calview,#lnkview,#habview,#jouview,#subview,#orcview,#monview,#actview,#brainview,#pageview,#musicview,#climaview,#metasview,#saudeview,#cofreview,#painelview,#inicioview,#locview{padding:16px 14px}
  #log{padding:14px 14px}
  .msg{max-width:92%!important}
  #calgrid{gap:3px}.cal-cell{min-height:62px;padding:4px}
}
/* Mobile (<=760): barras laterais deslizam DE BAIXO (bottom sheet). Depois do
   bloco 980 pra vencer a regra de drawer lateral. */
@media(max-width:760px){
  #left,#right{top:auto;left:0;right:0;bottom:0;width:auto;max-height:82vh;
    border:1px solid var(--line);border-bottom:0;border-radius:20px 20px 0 0;
    transform:translateY(107%);padding:16px 16px calc(20px + env(safe-area-inset-bottom));
    box-shadow:0 -24px 60px rgba(0,0,0,.72)}
  #left::before,#right::before{content:"";display:block;flex:none;width:42px;height:4px;
    border-radius:3px;background:var(--line-2);margin:0 auto 14px}
  body.m-left #left,body.m-right #right{transform:translateY(0)}
  /* modals/pickers as bottom sheets too — matches the drawer language above
     and keeps everything reachable with a thumb instead of a centered floating box */
  #modal{align-items:flex-end}
  .mcard{width:100%;max-width:100%;max-height:86vh;border-radius:20px 20px 0 0;
    padding:16px 16px calc(18px + env(safe-area-inset-bottom));
    box-shadow:0 -24px 60px rgba(0,0,0,.72);animation:sheetUp .22s ease-out}
  .mcard::before{content:"";display:block;width:42px;height:4px;border-radius:3px;
    background:var(--line-2);margin:0 auto 14px}
  .mbar{flex-direction:column-reverse;gap:8px}
  .mbar button{width:100%;padding:12px 16px}
  /* bigger touch targets for small tap zones */
  .mrow input{width:21px;height:21px}
  .ov-task .ck{width:23px;height:23px}
}
@keyframes sheetUp{from{transform:translateY(28px);opacity:.5}to{transform:translateY(0);opacity:1}}
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
    <div class="state" id="state" data-i18n="state.idle">standby</div>
    <div class="eyebrow" data-i18n="side.conversations">Conversations</div>
    <div id="folders"></div>
    <div class="newf" id="newf" data-i18n="side.newfolder">+ new folder</div>
    <div class="sysbox">
      <span class="hud-c tl"></span><span class="hud-c tr"></span><span class="hud-c bl"></span><span class="hud-c br"></span>
      <div class="kv"><span>STATUS</span><b id="s-status" class="on-dot">ONLINE</b></div>
      <div class="kv"><span data-i18n="sys.provider">PROVIDER</span><b id="s-prov">—</b></div>
      <div class="kv"><span data-i18n="sys.model">MODEL</span><b id="s-model">—</b></div>
      <div class="kv"><span data-i18n="sys.latency">LATENCY</span><b id="s-lat">—</b></div>
      <div class="load"><i id="s-load"></i></div>
      <div class="kv"><span id="s-counts">—</span></div>
      <div class="kv"><span data-i18n="sys.time">TIME</span><b id="s-clock">—</b></div>
    </div>
  </aside>
  <main id="center">
    <div class="topbar">
      <button class="tbtn ico" id="tgl-left" title="Hide/show folders" data-i18n-title="top.togLeft"><i data-lucide="panel-left"></i></button>
      <button class="tbtn ico tabs-nav" id="tabs-prev" title="Scroll tabs left" data-i18n-title="top.tabsPrev"><i data-lucide="chevron-left"></i></button>
      <div class="tabs" id="tabs"></div>
      <button class="tbtn ico tabs-nav" id="tabs-next" title="Scroll tabs right" data-i18n-title="top.tabsNext"><i data-lucide="chevron-right"></i></button>
      <button id="mnav" class="mnav" type="button" title="Go to" data-i18n-title="top.goto"><span id="mnav-lbl">Home</span><i data-lucide="chevron-down"></i></button>
      <span class="eyebrow" id="scope">geral</span>
      <span class="mm-badge" id="mm-badge" title="Focus mode on — click to turn off" data-i18n-title="top.focusBadge"><i data-lucide="skull"></i><span class="mm-lbl" data-i18n="top.focusLbl">FOCUS MODE</span></span>
      <button class="tbtn ico" id="gsearch" title="Search everything" data-i18n-title="top.search"><i data-lucide="search"></i></button>
      <button class="tbtn ic-txt" id="vcopen" title="Talk" data-i18n-title="top.talk"><i data-lucide="mic"></i><span data-i18n="top.talkLbl">TALK</span></button>
      <button class="tbtn ic-txt" id="amb" title="Ambient presence — always listens for &quot;E.V. ...&quot;" data-i18n-title="top.ambient"><i data-lucide="radio"></i><span data-i18n="top.ambientLbl">AMBIENT</span></button>
      <button class="tbtn ic-txt" id="term" title="Terminal mode" data-i18n-title="top.terminal"><i data-lucide="square-terminal"></i><span data-i18n="top.terminalLbl">TERMINAL</span></button>
      <button class="tbtn ic-txt on" id="voz" title="E.V.'s voice" data-i18n-title="top.voice"><i data-lucide="volume-2"></i><span data-i18n="top.voiceLbl">VOICE</span></button>
      <button class="tbtn ico" id="sfx" title="Interface sounds" data-i18n-title="top.sfx"><i data-lucide="audio-lines"></i></button>
      <button class="tbtn ico" id="theme" title="Pick a color theme" data-i18n-title="top.theme"><i data-lucide="palette"></i></button>
      <div id="theme-menu" role="menu" aria-label="Color theme"></div><button class="tbtn ico" id="lang" title="Language" data-i18n-title="top.lang"><i data-lucide="languages"></i></button><div id="lang-menu" role="menu" aria-label="Language"></div>
      <button class="tbtn ico" id="tgl-right" title="Hide/show panel" data-i18n-title="top.togRight"><i data-lucide="panel-right"></i></button>
      <button class="tbtn ico" id="tgl-zen" title="Clean mode (hide panels)" data-i18n-title="top.zen"><i data-lucide="minimize-2"></i></button></div>
    <div id="chatview">
      <div id="log"></div>
      <div id="audprev"></div>
      <div id="imgprev"></div>
      <form id="f"><div id="slash"></div>
        <button type="button" class="icon" id="attach" title="Attach" data-i18n-title="chat.attach"><i data-lucide="plus"></i></button>
        <button type="button" class="icon mic" id="mic" title="Talk" data-i18n-title="chat.mic"><span class="mg"><i data-lucide="mic"></i></span><span class="wave"><b></b><b></b><b></b><b></b></span></button>
        <button type="button" class="icon" id="imgbtn" title="Send image" data-i18n-title="chat.img"><i data-lucide="image"></i></button>
        <button type="button" class="icon" id="cambtn" title="Live camera" data-i18n-title="chat.cam"><i data-lucide="camera"></i></button>
        <input type="file" id="imgfile" accept="image/*" style="display:none">
        <div class="field"><input id="txt" placeholder="Talk to E.V.  ·  type / for commands" data-i18n-ph="chat.input" autocomplete="off"></div>
        <button class="icon send" id="send" title="Send" data-i18n-title="chat.send"><i data-lucide="arrow-up"></i></button></form>
    </div>
    <div id="taskview">
      <div class="tv-h" data-i18n="tasks.h">Tasks</div>
      <form id="taskform" class="tv-form">
        <input id="task-text" placeholder="New task..." data-i18n-ph="tasks.new" autocomplete="off">
        <input id="task-cat" placeholder="category" value="geral" data-i18n-ph="common.categoryPh" autocomplete="off">
        <input id="task-due" type="datetime-local" title="Due date (optional)" data-i18n-title="tasks.duePh" style="flex:none">
        <select id="task-recur" title="Repeat" data-i18n-title="common.repeat"><option value="" data-i18n="recur.once">Once</option><option value="daily" data-i18n="recur.daily">Daily</option><option value="weekly" data-i18n="recur.weekly">Weekly</option><option value="monthly" data-i18n="recur.monthly">Monthly</option></select>
        <button class="mbtn" type="submit" data-i18n="common.add">Add</button>
      </form>
      <input class="tv-search" id="tasks-search" placeholder="Search tasks..." data-i18n-ph="tasks.search" autocomplete="off">
      <div id="tasklist"></div>
    </div>
    <div id="kbview">
      <div class="tv-h" data-i18n="kb.h">Knowledge base</div>
      <div class="kb-add">
        <form id="kb-urlf" class="tv-form"><input id="kb-url" placeholder="https://...  (index a page)" data-i18n-ph="kb.urlPh"><button class="mbtn" type="submit" data-i18n="kb.indexUrl">Index URL</button></form>
        <div class="tv-form" style="align-items:center"><label class="mbtn2" for="kb-file" style="cursor:pointer" data-i18n="kb.upload">⬱ Upload file (PDF / Word / txt)</label><input id="kb-file" type="file" accept=".pdf,.docx,.txt,.md" style="display:none"><span id="kb-fmsg" class="tv-empty"></span></div>
        <form id="kb-textf"><input id="kb-title" class="minput" placeholder="Note title" data-i18n-ph="kb.notePh" style="margin-bottom:8px"><textarea id="kb-text" class="minput" placeholder="Paste text for E.V. to learn and answer from..." data-i18n-ph="kb.textPh"></textarea><button class="mbtn" type="submit" style="margin-top:8px" data-i18n="kb.addText">Add text</button></form>
      </div>
      <input class="tv-search" id="kb-search" placeholder="Search the base..." data-i18n-ph="kb.search" autocomplete="off">
      <div class="tv-cat" data-i18n="kb.indexed">Indexed documents</div>
      <div id="kblist"></div>
    </div>
    <div id="expview">
      <div class="tv-h" data-i18n="exp.h">Expenses</div>
      <form id="expform" class="tv-form"><input id="exp-amt" placeholder="Amount" data-i18n-ph="common.amount" style="width:110px;flex:none"><input id="exp-desc" placeholder="Description" data-i18n-ph="common.description"><input id="exp-cat" placeholder="category" value="geral" style="width:140px;flex:none" data-i18n-ph="common.categoryPh2"><button class="mbtn" type="submit" data-i18n="common.log">Log</button></form>
      <div id="expchart"></div>
      <input class="tv-search" id="exp-search" placeholder="Search expenses..." data-i18n-ph="exp.search" autocomplete="off">
      <div class="tv-cat" data-i18n="exp.last60">Last 60 days</div>
      <div id="explist"></div>
    </div>
    <div id="remview">
      <div class="tv-h" data-i18n="rem.h">Reminders</div>
      <form id="remform" class="tv-form"><input id="rem-text" placeholder="Remind me to..." data-i18n-ph="rem.newPh"><input id="rem-when" type="datetime-local" style="flex:none"><select id="rem-recur" title="Repeat" data-i18n-title="common.repeat2"><option value="" data-i18n="recur.once2">Once</option><option value="daily" data-i18n="recur.daily2">Daily</option><option value="weekly" data-i18n="recur.weekly2">Weekly</option><option value="monthly" data-i18n="recur.monthly2">Monthly</option></select><button class="mbtn" type="submit" data-i18n="common.create">Create</button></form>
      <input class="tv-search" id="rem-search" placeholder="Search reminders..." data-i18n-ph="rem.search" autocomplete="off">
      <div class="tv-cat" data-i18n="rem.open">Open</div>
      <div id="remlist"></div>
    </div>
    <div id="calview">
      <div class="cal-head"><button class="tbtn" id="cal-prev">‹</button><div class="tv-h" id="cal-title" style="margin:0;min-width:200px;text-align:center"></div><button class="tbtn" id="cal-next">›</button></div>
      <div class="cal-send"><button class="mbtn2" id="cal-email" data-i18n="cal.email">Send email</button><button class="mbtn2" id="cal-msg" data-i18n="cal.msg">Telegram message</button></div>
      <div id="calgrid"></div>
    </div>
    <div id="memview">
      <div class="tv-h" data-i18n="mem.h">Memories<span id="mem-count" style="font-size:13px;color:var(--subtle);margin-left:10px"></span></div>
      <form id="memform" class="tv-form"><input id="mem-text" placeholder="Something E.V. should remember about you..." data-i18n-ph="mem.newPh"><button class="mbtn" type="submit" data-i18n="common.save">Save</button></form>
      <input class="tv-search" id="mem-search" placeholder="Search the brain..." data-i18n-ph="mem.search" autocomplete="off">
      <div class="tv-cat" style="display:flex;justify-content:space-between;align-items:center" data-i18n="mem.knows">What E.V. knows<span id="mem-clear" style="cursor:pointer;color:var(--muted);font-family:var(--mono);font-size:10px;letter-spacing:.1em" data-i18n="mem.forgetAll">forget all</span></div>
      <div id="memlist"></div>
    </div>
    <div id="lnkview">
      <div class="tv-h" data-i18n="lnk.h">Links</div>
      <form id="lnkform" class="tv-form"><input id="lnk-name" placeholder="Name" data-i18n-ph="common.name"><input id="lnk-url" placeholder="https://..."><input id="lnk-cat" placeholder="category" value="geral" style="width:150px;flex:none" data-i18n-ph="common.categoryPh3"><button class="mbtn" type="submit" data-i18n="common.save2">Save</button></form>
      <input class="tv-search" id="lnk-search" placeholder="Search links..." data-i18n-ph="lnk.search" autocomplete="off">
      <div id="lnklist"></div>
    </div>
    <div id="habview">
      <div class="tv-h" data-i18n="hab.h">Habits</div>
      <form id="habform" class="tv-form"><input id="hab-name" placeholder="New habit (e.g. workout)" data-i18n-ph="hab.newPh"><button class="mbtn" type="submit" data-i18n="common.create2">Create</button></form>
      <input class="tv-search" id="hab-search" placeholder="Search habits..." data-i18n-ph="hab.search" autocomplete="off">
      <div id="hablist"></div>
    </div>
    <div id="jouview">
      <div class="tv-h" data-i18n="jou.h">Journal</div>
      <form id="jouform" class="tv-form"><input id="jou-text" placeholder="How was your day?" data-i18n-ph="jou.newPh"><button class="mbtn" type="submit" data-i18n="common.log2">Log</button></form>
      <input class="tv-search" id="jou-search" placeholder="Search the journal..." data-i18n-ph="jou.search" autocomplete="off">
      <div id="joulist"></div>
    </div>
    <div id="subview">
      <div class="tv-h" data-i18n="sub.h">Subscriptions</div>
      <form id="subform" class="tv-form"><input id="sub-amt" placeholder="Amount" style="width:100px;flex:none" data-i18n-ph="common.amount2"><input id="sub-desc" placeholder="e.g. Netflix" data-i18n-ph="sub.descPh"><input id="sub-day" type="number" min="1" max="28" value="1" title="day of month" data-i18n-title="sub.dayPh" style="width:70px;flex:none"><button class="mbtn" type="submit" data-i18n="common.save3">Save</button></form>
      <input class="tv-search" id="sub-search" placeholder="Search subscriptions..." data-i18n-ph="sub.search" autocomplete="off">
      <div id="sublist"></div>
    </div>
    <div id="orcview">
      <div class="tv-h" data-i18n="orc.h">Budgets</div>
      <form id="orcform" class="tv-form"><input id="orc-cat" placeholder="Category (e.g. food)" data-i18n-ph="orc.catPh"><input id="orc-amt" placeholder="Limit/month" style="width:130px;flex:none" data-i18n-ph="orc.limitPh"><button class="mbtn" type="submit" data-i18n="orc.set">Set</button></form>
      <input class="tv-search" id="orc-search" placeholder="Search budgets..." data-i18n-ph="orc.search" autocomplete="off">
      <div id="orclist"></div>
    </div>
    <div id="monview">
      <div class="tv-h" data-i18n="mon.h">Web monitors</div>
      <form id="monform" class="tv-form"><input id="mon-url" placeholder="https://... (page to watch)" data-i18n-ph="mon.urlPh"><input id="mon-kw" placeholder="keyword (optional)" style="width:160px;flex:none" data-i18n-ph="mon.kwPh"><button class="mbtn" type="submit" data-i18n="mon.watch">Watch</button></form>
      <input class="tv-search" id="mon-search" placeholder="Search monitors..." data-i18n-ph="mon.search" autocomplete="off">
      <div id="monlist"></div>
    </div>
    <div id="actview">
      <div class="tv-h" data-i18n="act.h">Activity history</div>
      <div class="tv-form" style="align-items:center">
        <select id="act-cat" class="tv-search" style="max-width:260px"><option value="" data-i18n="act.allCats">All categories</option></select>
      </div>
      <input class="tv-search" id="act-search" placeholder="Search history..." data-i18n-ph="act.search" autocomplete="off">
      <div id="actlist"></div>
    </div>
    <div id="mapview">
      <div class="tv-h" data-i18n="map.h">Map · you and what's nearby</div>
      <div id="map-status" class="eyebrow" style="margin:0 2px 8px" data-i18n="map.statusInit">tap "Where am I" to locate your device</div>
      <div id="map-chips" class="mchips"></div>
      <div class="tv-form" style="margin:6px 0 10px;gap:8px;flex-wrap:wrap">
        <input class="tv-search" id="map-q" placeholder="Search nearby: bakery, pharmacy..." data-i18n-ph="map.searchPh" autocomplete="off" style="flex:1;min-width:170px">
        <button class="mchip" id="map-fix" type="button"><i data-lucide="crosshair"></i><span data-i18n="map.fix">Fix location</span></button>
        <button class="mchip" id="map-mine" type="button"><i data-lucide="star"></i><span data-i18n="map.mine">My places</span></button>
        <button class="mchip" id="map-plan" type="button"><i data-lucide="route"></i><span data-i18n="map.plan">Time A→B</span></button>
        <button class="mchip" id="map-addr" type="button"><i data-lucide="search"></i><span data-i18n="map.addr">Add address</span></button>
        <button class="mchip" id="map-add" type="button"><i data-lucide="map-pin"></i><span data-i18n="map.add">Add place</span></button>
        <button class="mchip" id="map-sat" type="button"><i data-lucide="satellite"></i><span data-i18n="map.sat">Satellite</span></button>
        <button class="mchip" id="map-street" type="button"><i data-lucide="eye"></i><span data-i18n="map.street">Street view</span></button>
        <button class="mchip" id="map-gmaps" type="button"><i data-lucide="external-link"></i><span data-i18n="map.gmaps">Open in Google Maps</span></button>
        <button class="mchip" id="map-ask" type="button"><i data-lucide="message-circle"></i><span data-i18n="map.ask">Ask E.V.</span></button>
      </div>
      <div id="map-planner" style="display:none;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 10px">
        <span class="eyebrow" style="margin:0" data-i18n="map.from">From</span><select id="plan-from" class="tv-search" style="max-width:190px"></select>
        <span class="eyebrow" style="margin:0" data-i18n="map.to">to</span><select id="plan-to" class="tv-search" style="max-width:190px"></select>
        <button class="mchip" id="plan-go" type="button"><i data-lucide="clock"></i><span data-i18n="map.showTime">Show time</span></button>
      </div>
      <div id="map-wrap"><div id="map"></div><div id="map-results"></div><div id="map-route"></div></div>
    </div>
    <div id="brainview">
      <div class="tv-h" data-i18n="brain.h">Brain · everything E.V. knows</div>
      <div class="tv-form" style="align-items:center;gap:10px">
        <span class="eyebrow" id="brain-count" style="margin:0"></span>
        <button class="mchip" id="brain-reset" type="button"><i data-lucide="focus"></i><span data-i18n="brain.recenter">Recenter</span></button>
      </div>
      <div id="brain-wrap">
        <canvas id="brain-canvas"></canvas>
        <div id="brain-labels"></div>
        <span class="brain-corner tl"></span><span class="brain-corner tr"></span><span class="brain-corner bl"></span><span class="brain-corner br"></span>
        <div id="brain-tip"></div>
        <div id="brain-menu"></div>
      </div>
    </div>
    <div id="locview">
      <div class="tv-h" data-i18n="loc.h">Local executor · runs on your computer</div>
      <div class="tv-empty" style="margin-bottom:10px" data-i18n="loc.intro">Every task below only runs after you approve it here or on Telegram — E.V. never runs anything on your PC by itself. Browser tasks on WhatsApp/Instagram (🔴 high risk) require a second confirmation before sending/posting anything.</div>
      <div class="tv-cat" data-i18n="loc.confirmsCat">⚠️ High-risk confirmations (action about to happen)</div>
      <div id="loc-confirms"></div>
      <div class="tv-cat" data-i18n="loc.pendingCat">Awaiting approval</div>
      <div id="loc-pending"></div>
      <div class="tv-cat" data-i18n="loc.histCat">History</div>
      <div id="loc-hist"></div>
      <div class="tv-cat" style="margin-top:18px" data-i18n="loc.scriptsCat">Registered scripts (allowlist)</div>
      <form id="locscriptform" class="tv-form"><input id="locs-name" placeholder="Name (e.g. run backup)" data-i18n-ph="loc.scriptNamePh"><input id="locs-cmd" placeholder="Command/path to run" data-i18n-ph="loc.scriptCmdPh"><button class="mbtn" type="submit" data-i18n="loc.register">Register</button></form>
      <div id="loc-scripts"></div>
    </div>
    <div id="chartsview">
      <div class="tv-h" data-i18n="graf.h">Charts · your data</div>
      <div class="tv-form" style="gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px">
        <select id="ch-period" class="tv-search" style="max-width:190px">
          <option value="month" data-i18n="graf.pMonth">This month</option>
          <option value="30" data-i18n="graf.p30">Last 30 days</option>
          <option value="90" data-i18n="graf.p90">Last 3 months</option>
          <option value="180" data-i18n="graf.p180">Last 6 months</option>
          <option value="year" data-i18n="graf.pYear">This year</option>
          <option value="custom" data-i18n="graf.pCustom">Custom</option>
        </select>
        <input type="date" id="ch-from" class="tv-search" style="max-width:160px;display:none">
        <input type="date" id="ch-to" class="tv-search" style="max-width:160px;display:none">
        <span class="eyebrow" id="ch-range" style="margin:0"></span>
      </div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.expCat">Expenses by category</div><canvas id="ch-cat"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.expPeriod">Expenses over the period</div><canvas id="ch-day"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.habits">Habits (days checked in the period)</div><canvas id="ch-hab"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.interactions">Interactions over time</div><canvas id="ch-int"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.provUse">AI provider usage</div><canvas id="ch-prov"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.actType">Activity by type</div><canvas id="ch-act"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.tasksCC">Tasks: created vs completed</div><canvas id="ch-task"></canvas></div>
      <div class="chart-card"><div class="chart-t" data-i18n="graf.memGrowth">Memory growth</div><canvas id="ch-mem"></canvas></div>
    </div>
    <div id="pageview"></div>
    <div id="climaview">
      <div class="tv-form" style="gap:8px;margin-bottom:14px;flex-wrap:wrap">
        <input id="wx-city" class="tv-search" placeholder="city (e.g. Sao Paulo)" data-i18n-ph="clima.cityPh" style="max-width:260px">
        <button class="mchip" id="wx-go" type="button"><i data-lucide="search"></i><span data-i18n="clima.view">View</span></button>
      </div>
      <div id="wx-body"></div>
    </div>
    <div id="musicview">
      <div class="tv-h" data-i18n="mus.h">Music · Spotify</div>
      <div id="sp-section" style="max-width:760px;margin-bottom:16px"></div>
      <div class="eyebrow" style="margin:-8px 0 12px" data-i18n="mus.paste">Or paste a Spotify playlist/track/album link (embedded player, no Premium):</div>
      <div class="tv-form" style="gap:8px;flex-wrap:wrap;margin-bottom:12px">
        <input class="tv-search" id="mu-url" placeholder="https://open.spotify.com/playlist/..." style="flex:1;min-width:200px">
        <input class="tv-search" id="mu-label" placeholder="nickname (optional)" data-i18n-ph="mus.nickPh" style="max-width:170px">
        <button class="mchip" id="mu-add" type="button"><i data-lucide="plus"></i><span data-i18n="common.add2">Add</span></button>
      </div>
      <div id="mu-player"></div>
      <div id="mu-list"></div>
    </div>
    <div id="metasview">
      <div class="tv-h" data-i18n="metas.h">Goals · piggy bank</div>
      <div class="tv-form" style="gap:8px;flex-wrap:wrap;margin-bottom:14px">
        <input class="tv-search" id="gl-name" placeholder="goal name (e.g. Trip)" data-i18n-ph="metas.namePh" style="max-width:240px">
        <input class="tv-search" id="gl-target" type="number" placeholder="target amount (R$)" data-i18n-ph="metas.targetPh" style="max-width:160px">
        <button class="mchip" id="gl-add" type="button"><i data-lucide="target"></i><span data-i18n="metas.create">Create goal</span></button>
      </div>
      <div id="gl-list"></div>
    </div>
    <div id="saudeview">
      <div class="tv-h" data-i18n="saude.h">Health & routine</div>
      <div id="sa-body"></div>
    </div>
    <div id="cofreview">
      <div class="tv-h" data-i18n="cofre.h">Document vault</div>
      <div class="eyebrow" style="margin:-8px 0 12px" data-i18n="cofre.sub">Stored encrypted in your database. Images become searchable text (OCR).</div>
      <div class="tv-form" style="gap:8px;flex-wrap:wrap;margin-bottom:12px">
        <input class="tv-search" id="cf-q" placeholder="search by name or text..." data-i18n-ph="cofre.search" style="flex:1;min-width:180px">
        <label class="mchip" for="cf-file" style="cursor:pointer"><i data-lucide="upload"></i><span data-i18n="cofre.upload">Upload document</span></label>
        <input id="cf-file" type="file" style="display:none">
      </div>
      <div id="cf-list"></div>
    </div>
    <div id="inicioview">
      <div id="ov-grid" class="ov-grid"></div>
    </div>
    <div id="painelview">
      <div class="tv-h" data-i18n="painel.h">Panel · astronomy & world</div>
      <div class="rd-grid">
        <div class="rd-half"><div class="pd-t" data-i18n="painel.astro">☾ Astronomy</div><div id="pd-astro"></div></div>
        <div class="rd-half"><div class="pd-t" data-i18n="painel.radar">◎ World radar</div><div id="pd-radar"></div></div>
        <div class="rd-full"><div class="pd-t" data-i18n="painel.backup">⛁ Backup</div><div id="pd-backup"></div></div>
      </div>
    </div>
  </main>
  <aside id="right" class="rail">
    <div class="eyebrow" data-i18n="right.system">System <span class="mini" id="edit-stats" data-i18n="common.edit">edit</span></div>
    <div id="stats"></div>
    <div class="eyebrow" data-i18n="right.quickActions">Quick actions <span class="mini" id="edit-acts" data-i18n="common.edit2">edit</span></div>
    <div class="grid2" id="acts"></div>
    <div class="eyebrow" data-i18n="right.pages">Pages <span class="mini" id="new-page" data-i18n="right.newPage">+ new</span></div>
    <div id="pages-nav"></div>
    <div class="eyebrow" data-i18n="right.aiProvider">AI provider</div>
    <select id="prov"><option>auto</option><option>gemini</option><option>groq</option><option>openrouter</option><option>ollama</option></select>
    <button class="act" id="btn-voice" style="margin-top:12px;width:100%"><i data-lucide="mic-vocal"></i><span data-i18n="right.voice">E.V.'s voice</span></button>
    <button class="act" id="btn-conn" style="margin-top:8px;width:100%"><i data-lucide="plug-zap"></i><span data-i18n="right.connectors">API connectors</span></button>
    <button class="act" id="btn-keys" style="margin-top:8px;width:100%"><i data-lucide="key-round"></i><span data-i18n="right.keys">API keys</span></button>
    <button class="act" id="btn-term" style="margin-top:8px;width:100%"><i data-lucide="square-terminal"></i><span data-i18n="right.term">Action terminal</span></button>
    <button class="act" id="btn-notifs" style="margin-top:8px;width:100%"><i data-lucide="bell"></i><span data-i18n="right.notifs">Notifications</span><span id="notif-badge" class="nbadge"></span></button>
  </aside>
</div>
<div id="mbackdrop"></div>
<button id="qc-fab" title="Quick capture (Ctrl/Cmd+J)" data-i18n-title="fab.quickCapture"><i data-lucide="zap"></i></button>
<div id="vc">
  <button id="vc-x" data-i18n="common.close">CLOSE</button>
  <div id="vc-orb"><canvas id="vc-viz" width="480" height="480"></canvas><div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div></div>
  <div id="vc-txt" data-i18n="vc.tapMic">Tap the microphone and speak.</div>
  <div id="vc-sub" data-i18n="vc.sub">live voice</div>
  <div id="vc-actions"><button class="vcbtn" id="vc-mic"><i data-lucide="mic"></i></button></div>
  <button id="vc-cont" class="tbtn" style="margin-top:14px"><i data-lucide="infinity"></i> <span data-i18n="vc.cont">Continuous mode: off</span></button>
  <button id="vc-convo" class="tbtn" style="margin-top:8px"><i data-lucide="messages-square"></i> <span data-i18n="vc.convo">Conversation: off</span></button>
</div>
<div id="serfx"></div>
<div id="np-mini">
  <div class="npm-top">
    <img id="npm-art" alt="">
    <div class="npm-i" title="Open Music" data-i18n-title="np.open"><div class="npm-t"></div><div class="npm-a"></div></div>
    <div class="npm-c">
      <button id="npm-prev" title="Previous" data-i18n-title="np.prev"></button>
      <button id="npm-tog" title="Play/Pause" data-i18n-title="np.tog"></button>
      <button id="npm-next" title="Next" data-i18n-title="np.next"></button>
    </div>
  </div>
  <div id="npm-bar" title="Drag to seek" data-i18n-title="np.seek"><i></i></div>
</div>
<nav id="bnav">
  <button data-view="inicio"><i data-lucide="layout-dashboard"></i><span data-i18n="bnav.home">Home</span></button>
  <button data-view="chat"><i data-lucide="message-square"></i><span data-i18n="bnav.chat">Chat</span></button>
  <button data-view="tasks"><i data-lucide="list-checks"></i><span data-i18n="bnav.tasks">Tasks</span></button>
  <button data-view="exp"><i data-lucide="wallet"></i><span data-i18n="bnav.exp">Expenses</span></button>
  <button id="bnav-more"><i data-lucide="menu"></i><span data-i18n="bnav.more">More</span></button>
</nav>
<div id="cam">
  <button id="cam-x" data-i18n="common.close2">CLOSE</button>
  <div id="cam-stage"><video id="cam-video" autoplay playsinline muted></video><canvas id="cam-fx"></canvas></div>
  <div id="cam-result"></div>
  <div id="cam-hint" data-i18n="cam.hint">Point the camera. Tap capture, "what is this?", or turn on live mode.</div>
  <div id="cam-actions">
    <button class="vcbtn" id="cam-flip" title="Switch camera" data-i18n-title="cam.flip"><i data-lucide="refresh-cw"></i></button>
    <button class="vcbtn" id="cam-live" title="Live (marks faces + narrates)" data-i18n-title="cam.live"><i data-lucide="scan-eye"></i></button>
    <button class="vcbtn" id="cam-what" title="What is this?" data-i18n-title="cam.what"><i data-lucide="search"></i></button>
    <button class="vcbtn" id="cam-tr" title="Translate the text" data-i18n-title="cam.tr"><i data-lucide="languages"></i></button>
    <button class="vcbtn" id="cam-food" title="Food calories" data-i18n-title="cam.food"><i data-lucide="utensils"></i></button>
    <button class="vcbtn" id="cam-qr" title="Read QR / barcode" data-i18n-title="cam.qr"><i data-lucide="qr-code"></i></button>
    <button class="vcbtn" id="cam-scan" title="Scan document to the base" data-i18n-title="cam.scan"><i data-lucide="scan-line"></i></button>
    <button class="vcbtn" id="cam-face" title="Who am I? (recognizes only you — hold to erase)" data-i18n-title="cam.face"><i data-lucide="user-round-check"></i></button>
    <button class="vcbtn" id="cam-shot" title="Capture and ask in chat" data-i18n-title="cam.shot"><i data-lucide="camera"></i></button>
  </div>
</div>
<div id="street">
  <button id="street-x" data-i18n="common.close3">CLOSE</button>
  <div id="street-view"></div>
  <div id="street-hint" data-i18n="street.loading">Loading the street…</div>
</div>
<div id="pomo">
  <button id="pomo-x" data-i18n="common.close4">CLOSE</button>
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="pomo-timebox"><div id="pomo-time">25:00</div><div id="pomo-label" data-i18n="pomo.focus">Focus</div></div>
  <div id="pomo-ctl"><button data-m="-5">−5</button><button id="pomo-toggle"><i data-lucide="play"></i></button><button data-m="5">+5</button><button id="pomo-reset" data-i18n="pomo.reset">reset</button></div>
  <div id="pomo-presets"><button data-set="15">15 min</button><button data-set="25">25 min</button><button data-set="50">50 min</button></div>
  <button id="pomo-pip" data-i18n="pomo.min">⧉ minimize</button>
</div>
<div id="pomo-mini">
  <div class="pm-head"><span class="pm-grip">⋮⋮</span><span style="flex:1"></span><button class="pm-btn" id="pm-open" title="expand" data-i18n-title="pm.expand">⤢</button><button class="pm-btn" id="pm-close" title="close" data-i18n-title="pm.close">✕</button></div>
  <div class="pm-body"></div>
</div>
<div id="modal"></div>
<div id="cmdk"><div class="ck-card"><input id="ck-input" placeholder="Search action or command...  (Esc to close)" data-i18n-ph="ck.ph" autocomplete="off"><div id="ck-list"></div></div></div>
<div id="login">
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div class="brand" style="text-align:center"><div class="name" style="font-size:38px">E.V.</div><div class="eyebrow">Personal Intelligence</div></div>
  <input id="login-token" type="password" placeholder="Access token" data-i18n-ph="login.tokenPh" autocomplete="off">
  <button id="login-btn" class="mbtn" data-i18n="login.enter">Enter</button>
  <div class="login-or"><span></span><span data-i18n="login.or">or</span><span></span></div>
  <a id="login-google" class="mbtn2 login-oauth" href="/auth/google" data-i18n="login.google">Sign in with Google</a>
  <a id="login-github" class="mbtn2 login-oauth" href="/auth/github" data-i18n="login.github">Sign in with GitHub</a>
  <div id="login-err"></div>
</div>
<div id="welcome">
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="welcome-txt"></div>
</div>
<div id="standby">
  <div class="sb-top">E.V. // <b>ONLINE</b></div>
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="sb-clock">--:--:--</div>
  <div id="sb-date"></div>
  <div id="sb-status"></div>
  <div class="sb-load"><i></i></div>
  <div class="sb-hint" data-i18n="standby.hint">tap or speak to resume</div>
</div>
<script>

// --- i18n (English default + Portuguese) ---
const I18N={en:{'state.idle':'standby','side.conversations':'Conversations','side.newfolder':'+ new folder','sys.provider':'PROVIDER','sys.model':'MODEL','sys.latency':'LATENCY','sys.time':'TIME','top.togLeft':'Hide/show folders','top.tabsPrev':'Scroll tabs left','top.tabsNext':'Scroll tabs right','top.goto':'Go to','top.focusBadge':'Focus mode on — click to turn off','top.focusLbl':'FOCUS MODE','top.search':'Search everything','top.talk':'Talk','top.talkLbl':'TALK','top.ambient':'Ambient presence — always listens for "E.V. ..."','top.ambientLbl':'AMBIENT','top.terminal':'Terminal mode','top.terminalLbl':'TERMINAL','top.voice':'E.V.\'s voice','top.voiceLbl':'VOICE','top.sfx':'Interface sounds','top.theme':'Pick a color theme','top.togRight':'Hide/show panel','top.zen':'Clean mode (hide panels)','top.lang':'Language','chat.attach':'Attach','chat.mic':'Talk','chat.img':'Send image','chat.cam':'Live camera','chat.input':'Talk to E.V.  ·  type / for commands','chat.send':'Send','tasks.h':'Tasks','tasks.new':'New task...','common.categoryPh':'category','tasks.duePh':'Due date (optional)','common.repeat':'Repeat','recur.once':'Once','recur.daily':'Daily','recur.weekly':'Weekly','recur.monthly':'Monthly','common.add':'Add','tasks.search':'Search tasks...','kb.h':'Knowledge base','kb.urlPh':'https://...  (index a page)','kb.indexUrl':'Index URL','kb.upload':'⬱ Upload file (PDF / Word / txt)','kb.notePh':'Note title','kb.textPh':'Paste text for E.V. to learn and answer from...','kb.addText':'Add text','kb.search':'Search the base...','kb.indexed':'Indexed documents','exp.h':'Expenses','common.amount':'Amount','common.description':'Description','common.categoryPh2':'category','common.log':'Log','exp.search':'Search expenses...','exp.last60':'Last 60 days','rem.h':'Reminders','rem.newPh':'Remind me to...','common.repeat2':'Repeat','recur.once2':'Once','recur.daily2':'Daily','recur.weekly2':'Weekly','recur.monthly2':'Monthly','common.create':'Create','rem.search':'Search reminders...','rem.open':'Open','cal.email':'Send email','cal.msg':'Telegram message','mem.h':'Memories','mem.newPh':'Something E.V. should remember about you...','common.save':'Save','mem.search':'Search the brain...','mem.knows':'What E.V. knows','mem.forgetAll':'forget all','lnk.h':'Links','common.name':'Name','common.categoryPh3':'category','common.save2':'Save','lnk.search':'Search links...','hab.h':'Habits','hab.newPh':'New habit (e.g. workout)','common.create2':'Create','hab.search':'Search habits...','jou.h':'Journal','jou.newPh':'How was your day?','common.log2':'Log','jou.search':'Search the journal...','sub.h':'Subscriptions','common.amount2':'Amount','sub.descPh':'e.g. Netflix','sub.dayPh':'day of month','common.save3':'Save','sub.search':'Search subscriptions...','orc.h':'Budgets','orc.catPh':'Category (e.g. food)','orc.limitPh':'Limit/month','orc.set':'Set','orc.search':'Search budgets...','mon.h':'Web monitors','mon.urlPh':'https://... (page to watch)','mon.kwPh':'keyword (optional)','mon.watch':'Watch','mon.search':'Search monitors...','act.h':'Activity history','act.allCats':'All categories','act.search':'Search history...','map.h':'Map · you and what\'s nearby','map.statusInit':'tap "Where am I" to locate your device','map.searchPh':'Search nearby: bakery, pharmacy...','map.fix':'Fix location','map.mine':'My places','map.plan':'Time A→B','map.addr':'Add address','map.add':'Add place','map.sat':'Satellite','map.street':'Street view','map.gmaps':'Open in Google Maps','map.ask':'Ask E.V.','map.from':'From','map.to':'to','map.showTime':'Show time','brain.h':'Brain · everything E.V. knows','brain.recenter':'Recenter','loc.h':'Local executor · runs on your computer','loc.intro':'Every task below only runs after you approve it here or on Telegram — E.V. never runs anything on your PC by itself. Browser tasks on WhatsApp/Instagram (🔴 high risk) require a second confirmation before sending/posting anything.','loc.confirmsCat':'⚠️ High-risk confirmations (action about to happen)','loc.pendingCat':'Awaiting approval','loc.histCat':'History','loc.scriptsCat':'Registered scripts (allowlist)','loc.scriptNamePh':'Name (e.g. run backup)','loc.scriptCmdPh':'Command/path to run','loc.register':'Register','graf.h':'Charts · your data','graf.pMonth':'This month','graf.p30':'Last 30 days','graf.p90':'Last 3 months','graf.p180':'Last 6 months','graf.pYear':'This year','graf.pCustom':'Custom','graf.expCat':'Expenses by category','graf.expPeriod':'Expenses over the period','graf.habits':'Habits (days checked in the period)','graf.interactions':'Interactions over time','graf.provUse':'AI provider usage','graf.actType':'Activity by type','graf.tasksCC':'Tasks: created vs completed','graf.memGrowth':'Memory growth','clima.cityPh':'city (e.g. Sao Paulo)','clima.view':'View','mus.h':'Music · Spotify','mus.paste':'Or paste a Spotify playlist/track/album link (embedded player, no Premium):','mus.nickPh':'nickname (optional)','common.add2':'Add','metas.h':'Goals · piggy bank','metas.namePh':'goal name (e.g. Trip)','metas.targetPh':'target amount (R$)','metas.create':'Create goal','saude.h':'Health & routine','cofre.h':'Document vault','cofre.sub':'Stored encrypted in your database. Images become searchable text (OCR).','cofre.search':'search by name or text...','cofre.upload':'Upload document','painel.h':'Panel · astronomy & world','painel.astro':'☾ Astronomy','painel.radar':'◎ World radar','painel.backup':'⛁ Backup','right.system':'System','common.edit':'edit','right.quickActions':'Quick actions','common.edit2':'edit','right.pages':'Pages','right.newPage':'+ new','right.aiProvider':'AI provider','right.voice':'E.V.\'s voice','right.connectors':'API connectors','right.keys':'API keys','right.term':'Action terminal','right.notifs':'Notifications','fab.quickCapture':'Quick capture (Ctrl/Cmd+J)','common.close':'CLOSE','vc.tapMic':'Tap the microphone and speak.','vc.sub':'live voice','vc.cont':'Continuous mode: off','vc.convo':'Conversation: off','np.open':'Open Music','np.prev':'Previous','np.tog':'Play/Pause','np.next':'Next','np.seek':'Drag to seek','bnav.home':'Home','bnav.chat':'Chat','bnav.tasks':'Tasks','bnav.exp':'Expenses','bnav.more':'More','common.close2':'CLOSE','cam.hint':'Point the camera. Tap capture, "what is this?", or turn on live mode.','cam.flip':'Switch camera','cam.live':'Live (marks faces + narrates)','cam.what':'What is this?','cam.tr':'Translate the text','cam.food':'Food calories','cam.qr':'Read QR / barcode','cam.scan':'Scan document to the base','cam.face':'Who am I? (recognizes only you — hold to erase)','cam.shot':'Capture and ask in chat','common.close3':'CLOSE','street.loading':'Loading the street…','common.close4':'CLOSE','pomo.focus':'Focus','pomo.reset':'reset','pomo.min':'⧉ minimize','pm.expand':'expand','pm.close':'close','ck.ph':'Search action or command...  (Esc to close)','login.tokenPh':'Access token','login.enter':'Enter','login.or':'or','login.google':'Sign in with Google','login.github':'Sign in with GitHub','standby.hint':'tap or speak to resume','state.listening':'listening','state.thinking':'thinking','state.speaking':'speaking','status.online':'ONLINE','status.reconnecting':'RECONNECTING','view.chat':'Chat','view.inicio':'Home','view.tasks':'Tasks','view.exp':'Expenses','view.rem':'Reminders','view.cal':'Calendar','view.mem':'Memories','view.lnk':'Links','view.hab':'Habits','view.jou':'Journal','view.sub':'Subscriptions','view.orc':'Budgets','view.mon':'Monitors','view.act':'History','view.kb':'Base','view.map':'Map','view.brain':'Brain','view.graf':'Charts','view.musica':'Music','view.clima':'Weather','view.metas':'Goals','view.saude':'Health','view.cofre':'Vault','view.painel':'Panel','view.loc':'Local executor','grp.main':'Main','grp.productivity':'Productivity','grp.finance':'Finance','grp.knowledge':'Knowledge','grp.explore':'Explore','grp.automation':'Automation','tabs.pick':'Choose tabs','tabs.pickTitle':'Top tabs','tabs.pickSub':'Choose which tabs appear at the top.','common.cancel':'Cancel','common.save4':'Save','common.closeBtn':'Close','common.confirm':'Confirm','common.delete':'Delete','cat.inicio':'Home','cat.plano':'Day plan','cat.pendencias':'Pending','cat.padroes':'Patterns','cat.automacoes':'Automations','cat.bak':'Backup','cat.tarefas':'Tasks','cat.lembretes':'Reminders','cat.gastos':'Expenses','cat.memorias':'Memories','cat.kb':'Base','cat.map':'Map','cat.graf':'Charts','cat.brain':'Brain','cat.musica':'Music','cat.metas':'Goals','cat.saude':'Health','cat.cofre':'Vault','cat.painel':'Panel','cat.cam':'Camera','cat.buscar':'Web search','cat.noticias':'News','cat.clima':'Weather','cat.relatorio':'Report','cat.status':'Status','cat.semana':'Week','cat.foco':'Pomodoro','cat.procurar':'Find','cat.calendario':'Calendar','cat.habitos':'Habits','cat.diario':'Journal','cat.orcamentos':'Budgets','cat.assinaturas':'Subscriptions','cat.dados':'My data','cat.insights':'Insights','cat.quiz':'Quiz','sm.tasks':'Tasks','sm.reminders':'Reminders','sm.expenses':'Expenses · month','sm.memories':'Memories','sm.kb':'Base','sm.kbfiles':'Files','sm.links':'Links','sm.habits':'Habits','sm.journal':'Journal','sm.subscriptions':'Subscriptions','sm.budgets':'Budgets','sm.watches':'Monitors','sm.agenda':'Agenda · 7d','sm.activity':'History · 24h','sm.provider':'Provider','sm.model':'Model','sm.disk':'Disk','sm.ram':'RAM','sm.uptime':'Uptime','menu.gView':'View','menu.gCreate':'Create','menu.gTools':'Tools','menu.gSettings':'Settings','menu.emails':'E-mails','menu.task':'Task','menu.reminder':'Reminder','menu.expense':'Expense','menu.event':'Event','menu.email':'E-mail','menu.link':'Link','menu.kbnote':'Base note','menu.summarize':'Summarize link','menu.provider':'Provider','menu.mute':'Mute','menu.help':'Help','cat.map0':'Links','menu.header':'Menu — tap to open or fill','cal.repeatEv':'Repeat (E.V. only)','chart.you':'You','chart.created':'Created','chart.completed':'Completed','chart.memories':'Memories','empty.notifT':'No notifications','empty.notifH':'Reminders and alerts show up here.','empty.goalsT':'No goals yet','empty.goalsH':'Create one above.','empty.vaultT':'No documents','empty.vaultH':'Upload one above.','empty.musicT':'No saved music','empty.musicH':'Paste a Spotify link above.','empty.actT':'Nothing logged yet','empty.actH':'Your actions (create, complete, delete) show up here — from Telegram and the web.','empty.subT':'No subscriptions','empty.subH':'Add one to track due dates.','empty.orcT':'No budgets set','empty.orcH':'Set a monthly limit per category.','empty.monT':'No monitors','empty.monH':'Create one to track prices or pages.','empty.locConfT':'Nothing awaiting confirmation','empty.locConfH':'High-risk actions (WhatsApp/Instagram) pause here before sending/posting.','empty.locPendT':'Nothing pending','empty.locPendH':'When E.V. asks to run something on your PC, it shows up here.','empty.locHistT':'No history yet','empty.locHistH':'Approved/rejected tasks show up here.','empty.locScrT':'No registered scripts','empty.locScrH':'Register one above so E.V. can run it by name.','empty.lnkT':'No saved links','empty.lnkH':'Paste a URL above to save it.','empty.habT':'No habits','empty.habH':'Create one above.','empty.jouT':'Empty journal','empty.jouH':'Write your first entry above.','empty.expT':'No expenses logged','empty.expH':'Add an expense above.','empty.remT':'No open reminders','empty.remH':'Create one above.','empty.memT':'Empty brain','empty.memH':'Add above, or tell E.V. what to remember.','empty.kbT':'Nothing in the base yet','empty.kbH':'Add a URL, file or text above.','empty.tasksT':'No open tasks','empty.tasksH':'Create one above.','modal.connectors':'API connectors','modal.voice':'E.V.\'s voice','modal.notifs':'Notifications','modal.gevent':'Google event','form.keys':'API keys','form.quickCap':'Quick capture','form.renameFolder':'Rename folder','form.newFolder':'New folder','form.editSub':'Edit subscription','form.editMon':'Edit monitor','form.editLink':'Edit link','form.renameHab':'Rename habit','form.editEntry':'Edit entry','form.editEvent':'Edit event','form.editExp':'Edit expense','form.editRem':'Edit reminder','form.editTask':'Edit task','form.indexPage':'Index page','form.nameFile':'Name file','form.sendEmail':'Send email','form.tgMsg':'Message to my Telegram','form.searchAll':'Search everything','mobile.menu':'Menu','pick.actsSub':'Choose the panel shortcuts.','pick.statsSub':'Choose which indicators are shown.','ov.customize':'Customize Home','ov.customizeSub':'Choose which cards appear on your panel.','form.newSubfolder':'New subfolder in','form.editBudget':'Edit budget','form.newEvent':'New event','cal.eventsOn':'Events','page.edit':'Edit page','page.new':'New page','field.name':'Name','field.url':'URL','field.category':'Category','field.description':'Description','field.amountRs':'Amount (R$)','field.text':'Text','field.time':'Time','field.event':'Event','field.dayOfMonth':'Day of month','field.monthlyRs':'Monthly amount (R$)','field.keyword':'Keyword','field.newName':'New name','field.folderPh':'e.g. projects','field.remindOf':'Remind me to','field.whenIso':'When (YYYY-MM-DDTHH:MM)','field.where':'Where','field.evReminder':'E.V. reminder','field.dateIso':'Date (YYYY-MM-DD)','field.dueOpt':'Due date (optional)','field.catPh':'e.g. college','field.to':'To','field.subject':'Subject','field.message':'Message','field.tgPh':'text delivered to your Telegram','field.nameId':'Name (to identify)','field.search':'Search','field.searchAllPh':'tasks, expenses, memories, base...','form.qcLabel':'What do you want to save? (task, reminder, expense, note…)','form.qcPh':'e.g. buy milk · meeting at 3pm tomorrow · spent 40 at the market','toast.backupDl':'Downloading encrypted backup…','toast.capturing':'Capturing…','toast.captured':'Captured.','toast.captureFail':'Couldn\'t capture. Try again.','toast.backupOk':'Backup created.','toast.backupErr':'Failed to create backup.','panel.backupNow':'Back up now','panel.generating':'Generating…','panel.last':'Last','panel.noBackup':'No backup yet','panel.encBackups':'Encrypted backups','ov.syncing':'Syncing systems…','ov.loadFail':'Couldn\'t load the panel.','ov.personalize':'Customize','ov.morning':'Good morning','ov.afternoon':'Good afternoon','ov.evening':'Good evening','ov.greetFallback':'Systems online. All set for you.','ov.askPh':'Ask E.V…','ov.send':'Send','ov.talkEv':'Talk to E.V.','ov.tSystem':'SYSTEM','ov.tAI':'AI','ov.tModel':'MODEL','ov.tMemories':'MEMORIES','ov.tAlerts':'ALERTS','ov.sgSummary':'Day summary','ov.sgToday':'What do I have today?','ov.sgExpenses':'This month\'s expenses','ov.sgWeather':'Weather','ov.tasksToday':'Today\'s tasks','ov.open':'open','ov.nothingPending':'Nothing pending. 🎉','ov.newTask':'New task…','ov.habitsToday':'Today\'s habits','ov.noHabits':'No habits yet — create one in the Habits tab.','ov.healthWater':'Health & water','ov.cup':'cup','ov.sleep':'Sleep','ov.mood':'Mood','ov.noReminders':'No active reminders.','ov.newReminder':'new reminder','ov.top':'top','ov.quickExp':'+ quick expense: 50 uber #transport','ov.quickExpHint':'enter an amount, e.g. 50 uber #transport','ov.weatherNow':'Weather now','ov.loadingForecast':'loading forecast','wx.hi':'high','wx.lo':'low','ov.agendaToday':'Today\'s agenda','ov.events':'events','ov.agendaTap':'Tap to see the full agenda','ov.agendaConnect':'Connect Google Calendar in API keys','ov.recentAct':'Recent activity','ov.noActivity':'Nothing logged yet. Your actions show up here.','ov.nowPlaying':'Now playing','ov.loading':'loading…','painel.astro2':'Astronomy','ov.loadingShort':'loading','ov.waxing':'waxing','ov.waning':'waning','wx.sunrise':'sunrise','wx.sunset':'sunset','ov.rates':'Rates','rate.usd':'Dollar','rate.eur':'Euro','rate.btc':'Bitcoin','ov.unavailNow':'unavailable right now','chip.memories':'memories','chip.sources':'sources','chip.links':'links','chip.journal':'journal','chip.places':'places','chip.subs':'subscriptions','chip.autos':'automations','ov.spConfig':'Configure Spotify in API keys to listen here.','ov.spConnect':'Connect Spotify','ov.nothingPlaying':'Nothing playing','ck.actionTerm':'E.V. action terminal','ck.liveVoice':'Live voice','ck.focusToggle':'Focus mode (toggle)','ck.go':'go','ck.open':'open','ck.content':'content','wx.fail':'couldn\'t get the weather.','wx.feels':'feels like','wx.nextHours':'Next hours','wx.tenDay':'10-day forecast','wx.uvLow':'low','wx.uvMod':'moderate','wx.uvHigh':'high','wx.uvVHigh':'very high','wx.uvExtreme':'extreme','wx.rainChance':'Chance of rain','wx.upTo':'up to','wx.throughDay':'through the day','wx.wind':'Wind','wx.gusts':'gusts','wx.humidity':'Humidity','wx.uvIndex':'UV index','wx.maxToday':'max today','wx.sun':'Sun','wx.feelsC':'Feels like','wx.realTemp':'real temperature','wx.cloud':'Cloudiness','wx.pressure':'Pressure','act.taskNew':'task created','act.taskDone':'task completed','act.taskDel':'task deleted','act.remNew':'reminder created','act.remDone':'reminder fired','act.remCancel':'reminder canceled','act.expNew':'expense added','act.expDel':'expense deleted','act.habDone':'habit done','loc.kScript':'script','loc.kOpen':'open','loc.kBrowser':'browser','loc.kShell':'shell','loc.sPending':'awaiting approval','loc.sApproved':'approved · queued','loc.sRunning':'running','loc.sDone':'done','loc.sFailed':'failed','loc.sRejected':'rejected','loc.highRisk':'🔴 high risk','loc.taskPaused1':'task','loc.taskPaused2':'is paused awaiting this confirmation','loc.approve':'approve','loc.reject':'reject','loc.confirmProceed':'confirm and let it proceed','loc.rejectAction':'reject this action','notif.markAll':'Mark all read','notif.clearRead':'Clear read','notif.activeNow':'active now','page.widgets':'Widgets','conn.savedKeys':'Saved keys','conn.connectors':'Connectors','conn.blurb':'Connect any HTTPS API from the interface — no code. Store the key here and use {{KEY_NAME}} in the URL or headers.','voice.blurb':'Pick a voice and hear a sample. Gemini sounds more natural (a few seconds slower); Edge is faster.','voice.speed':'Speed','voice.pitch':'Pitch','right.noPages':'none yet','chat.folderPrefix':'Folder','chat.startConv':'start the conversation.','confirm.delFolder1':'Delete','confirm.delFolder2':'(and subfolders/chats)? This cannot be undone.','confirm.rmSub':'Remove subscription?','confirm.rmBudget':'Remove budget?','confirm.rmMon':'Remove monitor?','confirm.rmHab':'Delete habit?','confirm.forgetAll':'Forget ALL of E.V.\'s memories? This erases everything she knows about you (does not affect tasks, expenses, etc.).','confirm.rmKb1':'Remove','confirm.rmKb2':'from the base?','confirm.rmGcal':'Delete this event from Google Calendar?','confirm.rmBrain1':'Delete','confirm.rmBrain2':'This really removes the item from E.V.','confirm.rmScript':'Remove script','confirm.logRs':'Log','brain.deleteNode':'Delete from the brain','brain.editNode':'Edit','brain.openNode':'Open','pomo.break':'Break','pomo.cycleDone':'Cycle complete','map.unavail':'Map unavailable (no connection to Leaflet).','painel.astroUnavail':'astronomy unavailable.','painel.radarUnavail':'radar unavailable.','painel.statusUnavail':'status unavailable.','painel.moon':'Moon','painel.waxing':'waxing','painel.waning':'waning','painel.iss':'Space Station (ISS)','painel.clocks':'Clocks','painel.ratesUnavail':'rates unavailable','painel.headlines':'Headlines · TabNews','painel.noHeadlines':'no headlines','wtype.note':'Note','wtype.connector':'Connector','wtype.command':'Command button','wtype.chart':'Expense chart','wtype.spotify':'Spotify (link)','saude.waterToday':'Water today','saude.cups':'cups','saude.lastSleep':'Last night\'s sleep','saude.moodToday':'Today\'s mood','saude.lastDays':'Last days','voice.gemini':'Gemini · more natural','voice.edge':'Edge · faster','voice.listFail':'Couldn\'t list voices right now.','mus.myPlaylists':'My playlists','mus.noPlaylists':'No playlists found.','recur.repeatsPrefix':'repeats','recur.shortDaily':'daily','recur.shortWeekly':'weekly','recur.shortMonthly':'monthly','time.today':'today','time.at':'at','cal.allDay':'all day','cal.creatingGoogle':'Creating on Google…','cal.eventCreated':'Event created on Google Calendar.','cal.createFail':'Failed to create.','cal.eventDeleted':'Event deleted.','cal.deleteFail':'Failed to delete.','hab.doneToday':'done today','hab.markDone':'mark done','hab.daysWord':'days','mem.memoryWord':'memory','mem.memoriesWord':'memories','common.deleteT':'delete','common.openTitle':'open','common.complete':'complete','common.dragReorder':'drag to reorder','common.forgetT':'forget','common.err':'error','common.errPrefix':'error: ','common.test':'Test','folder.subfolder':'subfolder','folder.moveRoot':'move to root','page.notFound':'Page not found.','tasks.none':'No tasks.','receipt.logExpense':'Log as expense','receipt.noValue':'Couldn\'t find an amount on that receipt.','receipt.readFail':'Failed to read the receipt.','keys.updated':'Keys updated: ','voice.updated':'E.V.\'s voice updated','mus.connectMine':'Connect my Spotify','mus.disconnect':'disconnect','mus.cantPlay':'couldn\'t play','sp.playingVia':'Playing through E.V. — lock-screen controls active.','sp.transferFail':'Couldn\'t transfer.','panel.copiesStored':'copy(ies) stored','panel.autoDaily':'· automatic 1x/day','panel.runsAutoDaily':'runs automatically 1x/day (via Telegram)','mail.fillToBody':'Fill in recipient and message.','mail.sending':'Sending email…','mail.sent':'Email sent.','mail.sendFail':'Failed to send.','mail.noConn':'No connection while sending the email.','msg.sent':'Message sent.','msg.sendFail':'Failed to send.','msg.noConn':'No connection while sending the message.','kb.fileNotFound':'File not found.','kb.openFail':'Couldn\'t open the file.','kb.indexing':'indexing…','kb.uploadErr':'upload error','kb.defaultNote':'Note','brain.unavail3d':'3D brain unavailable (no connection to Three.js)','brain.editPrompt':'Edit:','chat.noReply':'(no reply)','img.sendFail':'Failed to send the image.','undo.btn':'Undo','undo.deleted':'deleted','ent.item':'Item','ent.reminder':'Reminder','ent.link':'Link','ent.entry':'Entry','ent.event':'Event','ent.expense':'Expense','ent.memory':'Memory','ent.task':'Task','login.enterToken':'Enter the token.','login.checking':'checking…','login.invalid':'Invalid token.','audio.blocked':'The browser blocked autoplay audio. Tap the screen once and E.V. will speak again.','sys.tokenInvalid':'Invalid token — reload and enter the right token.','sys.noConn':'No connection to E.V. — ','stt.notUnderstood':'I didn\'t catch the audio — speak closer and try again.','stt.transcribeFail':'Failed to transcribe the audio. Try again.','stt.recUnavail':'Audio recording unavailable in this browser.','vc.tapSpeak':'Tap the microphone and speak. Tap again to send.','vc.folderLine1':'folder: ','vc.folderLine2':' · the conversation is saved here','vc.listening':'listening… (tap again to send)','vc.transcribing':'transcribing…','vc.notUnderstood2':'I didn\'t catch that. Tap the microphone and speak again.','vc.processFail':'Failed to process the audio. Try again.','vc.handsFreeNeed':'Hands-free needs Chrome, Edge or Safari. On Firefox, use the manual microphone.','vc.handsFreeOn':'Hands-free mode on. Just say: "E.V., ..."','vc.convoOn':'Conversation mode on — talk naturally, no need to say my name. Say "stop" to end.','vc.ambientOn':'Ambient presence on — always listens for "E.V. ..."','stt.micDenied':'Microphone permission denied. Tap the lock/site icon in the address bar and enable the microphone for this site.','stt.micNotFound':'No microphone found on the device.','stt.micBusy':'The microphone is being used by another app. Close it and try again.','stt.micHttps':'The microphone requires HTTPS.','stt.micFail':'Couldn\'t access the microphone: ','map.awayFrom':'away','map.locatingRoute':'Locating to plot the route…','map.routeFail':'Couldn\'t calculate the route right now.','map.searching':'Searching','map.addrNotFound':'Couldn\'t find that address. Try more detail.','map.point':'Place','map.saved':'saved','map.needLoc':'I need your location — locating…','map.searchingNearby1':'Searching','map.searchingNearby2':'nearby…','map.notFound1':'Couldn\'t find','map.notFound2':'within ~1.6 km.','map.resultsFor':'result(s) for','map.noSaved':'You haven\'t saved any places yet. Use "Add place" or "Add address".','map.placesSaved':'place(s) saved','map.geoUnavail':'Geolocation unavailable in this browser.','map.approxLoc1':'Approximate location (~','map.approxLoc2':' m) — on desktop it\'s often wrong. Use "Fix location" if it\'s off.','map.youAreHere':'You are here','map.pickPlaceType':' · tap a place type','map.locFail':'Couldn\'t get your location — allow access and try again.','map.addrNotFound2':'Couldn\'t find that address. Try with more detail (street, number, city).','map.locByAddr':'Location set by address.','map.tapToFix':'Tap the map exactly where you are to set your location.','map.mapLbl':'Map','map.addMode':'Add mode: tap the map to create a place','map.noLocSet':'Your location isn\'t set — tap "Where am I".','map.pickDest':'Choose the destination.','map.pickDiff':'Choose different origin and destination.','map.locOnMap':'Location set on the map. Searches and routes start from here.','map.namePrompt':'Place name (e.g. Home, Work):','map.linkUnsupported':'link not supported','street.needToken':'To see the street INSIDE E.V., add a free Mapillary token under "API keys".','street.searching':'Looking for street imagery here…','street.noCoverage':'No street coverage here — opening in Google.','street.openFail':'Couldn\'t open the street here — opening in Google.','cam.openHint':'Point the camera and tap to capture — E.V. analyzes what it sees.','cam.unavailable':'Camera unavailable in this browser.','cam.openFail':'Couldn\'t open the camera: ','cam.analyzing':'Analyzing…','cam.gesture':'Gesture: ','cam.faceWord':'face','cam.objWord':'object','cam.liveHintSuffix':'👍 what is it · ✌️ translate · ✋ close','cam.livePreparing':'Live mode: preparing vision…','cam.liveOn':'Live: faces and objects marked + motion narrated','cam.liveOnNoDetect':'Live: motion narration (detection unavailable in this browser)','cam.translating':'Translating…','cam.estimating':'Estimating calories…','cam.readingDoc':'Reading the document…','cam.ready':'Done.','cam.scanFail':'Failed to scan the document.','cam.linkPrefix':'Link: ','cam.codeRead':'Code read: ','cam.cantRead':'Couldn\'t read it.','cam.qrNeedChrome':'QR/barcode reading needs Chrome or Edge.','cam.codeUnavail':'Code reading unavailable.','cam.qrPoint':'Point at a QR or barcode…','cam.waitLoad':'Wait for the camera to load…','cam.faceAnalyzing':'Analyzing your face…','cam.faceNotClear':'Couldn\'t find a clear face — come closer, with light.','cam.faceEnrollAsk':'I don\'t recognize you yet. Enroll YOUR face now? (only to greet you; the token is still the security)','cam.faceEnrolled':'Face enrolled! Next time I\'ll recognize you, Ryan. 👋','cam.faceHi':'Hi, Ryan! 👋 Recognized you.','cam.faceUnknown':'I don\'t recognize who\'s on camera. 🔒','cam.faceUnavail':'Face recognition unavailable in this browser.','cam.faceEraseAsk':'Erase your enrolled face from E.V.?','cam.faceErased':'Face erased. No biometrics are stored.','common.editT':'edit','common.renameT':'rename','common.removeT':'remove','common.downloadT':'download','mem.editHint':'click to edit','mus.queueAdd':'add to queue','mus.queued':'queued','conn.nameUrlReq':'name and https URL are required','conn.saveConnector':'Save connector','et.askPh':'ask E.V. something…','mus.activatePlayer':'Open Music once and play something to activate E.V.\'s player (Premium required).','page.namePh':'page name (e.g. College)','common.giveName':'enter a name','amb.needBrowser':'Ambient presence needs Chrome, Edge or Safari.','amb.on':'Ambient presence on — just say "E.V. ..." anytime.','metas.nameTargetReq':'enter a name and a target amount','map.addrPrompt':'Address or place (e.g. Av. Paulista 1578, São Paulo):','map.fixPrompt':'Your current address (or leave empty to pick by tapping the map):','et.thinking':'▸ thinking…','et.interrupted':'■ interrupted.','mobile.foldersChats':'Conversations & folders','mobile.focusMode':'Focus mode','mobile.listenEv':'Listen on E.V. (lock-screen controls)','key.setKeep':'set — leave blank to keep','key.notSet':'not set','key.invalidName':'invalid name','conn.phName':'name (e.g. USD rate)','conn.phUrl':'https://api.example.com/... (you can use {{KEY}})','conn.phHeader':'optional header  e.g. Authorization: Bearer {{KEY}}','conn.phPath':'path in the JSON (e.g. rates.BRL or data[0].price)','exp.nonePeriod':'No expenses in the period.','time.justNow':'just now','time.agoPrefix':'','time.agoSuffix':' ago','map.routeHere':'Plot route (here)','map.byFoot':' on foot','map.byBike':' by bike','map.byCar':' by car','map.car':'Car','map.foot':'Foot','map.bike':'Bike','map.myLocation':'My location','map.chip.locate':'Where am I','map.chip.subway':'Subway','map.chip.train':'Train','map.chip.bus':'Bus','map.chip.pharmacy':'Pharmacy','map.chip.market':'Market','map.chip.restaurant':'Restaurant','map.chip.bakery':'Bakery','map.chip.cafe':'Café','map.chip.gas':'Gas','map.chip.bank':'Bank','map.chip.hospital':'Hospital','map.chip.gym':'Gym','due.next':'next ','due.overdue':'overdue · ','due.due':'due ','receipt.imgHint':' — send, or tap the wallet to log an expense','common.nothingFound':'Nothing found.'},pt:{'state.idle':'em espera','side.conversations':'Conversas','side.newfolder':'+ nova pasta','sys.provider':'PROVEDOR','sys.model':'MODELO','sys.latency':'LATÊNCIA','sys.time':'HORA','top.togLeft':'Ocultar/mostrar pastas','top.tabsPrev':'Rolar abas pra esquerda','top.tabsNext':'Rolar abas pra direita','top.goto':'Ir para','top.focusBadge':'Modo foco ativo — clique pra desligar','top.focusLbl':'MODO FOCO','top.search':'Buscar em tudo','top.talk':'Falar','top.talkLbl':'FALAR','top.ambient':'Presença ambiente — escuta "E.V. ..." sempre','top.ambientLbl':'AMBIENTE','top.terminal':'Modo terminal','top.terminalLbl':'TERMINAL','top.voice':'Voz da E.V.','top.voiceLbl':'VOZ','top.sfx':'Sons da interface','top.theme':'Escolher tema de cor','top.togRight':'Ocultar/mostrar painel','top.zen':'Modo limpo (ocultar painéis)','top.lang':'Idioma','chat.attach':'Anexar','chat.mic':'Falar','chat.img':'Enviar imagem','chat.cam':'Câmera ao vivo','chat.input':'Fala com a E.V.  ·  digite / para comandos','chat.send':'Enviar','tasks.h':'Tarefas','tasks.new':'Nova tarefa...','common.categoryPh':'categoria','tasks.duePh':'Vencimento (opcional)','common.repeat':'Repetir','recur.once':'Uma vez','recur.daily':'Diário','recur.weekly':'Semanal','recur.monthly':'Mensal','common.add':'Adicionar','tasks.search':'Buscar tarefas...','kb.h':'Base de conhecimento','kb.urlPh':'https://...  (indexar uma página)','kb.indexUrl':'Indexar URL','kb.upload':'⬱ Enviar arquivo (PDF / Word / txt)','kb.notePh':'Título da nota','kb.textPh':'Cole um texto pra E.V. aprender e responder com base nele...','kb.addText':'Adicionar texto','kb.search':'Buscar na base...','kb.indexed':'Documentos indexados','exp.h':'Gastos','common.amount':'Valor','common.description':'Descrição','common.categoryPh2':'categoria','common.log':'Registrar','exp.search':'Buscar gastos...','exp.last60':'Últimos 60 dias','rem.h':'Lembretes','rem.newPh':'Lembrar de...','common.repeat2':'Repetir','recur.once2':'Uma vez','recur.daily2':'Diário','recur.weekly2':'Semanal','recur.monthly2':'Mensal','common.create':'Criar','rem.search':'Buscar lembretes...','rem.open':'Em aberto','cal.email':'Enviar email','cal.msg':'Mensagem no Telegram','mem.h':'Memórias','mem.newPh':'Algo que a E.V. deve lembrar sobre você...','common.save':'Salvar','mem.search':'Buscar no cérebro...','mem.knows':'O que a E.V. sabe','mem.forgetAll':'esquecer tudo','lnk.h':'Links','common.name':'Nome','common.categoryPh3':'categoria','common.save2':'Salvar','lnk.search':'Buscar links...','hab.h':'Hábitos','hab.newPh':'Novo hábito (ex: treino)','common.create2':'Criar','hab.search':'Buscar hábitos...','jou.h':'Diário','jou.newPh':'Como foi seu dia?','common.log2':'Registrar','jou.search':'Buscar no diário...','sub.h':'Assinaturas','common.amount2':'Valor','sub.descPh':'Ex: Netflix','sub.dayPh':'dia do mês','common.save3':'Salvar','sub.search':'Buscar assinaturas...','orc.h':'Orçamentos','orc.catPh':'Categoria (ex: comida)','orc.limitPh':'Limite/mês','orc.set':'Definir','orc.search':'Buscar orçamentos...','mon.h':'Monitores web','mon.urlPh':'https://... (página a vigiar)','mon.kwPh':'palavra (opcional)','mon.watch':'Vigiar','mon.search':'Buscar monitores...','act.h':'Histórico de atividade','act.allCats':'Todas as categorias','act.search':'Buscar no histórico...','map.h':'Mapa · você e o que tem por perto','map.statusInit':'toque em "Onde estou" para localizar seu dispositivo','map.searchPh':'Buscar por perto: padaria, farmácia...','map.fix':'Corrigir localização','map.mine':'Meus pontos','map.plan':'Tempo A→B','map.addr':'Adicionar endereço','map.add':'Adicionar ponto','map.sat':'Satélite','map.street':'Ver rua','map.gmaps':'Abrir no Google Maps','map.ask':'Perguntar à E.V.','map.from':'De','map.to':'para','map.showTime':'Ver tempo','brain.h':'Cérebro · tudo que a E.V. sabe','brain.recenter':'Centralizar','loc.h':'Executor local · roda no seu computador','loc.intro':'Toda tarefa abaixo só executa depois que você aprovar aqui ou no Telegram — a E.V. nunca roda nada sozinha no seu PC. Tarefas de navegador em WhatsApp/Instagram (🔴 alto risco) pedem uma segunda confirmação antes de enviar/postar qualquer coisa.','loc.confirmsCat':'⚠️ Confirmações de alto risco (ação prestes a acontecer)','loc.pendingCat':'Pendentes de aprovação','loc.histCat':'Histórico','loc.scriptsCat':'Scripts cadastrados (allowlist)','loc.scriptNamePh':'Nome (ex: rodar backup)','loc.scriptCmdPh':'Comando/caminho a executar','loc.register':'Cadastrar','graf.h':'Gráficos · seus dados','graf.pMonth':'Este mês','graf.p30':'Últimos 30 dias','graf.p90':'Últimos 3 meses','graf.p180':'Últimos 6 meses','graf.pYear':'Este ano','graf.pCustom':'Personalizado','graf.expCat':'Gastos por categoria','graf.expPeriod':'Gastos ao longo do período','graf.habits':'Hábitos (dias marcados no período)','graf.interactions':'Interações ao longo do tempo','graf.provUse':'Uso de provedor de IA','graf.actType':'Atividade por tipo','graf.tasksCC':'Tarefas: criadas vs concluídas','graf.memGrowth':'Crescimento da memória','clima.cityPh':'cidade (ex: São Paulo)','clima.view':'Ver','mus.h':'Música · Spotify','mus.paste':'Ou cole o link de uma playlist/faixa/álbum do Spotify (player embutido, sem Premium):','mus.nickPh':'apelido (opcional)','common.add2':'Adicionar','metas.h':'Metas · cofrinho','metas.namePh':'nome da meta (ex: Viagem)','metas.targetPh':'valor alvo (R$)','metas.create':'Criar meta','saude.h':'Saúde & rotina','cofre.h':'Cofre de documentos','cofre.sub':'Guardados cifrados no seu banco. Imagens viram texto pesquisável (OCR).','cofre.search':'buscar por nome ou texto...','cofre.upload':'Enviar documento','painel.h':'Painel · astronomia & mundo','painel.astro':'☾ Astronomia','painel.radar':'◎ Radar do mundo','painel.backup':'⛁ Backup','right.system':'Sistema','common.edit':'editar','right.quickActions':'Ações rápidas','common.edit2':'editar','right.pages':'Páginas','right.newPage':'+ nova','right.aiProvider':'Provedor de IA','right.voice':'Voz da E.V.','right.connectors':'Conectores de API','right.keys':'Chaves de API','right.term':'Terminal de ação','right.notifs':'Notificações','fab.quickCapture':'Captura rápida (Ctrl/Cmd+J)','common.close':'FECHAR','vc.tapMic':'Toque no microfone e fale.','vc.sub':'voz ao vivo','vc.cont':'Modo contínuo: off','vc.convo':'Conversa: off','np.open':'Abrir Música','np.prev':'Anterior','np.tog':'Play/Pause','np.next':'Próxima','np.seek':'Arraste para mudar a posição','bnav.home':'Início','bnav.chat':'Conversa','bnav.tasks':'Tarefas','bnav.exp':'Gastos','bnav.more':'Mais','common.close2':'FECHAR','cam.hint':'Aponte a câmera. Toque em capturar, em "o que é isso?", ou ligue o modo ao vivo.','cam.flip':'Trocar câmera','cam.live':'Ao vivo (marca rostos + narra)','cam.what':'O que é isso?','cam.tr':'Traduzir o texto','cam.food':'Calorias da comida','cam.qr':'Ler QR / código de barras','cam.scan':'Escanear documento pra Base','cam.face':'Quem sou eu? (reconhece só você — segure para apagar)','cam.shot':'Capturar e perguntar no chat','common.close3':'FECHAR','street.loading':'Carregando a rua…','common.close4':'FECHAR','pomo.focus':'Foco','pomo.reset':'reset','pomo.min':'⧉ minimizar','pm.expand':'expandir','pm.close':'fechar','ck.ph':'Buscar ação ou comando...  (Esc pra fechar)','login.tokenPh':'Token de acesso','login.enter':'Entrar','login.or':'ou','login.google':'Entrar com Google','login.github':'Entrar com GitHub','standby.hint':'toque ou fale para retomar','state.listening':'ouvindo','state.thinking':'processando','state.speaking':'falando','status.online':'ONLINE','status.reconnecting':'RECONECTANDO','view.chat':'Conversa','view.inicio':'Início','view.tasks':'Tarefas','view.exp':'Gastos','view.rem':'Lembretes','view.cal':'Agenda','view.mem':'Memórias','view.lnk':'Links','view.hab':'Hábitos','view.jou':'Diário','view.sub':'Assinaturas','view.orc':'Orçamentos','view.mon':'Monitores','view.act':'Histórico','view.kb':'Base','view.map':'Mapa','view.brain':'Cérebro','view.graf':'Gráficos','view.musica':'Música','view.clima':'Clima','view.metas':'Metas','view.saude':'Saúde','view.cofre':'Cofre','view.painel':'Painel','view.loc':'Executor local','grp.main':'Principal','grp.productivity':'Produtividade','grp.finance':'Financeiro','grp.knowledge':'Conhecimento','grp.explore':'Explorar','grp.automation':'Automação','tabs.pick':'Escolher abas','tabs.pickTitle':'Abas do topo','tabs.pickSub':'Escolha quais abas aparecem no topo.','common.cancel':'Cancelar','common.save4':'Salvar','common.closeBtn':'Fechar','common.confirm':'Confirmar','common.delete':'Apagar','cat.inicio':'Início','cat.plano':'Plano do dia','cat.pendencias':'Pendências','cat.padroes':'Padrões','cat.automacoes':'Automações','cat.bak':'Backup','cat.tarefas':'Tarefas','cat.lembretes':'Lembretes','cat.gastos':'Gastos','cat.memorias':'Memórias','cat.kb':'Base','cat.map':'Mapa','cat.graf':'Gráficos','cat.brain':'Cérebro','cat.musica':'Música','cat.metas':'Metas','cat.saude':'Saúde','cat.cofre':'Cofre','cat.painel':'Painel','cat.cam':'Câmera','cat.buscar':'Buscar web','cat.noticias':'Notícias','cat.clima':'Clima','cat.relatorio':'Relatório','cat.status':'Status','cat.semana':'Semana','cat.foco':'Pomodoro','cat.procurar':'Procurar','cat.calendario':'Agenda','cat.habitos':'Hábitos','cat.diario':'Diário','cat.orcamentos':'Orçamentos','cat.assinaturas':'Assinaturas','cat.dados':'Meus dados','cat.insights':'Insights','cat.quiz':'Quiz','sm.tasks':'Tarefas','sm.reminders':'Lembretes','sm.expenses':'Gastos · mês','sm.memories':'Memórias','sm.kb':'Base','sm.kbfiles':'Arquivos','sm.links':'Links','sm.habits':'Hábitos','sm.journal':'Diário','sm.subscriptions':'Assinaturas','sm.budgets':'Orçamentos','sm.watches':'Monitores','sm.agenda':'Agenda · 7d','sm.activity':'Histórico · 24h','sm.provider':'Provedor','sm.model':'Modelo','sm.disk':'Disco','sm.ram':'RAM','sm.uptime':'Uptime','menu.gView':'Ver','menu.gCreate':'Criar','menu.gTools':'Ferramentas','menu.gSettings':'Ajustes','menu.emails':'E-mails','menu.task':'Tarefa','menu.reminder':'Lembrete','menu.expense':'Gasto','menu.event':'Evento','menu.email':'E-mail','menu.link':'Link','menu.kbnote':'Nota na base','menu.summarize':'Resumir link','menu.provider':'Provedor','menu.mute':'Silenciar','menu.help':'Ajuda','cat.map0':'Links','menu.header':'Menu — toque para abrir ou preencher','cal.repeatEv':'Repetir (só na E.V.)','chart.you':'Você','chart.created':'Criadas','chart.completed':'Concluídas','chart.memories':'Memórias','empty.notifT':'Nenhuma notificação','empty.notifH':'Lembretes e alertas aparecem aqui.','empty.goalsT':'Nenhuma meta ainda','empty.goalsH':'Crie uma acima.','empty.vaultT':'Nenhum documento','empty.vaultH':'Envie um acima.','empty.musicT':'Nenhuma música salva','empty.musicH':'Cole um link do Spotify acima.','empty.actT':'Nada registrado ainda','empty.actH':'Suas ações (criar, concluir, apagar) aparecem aqui — do Telegram e da web.','empty.subT':'Nenhuma assinatura','empty.subH':'Adicione uma para acompanhar vencimentos.','empty.orcT':'Nenhum orçamento definido','empty.orcH':'Defina um limite mensal por categoria.','empty.monT':'Nenhum monitor','empty.monH':'Crie um para acompanhar preços ou páginas.','empty.locConfT':'Nada aguardando confirmação','empty.locConfH':'Ações de alto risco (WhatsApp/Instagram) pausam aqui antes de enviar/postar.','empty.locPendT':'Nada pendente','empty.locPendH':'Quando a E.V. pedir pra rodar algo no seu PC, aparece aqui.','empty.locHistT':'Sem histórico ainda','empty.locHistH':'Tarefas aprovadas/recusadas aparecem aqui.','empty.locScrT':'Nenhum script cadastrado','empty.locScrH':'Cadastre um acima pra E.V. poder pedir pra rodar por nome.','empty.lnkT':'Nenhum link salvo','empty.lnkH':'Cole uma URL acima para guardar.','empty.habT':'Nenhum hábito','empty.habH':'Crie um acima.','empty.jouT':'Diário vazio','empty.jouH':'Escreva sua primeira entrada acima.','empty.expT':'Nenhum gasto registrado','empty.expH':'Adicione um gasto acima.','empty.remT':'Nenhum lembrete em aberto','empty.remH':'Crie um acima.','empty.memT':'Cérebro vazio','empty.memH':'Adicione acima, ou diga à E.V. o que lembrar.','empty.kbT':'Nada na base ainda','empty.kbH':'Adicione uma URL, arquivo ou texto acima.','empty.tasksT':'Nenhuma tarefa em aberto','empty.tasksH':'Crie uma acima.','modal.connectors':'Conectores de API','modal.voice':'Voz da E.V.','modal.notifs':'Notificações','modal.gevent':'Evento do Google','form.keys':'Chaves de API','form.quickCap':'Captura rápida','form.renameFolder':'Renomear pasta','form.newFolder':'Nova pasta','form.editSub':'Editar assinatura','form.editMon':'Editar monitor','form.editLink':'Editar link','form.renameHab':'Renomear hábito','form.editEntry':'Editar entrada','form.editEvent':'Editar evento','form.editExp':'Editar gasto','form.editRem':'Editar lembrete','form.editTask':'Editar tarefa','form.indexPage':'Indexar página','form.nameFile':'Nomear arquivo','form.sendEmail':'Enviar email','form.tgMsg':'Mensagem no meu Telegram','form.searchAll':'Buscar em tudo','mobile.menu':'Menu','pick.actsSub':'Escolha os atalhos do painel.','pick.statsSub':'Escolha os indicadores exibidos.','ov.customize':'Personalizar Início','ov.customizeSub':'Escolha quais cards aparecem no seu painel.','form.newSubfolder':'Nova subpasta em','form.editBudget':'Editar orçamento','form.newEvent':'Novo evento','cal.eventsOn':'Eventos','page.edit':'Editar página','page.new':'Nova página','field.name':'Nome','field.url':'URL','field.category':'Categoria','field.description':'Descrição','field.amountRs':'Valor (R$)','field.text':'Texto','field.time':'Hora','field.event':'Evento','field.dayOfMonth':'Dia do mês','field.monthlyRs':'Valor mensal (R$)','field.keyword':'Palavra-chave','field.newName':'Novo nome','field.folderPh':'ex: projetos','field.remindOf':'Lembrar de','field.whenIso':'Quando (AAAA-MM-DDTHH:MM)','field.where':'Onde','field.evReminder':'Lembrete da E.V.','field.dateIso':'Data (AAAA-MM-DD)','field.dueOpt':'Vencimento (opcional)','field.catPh':'ex: faculdade','field.to':'Para','field.subject':'Assunto','field.message':'Mensagem','field.tgPh':'texto que chega no seu Telegram','field.nameId':'Nome (pra identificar)','field.search':'Buscar','field.searchAllPh':'tarefas, gastos, memórias, base...','form.qcLabel':'O que você quer guardar? (tarefa, lembrete, gasto, nota…)','form.qcPh':'Ex: comprar leite · reunião às 15h amanhã · gastei 40 no mercado','toast.backupDl':'Baixando backup cifrado…','toast.capturing':'Capturando…','toast.captured':'Capturado.','toast.captureFail':'Não consegui capturar. Tenta de novo.','toast.backupOk':'Backup gerado.','toast.backupErr':'Falha ao gerar backup.','panel.backupNow':'Fazer backup agora','panel.generating':'Gerando…','panel.last':'Último','panel.noBackup':'Nenhum backup ainda','panel.encBackups':'Backups cifrados','ov.syncing':'Sincronizando sistemas…','ov.loadFail':'Não consegui carregar o painel.','ov.personalize':'Personalizar','ov.morning':'Bom dia','ov.afternoon':'Boa tarde','ov.evening':'Boa noite','ov.greetFallback':'Sistemas online. Tudo pronto pra você.','ov.askPh':'Pergunte à E.V…','ov.send':'Enviar','ov.talkEv':'Falar com a E.V.','ov.tSystem':'SISTEMA','ov.tAI':'IA','ov.tModel':'MODELO','ov.tMemories':'MEMÓRIAS','ov.tAlerts':'ALERTAS','ov.sgSummary':'Resumo do dia','ov.sgToday':'O que tenho hoje?','ov.sgExpenses':'Gastos do mês','ov.sgWeather':'Clima','ov.tasksToday':'Tarefas de hoje','ov.open':'abertas','ov.nothingPending':'Nada pendente. 🎉','ov.newTask':'Nova tarefa…','ov.habitsToday':'Hábitos de hoje','ov.noHabits':'Nenhum hábito ainda — crie na aba Hábitos.','ov.healthWater':'Saúde & água','ov.cup':'copo','ov.sleep':'Sono','ov.mood':'Humor','ov.noReminders':'Sem lembretes ativos.','ov.newReminder':'novo lembrete','ov.top':'maior','ov.quickExp':'+ gasto rápido: 50 uber #transporte','ov.quickExpHint':'informe um valor, ex: 50 uber #transporte','ov.weatherNow':'Clima agora','ov.loadingForecast':'carregando previsão','wx.hi':'máx','wx.lo':'mín','ov.agendaToday':'Agenda de hoje','ov.events':'eventos','ov.agendaTap':'Toque para ver a agenda completa','ov.agendaConnect':'Conecte o Google Agenda em Chaves de API','ov.recentAct':'Atividade recente','ov.noActivity':'Nada registrado ainda. Suas ações aparecem aqui.','ov.nowPlaying':'Tocando agora','ov.loading':'carregando…','painel.astro2':'Astronomia','ov.loadingShort':'carregando','ov.waxing':'crescente','ov.waning':'minguante','wx.sunrise':'nascer','wx.sunset':'pôr','ov.rates':'Cotações','rate.usd':'Dólar','rate.eur':'Euro','rate.btc':'Bitcoin','ov.unavailNow':'indisponível agora','chip.memories':'memórias','chip.sources':'fontes','chip.links':'links','chip.journal':'diário','chip.places':'lugares','chip.subs':'assinaturas','chip.autos':'automações','ov.spConfig':'Configure o Spotify em Chaves de API pra ouvir aqui.','ov.spConnect':'Conectar Spotify','ov.nothingPlaying':'Nada tocando','ck.actionTerm':'Terminal de ação da E.V.','ck.liveVoice':'Voz ao vivo','ck.focusToggle':'Modo foco (liga/desliga)','ck.go':'ir','ck.open':'abrir','ck.content':'conteúdo','wx.fail':'não consegui o clima.','wx.feels':'sensação','wx.nextHours':'Próximas horas','wx.tenDay':'Previsão de 10 dias','wx.uvLow':'baixo','wx.uvMod':'moderado','wx.uvHigh':'alto','wx.uvVHigh':'muito alto','wx.uvExtreme':'extremo','wx.rainChance':'Chance de chuva','wx.upTo':'até','wx.throughDay':'ao longo do dia','wx.wind':'Vento','wx.gusts':'rajadas','wx.humidity':'Umidade','wx.uvIndex':'Índice UV','wx.maxToday':'máx hoje','wx.sun':'Sol','wx.feelsC':'Sensação','wx.realTemp':'temperatura real','wx.cloud':'Nebulosidade','wx.pressure':'Pressão','act.taskNew':'tarefa criada','act.taskDone':'tarefa concluída','act.taskDel':'tarefa apagada','act.remNew':'lembrete criado','act.remDone':'lembrete disparado','act.remCancel':'lembrete cancelado','act.expNew':'gasto adicionado','act.expDel':'gasto apagado','act.habDone':'hábito feito','loc.kScript':'script','loc.kOpen':'abrir','loc.kBrowser':'navegador','loc.kShell':'shell','loc.sPending':'aguardando aprovação','loc.sApproved':'aprovado · na fila','loc.sRunning':'executando','loc.sDone':'concluído','loc.sFailed':'falhou','loc.sRejected':'recusado','loc.highRisk':'🔴 alto risco','loc.taskPaused1':'tarefa','loc.taskPaused2':'está pausada aguardando esta confirmação','loc.approve':'aprovar','loc.reject':'recusar','loc.confirmProceed':'confirmar e deixar prosseguir','loc.rejectAction':'recusar esta ação','notif.markAll':'Marcar todas lidas','notif.clearRead':'Limpar lidas','notif.activeNow':'ativo agora','page.widgets':'Widgets','conn.savedKeys':'Chaves guardadas','conn.connectors':'Conectores','conn.blurb':'Conecte qualquer API HTTPS pela interface — sem código. Guarde a chave aqui e use {{NOME_DA_CHAVE}} na URL ou nos headers.','voice.blurb':'Escolha a voz e ouça uma amostra. Gemini soa mais natural (uns segundos a mais); Edge é mais rápida.','voice.speed':'Velocidade','voice.pitch':'Tom','right.noPages':'nenhuma ainda','chat.folderPrefix':'Pasta','chat.startConv':'comece a conversa.','confirm.delFolder1':'Apagar','confirm.delFolder2':'(e subpastas/conversas)? Não dá pra desfazer.','confirm.rmSub':'Remover assinatura?','confirm.rmBudget':'Remover orçamento?','confirm.rmMon':'Remover monitor?','confirm.rmHab':'Apagar hábito?','confirm.forgetAll':'Esquecer TODAS as memórias da E.V.? Isso apaga tudo que ela sabe sobre você (não afeta tarefas, gastos etc).','confirm.rmKb1':'Remover','confirm.rmKb2':'da base?','confirm.rmGcal':'Apagar este evento do Google Calendar?','confirm.rmBrain1':'Apagar','confirm.rmBrain2':'Isso remove o item de verdade da E.V.','confirm.rmScript':'Remover script','confirm.logRs':'Lançar','brain.deleteNode':'Apagar do cérebro','brain.editNode':'Editar','brain.openNode':'Abrir','pomo.break':'Pausa','pomo.cycleDone':'Ciclo concluído','map.unavail':'Mapa indisponível (sem conexão com o Leaflet).','painel.astroUnavail':'astronomia indisponível.','painel.radarUnavail':'radar indisponível.','painel.statusUnavail':'status indisponível.','painel.moon':'Lua','painel.waxing':'crescendo','painel.waning':'minguando','painel.iss':'Estação Espacial (ISS)','painel.clocks':'Relógios','painel.ratesUnavail':'cotações indisponíveis','painel.headlines':'Manchetes · TabNews','painel.noHeadlines':'sem manchetes','wtype.note':'Nota','wtype.connector':'Conector','wtype.command':'Botão de comando','wtype.chart':'Gráfico de gastos','wtype.spotify':'Spotify (link)','saude.waterToday':'Água hoje','saude.cups':'copos','saude.lastSleep':'Sono da última noite','saude.moodToday':'Humor de hoje','saude.lastDays':'Últimos dias','voice.gemini':'Gemini · mais natural','voice.edge':'Edge · rápida','voice.listFail':'Não consegui listar as vozes agora.','mus.myPlaylists':'Minhas playlists','mus.noPlaylists':'Nenhuma playlist encontrada.','recur.repeatsPrefix':'repete','recur.shortDaily':'diário','recur.shortWeekly':'semanal','recur.shortMonthly':'mensal','time.today':'hoje','time.at':'às','cal.allDay':'dia todo','cal.creatingGoogle':'Criando no Google...','cal.eventCreated':'Evento criado no Google Calendar.','cal.createFail':'Falha ao criar.','cal.eventDeleted':'Evento apagado.','cal.deleteFail':'Falha ao apagar.','hab.doneToday':'feito hoje','hab.markDone':'marcar feito','hab.daysWord':'dias','mem.memoryWord':'memória','mem.memoriesWord':'memórias','common.deleteT':'apagar','common.openTitle':'abrir','common.complete':'concluir','common.dragReorder':'arrastar pra reordenar','common.forgetT':'esquecer','common.err':'erro','common.errPrefix':'erro: ','common.test':'Testar','folder.subfolder':'subpasta','folder.moveRoot':'mover para a raiz','page.notFound':'Página não encontrada.','tasks.none':'Sem tarefas.','receipt.logExpense':'Lançar como gasto','receipt.noValue':'Não consegui identificar um valor nesse comprovante.','receipt.readFail':'Falha ao ler o comprovante.','keys.updated':'Chaves atualizadas: ','voice.updated':'Voz da E.V. atualizada','mus.connectMine':'Conectar meu Spotify','mus.disconnect':'desconectar','mus.cantPlay':'não consegui tocar','sp.playingVia':'Tocando pela E.V. — controles no bloqueio ativos.','sp.transferFail':'Não consegui transferir.','panel.copiesStored':'cópia(s) guardada(s)','panel.autoDaily':'· automático 1x/dia','panel.runsAutoDaily':'roda automaticamente 1x/dia (via Telegram)','mail.fillToBody':'Preencha destinatário e mensagem.','mail.sending':'Enviando email...','mail.sent':'Email enviado.','mail.sendFail':'Falha ao enviar.','mail.noConn':'Sem conexão ao enviar o email.','msg.sent':'Mensagem enviada.','msg.sendFail':'Falha ao enviar.','msg.noConn':'Sem conexão ao enviar a mensagem.','kb.fileNotFound':'Arquivo não encontrado.','kb.openFail':'Não consegui abrir o arquivo.','kb.indexing':'indexando...','kb.uploadErr':'erro no upload','kb.defaultNote':'Nota','brain.unavail3d':'cérebro 3D indisponível (sem conexão com o Three.js)','brain.editPrompt':'Editar:','chat.noReply':'(sem resposta)','img.sendFail':'Falha ao enviar a imagem.','undo.btn':'Desfazer','undo.deleted':'apagado','ent.item':'Item','ent.reminder':'Lembrete','ent.link':'Link','ent.entry':'Entrada','ent.event':'Evento','ent.expense':'Gasto','ent.memory':'Memória','ent.task':'Tarefa','login.enterToken':'Informe o token.','login.checking':'verificando...','login.invalid':'Token inválido.','audio.blocked':'O navegador bloqueou o áudio automático. Toque uma vez na tela e a E.V. volta a falar.','sys.tokenInvalid':'Token inválido — recarregue e informe o token certo.','sys.noConn':'Sem conexão com a E.V. — ','stt.notUnderstood':'Não entendi o áudio — fale mais perto e tente de novo.','stt.transcribeFail':'Falha ao transcrever o áudio. Tente de novo.','stt.recUnavail':'Gravação de áudio indisponível neste navegador.','vc.tapSpeak':'Toque no microfone e fale. Toque de novo para enviar.','vc.folderLine1':'pasta: ','vc.folderLine2':' · a conversa fica salva aqui','vc.listening':'ouvindo... (toque de novo para enviar)','vc.transcribing':'transcrevendo...','vc.notUnderstood2':'Não entendi. Toque no microfone e fale de novo.','vc.processFail':'Falha ao processar o áudio. Tente de novo.','vc.handsFreeNeed':'Mãos-livres precisa do Chrome, Edge ou Safari. No Firefox, use o microfone manual.','vc.handsFreeOn':'Modo mãos-livres ligado. É só dizer: "E.V., ..."','vc.convoOn':'Modo conversa ligado — pode falar naturalmente, sem dizer meu nome. Diga "parar" pra encerrar.','vc.ambientOn':'Presença ambiente ligada — escuta "E.V. ..." sempre','stt.micDenied':'Permissão do microfone negada. Toque no ícone de cadeado/site na barra de endereço e habilite o microfone para este site.','stt.micNotFound':'Nenhum microfone encontrado no aparelho.','stt.micBusy':'O microfone está sendo usado por outro app. Feche-o e tente de novo.','stt.micHttps':'O microfone exige HTTPS.','stt.micFail':'Não consegui acessar o microfone: ','map.awayFrom':'de você','map.locatingRoute':'Localizando pra traçar a rota...','map.routeFail':'Não consegui calcular a rota agora.','map.searching':'Procurando','map.addrNotFound':'Não achei esse endereço. Tenta mais detalhado.','map.point':'Ponto','map.saved':'salvo','map.needLoc':'Preciso da sua localização — localizando...','map.searchingNearby1':'Buscando','map.searchingNearby2':'por perto...','map.notFound1':'Não achei','map.notFound2':'num raio de ~1,6 km.','map.resultsFor':'resultado(s) para','map.noSaved':'Você ainda não salvou pontos. Use "Adicionar ponto" ou "Adicionar endereço".','map.placesSaved':'ponto(s) salvo(s)','map.geoUnavail':'Geolocalização indisponível neste navegador.','map.approxLoc1':'Localização aproximada (~','map.approxLoc2':' m) — no PC costuma errar. Use "Corrigir localização" se estiver errado.','map.youAreHere':'Você está aqui','map.pickPlaceType':' · toque num tipo de lugar','map.locFail':'Não consegui pegar sua localização — permita o acesso e tente de novo.','map.addrNotFound2':'Não achei esse endereço. Tenta com mais detalhe (rua, número, cidade).','map.locByAddr':'Localização definida por endereço.','map.tapToFix':'Toque no mapa exatamente onde você está pra definir sua localização.','map.mapLbl':'Mapa','map.addMode':'Modo adicionar: toque no mapa pra criar um ponto','map.noLocSet':'Sua localização não foi definida — toque em "Onde estou".','map.pickDest':'Escolha o destino.','map.pickDiff':'Escolha origem e destino diferentes.','map.locOnMap':'Localização definida no mapa. É daqui que as buscas e rotas vão partir.','map.namePrompt':'Nome do ponto (ex: Casa, Trabalho):','map.linkUnsupported':'link não suportado','street.needToken':'Pra ver a rua DENTRO da E.V., adicione um token grátis do Mapillary em "Chaves de API".','street.searching':'Procurando imagens de rua aqui…','street.noCoverage':'Sem cobertura de rua aqui — abrindo no Google.','street.openFail':'Não consegui abrir a rua aqui — abrindo no Google.','cam.openHint':'Aponte a câmera e toque para capturar — a E.V. analisa o que vê.','cam.unavailable':'Câmera indisponível neste navegador.','cam.openFail':'Não consegui abrir a câmera: ','cam.analyzing':'Analisando...','cam.gesture':'Gesto: ','cam.faceWord':'rosto','cam.objWord':'objeto','cam.liveHintSuffix':'👍 o que é · ✌️ traduzir · ✋ fechar','cam.livePreparing':'Modo ao vivo: preparando visão...','cam.liveOn':'Ao vivo: rostos e objetos marcados + movimento narrado','cam.liveOnNoDetect':'Ao vivo: narração por movimento (detecção indisponível neste navegador)','cam.translating':'Traduzindo...','cam.estimating':'Estimando calorias...','cam.readingDoc':'Lendo o documento...','cam.ready':'Pronto.','cam.scanFail':'Falha ao escanear o documento.','cam.linkPrefix':'Link: ','cam.codeRead':'Código lido: ','cam.cantRead':'Não consegui ler.','cam.qrNeedChrome':'Leitura de QR/código precisa do Chrome ou Edge.','cam.codeUnavail':'Leitura de código indisponível.','cam.qrPoint':'Aponte para um QR ou código de barras...','cam.waitLoad':'Espere a câmera carregar...','cam.faceAnalyzing':'Analisando seu rosto…','cam.faceNotClear':'Não achei um rosto nítido — chega mais perto, com luz.','cam.faceEnrollAsk':'Ainda não reconheço você. Cadastrar SEU rosto agora? (fica só pra te cumprimentar; o token continua sendo a segurança)','cam.faceEnrolled':'Rosto cadastrado! Da próxima vez eu te reconheço, Ryan. 👋','cam.faceHi':'Olá, Ryan! 👋 Reconheci você.','cam.faceUnknown':'Não reconheço quem está na câmera. 🔒','cam.faceUnavail':'Reconhecimento facial indisponível neste navegador.','cam.faceEraseAsk':'Apagar seu rosto cadastrado da E.V.?','cam.faceErased':'Rosto apagado. Nenhuma biometria fica guardada.','common.editT':'editar','common.renameT':'renomear','common.removeT':'remover','common.downloadT':'baixar','mem.editHint':'clique para editar','mus.queueAdd':'adicionar à fila','mus.queued':'na fila','conn.nameUrlReq':'nome e URL https são obrigatórios','conn.saveConnector':'Salvar conector','et.askPh':'pedir algo à E.V…','mus.activatePlayer':'Abra a Música uma vez e toque algo pra ativar o player da E.V. (precisa Premium).','page.namePh':'nome da página (ex: Faculdade)','common.giveName':'dê um nome','amb.needBrowser':'Presença ambiente precisa do Chrome, Edge ou Safari.','amb.on':'Presença ambiente ligada — é só dizer "E.V. ..." a qualquer momento.','metas.nameTargetReq':'dê um nome e um valor alvo','map.addrPrompt':'Endereço ou local (ex: Av. Paulista 1578, São Paulo):','map.fixPrompt':'Seu endereço atual (ou deixe vazio pra escolher tocando no mapa):','et.thinking':'▸ pensando…','et.interrupted':'■ interrompido.','mobile.foldersChats':'Conversas & pastas','mobile.focusMode':'Modo foco','mobile.listenEv':'Ouvir na E.V. (controles no bloqueio)','key.setKeep':'definida — deixe em branco pra manter','key.notSet':'não definida','key.invalidName':'nome inválido','conn.phName':'nome (ex: Cotação dólar)','conn.phUrl':'https://api.exemplo.com/... (pode usar {{CHAVE}})','conn.phHeader':'header opcional  ex: Authorization: Bearer {{CHAVE}}','conn.phPath':'caminho no JSON (ex: rates.BRL ou data[0].price)','exp.nonePeriod':'Sem gastos no período.','time.justNow':'agora mesmo','time.agoPrefix':'há ','time.agoSuffix':'','map.routeHere':'Traçar rota (aqui)','map.byFoot':' a pé','map.byBike':' de bike','map.byCar':' de carro','map.car':'Carro','map.foot':'A pé','map.bike':'Bike','map.myLocation':'Minha localização','map.chip.locate':'Onde estou','map.chip.subway':'Metrô','map.chip.train':'Trem','map.chip.bus':'Ônibus','map.chip.pharmacy':'Farmácia','map.chip.market':'Mercado','map.chip.restaurant':'Restaurante','map.chip.bakery':'Padaria','map.chip.cafe':'Café','map.chip.gas':'Posto','map.chip.bank':'Banco','map.chip.hospital':'Hospital','map.chip.gym':'Academia','due.next':'próxima ','due.overdue':'atrasada · ','due.due':'vence ','receipt.imgHint':' — envie, ou toque na carteira pra lançar gasto','common.nothingFound':'Nada encontrado.'}};
let _lang=(localStorage.getItem('ev_lang')||'en');if(!I18N[_lang])_lang='en';
function t(k){return (I18N[_lang]&&I18N[_lang][k])||I18N.en[k]||k;}
function TR(k){return t(k);}  // alias for scopes where a local var shadows t
function _applyStatic(){
  document.querySelectorAll('[data-i18n]').forEach(el=>{el.textContent=t(el.dataset.i18n);});
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{el.setAttribute('placeholder',t(el.dataset.i18nPh));});
  document.querySelectorAll('[data-i18n-title]').forEach(el=>{el.setAttribute('title',t(el.dataset.i18nTitle));});
}
function applyLang(lang,initial){_lang=I18N[lang]?lang:'en';localStorage.setItem('ev_lang',_lang);
  document.documentElement.lang=(_lang==='pt'?'pt-br':'en');_applyStatic();
  try{buildLangMenu();}catch(e){}
  if(!initial){
    // Unified control: choosing the UI language also sets how E.V. talks
    // (LLM replies + TTS voice). Fire-and-forget, like the focus-mode toggle.
    try{fetch('/api/lang',{method:'POST',headers:H(),body:JSON.stringify({lang:_lang})}).catch(()=>{});}catch(e){}
    try{if(typeof renderTabs==='function')renderTabs();}catch(e){}
    try{if(typeof renderActs==='function')renderActs();}catch(e){}
    try{if(typeof renderStats==='function')renderStats();}catch(e){}
    try{if(typeof _idleLabel==='function')_idleLabel();}catch(e){}
    try{const mnl=document.getElementById('mnav-lbl');if(mnl&&typeof curView!=='undefined'&&VIEW_LABELS[curView])mnl.textContent=VIEW_LABELS[curView];}catch(e){}
    try{const se=document.getElementById('scope');if(se&&typeof thread!=='undefined'&&/·/.test(se.textContent))se.textContent=t('bnav.chat')+' · '+thread;}catch(e){}
    try{if(typeof renderMapChips==='function'&&document.getElementById('map-chips'))renderMapChips();}catch(e){}
    try{if(typeof curView!=='undefined'&&typeof switchView==='function'&&typeof VIEWS!=='undefined'&&VIEWS[curView])switchView(curView);}catch(e){}
  }
}
// language picker menu (mirrors #theme-menu)
function buildLangMenu(){const m=document.getElementById('lang-menu');if(!m)return;m.textContent='';
  const mk=(code,label)=>{const b=document.createElement('button');b.setAttribute('role','menuitemradio');
    const active=(_lang===code);b.setAttribute('aria-checked',active?'true':'false');if(active)b.classList.add('on');
    const sp=document.createElement('span');sp.className='tm-lbl';sp.textContent=label;b.appendChild(sp);
    const ck=document.createElement('i');ck.setAttribute('data-lucide','check');ck.classList.add('tm-ck');b.appendChild(ck);
    b.onclick=()=>{m.classList.remove('on');applyLang(code);};m.appendChild(b);};
  mk('en','English');mk('pt','Portugu\u00eas');window.lucide&&lucide.createIcons();}
function openLangMenu(){const m=document.getElementById('lang-menu'),b=document.getElementById('lang');if(!m||!b)return;buildLangMenu();
  const r=b.getBoundingClientRect();m.style.top=(r.bottom+8)+'px';m.style.left='auto';
  m.style.right=Math.max(8,window.innerWidth-r.right)+'px';m.classList.add('on');}
function closeLangMenu(){const m=document.getElementById('lang-menu');if(m)m.classList.remove('on');}
{const lb=document.getElementById('lang');if(lb)lb.onclick=(e)=>{e.stopPropagation();const m=document.getElementById('lang-menu');
   if(m&&m.classList.contains('on'))closeLangMenu();else openLangMenu();};
 document.addEventListener('click',(e)=>{const m=document.getElementById('lang-menu');if(!m||!m.classList.contains('on'))return;
   if(m.contains(e.target)||(e.target.closest&&e.target.closest('#lang')))return;closeLangMenu();});}
(function(){try{var st=document.createElement('style');st.textContent='#lang-menu{position:fixed;z-index:9997}';document.head.appendChild(st);}catch(e){}})();
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
  stateEl.textContent=s==='listening'?t('state.listening'):s==='thinking'?t('state.thinking'):t('state.idle');}
// cor de acento viva (segue o modo foco) — para superfícies em canvas/WebGL
function ACC(){return (getComputedStyle(document.body).getPropertyValue('--accent')||'').trim()||'#35c8ff';}
function ACCN(a){return 'rgba('+((getComputedStyle(document.body).getPropertyValue('--accent-rgb')||'').trim()||'53,200,255')+','+a+')';}
function _idleLabel(){if(stateEl)stateEl.textContent=(_hf||_ambient||_convo)?t('state.listening'):t('state.idle');}
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
$('#qc-fab').onclick=()=>openQuickCapture();
$('#modal').onclick=e=>{if(e.target.id==='modal')e.target.classList.remove('on');};
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
function emptyState(icon,title,hint){const w=el('div','tv-empty tv-empty-ic');
  const ic=el('div','tv-empty-icon');ic.appendChild(ficon(icon));w.appendChild(ic);
  w.appendChild(el('div','tv-empty-title',title));
  if(hint)w.appendChild(el('div','tv-empty-hint',hint));
  return w;}
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
  const day=d.exp_day||[];mk('ch-day',{type:'bar',data:{labels:day.map(x=>x.label),datasets:[{data:day.map(x=>x.value),backgroundColor:ACC(),borderRadius:4}]},options:{plugins:{legend:{display:false}},scales:{x:{grid:{color:grid}},y:{grid:{color:grid}}}}});
  const hab=d.habits||[];mk('ch-hab',{type:'bar',data:{labels:hab.map(x=>x.label),datasets:[{data:hab.map(x=>x.value),backgroundColor:ACC(),borderRadius:4}]},options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{grid:{color:grid}},y:{grid:{color:grid}}}}});
  // 1. Interações ao longo do tempo (você vs E.V.)
  const it=d.interactions||{labels:[],user:[],model:[]};mk('ch-int',{type:'line',data:{labels:it.labels||[],datasets:[{label:t('chart.you'),data:it.user||[],borderColor:PAL[0],backgroundColor:PAL[0],tension:.3,fill:false},{label:'E.V.',data:it.model||[],borderColor:PAL[5],backgroundColor:PAL[5],tension:.3,fill:false}]},options:{plugins:{legend:{position:'top'}},scales:{x:{grid:{color:grid}},y:{beginAtZero:true,grid:{color:grid}}}}});
  // 2. Uso de provedor de IA
  const pr=d.providers||[];mk('ch-prov',{type:'doughnut',data:{labels:pr.map(x=>x.label),datasets:[{data:pr.map(x=>x.value),backgroundColor:PAL,borderColor:'#04070c',borderWidth:2}]},options:{plugins:{legend:{position:'right'}}}});
  // 3. Atividade por tipo (barra horizontal)
  const ac=d.activity||[];mk('ch-act',{type:'bar',data:{labels:ac.map(x=>x.label),datasets:[{data:ac.map(x=>x.value),backgroundColor:ACC(),borderRadius:4}]},options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:grid}},y:{grid:{color:grid}}}}});
  // 4. Tarefas: criadas vs concluídas
  const tk=d.tasks_daily||{labels:[],created:[],completed:[]};mk('ch-task',{type:'bar',data:{labels:tk.labels||[],datasets:[{label:t('chart.created'),data:tk.created||[],backgroundColor:PAL[0],borderRadius:4},{label:t('chart.completed'),data:tk.completed||[],backgroundColor:PAL[4],borderRadius:4}]},options:{plugins:{legend:{position:'top'}},scales:{x:{grid:{color:grid}},y:{beginAtZero:true,grid:{color:grid}}}}});
  // 5. Crescimento da memória (cumulativo)
  const mg=d.memory_growth||{labels:[],values:[]};mk('ch-mem',{type:'line',data:{labels:mg.labels||[],datasets:[{label:t('chart.memories'),data:mg.values||[],borderColor:PAL[2],backgroundColor:ACCN(.15),tension:.3,fill:true}]},options:{plugins:{legend:{display:false}},scales:{x:{grid:{color:grid}},y:{beginAtZero:true,grid:{color:grid}}}}});}
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
function ev(t){const d=el('div','msg ev');sfx('recv');revealReply(d,t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function sys(t){const d=el('div','msg sys',t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function thinking(){const d=el('div','msg ev');d.innerHTML='<span class="tp"><i></i><i></i><i></i></span>';log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ripple(b,e){const r=el('span','ripple');const q=b.getBoundingClientRect(),s=Math.max(q.width,q.height);
  r.style.width=r.style.height=s+'px';r.style.left=((e?e.clientX:q.left+q.width/2)-q.left-s/2)+'px';
  r.style.top=((e?e.clientY:q.top+q.height/2)-q.top-s/2)+'px';b.appendChild(r);setTimeout(()=>r.remove(),500);sfx('click');}
let _audio=null,_audioMsg=false,_speaking=false;
function stopSpeaking(){try{if(_audio){_audio.pause();_audio.currentTime=0;}}catch(e){}_speaking=false;document.body.classList.remove('speaking');_idleLabel();}
// audio-reactive visualizer for the live voice screen (Web Audio analyser on _audio)
let _actx=null,_analyser=null,_vizData=null,_vizSrc=null;
function ensureViz(){if(_analyser||!_audio)return;
  try{_actx=new (window.AudioContext||window.webkitAudioContext)();
    _vizSrc=_actx.createMediaElementSource(_audio);_analyser=_actx.createAnalyser();_analyser.fftSize=128;
    _vizSrc.connect(_analyser);_analyser.connect(_actx.destination);
    _vizData=new Uint8Array(_analyser.frequencyBinCount);}catch(e){_analyser=null;}}
function resumeAudioCtx(){try{if(_actx&&_actx.state==='suspended')_actx.resume();}catch(e){}}
function vizFrame(){requestAnimationFrame(vizFrame);
  // amplitude drives the reactive presence orb (CSS var --talk) everywhere
  let amp=0;
  if(_speaking&&_analyser){_analyser.getByteFrequencyData(_vizData);let s=0;for(let i=0;i<_vizData.length;i++)s+=_vizData[i];amp=s/_vizData.length/255;}
  document.documentElement.style.setProperty('--talk',amp.toFixed(3));
  document.body.classList.toggle('talking',_speaking);
  const cv=document.getElementById('vc-viz');if(!cv)return;
  const open=vc&&vc.classList.contains('on');
  cv.style.opacity=(open&&_speaking)?'1':'0';
  const ctx=cv.getContext('2d');const W=cv.width,H=cv.height;ctx.clearRect(0,0,W,H);
  if(!open||!_speaking||!_analyser)return;
  const cx=W/2,cy=H/2,R=Math.min(W,H)*0.24,N=_vizData.length;
  ctx.lineWidth=3.4;ctx.lineCap='round';ctx.strokeStyle=ACCN('.92');
  for(let i=0;i<N;i++){const a=(i/N)*Math.PI*2-Math.PI/2;const v=_vizData[i]/255;const len=R*0.2+v*R*0.95;
    ctx.globalAlpha=0.3+v*0.7;
    ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*R,cy+Math.sin(a)*R);ctx.lineTo(cx+Math.cos(a)*(R+len),cy+Math.sin(a)*(R+len));ctx.stroke();}
  ctx.globalAlpha=1;}
requestAnimationFrame(vizFrame);
function unlockAudio(){if(!_audio)_audio=new Audio();ensureViz();resumeAudioCtx();try{_audio.play().catch(()=>{});}catch(e){}}
window.addEventListener('pointerdown',unlockAudio,{once:true});
// --- UI sound design (synth blips via WebAudio, no assets) ---
let _sfxOn=localStorage.getItem('ev_sfx')!=='0',_sfxCtx=null;
function sfxCtx(){if(!_sfxCtx){try{_sfxCtx=new (window.AudioContext||window.webkitAudioContext)();}catch(e){}}if(_sfxCtx&&_sfxCtx.state==='suspended')_sfxCtx.resume();return _sfxCtx;}
function blip(f0,f1,dur,type,vol){const c=sfxCtx();if(!c)return;const o=c.createOscillator(),g=c.createGain();o.type=type||'sine';
  o.frequency.setValueAtTime(f0,c.currentTime);if(f1)o.frequency.exponentialRampToValueAtTime(f1,c.currentTime+dur);
  g.gain.setValueAtTime(0,c.currentTime);g.gain.linearRampToValueAtTime(vol||0.05,c.currentTime+0.008);g.gain.exponentialRampToValueAtTime(0.0001,c.currentTime+dur);
  o.connect(g);g.connect(c.destination);o.start();o.stop(c.currentTime+dur+0.02);}
function sfx(name){if(!_sfxOn)return;try{
  if(name==='click')blip(620,720,0.05,'triangle',0.025);
  else if(name==='send')blip(680,1180,0.12,'sine',0.045);
  else if(name==='recv')blip(1180,760,0.14,'sine',0.04);
  else if(name==='confirm')blip(560,860,0.11,'sine',0.055);
  else if(name==='error')blip(200,120,0.2,'sawtooth',0.05);
  else if(name==='boot')blip(280,900,0.55,'sine',0.05);
  else if(name==='toggle')blip(900,900,0.05,'square',0.03);
  else if(name==='wake')blip(760,1320,0.13,'sine',0.05);}catch(e){}}
function wakePulse(){const b=document.body;b.classList.remove('heard');void b.offsetWidth;b.classList.add('heard');setTimeout(()=>b.classList.remove('heard'),700);}
function toggleSfx(){_sfxOn=!_sfxOn;localStorage.setItem('ev_sfx',_sfxOn?'1':'0');const b=$('#sfx');if(b)b.classList.toggle('on',_sfxOn);if(_sfxOn)sfx('toggle');}
{const _sb=$('#sfx');if(_sb){_sb.classList.toggle('on',_sfxOn);_sb.onclick=toggleSfx;}}
// --- decode/typewriter reveal for E.V.'s replies ---
function revealReply(box,text){
  const reduced=window.matchMedia&&window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  if(reduced||!text||text.length>420){renderReply(box,text);return;}
  const G='01<>/\\|=+*#λΦ◇◆∆ANDXYZ';const pre=el('div','decoding');box.textContent='';box.appendChild(pre);
  let i=0;const stepN=Math.max(2,Math.ceil(text.length/24));
  const iv=setInterval(()=>{i+=stepN;
    if(i>=text.length){clearInterval(iv);renderReply(box,text);if(window.lucide)lucide.createIcons();if(log)log.scrollTop=log.scrollHeight;return;}
    let s=text.slice(0,i);for(let k=0;k<7&&i+k<text.length;k++){const ch=text[i+k];s+=(ch===' '||ch==='\n')?ch:G[(Math.random()*G.length)|0];}
    pre.textContent=s;if(log)log.scrollTop=log.scrollHeight;
  },26);
}
// canal único de voz: SEMPRE para o áudio anterior antes de tocar o novo,
// pra E.V. nunca falar por cima de si mesma (saudação, TTS, modo foco…).
let _speakSeq=0;
function playVoice(url){if(!_audio)_audio=new Audio();
  try{_audio.pause();_audio.currentTime=0;}catch(e){}
  const seq=++_speakSeq;ensureViz();resumeAudioCtx();_audio.src=url;
  _speaking=true;document.body.classList.add('speaking');if(stateEl)stateEl.textContent=t('state.speaking');
  _audio.onended=()=>{if(seq!==_speakSeq)return;_speaking=false;document.body.classList.remove('speaking');_idleLabel();};
  return _audio.play().catch(()=>{if(seq!==_speakSeq)return;_speaking=false;document.body.classList.remove('speaking');_idleLabel();if(!_audioMsg){_audioMsg=true;sys(TR('audio.blocked'));}});}
async function speak(t,force){if((!voiceOn&&!force)||!t)return;try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text:t})});if(!r.ok)return;await playVoice(URL.createObjectURL(await r.blob()));}catch(e){_speaking=false;document.body.classList.remove('speaking');_idleLabel();}}

async function send(msg){if(!msg)return;you(msg);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/chat/stream',{method:'POST',headers:H(),body:JSON.stringify({message:msg,thread})});
    if(r.status===401){p.remove();sys(TR('sys.tokenInvalid'));localStorage.removeItem('ev_token');return;}
    p.remove();
    if(!r.body){const t=await r.text();ev(t);speak(t);loadPanel();return;}          // fallback: no streaming
    const bubble=ev('');const reader=r.body.getReader();const dec=new TextDecoder();let full='';
    while(true){const{done,value}=await reader.read();if(done)break;full+=dec.decode(value,{stream:true});renderReply(bubble,full);log.scrollTop=log.scrollHeight;}
    speak(full);loadPanel();
  }catch(e){p.remove();sys(TR('sys.noConn')+e);}finally{setState();}}
// interactive /menu — tappable chips grouped by area (like the Telegram button menu)
const MENU=[
  {h:'menu.gView',gi:'eye',items:[
    {c:'/tarefas',l:'cat.tarefas',i:'list-checks'},{c:'/lembretes',l:'cat.lembretes',i:'alarm-clock'},
    {c:'/gastos',l:'cat.gastos',i:'wallet'},{c:'/calendario',l:'cat.calendario',i:'calendar'},
    {c:'/habitos',l:'cat.habitos',i:'repeat'},{c:'/diario',l:'cat.diario',i:'notebook-pen'},
    {c:'/memorias',l:'cat.memorias',i:'brain'},{c:'/links',l:'cat.map0',i:'link'},
    {c:'/relatorio',l:'cat.relatorio',i:'bar-chart-3'},{c:'/semana',l:'cat.semana',i:'calendar-days'},
    {c:'/emails',l:'menu.emails',i:'mail'},
    {c:'/status',l:'cat.status',i:'activity'},{c:'/dados',l:'cat.dados',i:'database'}]},
  {h:'menu.gCreate',gi:'plus-circle',items:[
    {c:'/tarefa',l:'menu.task',i:'plus',fill:1},{c:'/lembrete',l:'menu.reminder',i:'alarm-clock',fill:1},
    {c:'/gasto',l:'menu.expense',i:'wallet',fill:1},{c:'/evento',l:'menu.event',i:'calendar-plus',fill:1},
    {c:'/email',l:'menu.email',i:'mail',fill:1},{c:'/link',l:'menu.link',i:'link',fill:1},
    {c:'/kb',l:'menu.kbnote',i:'book-open',fill:1}]},
  {h:'menu.gTools',gi:'wand-2',items:[
    {c:'/foco',l:'cat.foco',i:'timer',pomo:1},{c:'/buscar',l:'cat.buscar',i:'search',fill:1},
    {c:'/procurar',l:'cat.procurar',i:'file-search',fill:1},{c:'/resumir',l:'menu.summarize',i:'link',fill:1},
    {c:'/noticias',l:'cat.noticias',i:'newspaper'},{c:'/clima',l:'cat.clima',i:'cloud-sun',fill:1},
    {c:'/quiz',l:'cat.quiz',i:'graduation-cap'}]},
  {h:'menu.gSettings',gi:'settings',items:[
    {c:'/provedor',l:'menu.provider',i:'server',fill:1},{c:'/modelo',l:'sm.model',i:'cpu'},
    {c:'/silenciar',l:'menu.mute',i:'bell-off',fill:1},{c:'/ajuda',l:'menu.help',i:'help-circle'}]},
];
function showMenu(){const d=el('div','msg ev');
  const h=el('span','h');h.appendChild(ficon('layout-grid'));h.appendChild(document.createTextNode(t('menu.header')));d.appendChild(h);
  MENU.forEach(g=>{const sub=el('div','sub');sub.appendChild(ficon(g.gi));const sp=el('span','');sp.textContent=t(g.h);sub.appendChild(sp);d.appendChild(sub);
    const wrap=el('div','mchips');
    g.items.forEach(it=>{const b=el('button','mchip');b.type='button';b.appendChild(ficon(it.i));b.appendChild(document.createTextNode(t(it.l)));
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
  txt.value='';hideSlash();if(!m)return;sfx('send');
  if(m.startsWith('/')){const raw=m.slice(1).trim().toLowerCase();
    if(raw==='modo'||raw.startsWith('modo ')){
      const arg=raw.split(/\s+/)[1]||'';const on=arg==='off'?false:arg==='on'?true:!_serious;
      applySerious(on,true);fetch('/api/serious',{method:'POST',headers:H(),body:JSON.stringify({on})}).catch(()=>{});
      sys(on?'Modo foco ativado.':'Modo foco desativado.');return;}
    runCmd(m.slice(1));}
  else send(m);};

const CAT={inicio:['cat.inicio','layout-dashboard'],plano:['cat.plano','sunrise'],pendencias:['cat.pendencias','bell-ring'],padroes:['cat.padroes','sparkles'],automacoes:['cat.automacoes','zap'],bak:['cat.bak','database-backup'],tarefas:['cat.tarefas','list-checks'],lembretes:['cat.lembretes','alarm-clock'],gastos:['cat.gastos','wallet'],memorias:['cat.memorias','brain'],kb:['cat.kb','book-open'],map:['cat.map','map'],graf:['cat.graf','bar-chart-3'],brain:['cat.brain','brain-circuit'],musica:['cat.musica','music'],metas:['cat.metas','target'],saude:['cat.saude','heart-pulse'],cofre:['cat.cofre','folder-lock'],painel:['cat.painel','satellite-dish'],cam:['cat.cam','camera'],buscar:['cat.buscar','search'],noticias:['cat.noticias','newspaper'],clima:['cat.clima','cloud-sun'],relatorio:['cat.relatorio','bar-chart-3'],status:['cat.status','activity'],semana:['cat.semana','calendar-days'],foco:['cat.foco','timer'],procurar:['cat.procurar','file-search'],calendario:['cat.calendario','calendar'],habitos:['cat.habitos','repeat'],diario:['cat.diario','notebook-pen'],orcamentos:['cat.orcamentos','piggy-bank'],assinaturas:['cat.assinaturas','credit-card'],dados:['cat.dados','database'],insights:['cat.insights','sparkles'],quiz:['cat.quiz','graduation-cap']};
const SM={tasks:['sm.tasks','list-checks','tarefas'],reminders:['sm.reminders','alarm-clock','lembretes'],expenses:['sm.expenses','wallet','gastos'],memories:['sm.memories','brain','memorias'],kb:['sm.kb','book-open','kb'],kbfiles:['sm.kbfiles','file-text','kb'],links:['sm.links','link','links'],habits:['sm.habits','repeat','habitos'],journal:['sm.journal','notebook-pen','diario'],subscriptions:['sm.subscriptions','credit-card','assinaturas'],budgets:['sm.budgets','piggy-bank','orcamentos'],watches:['sm.watches','radar','monitores'],agenda:['sm.agenda','calendar','calendario'],activity:['sm.activity','history','status'],provider:['sm.provider','cpu','status'],model:['sm.model','box','modelo'],disk:['sm.disk','hard-drive','status'],ram:['sm.ram','memory-stick','status'],uptime:['sm.uptime','clock','status']};
function RECUR(){return [{v:'',l:t('recur.once')},{v:'daily',l:t('recur.daily')},{v:'weekly',l:t('recur.weekly')},{v:'monthly',l:t('recur.monthly')}];}
const RECUR_LBL={daily:'repete diário',weekly:'repete semanal',monthly:'repete mensal'};
let config={actions:['plano','buscar','noticias','clima','relatorio','semana'],stats:['tasks','reminders','expenses','memories','kb']};let _counts={};
function renderStats(){const box=$('#stats');box.textContent='';config.stats.forEach(k=>{const m=SM[k];if(!m)return;
  const VMAP={tasks:'tasks',reminders:'rem',expenses:'exp',memories:'mem',kb:'kb',kbfiles:'kb',links:'lnk',habits:'hab',journal:'jou',subscriptions:'sub',budgets:'orc',watches:'mon',agenda:'cal',activity:'act'};
  const s=el('div','stat');s.onclick=()=>{if(VMAP[k])switchView(VMAP[k]);else runCmd(m[2]);};const lbl=el('span','lbl');lbl.appendChild(ficon(m[1]));lbl.appendChild(document.createTextNode(t(m[0])));
  const num=el('span','num');if(k==='expenses'){const rs=el('span','','R$');rs.style.cssText='font-size:12px;color:var(--subtle);margin-right:2px';num.appendChild(rs);}
  num.appendChild(document.createTextNode(_counts[k]!=null?_counts[k]:'0'));s.appendChild(lbl);s.appendChild(num);box.appendChild(s);});window.lucide&&lucide.createIcons();}
function renderActs(){const box=$('#acts');box.textContent='';config.actions.forEach(cmd=>{const m=CAT[cmd]||[cmd,'chevron-right'];
  const b=el('button','act');b.appendChild(ficon(m[1]));b.appendChild(document.createTextNode(t(m[0])));
  b.onclick=e=>{if(cmd==='foco'){openPomo(25);return;}ripple(b,e);if(cmd==='cam'){$('#cambtn').click();return;}if(cmd==='bak'){window.location='/api/backup?k='+encodeURIComponent(token);toast(t('toast.backupDl'));return;}if(VIEWS[cmd]){switchView(cmd);return;}runCmd(cmd,b,e);};box.appendChild(b);});window.lucide&&lucide.createIcons();}
let _serious=false;
// announce=true só quando o usuário aciona (toggle/comando). No carregamento
// (sync via loadPanel) NÃO fala nem anima — pra não atropelar a saudação.
function applySerious(on,announce){on=!!on;document.body.classList.toggle('serious',on);
  if(on===_serious)return;_serious=on;
  if(on&&_bnd)applyBnd(false);  // modos mutuamente exclusivos
  if(!announce)return;
  const fx=$('#serfx');if(fx){fx.classList.remove('sweep');void fx.offsetWidth;fx.classList.add('sweep');}
  try{if(window.speak)speak(on?'Modo foco ativado. Foco total.':'Modo foco desativado. De volta ao normal.');}catch(e){}}
function toggleSerious(){const on=!_serious;applySerious(on,true);
  fetch('/api/serious',{method:'POST',headers:H(),body:JSON.stringify({on})}).catch(()=>{});}
{const mb=$('#mm-badge');if(mb)mb.onclick=()=>toggleSerious();}
// --- Brand New Day: tema arc-reactor azul, opt-in client-side, independente do modo foco ---
let _bnd=false;
function applyBnd(on){on=!!on;document.body.classList.toggle('bnd',on);_bnd=on;
  const b=$('#theme');if(b)b.classList.toggle('on',on);
  // modos mutuamente exclusivos: ligar Brand New Day desliga o Modo Foco
  if(on&&_serious){applySerious(false,false);try{fetch('/api/serious',{method:'POST',headers:H(),body:JSON.stringify({on:false})}).catch(()=>{});}catch(e){}}
  try{if(on)localStorage.setItem('ev_theme','bnd');else localStorage.removeItem('ev_theme');}catch(e){}}
function toggleBnd(){applyBnd(!_bnd);try{sfx('toggle');}catch(e){}}
// --- Color-theme picker menu (mirrors #brain-menu): Normal vs Brand New Day ---
function buildThemeMenu(){const m=$('#theme-menu');if(!m)return;m.textContent='';
  const mk=(label,icon,active,fn)=>{const b=el('button','');b.setAttribute('role','menuitemradio');b.setAttribute('aria-checked',active?'true':'false');
    if(active)b.classList.add('on');
    b.appendChild(ficon(icon));
    b.appendChild(el('span','tm-lbl',label));
    const ck=ficon('check');ck.classList.add('tm-ck');b.appendChild(ck);
    b.onclick=()=>{m.classList.remove('on');fn();};m.appendChild(b);};
  mk('Normal','circle',!_bnd,()=>applyBnd(false));
  mk('Brand New Day','atom',_bnd,()=>{applyBnd(true);try{sfx('toggle');}catch(e){}});
  window.lucide&&lucide.createIcons();}
function openThemeMenu(){const m=$('#theme-menu'),b=$('#theme');if(!m||!b)return;buildThemeMenu();
  const r=b.getBoundingClientRect();m.style.top=(r.bottom+8)+'px';m.style.left='auto';
  m.style.right=Math.max(8,window.innerWidth-r.right)+'px';m.classList.add('on');}
function closeThemeMenu(){const m=$('#theme-menu');if(m)m.classList.remove('on');}
{const tb=$('#theme');if(tb)tb.onclick=(e)=>{e.stopPropagation();const m=$('#theme-menu');
   if(m&&m.classList.contains('on'))closeThemeMenu();else openThemeMenu();};
 // clicar fora fecha o menu (espelha o comportamento do #brain-menu)
 document.addEventListener('click',(e)=>{const m=$('#theme-menu');if(!m||!m.classList.contains('on'))return;
   if(m.contains(e.target)||(e.target.closest&&e.target.closest('#theme')))return;closeThemeMenu();});
 try{if(localStorage.getItem('ev_theme')==='bnd')applyBnd(true);}catch(e){}}
async function loadPanel(){const _t0=(window.performance||Date).now();try{const r=await fetch('/api/panel',{headers:H()});if(!r.ok)return;_counts=await r.json();
  applySerious(_counts.serious);
  renderStats();$('#s-prov').textContent=_counts.provider;$('#s-model').textContent=_counts.model;$('#prov').value=_counts.provider;updateNBadge(_counts.notifs);
  const lat=Math.round((window.performance||Date).now()-_t0),sl=$('#s-lat');if(sl)sl.textContent='~'+lat+'ms';
  const st=$('#s-status');if(st){st.textContent=t('status.online');st.classList.add('on-dot');}
  const sc=$('#s-counts');if(sc)sc.textContent='T '+(_counts.tasks||0)+' · L '+(_counts.reminders||0)+' · M '+(_counts.memories||0)+' · KB '+(_counts.kb||0);
}catch(e){const st=$('#s-status');if(st){st.textContent=t('status.reconnecting');st.classList.remove('on-dot');}}}
async function loadConfig(){try{config=await (await fetch('/api/config',{headers:H()})).json();}catch(e){}renderActs();}
async function saveConfig(){try{await fetch('/api/config',{method:'POST',headers:H(),body:JSON.stringify(config)});}catch(e){}}
$('#prov').onchange=()=>runCmd('provedor '+$('#prov').value);
async function openKeys(){let d;try{d=await (await fetch('/api/keys',{headers:H()})).json();}catch(e){return;}
  const fields=d.keys.map(k=>({key:k.field,label:k.label,type:'password',placeholder:k.set?TR('key.setKeep'):TR('key.notSet')}));
  openForm(t('form.keys'),fields,async v=>{const body={};Object.keys(v).forEach(k=>{if(v[k])body[k]=v[k];});
    if(Object.keys(body).length){const r=await (await fetch('/api/keys',{method:'POST',headers:H(),body:JSON.stringify(body)})).json();sys(TR('keys.updated')+(r.changed||[]).join(', '));loadPanel();}});}
$('#btn-keys').onclick=openKeys;
$('#btn-voice').onclick=openVoicePicker;
$('#btn-conn').onclick=openConnectors;
async function openConnectors(){
  let conns=[],keys=[];
  try{conns=(await (await fetch('/api/connectors',{headers:H()})).json()).items||[];}catch(e){}
  try{keys=(await (await fetch('/api/keys/custom',{headers:H()})).json()).keys||[];}catch(e){}
  const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('modal.connectors')));
  card.appendChild(el('div','mconf',t('conn.blurb')));
  // --- secret keys ---
  card.appendChild(el('div','tv-cat',t('conn.savedKeys')));
  const klist=el('div','vlist');
  const drawKeys=()=>{klist.textContent='';if(!keys.length)klist.appendChild(el('div','tv-empty','Nenhuma chave ainda.'));
    keys.forEach(k=>{const row=el('div','vrow');row.appendChild(el('span','vname',k.name+(k.set?' ✓':'')));
      const del=el('button','vplay');del.appendChild(ficon('trash-2'));del.onclick=async()=>{await fetch('/api/keys/custom',{method:'POST',headers:H(),body:JSON.stringify({name:k.name,clear:true})});keys=keys.filter(x=>x.name!==k.name);drawKeys();};
      row.appendChild(del);klist.appendChild(row);});};
  drawKeys();card.appendChild(klist);
  const kf=el('div','vrange');const kn=document.createElement('input');kn.className='minput';kn.placeholder='NOME_DA_CHAVE (ex: OPENWEATHER_KEY)';kn.style.marginBottom='6px';
  const kv=document.createElement('input');kv.className='minput';kv.placeholder='valor da chave';kv.type='password';
  const kb=el('button','mbtn2','Guardar chave');kb.style.marginTop='6px';
  kb.onclick=async()=>{const nm=(kn.value||'').trim().toUpperCase();if(!nm||!kv.value)return;
    const r=await fetch('/api/keys/custom',{method:'POST',headers:H(),body:JSON.stringify({name:nm,value:kv.value})});
    if(r.ok){if(!keys.find(x=>x.name===nm))keys.push({name:nm,set:true});kn.value='';kv.value='';drawKeys();sfx('confirm');}else{const e=await r.json().catch(()=>({}));toast(e.detail||TR('key.invalidName'));}};
  kf.appendChild(kn);kf.appendChild(kv);kf.appendChild(kb);card.appendChild(kf);
  // --- connectors ---
  card.appendChild(el('div','tv-cat',t('conn.connectors')));
  const clist=el('div','vlist');
  const drawConns=()=>{clist.textContent='';if(!conns.length)clist.appendChild(el('div','tv-empty','Nenhum conector ainda.'));
    conns.forEach(c=>{const row=el('div','vrow');row.appendChild(el('span','vname',c.name));
      const test=el('button','vplay');test.appendChild(ficon('play'));test.onclick=async()=>{test.classList.add('busy');const r=await (await fetch('/api/connectors/run',{method:'POST',headers:H(),body:JSON.stringify({name:c.name})})).json();test.classList.remove('busy');toast(r.ok?('→ '+r.value):(TR('common.errPrefix')+r.error));};
      const del=el('button','vplay');del.appendChild(ficon('trash-2'));del.onclick=async()=>{await fetch('/api/connectors/delete',{method:'POST',headers:H(),body:JSON.stringify({id:c.id})});conns=conns.filter(x=>x.id!==c.id);drawConns();};
      row.appendChild(test);row.appendChild(del);clist.appendChild(row);});};
  drawConns();card.appendChild(clist);
  const mk=(ph,val)=>{const i=document.createElement('input');i.className='minput';i.placeholder=ph;i.style.marginBottom='6px';if(val)i.value=val;return i;};
  const cn=mk(TR('conn.phName')),cu=mk(TR('conn.phUrl')),ch=mk(TR('conn.phHeader')),cp=mk(TR('conn.phPath'));
  [cn,cu,ch,cp].forEach(i=>card.appendChild(i));
  const parseH=()=>{const t=(ch.value||'').trim();if(!t)return{};const i=t.indexOf(':');return i>0?{[t.slice(0,i).trim()]:t.slice(i+1).trim()}:{};};
  const bar=el('div','mbar');
  const tb=el('button','mbtn2',t('common.test'));tb.onclick=async()=>{const r=await (await fetch('/api/connectors/run',{method:'POST',headers:H(),body:JSON.stringify({url:cu.value.trim(),headers:parseH(),path:cp.value.trim()})})).json();toast(r.ok?('→ '+r.value):(TR('common.errPrefix')+r.error));};
  const sv=el('button','mbtn',TR('conn.saveConnector'));sv.onclick=async()=>{if(!cn.value.trim()||!cu.value.trim().startsWith('https://')){toast(TR('conn.nameUrlReq'));return;}
    const r=await fetch('/api/connectors',{method:'POST',headers:H(),body:JSON.stringify({name:cn.value.trim(),url:cu.value.trim(),headers:parseH(),path:cp.value.trim()})});
    if(r.ok){const j=await r.json();conns.push({id:j.id,name:cn.value.trim(),url:cu.value.trim(),headers:parseH(),path:cp.value.trim()});cn.value=cu.value=ch.value=cp.value='';drawConns();sfx('confirm');}};
  const cl=el('button','mbtn2',t('common.closeBtn'));cl.onclick=()=>m.classList.remove('on');
  bar.appendChild(cl);bar.appendChild(tb);bar.appendChild(sv);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');window.lucide&&lucide.createIcons();}
async function openVoicePicker(){
  let d;try{d=await (await fetch('/api/voice',{headers:H()})).json();}catch(e){return;}
  const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('modal.voice')));
  card.appendChild(el('div','mconf',t('voice.blurb')));
  let engine=d.engine||'edge',sel=(engine==='gemini'?d.gvoice:d.voice),rate=d.rate||'+0%',pitch=d.pitch||'+0Hz';
  const SAMPLE='Olá, Ryan. Sou a E.V., sua inteligência pessoal. Tudo pronto pra você.';
  const list=el('div','vlist');
  const rows=[];
  function mkRow(id,label,eng,previewBody){
    const on=(eng===engine&&id===sel);const row=el('div','vrow'+(on?' on':''));
    row.appendChild(el('span','vname',label));
    const play=el('button','vplay');play.appendChild(ficon('play'));
    play.onclick=async e=>{e.stopPropagation();play.classList.add('busy');
      try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify(Object.assign({text:SAMPLE},previewBody))});
        if(r.ok)playVoice(URL.createObjectURL(await r.blob()));}catch(_){}
      setTimeout(()=>play.classList.remove('busy'),600);};
    row.onclick=()=>{engine=eng;sel=id;rows.forEach(x=>x.classList.remove('on'));row.classList.add('on');};
    rows.push(row);return row;}
  if((d.gemini_voices||[]).length){
    list.appendChild(el('div','vgroup',t('voice.gemini')));
    d.gemini_voices.forEach(v=>list.appendChild(mkRow(v.id,v.id+' — '+v.desc,'gemini',{gvoice:v.id})));}
  list.appendChild(el('div','vgroup',t('voice.edge')));
  (d.voices||[]).forEach(v=>list.appendChild(mkRow(v.id,v.name+(v.gender==='Female'?' ♀':(v.gender==='Male'?' ♂':'')),'edge',{voice:v.id,rate,pitch})));
  if(!(d.voices||[]).length&&!(d.gemini_voices||[]).length)list.appendChild(el('div','tv-empty',t('voice.listFail')));
  card.appendChild(list);
  const mkR=(lbl,val,min,max,unit,cb)=>{const w=el('div','vrange');const l=el('label','mlabel');l.textContent=lbl;const out=el('span','vval');out.textContent=val+unit;
    const i=document.createElement('input');i.type='range';i.min=min;i.max=max;i.step=5;i.value=val;i.oninput=()=>{out.textContent=(i.value>=0?'+':'')+i.value+unit;cb(parseInt(i.value));};
    l.appendChild(out);w.appendChild(l);w.appendChild(i);return w;};
  card.appendChild(mkR(t('voice.speed'),parseInt(rate)||0,-40,40,'%',v=>{rate=(v>=0?'+':'')+v+'%';}));
  card.appendChild(mkR(t('voice.pitch'),parseInt(pitch)||0,-40,40,'Hz',v=>{pitch=(v>=0?'+':'')+v+'Hz';}));
  const bar=el('div','mbar');const c=el('button','mbtn2',t('common.cancel'));c.onclick=()=>m.classList.remove('on');
  const s=el('button','mbtn',t('common.save'));s.onclick=async()=>{try{await fetch('/api/voice',{method:'POST',headers:H(),body:JSON.stringify({engine,voice:sel,rate,pitch})});}catch(_){}
    m.classList.remove('on');sfx('confirm');sys(TR('voice.updated')+(engine==='gemini'?' (Gemini · '+sel+').':' ('+sel+').'));};
  bar.appendChild(c);bar.appendChild(s);card.appendChild(bar);m.appendChild(card);m.classList.add('on');window.lucide&&lucide.createIcons();}
function updateNBadge(n){const b=$('#notif-badge');if(!b)return;n=n||0;b.textContent=n>99?'99+':n;b.classList.toggle('on',n>0);}
function nfmt(iso){try{const d=new Date(iso);const now=new Date();const diff=(now-d)/1000;
  if(diff<60)return 'agora';if(diff<3600)return Math.floor(diff/60)+'min';
  if(d.toDateString()===now.toDateString())return TR('time.today')+' '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})+' '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});}catch(e){return '';}}
async function openNotifs(){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('modal.notifs')));
  const list=el('div','nlist');card.appendChild(list);
  async function refresh(){let d;try{d=await (await fetch('/api/notifications',{headers:H()})).json();}catch(e){return;}
    updateNBadge(d.unread);list.textContent='';
    if(!d.items||!d.items.length){list.appendChild(emptyState('bell',t('empty.notifT'),t('empty.notifH')));window.lucide&&lucide.createIcons();return;}
    d.items.forEach(it=>{const row=el('div','nrow'+((it.read&&!it.ephemeral)?'':' unread')+(it.ephemeral?' nproac':''));
      const ico=ficon(it.ephemeral?(it.kind==='sub'?'credit-card':'wallet'):'bell');ico.classList.add('nico');row.appendChild(ico);
      const c=el('div','ncont');c.appendChild(el('div','ntitle',it.title));
      if(it.body)c.appendChild(el('div','nbody',it.body));
      if(it.created)c.appendChild(el('div','ntime',nfmt(it.created)));
      else if(it.ephemeral)c.appendChild(el('div','ntime',t('notif.activeNow')));
      row.appendChild(c);
      if(!it.ephemeral){
        const x=el('button','nx');x.appendChild(ficon('x'));x.title=t('common.delete');
        x.onclick=async(e)=>{e.stopPropagation();await fetch('/api/notifications/delete',{method:'POST',headers:H(),body:JSON.stringify({id:it.id})});refresh();};
        row.appendChild(x);
        row.onclick=async()=>{if(!it.read){await fetch('/api/notifications/read',{method:'POST',headers:H(),body:JSON.stringify({id:it.id})});refresh();}};
      }else{
        row.onclick=()=>{m.classList.remove('on');switchView(it.kind==='sub'?'sub':'orc');};
      }
      list.appendChild(row);});
    window.lucide&&lucide.createIcons();}
  const bar=el('div','mbar');
  const rd=el('button','mbtn2',t('notif.markAll'));rd.onclick=async()=>{await fetch('/api/notifications/read',{method:'POST',headers:H(),body:JSON.stringify({})});refresh();};
  const cl=el('button','mbtn2',t('notif.clearRead'));cl.onclick=async()=>{await fetch('/api/notifications/clear',{method:'POST',headers:H(),body:JSON.stringify({scope:'read'})});refresh();};
  const ok=el('button','mbtn',t('common.closeBtn'));ok.onclick=()=>m.classList.remove('on');
  bar.appendChild(rd);bar.appendChild(cl);bar.appendChild(ok);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');refresh();}
$('#btn-notifs').onclick=openNotifs;
// --- Terminal de ação da E.V. (janela flutuante; multi; interromper) — só desktop ---
let _etSeq=0,_etN=0;
function _etGeo(){try{return JSON.parse(localStorage.getItem('ev_term_geo')||'null');}catch(e){return null;}}
function _etSaveGeo(w){try{localStorage.setItem('ev_term_geo',JSON.stringify({w:w.offsetWidth,h:w.offsetHeight}));}catch(e){}}
function openTerminal(prompt){
  const w=el('div','eterm');const id=++_etSeq;
  const g=_etGeo();
  w.style.left=Math.max(8,Math.min(innerWidth-540,120+(_etN%4)*36))+'px';w.style.top=(84+(_etN%4)*30)+'px';
  if(g&&g.w)w.style.width=Math.min(g.w,innerWidth-16)+'px';
  if(g&&g.h)w.style.height=Math.min(g.h,innerHeight-16)+'px';
  _etN++;
  const head=el('div','et-head');head.appendChild(ficon('square-terminal'));
  head.appendChild(el('div','et-title','E.V. // terminal '+id));
  const mk=(icon,title,fn)=>{const b=document.createElement('button');b.title=title;b.appendChild(ficon(icon));b.onclick=e=>{e.stopPropagation();fn();};head.appendChild(b);return b;};
  mk('plus','Novo terminal',()=>openTerminal());
  mk('square','Interromper',()=>{if(w._abort)w._abort.abort();});
  mk('x',t('common.closeBtn'),()=>{if(w._abort)w._abort.abort();w.remove();});
  w.appendChild(head);
  const body=el('div','et-body');w.appendChild(body);
  const form=el('form','et-form');const inp=document.createElement('input');inp.placeholder=TR('et.askPh');
  const snd=document.createElement('button');snd.type='submit';snd.textContent='▸';form.appendChild(inp);form.appendChild(snd);w.appendChild(form);
  form.onsubmit=e=>{e.preventDefault();const v=inp.value.trim();if(!v||w._abort)return;inp.value='';etRun(w,body,v);};
  document.body.appendChild(w);etDraggable(w,head);window.lucide&&lucide.createIcons();
  try{new ResizeObserver(()=>_etSaveGeo(w)).observe(w);}catch(e){}
  if(prompt){etRun(w,body,prompt);}else setTimeout(()=>inp.focus(),30);
  return w;}
function etLine(body,cls,text){const d=el('div','et-line '+(cls||''));if(text!=null)d.textContent=text;body.appendChild(d);body.scrollTop=body.scrollHeight;return d;}
async function etRun(w,body,prompt){
  etLine(body,'et-user','❯ '+prompt);const think=etLine(body,'et-think',TR('et.thinking'));
  const ac=new AbortController();w._abort=ac;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:prompt,thread}),signal:ac.signal});
    const j=await r.json();think.remove();
    for(const s of (j.steps||[])){await new Promise(rz=>setTimeout(rz,200));if(ac.signal.aborted)break;
      const args=Object.entries(s.args||{}).map(([k,v])=>k+'='+(typeof v==='string'?'"'+v+'"':JSON.stringify(v))).join(', ');
      const ln=etLine(body,'et-act','▸ ');const b=document.createElement('b');b.textContent=s.tool;ln.appendChild(b);
      ln.appendChild(document.createTextNode('('+args+')'+(s.result?'  ✓':'')));body.scrollTop=body.scrollHeight;}
    etLine(body,'et-res','◇ '+(j.reply||'…'));try{speak(j.reply);}catch(e){}loadPanel();
  }catch(e){think.remove();etLine(body,'et-err',ac.signal.aborted?TR('et.interrupted'):TR('common.errPrefix')+e);}
  finally{w._abort=null;}}
function etDraggable(w,handle){let sx,sy,ox,oy,drag=false;
  handle.addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;const r=w.getBoundingClientRect();drag=true;sx=e.clientX;sy=e.clientY;ox=r.left;oy=r.top;handle.style.cursor='grabbing';try{handle.setPointerCapture(e.pointerId);}catch(_){}});
  handle.addEventListener('pointermove',e=>{if(!drag)return;w.style.left=Math.max(4,Math.min(innerWidth-90,ox+e.clientX-sx))+'px';w.style.top=Math.max(4,Math.min(innerHeight-40,oy+e.clientY-sy))+'px';});
  const end=()=>{drag=false;handle.style.cursor='grab';};handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);}
const _btnTerm=$('#btn-term');if(_btnTerm)_btnTerm.onclick=()=>openTerminal();
// Menu mobile (abre pelo botão "Mais" da barra de baixo) — substitui as barras laterais no celular
function openMobileMenu(){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('mobile.menu')));
  const list=el('div','');list.style.cssText='display:flex;flex-direction:column;gap:8px;margin-top:12px';
  const row=(icon,label,fn)=>{const b=el('button','act');b.style.width='100%';b.appendChild(ficon(icon));b.appendChild(document.createTextNode(label));b.onclick=()=>{m.classList.remove('on');fn();};list.appendChild(b);};
  row('folder',TR('mobile.foldersChats'),()=>{document.body.classList.remove('m-right');document.body.classList.add('m-left');});
  row('layout-dashboard',TR('view.inicio'),()=>switchView('inicio'));
  row('mic-vocal',TR('right.voice'),openVoicePicker);
  row('plug-zap',TR('right.connectors'),openConnectors);
  row('key-round',TR('right.keys'),openKeys);
  row('bell',TR('right.notifs'),openNotifs);
  row('flame',TR('mobile.focusMode'),toggleSerious);
  row('cast',TR('mobile.listenEv'),()=>{
    if(!_spDevice){toast&&toast(TR('mus.activatePlayer'));return;}
    fetch('/api/spotify/transfer',{method:'POST',headers:H(),body:JSON.stringify({device_id:_spDevice})}).then(r=>r.json()).then(j=>{toast&&toast(j.ok?TR('sp.playingVia'):TR('sp.transferFail'));setTimeout(npTick,900);}).catch(()=>{});});
  row('music','Mini-player: '+(localStorage.getItem('ev_np_off')==='1'?'desligado':'ligado'),()=>{
    const off=localStorage.getItem('ev_np_off')==='1';localStorage.setItem('ev_np_off',off?'':'1');
    if(off){npTick();}else{const e=$('#np-mini');if(e)e.classList.remove('on');}});
  row('search','Buscar / ir para…',ckOpen);
  card.appendChild(list);
  const pl=el('div','');pl.style.marginTop='14px';pl.appendChild(el('label','mlabel','Provedor de IA'));
  const ps=document.createElement('select');['auto','gemini','groq','openrouter','ollama'].forEach(o=>{const op=document.createElement('option');op.textContent=o;ps.appendChild(op);});
  try{ps.value=(_counts&&_counts.provider)||'auto';}catch(e){}
  ps.style.cssText='width:100%;margin-top:6px;background:var(--surface);border:1px solid var(--line);border-radius:10px;color:var(--fg);padding:11px;font-family:var(--mono);cursor:pointer';
  ps.onchange=()=>{runCmd('provedor '+ps.value);};pl.appendChild(ps);card.appendChild(pl);
  const bar=el('div','mbar');const c=el('button','mbtn2',t('common.closeBtn'));c.onclick=()=>m.classList.remove('on');bar.appendChild(c);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');window.lucide&&lucide.createIcons();}
function openPicker(title,sub,items,selected,onSave){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  const tt=el('div','mtitle',title);tt.appendChild(el('small','',sub));card.appendChild(tt);const sel=new Set(selected);
  items.forEach(it=>{const row=el('label','mrow');const cb=document.createElement('input');cb.type='checkbox';cb.checked=sel.has(it.key);
    cb.onchange=()=>cb.checked?sel.add(it.key):sel.delete(it.key);row.appendChild(cb);row.appendChild(el('span','',it.label));card.appendChild(row);});
  const bar=el('div','mbar');const c=el('button','mbtn2',t('common.cancel'));c.onclick=()=>m.classList.remove('on');
  const sv=el('button','mbtn',t('common.save'));sv.onclick=()=>{onSave([...sel]);m.classList.remove('on');};bar.appendChild(c);bar.appendChild(sv);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');}
function confirmDialog(msg){return new Promise(res=>{const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('common.confirm')));card.appendChild(el('div','mconf',msg));
  const bar=el('div','mbar');const c=el('button','mbtn2',t('common.cancel'));c.onclick=()=>{m.classList.remove('on');res(false);};
  const s=el('button','mbtn',t('common.confirm'));s.onclick=()=>{m.classList.remove('on');sfx('confirm');res(true);};
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
  if(onDelete){const d=el('button','mbtn2',t('common.delete'));d.style.marginRight='auto';d.onclick=()=>{m.classList.remove('on');onDelete();};bar.appendChild(d);}
  const c=el('button','mbtn2',t('common.cancel'));c.onclick=()=>m.classList.remove('on');
  const s=el('button','mbtn',t('common.save'));s.onclick=()=>{const v={};Object.keys(inp).forEach(k=>v[k]=inp[k].value.trim());m.classList.remove('on');onSave(v);};
  bar.appendChild(c);bar.appendChild(s);card.appendChild(bar);m.appendChild(card);m.classList.add('on');
  setTimeout(()=>{const f=inp[fields[0].key];f.focus();if(f.select)f.select();},60);}
function openQuickCapture(){openForm(t('form.quickCap'),[{key:'text',label:t('form.qcLabel'),type:'textarea',placeholder:t('form.qcPh')}],
  async v=>{const t=(v.text||'').trim();if(!t)return;toast(TR('toast.capturing'));
    try{const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:t,thread})});
      const j=await r.json();toast((j.reply||TR('toast.captured')).slice(0,220));loadPanel();switchView(curView);}
    catch(e){toast(TR('toast.captureFail'));}});}
window.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='j'){e.preventDefault();openQuickCapture();}});
$('#edit-acts').onclick=()=>openPicker(t('right.quickActions'),t('pick.actsSub'),Object.keys(CAT).map(k=>({key:k,label:t(CAT[k][0])})),config.actions,async l=>{config.actions=l;await saveConfig();renderActs();});
// --- custom pages (declarative dashboards) ---
let _pages=[];
async function loadPages(){try{_pages=(await (await fetch('/api/pages',{headers:H()})).json()).items||[];}catch(e){_pages=[];}renderPagesNav();}
function renderPagesNav(){const box=$('#pages-nav');if(!box)return;box.textContent='';
  if(!_pages.length){const h=el('div','tv-empty');h.style.cssText='font-size:11px;padding:2px 2px 6px';h.textContent=t('right.noPages');box.appendChild(h);return;}
  _pages.forEach(p=>{const b=el('button','act');b.style.cssText='width:100%;margin-bottom:6px;justify-content:space-between';
    const l=el('span','');l.appendChild(ficon('layout-dashboard'));l.appendChild(document.createTextNode(' '+p.name));l.style.cssText='display:flex;align-items:center;gap:8px';
    const ed=document.createElement('span');ed.textContent='✎';ed.style.cssText='opacity:.5;cursor:pointer';ed.onclick=e=>{e.stopPropagation();openPageBuilder(p);};
    b.appendChild(l);b.appendChild(ed);b.onclick=e=>{ripple(b,e);switchView('page:'+p.id);};box.appendChild(b);});}
async function renderPage(id){const pv=$('#pageview');if(!pv)return;pv.textContent='';
  const p=_pages.find(x=>String(x.id)===String(id));if(!p){pv.appendChild(el('div','tv-empty',TR('page.notFound')));return;}
  const h=el('div','tv-h');h.textContent=p.name;pv.appendChild(h);
  for(const w of (p.widgets||[])){const card=el('div','pg-card');pv.appendChild(card);try{await renderWidget(card,w);}catch(e){}}
}
async function renderWidget(card,w){
  if(w.type==='note'){card.appendChild(el('div','pg-wt',t('wtype.note')));const b=el('div','');renderReply(b,w.text||'');card.appendChild(b);}
  else if(w.type==='tasks'){card.appendChild(el('div','pg-wt',t('view.tasks')+(w.category?(' · '+w.category):'')));
    const ts=(await (await fetch('/api/tasks',{headers:H()})).json()).tasks||[];
    const f=ts.filter(t=>!w.category||(t.category||'').toLowerCase()===String(w.category).toLowerCase());
    if(!f.length)card.appendChild(el('div','tv-empty',TR('tasks.none')));else f.forEach(t=>{const r=el('div','pg-li');r.textContent=t.text;card.appendChild(r);});}
  else if(w.type==='connector'){card.appendChild(el('div','pg-wt',w.name||t('wtype.connector')));const v=el('div','pg-big','…');card.appendChild(v);
    try{const r=await (await fetch('/api/connectors/run',{method:'POST',headers:H(),body:JSON.stringify({name:w.name})})).json();v.textContent=r.ok?r.value:(TR('common.errPrefix')+r.error);}catch(e){v.textContent=TR('common.err');}}
  else if(w.type==='command'){const b=el('button','act');b.appendChild(ficon(w.icon||'zap'));b.appendChild(document.createTextNode(' '+(w.label||w.cmd)));b.onclick=e=>{ripple(b,e);runCmd(w.cmd);};card.appendChild(b);}
  else if(w.type==='spotify'){card.appendChild(el('div','pg-wt','Spotify'));const f=document.createElement('iframe');
    f.src='https://open.spotify.com/embed/'+w.kind+'/'+w.ref;f.loading='lazy';f.allow='encrypted-media';
    f.style.cssText='width:100%;height:'+((w.kind==='track'||w.kind==='episode')?'152':'352')+'px;border:0;border-radius:12px';card.appendChild(f);}
  else if(w.type==='chart'){card.appendChild(el('div','pg-wt',t('graf.expCat')));
    try{const d=await (await fetch('/api/charts',{headers:H()})).json();const cs=(d.exp_cat||[]).slice(0,8);const mx=Math.max(1,...cs.map(c=>c.value));
      if(!cs.length)card.appendChild(el('div','tv-empty',TR('exp.nonePeriod')));
      cs.forEach(c=>{const row=el('div','pg-bar');const l=el('span','l');l.textContent=c.label;const t=el('span','t');const i=document.createElement('i');i.style.width=Math.round(c.value/mx*100)+'%';t.appendChild(i);const v=el('span','v','R$ '+c.value);row.appendChild(l);row.appendChild(t);row.appendChild(v);card.appendChild(row);});}catch(e){}}
}
function openPageBuilder(page){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',page?t('page.edit'):t('page.new')));
  const nm=document.createElement('input');nm.className='minput';nm.placeholder=TR('page.namePh');nm.style.marginBottom='10px';if(page)nm.value=page.name;card.appendChild(nm);
  let widgets=page?JSON.parse(JSON.stringify(page.widgets||[])):[];
  const list=el('div','vlist');
  const draw=()=>{list.textContent='';if(!widgets.length)list.appendChild(el('div','tv-empty','Sem widgets. Adicione abaixo.'));
    widgets.forEach((w,i)=>{const row=el('div','vrow');row.appendChild(el('span','vname',w.type+(w.category?(' · '+w.category):w.name?(' · '+w.name):w.cmd?(' · '+w.cmd):w.text?' · nota':'')));
      const del=el('button','vplay');del.appendChild(ficon('trash-2'));del.onclick=()=>{widgets.splice(i,1);draw();};row.appendChild(del);list.appendChild(row);});};
  draw();card.appendChild(el('div','tv-cat',t('page.widgets')));card.appendChild(list);
  const sel=document.createElement('select');sel.className='minput';['note','tasks','connector','command','chart','spotify'].forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent={note:TR('wtype.note'),tasks:TR('view.tasks'),connector:TR('wtype.connector'),command:TR('wtype.command'),chart:TR('wtype.chart'),spotify:TR('wtype.spotify')}[t];sel.appendChild(o);});sel.style.margin='8px 0 6px';card.appendChild(sel);
  const arg=document.createElement('input');arg.className='minput';arg.placeholder='detalhe (categoria / nome do conector / comando / texto)';card.appendChild(arg);
  const add=el('button','mbtn2','+ adicionar widget');add.style.marginTop='6px';add.onclick=()=>{const t=sel.value,a=(arg.value||'').trim();const w={type:t};
    if(t==='tasks')w.category=a;else if(t==='connector')w.name=a;else if(t==='command'){w.cmd=a;w.label=a;}else if(t==='note')w.text=a;else if(t==='spotify')w.url=a;
    widgets.push(w);arg.value='';draw();};card.appendChild(add);
  const bar=el('div','mbar');const cl=el('button','mbtn2',t('common.cancel'));cl.onclick=()=>m.classList.remove('on');
  if(page){const dl=el('button','mbtn2',t('common.delete'));dl.onclick=async()=>{await fetch('/api/pages/delete',{method:'POST',headers:H(),body:JSON.stringify({id:page.id})});m.classList.remove('on');await loadPages();if(curView==='page:'+page.id)switchView('chat');};bar.appendChild(dl);}
  const sv=el('button','mbtn',t('common.save'));sv.onclick=async()=>{if(!nm.value.trim()){toast(TR('common.giveName'));return;}
    const body={name:nm.value.trim(),widgets};if(page)body.id=page.id;
    const j=await (await fetch('/api/pages',{method:'POST',headers:H(),body:JSON.stringify(body)})).json();
    m.classList.remove('on');sfx('confirm');await loadPages();switchView('page:'+(page?page.id:j.id));};
  bar.appendChild(cl);bar.appendChild(sv);card.appendChild(bar);m.appendChild(card);m.classList.add('on');window.lucide&&lucide.createIcons();}
$('#new-page')&&($('#new-page').onclick=()=>openPageBuilder(null));
$('#edit-stats').onclick=()=>openPicker(t('right.system'),t('pick.statsSub'),Object.keys(SM).map(k=>({key:k,label:t(SM[k][0])})),config.stats,async l=>{config.stats=l;await saveConfig();renderStats();});
const PT=$('#pomo-time'),PL=$('#pomo-label'),PG=$('#pomo-toggle'),PBOX=$('#pomo-timebox'),PW=$('#pomo');
let pomo={rem:1500,total:1500,brk:300,phase:'focus',run:false,timer:null};
function pfmt(){const s=Math.max(0,pomo.rem);return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
function pIcon(){PG.innerHTML='';PG.appendChild(ficon(pomo.run?'pause':'play'));window.lucide&&lucide.createIcons();}
function prender(){PT.textContent=pfmt();PW.classList.toggle('run',pomo.run);PW.classList.toggle('brk',pomo.phase==='break');}
function ptick(){if(!pomo.run)return;pomo.rem--;
  if(pomo.rem<=0){
    if(pomo.phase==='focus'){pomo.phase='break';pomo.total=pomo.brk;pomo.rem=pomo.brk;PL.textContent=t('pomo.break');speak('Foco concluído, hora da pausa.',true);}
    else{pomo.rem=0;pstop();PL.textContent=t('pomo.cycleDone');speak('Pausa concluída. Bora pro próximo ciclo.',true);}
  }prender();}
function pstart(){if(pomo.timer)clearInterval(pomo.timer);pomo.run=true;pomo.timer=setInterval(ptick,1000);prender();pIcon();}
function pstop(){pomo.run=false;if(pomo.timer){clearInterval(pomo.timer);pomo.timer=null;}prender();pIcon();}
function openPomo(mins,brk){mins=mins||25;brk=brk||5;pomo.phase='focus';pomo.brk=brk*60;pomo.total=mins*60;pomo.rem=mins*60;PL.textContent=t('pomo.focus');PW.classList.add('on');pstart();speak('Iniciando o foco. '+mins+' minutos, vamos nessa, Ryan.',true);}
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
    const add=el('span','fx','+');add.title=TR('folder.subfolder');add.onclick=e=>{e.stopPropagation();childFolder(path);};f.appendChild(add);
    if(depth>0){const up=el('span','fx','↑');up.title=TR('folder.moveRoot');up.onclick=async e=>{e.stopPropagation();
      await fetch('/api/threads/move',{method:'POST',headers:H(),body:JSON.stringify({path,parent:''})});
      if(thread===path||thread.startsWith(path+'/')){thread=thread.replace(path,label);localStorage.setItem('ev_thread',thread);}
      await switchThread(thread);};f.appendChild(up);}
    if(path!=='geral'){const x=el('span','fx','✕');x.title=TR('common.deleteT');x.onclick=e=>{e.stopPropagation();delFolder(path);};f.appendChild(x);}
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
function childFolder(parent){openForm(t('form.newSubfolder')+' "'+parent+'"',[{key:'name',label:t('field.name'),placeholder:t('field.folderPh')}],async v=>{
  const name=(v.name||'').toLowerCase().replace(/\s+/g,'-').replace(/\//g,'-');if(!name)return;
  await fetch('/api/threads',{method:'POST',headers:H(),body:JSON.stringify({name,parent})});await switchThread(parent+'/'+name);});}
async function delFolder(path){if(!(await confirmDialog(t('confirm.delFolder1')+' "'+path+'" '+t('confirm.delFolder2'))))return;
  await fetch('/api/threads/delete',{method:'POST',headers:H(),body:JSON.stringify({name:path})});
  if(thread===path||thread.startsWith(path+'/'))await switchThread('geral');else loadFolders();}
function renameFolder(path){if(path==='geral')return;const seg=path.split('/');const leaf=seg[seg.length-1];
  openForm(t('form.renameFolder'),[{key:'name',label:t('field.newName'),value:leaf}],async v=>{const nv=(v.name||'').toLowerCase().replace(/\s+/g,'-').replace(/\//g,'-');if(!nv||nv===leaf)return;
    await fetch('/api/threads/rename',{method:'POST',headers:H(),body:JSON.stringify({old:path,new:nv})});
    const np=(seg.slice(0,-1).join('/')?seg.slice(0,-1).join('/')+'/':'')+nv;
    if(thread===path||thread.startsWith(path+'/')){thread=thread.replace(path,np);localStorage.setItem('ev_thread',thread);}
    await switchThread(thread);});}
async function switchThread(name){thread=name;localStorage.setItem('ev_thread',name);scopeEl.textContent=t('bnav.chat')+' · '+name;
  document.body.classList.remove('m-left','m-right');
  loadFolders();log.textContent='';await loadHistory();}
async function loadHistory(){try{const r=await fetch('/api/history?thread='+encodeURIComponent(thread),{headers:H()});const d=await r.json();
  if(!d.messages.length){sys(t('chat.folderPrefix')+' "'+thread+'" — '+t('chat.startConv'));return;}
  d.messages.forEach(m=>m.role==='user'?youHistory(m.content):ev(m.content));}catch(e){}}
$('#newf').onclick=()=>openForm(t('form.newFolder'),[{key:'name',label:t('field.name'),placeholder:t('field.folderPh')}],async v=>{
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
function micErrMsg(e){const n=(e&&e.name)||'';return {'NotAllowedError':TR('stt.micDenied'),'NotFoundError':TR('stt.micNotFound'),'NotReadableError':TR('stt.micBusy'),'SecurityError':TR('stt.micHttps')}[n]||(TR('stt.micFail')+((e&&e.message)||e));}
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
  const cancel=el('button','ap-cancel',t('common.cancel'));cancel.onclick=()=>{p.style.display='none';if(_audA){try{_audA.pause();}catch(e){}}};
  const sendb=el('button','ap-send','Enviar');sendb.onclick=async()=>{p.style.display='none';setState('thinking');
    try{const t=await sttBlob(blob);if(t)send(t);else sys(TR('stt.notUnderstood'));}
    catch(x){sys(TR('stt.transcribeFail'));}finally{setState();}};
  p.appendChild(play);p.appendChild(info);p.appendChild(cancel);p.appendChild(sendb);p.style.display='flex';}
micBtn.onclick=async e=>{ripple(micBtn,e);
  if(!RECOK){sys(TR('stt.recUnavail'));return;}
  if(_recActive){stopRec();return;}
  $('#audprev').style.display='none';micBtn.classList.add('on');setState('listening');
  const res=await startRec(blob=>{micBtn.classList.remove('on');setState();audioConfirm(blob);});
  if(res!==true){micBtn.classList.remove('on');setState();sys(micErrMsg(res));}};

// live voice console
const vc=$('#vc'),vcTxt=$('#vc-txt'),vcMic=$('#vc-mic');
// mostra a resposta da voz com a MESMA formatação bonita do chat (sem ** cru)
function vcShowReply(reply){vcTxt.innerHTML='';const b=el('div','msg ev');renderReply(b,reply||'(sem resposta)');vcTxt.appendChild(b);}
$('#vcopen').onclick=()=>{if(!RECOK){sys(TR('stt.recUnavail'));return;}vc.classList.add('on');vcTxt.textContent=TR('vc.tapSpeak');$('#vc-sub').textContent=TR('vc.folderLine1')+thread+TR('vc.folderLine2');};
$('#vc-x').onclick=()=>{if(_recActive)stopRec();if(_hf){stopHF();renderHFBtn();}if(_convo){_convo=false;maybeStopRec();renderConvoBtn();}stopSpeaking();vc.classList.remove('on');setState(_ambient?'listening':'');};
vcMic.onclick=async()=>{
  if(!RECOK){vcTxt.textContent=TR('stt.recUnavail');return;}
  if(_recActive){stopRec();vcTxt.textContent='transcrevendo...';return;}
  vcMic.classList.add('rec');setState('listening');vcTxt.textContent=TR('vc.listening');
  const res=await startRec(async blob=>{vcMic.classList.remove('rec');setState('thinking');vcTxt.textContent=TR('vc.transcribing');
    try{const t=await sttBlob(blob);if(!t){vcTxt.textContent=TR('vc.notUnderstood2');setState();return;}
      vcTxt.textContent='"'+t+'"';
      const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:t,thread})});const j=await r.json();
      vcShowReply(j.reply);speak(j.reply,true);loadPanel();
    }catch(x){vcTxt.textContent=TR('vc.processFail');}finally{setState();}});
  if(res!==true){vcMic.classList.remove('rec');setState();vcTxt.textContent=micErrMsg(res);}};

// --- hands-free: escuta contínua + palavra de ativação "E.V." (Web Speech API) ---
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let _hf=false,_rec=null,_hfBusy=false,_ambient=false,_convo=false;
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
  finally{_hfBusy=false;setState((_hf||_ambient||_convo)?'listening':'');}}
// Single SpeechRecognition shared by hands-free (voice screen) and ambient presence.
function ensureRec(){if(_rec)return true;if(!SR)return false;
  try{_rec=new SR();}catch(e){return false;}
  _rec.lang='pt-BR';_rec.continuous=true;_rec.interimResults=true;
  _rec.onresult=ev=>{for(let i=ev.resultIndex;i<ev.results.length;i++){const res=ev.results[i];
    const txt=res[0].transcript;
    // barge-in: se a E.V. está falando e o dono a chamou de novo, cala e escuta
    if(_speaking&&hasWake(txt))stopSpeaking();
    if(!res.isFinal)continue;
    if(_convo){                             // conversa contínua: sem palavra-mágica
      if(_speaking)continue;                // ignora a própria voz da E.V. (evita loop)
      const t=txt.trim();if(t.length<2)continue;
      if(/^(parar|encerrar|tchau|chega|para)\b/i.test(t)){toggleConvo(false);speak('Encerrando a conversa. Tô por perto.',true);continue;}
      sfx('wake');wakePulse();processHF(t);continue;
    }
    const cmd=extractCommand(txt);
    if(cmd===null)continue;                 // não foi chamada pela E.V.
    sfx('wake');wakePulse();                // heard her name → chirp + orb pulse
    if(!cmd){hfSay('Pois não, Ryan?');speak('Pois não?',true);continue;}
    processHF(cmd);}};
  _rec.onerror=e=>{if(e.error==='not-allowed'||e.error==='service-not-allowed'){
    _hf=false;_ambient=false;renderHFBtn();renderAmbBtn();hfSay('Permita o microfone para escutar por voz.');}};
  _rec.onend=()=>{if(_hf||_ambient||_convo){try{_rec.start();}catch(e){}}};   // reinicia (o SR para sozinho)
  try{_rec.start();}catch(e){}
  return true;}
function maybeStopRec(){if(!_hf&&!_ambient&&!_convo&&_rec){try{_rec.onend=null;_rec.stop();}catch(e){}_rec=null;}}
function startHF(){if(!SR){vcTxt.textContent=TR('vc.handsFreeNeed');return false;}
  return ensureRec();}
function stopHF(){_hf=false;maybeStopRec();}
function renderHFBtn(){const b=$('#vc-cont');b.innerHTML='';b.appendChild(ficon(_hf?'ear':'ear-off'));
  b.appendChild(document.createTextNode(' Mãos-livres: '+(_hf?'on — diga "E.V. ..."':'off')));b.classList.toggle('on',_hf);window.lucide&&lucide.createIcons();}
$('#vc-cont').onclick=()=>{if(!SR){vcTxt.textContent=TR('vc.handsFreeNeed');return;}
  if(_hf){stopHF();setState();}else{_hf=true;if(startHF()){vcTxt.textContent=TR('vc.handsFreeOn');setState('listening');}else{_hf=false;}}renderHFBtn();};
renderHFBtn();
// Conversa contínua — fala natural, sem palavra-mágica; ela escuta, responde e escuta de novo.
function renderConvoBtn(){const b=$('#vc-convo');if(!b)return;b.innerHTML='';b.appendChild(ficon(_convo?'messages-square':'message-square-off'));
  b.appendChild(document.createTextNode(' Conversa: '+(_convo?'on — pode falar':'off')));b.classList.toggle('on',_convo);window.lucide&&lucide.createIcons();}
function toggleConvo(on){const want=(on===undefined)?!_convo:on;
  if(want&&!SR){vcTxt.textContent='Conversa por voz precisa do Chrome, Edge ou Safari.';return;}
  _convo=want;
  if(_convo){if(ensureRec()){vcTxt.textContent=TR('vc.convoOn');setState('listening');speak('Modo conversa ligado. Pode falar, Ryan.',true);}else{_convo=false;}}
  else{maybeStopRec();setState((_hf||_ambient)?'listening':'');}
  renderConvoBtn();}
$('#vc-convo')&&($('#vc-convo').onclick=()=>toggleConvo());
renderConvoBtn();
// Ambient presence — keeps listening globally so "E.V. ..." works from any screen.
function renderAmbBtn(){const b=$('#amb');if(!b)return;b.classList.toggle('on',_ambient);
  b.title=_ambient?TR('vc.ambientOn'):TR('top.ambient');
  let d=document.getElementById('amb-dot');
  if(_ambient){if(!d){d=el('div','');d.id='amb-dot';d.style.cssText='position:fixed;bottom:22px;left:22px;display:flex;align-items:center;gap:8px;padding:7px 13px;border-radius:20px;background:rgba(4,7,12,.72);border:1px solid var(--accent);color:var(--fg);font-size:12px;letter-spacing:.06em;z-index:9998;box-shadow:0 0 18px var(--glow);backdrop-filter:blur(4px)';d.innerHTML='<span style="width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent);animation:ambpulse 1.4s infinite"></span>E.V. OUVINDO';document.body.appendChild(d);if(document.body.classList.contains('ff'))d.style.backdropFilter='none';}}
  else if(d){d.remove();}}
function toggleAmb(){if(!SR){toast(TR('amb.needBrowser'));return;}
  if(_ambient){_ambient=false;maybeStopRec();setState((_hf)?'listening':'');}
  else{_ambient=true;if(!ensureRec()){_ambient=false;}else{toast(TR('amb.on'));setState('listening');}}
  renderAmbBtn();}
$('#amb').onclick=toggleAmb;
renderAmbBtn();
// view tabs — customizable: pick which appear in the header (minimalist)
const VIEW_LABELS_K={chat:'view.chat',inicio:'view.inicio',tasks:'view.tasks',exp:'view.exp',rem:'view.rem',cal:'view.cal',mem:'view.mem',lnk:'view.lnk',hab:'view.hab',jou:'view.jou',sub:'view.sub',orc:'view.orc',mon:'view.mon',act:'view.act',kb:'view.kb',map:'view.map',brain:'view.brain',graf:'view.graf',musica:'view.musica',clima:'view.clima',metas:'view.metas',saude:'view.saude',cofre:'view.cofre',painel:'view.painel',loc:'view.loc'};const VIEW_LABELS=new Proxy(VIEW_LABELS_K,{get:(o,k)=>o[k]?t(o[k]):undefined,has:(o,k)=>k in o});
// groups only drive tab ORDER + subtle separators in the topbar strip — tabsShown still controls visibility
const VIEW_GROUPS=[['grp.main',['chat','inicio']],['grp.productivity',['tasks','rem','cal','hab','jou','metas','saude']],['grp.finance',['exp','sub','orc','cofre']],['grp.knowledge',['mem','lnk','kb','brain','act']],['grp.explore',['map','graf','musica','clima','mon','painel']],['grp.automation',['loc']]];
const VIEW_ICONS={chat:'message-square',inicio:'layout-dashboard',tasks:'list-checks',exp:'wallet',rem:'alarm-clock',cal:'calendar',mem:'database',lnk:'link',hab:'repeat',jou:'book-open',sub:'credit-card',orc:'pie-chart',mon:'radar',act:'activity',kb:'library',map:'map',brain:'brain',graf:'bar-chart-3',musica:'music',clima:'cloud-sun',metas:'target',saude:'heart-pulse',cofre:'lock',painel:'layout-panel-top',loc:'terminal'};
let curView='chat',tabsShown;try{tabsShown=JSON.parse(localStorage.getItem('ev_tabs'));}catch(e){}
// default to every section — the tab strip scrolls horizontally, so nothing
// needs to be hidden just to make room; "+" still lets you trim it down.
if(!Array.isArray(tabsShown)||!tabsShown.length)tabsShown=Object.keys(VIEW_LABELS);
function renderTabs(){const box=$('#tabs');if(!box)return;box.textContent='';
  VIEW_GROUPS.forEach(g=>{const vis=g[1].filter(v=>tabsShown.includes(v)&&VIEW_LABELS[v]);if(!vis.length)return;
    box.appendChild(el('span','tab-group-label',t(g[0])));
    vis.forEach(v=>{const b=el('button','tab'+(v===curView?' on':''),VIEW_LABELS[v]);b.dataset.view=v;b.onclick=()=>switchView(v);box.appendChild(b);});});
  const ed=el('button','tab tab-edit','+');ed.title=t('tabs.pick');ed.onclick=()=>openPicker(t('tabs.pickTitle'),t('tabs.pickSub'),Object.keys(VIEW_LABELS).map(k=>({key:k,label:VIEW_LABELS[k]})),tabsShown,l=>{tabsShown=l.length?l:['chat'];localStorage.setItem('ev_tabs',JSON.stringify(tabsShown));renderTabs();});box.appendChild(ed);
  updateTabsNav();}
// click-to-scroll arrows: shown only while the strip actually overflows,
// each disabled once you've scrolled all the way to that end.
function updateTabsNav(){const box=$('#tabs'),prev=$('#tabs-prev'),next=$('#tabs-next');if(!box||!prev||!next)return;
  const max=box.scrollWidth-box.clientWidth,has=max>4;
  prev.classList.toggle('show',has);next.classList.toggle('show',has);
  prev.disabled=box.scrollLeft<=2;next.disabled=box.scrollLeft>=max-2;}
(function(){const box=$('#tabs'),prev=$('#tabs-prev'),next=$('#tabs-next');if(!box||!prev||!next)return;
  prev.onclick=()=>box.scrollBy({left:-240,behavior:'smooth'});
  next.onclick=()=>box.scrollBy({left:240,behavior:'smooth'});
  box.addEventListener('scroll',updateTabsNav);window.addEventListener('resize',updateTabsNav);})();
renderTabs();
function openSectionsSheet(){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('top.goto')));
  VIEW_GROUPS.forEach(g=>{const vis=g[1].filter(v=>VIEW_LABELS[v]);if(!vis.length)return;
    card.appendChild(el('div','msheet-label',t(g[0])));
    vis.forEach(v=>{const b=el('button','msheet-row'+(v===curView?' on':''));b.appendChild(ficon(VIEW_ICONS[v]||'circle'));b.appendChild(document.createTextNode(VIEW_LABELS[v]));
      b.onclick=()=>{m.classList.remove('on');switchView(v);};card.appendChild(b);});});
  const bar=el('div','mbar');const c=el('button','mbtn2',t('common.closeBtn'));c.onclick=()=>m.classList.remove('on');bar.appendChild(c);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');window.lucide&&lucide.createIcons();}
$('#mnav').onclick=()=>openSectionsSheet();
const VIEWS={chat:'#chatview',inicio:'#inicioview',tasks:'#taskview',exp:'#expview',rem:'#remview',cal:'#calview',mem:'#memview',lnk:'#lnkview',hab:'#habview',jou:'#jouview',sub:'#subview',orc:'#orcview',mon:'#monview',kb:'#kbview',act:'#actview',map:'#mapview',brain:'#brainview',graf:'#chartsview',musica:'#musicview',clima:'#climaview',metas:'#metasview',saude:'#saudeview',cofre:'#cofreview',painel:'#painelview',loc:'#locview'};
function switchView(v){const isPage=(''+v).indexOf('page:')===0;
  if(!isPage&&!VIEWS[v])v='chat';curView=v;document.querySelectorAll('#tabs .tab').forEach(t=>t.classList.toggle('on',t.dataset.view===v));
  document.body.classList.toggle('v-chat',v==='chat');
  document.querySelectorAll('#bnav button[data-view]').forEach(bb=>bb.classList.toggle('on',bb.dataset.view===v));
  const mnl=$('#mnav-lbl');if(mnl&&!isPage&&VIEW_LABELS[v])mnl.textContent=VIEW_LABELS[v];
  document.body.classList.remove('m-left','m-right');
  Object.entries(VIEWS).forEach(([k,sel])=>{const el2=$(sel);if(el2)el2.style.display=(k===v)?((k==='chat'||k==='brain')?'flex':'block'):'none';});
  const pv=$('#pageview');if(pv)pv.style.display=isPage?'block':'none';
  if(isPage){renderPage(v.slice(5));return;}
  ({inicio:loadInicio,tasks:loadTasks,exp:loadExp,rem:loadRem,mem:loadMem,kb:loadKB,cal:loadCal,lnk:loadLinks,hab:loadHabits,jou:loadJournal,sub:loadSub,orc:loadOrc,mon:loadMon,act:loadAct,map:loadMap,brain:loadBrain,graf:loadCharts,musica:loadMusic,clima:loadClima,metas:loadGoals,saude:loadSaude,cofre:loadCofre,painel:loadPainel,loc:loadLoc}[v]||function(){})();}
// --- Início (command center: painel de uso interativo, pegada JARVIS) ---
function ovTile(spanCls,icon,title,view,key){
  const c=el('div','ov-card '+spanCls);c.dataset.key=key||view||'';
  const h=el('div','h');h.innerHTML='<i data-lucide="'+icon+'"></i>'+title;
  const grip=el('span','grip');grip.title=TR('common.dragReorder');grip.appendChild(ficon('grip-vertical'));h.appendChild(grip);
  if(view){const go=el('span','go');go.title=TR('common.openTitle');go.appendChild(ficon('arrow-up-right'));go.onclick=()=>switchView(view);h.appendChild(go);}
  c.appendChild(h);ovDraggable(c,grip);return c;
}
let _ovDrag=null;
function ovDraggable(card,grip){
  grip.addEventListener('pointerdown',e=>{
    e.preventDefault();_ovDrag=card;card.classList.add('dragging');
    try{grip.setPointerCapture(e.pointerId);}catch(_){}
  });
  grip.addEventListener('pointermove',e=>{
    if(_ovDrag!==card)return;
    const grid=card.parentElement;if(!grid)return;
    const under=document.elementFromPoint(e.clientX,e.clientY);
    const target=under&&under.closest?under.closest('.ov-card'):null;
    if(target&&target!==card&&target.parentElement===grid){
      const r=target.getBoundingClientRect();
      if(e.clientY<r.top+r.height/2)grid.insertBefore(card,target);else grid.insertBefore(card,target.nextSibling);
    }
  });
  const end=()=>{if(_ovDrag!==card)return;card.classList.remove('dragging');_ovDrag=null;ovSaveOrder(card.parentElement);};
  grip.addEventListener('pointerup',end);grip.addEventListener('pointercancel',end);
}
function ovSaveOrder(grid){
  if(!grid)return;
  try{localStorage.setItem('ev_ov_order',JSON.stringify([...grid.children].map(c=>c.dataset&&c.dataset.key).filter(Boolean)));}catch(e){}
}
const ALL_OV_CARDS=[['tasks','ov.tasksToday'],['hab','ov.habitsToday'],['saude','ov.healthWater'],['rem','view.rem'],
  ['exp','view.exp'],['clima','ov.weatherNow'],['acoes','right.quickActions'],['metas','view.metas'],['cal','ov.agendaToday'],
  ['act','ov.recentAct'],['musica','ov.nowPlaying'],['astro','painel.astro2'],['cotacoes','ov.rates'],['mem','kb.h']];
function ovHidden(){try{return new Set(JSON.parse(localStorage.getItem('ev_ov_hidden')||'[]'));}catch(e){return new Set();}}
function ovCustomize(){const hidden=ovHidden();const visible=ALL_OV_CARDS.map(c=>c[0]).filter(k=>!hidden.has(k));
  openPicker(t('ov.customize'),t('ov.customizeSub'),
    ALL_OV_CARDS.map(c=>({key:c[0],label:t(c[1])})),visible,
    l=>{const vis=new Set(l);const newHidden=ALL_OV_CARDS.map(c=>c[0]).filter(k=>!vis.has(k));
      try{localStorage.setItem('ev_ov_hidden',JSON.stringify(newHidden));}catch(e){}
      loadInicio();});}
function ovApplyOrder(grid){
  let order=[];try{order=JSON.parse(localStorage.getItem('ev_ov_order')||'[]');}catch(e){}
  if(!order.length)return;
  const hero=grid.querySelector('.ov-hero');
  const rest=[...grid.children].filter(c=>c!==hero);
  rest.sort((a,b)=>{
    const ia=order.indexOf(a.dataset.key),ib=order.indexOf(b.dataset.key);
    return (ia<0?999:ia)-(ib<0?999:ib);
  });
  if(hero)grid.appendChild(hero);
  rest.forEach(c=>grid.appendChild(c));
}
function ovRing(pct,label){pct=Math.min(100,Math.max(0,pct||0));
  const r=el('div','ovr');r.style.setProperty('--p',pct);
  const v=el('div','rv');v.innerHTML=Math.round(pct)+'%<br><small>'+esc(label||'')+'</small>';r.appendChild(v);return r;}
async function loadInicio(){
  const grid=$('#ov-grid');const hr=new Date().getHours();
  grid.innerHTML='<div class="tv-empty">'+t('ov.syncing')+'</div>';
  let o,pan={};
  try{const r=await fetch('/api/overview',{headers:H()});o=await r.json();if(!r.ok||!o||!o.tasks)throw 0;}
  catch(e){grid.innerHTML='<div class="tv-empty">'+t('ov.loadFail')+'</div>';return;}
  try{pan=await (await fetch('/api/panel',{headers:H()})).json();}catch(e){}
  grid.innerHTML='';

  // ---- HERO: núcleo + saudação + comando + telemetria ----
  const hero=el('div','ov-hero');hero.appendChild(el('div','core'));
  const cust=el('div','customize');cust.appendChild(ficon('sliders-horizontal'));cust.appendChild(document.createTextNode(t('ov.personalize')));cust.onclick=ovCustomize;hero.appendChild(cust);
  const hz=el('div','hz');const saud=(hr<12?t('ov.morning'):hr<18?t('ov.afternoon'):t('ov.evening'));
  hz.innerHTML='<div class="g">'+saud+', Ryan.</div><div class="s">'+esc(o.greeting||t('ov.greetFallback'))+'</div>';
  const nowD=new Date();
  const remToday=(o.reminders.items||[]).map(r=>({...r,d:new Date(r.when)})).filter(r=>r.when&&!isNaN(r.d)).sort((a,b)=>a.d-b.d);
  const nextRem=remToday.find(r=>r.d>=nowD)||remToday[0];
  const firstTask=(o.tasks.items||[])[0];
  const todayBits=[];
  if(nextRem)todayBits.push('<span><i data-lucide="alarm-clock"></i>'+esc(nextRem.text)+' '+TR('time.at')+' '+nextRem.d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})+'</span>');
  if(firstTask)todayBits.push('<span><i data-lucide="list-checks"></i>'+esc(firstTask.text)+'</span>');
  if(todayBits.length){const todayEl=el('div','ov-today');todayEl.innerHTML=todayBits.join('');hz.appendChild(todayEl);}
  hero.appendChild(hz);
  const ask=el('div','ov-ask');const ai=el('input');ai.placeholder=t('ov.askPh');const ab=el('button');ab.textContent=t('ov.send');
  const fire=()=>{const q=ai.value.trim();if(!q)return;ai.value='';switchView('chat');send(q);};
  ab.onclick=fire;ai.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();fire();}});
  const mic=el('button','mic');mic.appendChild(ficon('mic'));mic.title=t('ov.talkEv');mic.onclick=()=>{const v=$('#vcopen');if(v)v.click();};
  ask.appendChild(ai);ask.appendChild(mic);ask.appendChild(ab);hero.appendChild(ask);
  const tel=el('div','ov-tel');const chip=(cls,html)=>{const t=el('div','t'+(cls?' '+cls:''));t.innerHTML=html;tel.appendChild(t);};
  chip('on',t('ov.tSystem')+' <b>'+t('status.online')+'</b>');chip('',t('ov.tAI')+' <b>'+esc(pan.provider||'auto')+'</b>');
  if(pan.model)chip('',t('ov.tModel')+' <b>'+esc(pan.model)+'</b>');
  if(pan.uptime)chip('','UPTIME <b>'+esc(pan.uptime)+'</b>');
  if(pan.ram&&pan.ram!=='—')chip('','RAM <b>'+esc(pan.ram)+'</b>');
  chip('',t('ov.tMemories')+' <b>'+(o.counts.memories||0)+'</b>');
  if(pan.notifs)chip('',t('ov.tAlerts')+' <b>'+pan.notifs+'</b>');
  hero.appendChild(tel);
  const sug=el('div','ov-sugg');
  [[t('ov.sgSummary'),'Me dá um resumo do meu dia.'],[t('ov.sgToday'),'O que eu tenho pra hoje?'],[t('ov.sgExpenses'),'Como estão meus gastos este mês?'],[t('ov.sgWeather'),'Como está o tempo hoje?']].forEach(s=>{const b=el('button');b.textContent=s[0];b.onclick=()=>{switchView('chat');send(s[1]);};sug.appendChild(b);});
  hero.appendChild(sug);grid.appendChild(hero);
  fetch('/api/notifications',{headers:H()}).then(r=>r.json()).then(nd=>{
    const items=nd.items||[];const top=items.find(it=>it.ephemeral)||items.find(it=>!it.read);
    if(!top)return;
    const ins=el('div','ov-insight');ins.appendChild(ficon(top.ephemeral?(top.kind==='sub'?'credit-card':'wallet'):'bell'));
    ins.appendChild(el('span','',top.title+(top.body?(' — '+top.body):'')));
    ins.onclick=()=>{if(top.ephemeral)switchView(top.kind==='sub'?'sub':'orc');else openNotifs();};
    hz.appendChild(ins);if(window.lucide)lucide.createIcons();}).catch(()=>{});

  // ---- Tarefas (interativo, alto) ----
  const tt=ovTile('sp4 rw2','list-checks',t('ov.tasksToday'),'tasks');
  const tbig=el('div','big');tbig.innerHTML=o.tasks.count+' <small>'+t('ov.open')+'</small>';tt.appendChild(tbig);
  const tlist=el('div','');tlist.style.margin='8px 0 2px';
  o.tasks.items.forEach(t=>{const row=el('div','ov-task');const ck=el('div','ck');ck.appendChild(ficon('check'));
    ck.onclick=async()=>{row.classList.add('done');sfx('click');await fetch('/api/tasks/complete',{method:'POST',headers:H(),body:JSON.stringify({id:t.id})});setTimeout(loadInicio,340);};
    row.appendChild(ck);row.appendChild(el('div','tx',t.text));tlist.appendChild(row);});
  if(!o.tasks.items.length)tlist.appendChild(el('div','ov-li',t('ov.nothingPending')));
  tt.appendChild(tlist);
  const tadd=el('form','ov-add');const ti=el('input');ti.placeholder=t('ov.newTask');const tb=el('button');tb.type='submit';tb.appendChild(ficon('plus'));
  tadd.onsubmit=async e=>{e.preventDefault();const v=ti.value.trim();if(!v)return;ti.value='';await fetch('/api/tasks',{method:'POST',headers:H(),body:JSON.stringify({text:v,category:'',recur:'',due:''})});loadInicio();};
  tadd.appendChild(ti);tadd.appendChild(tb);tt.appendChild(tadd);grid.appendChild(tt);

  // ---- Hábitos (anel + chips clicáveis) ----
  const hb=o.habits;const ht=ovTile('sp4','repeat',t('ov.habitsToday'),'hab');
  const hr2=el('div','ov-row2');hr2.appendChild(ovRing(hb.total?hb.done/hb.total*100:0,hb.done+'/'+hb.total));
  const hcol=el('div','');hcol.style.flex='1';
  if(hb.items&&hb.items.length){const wrap=el('div','ov-hab');hb.items.forEach(h=>{const c=el('div','c'+(h.done?' done':''));c.appendChild(ficon(h.done?'check-circle-2':'circle'));c.appendChild(document.createTextNode(h.name));
      c.onclick=async()=>{if(h.done)return;c.classList.add('done');sfx('click');await fetch('/api/habits/done',{method:'POST',headers:H(),body:JSON.stringify({id:h.id})});setTimeout(loadInicio,340);};wrap.appendChild(c);});hcol.appendChild(wrap);}
  else hcol.appendChild(el('div','ov-li',t('ov.noHabits')));
  hr2.appendChild(hcol);ht.appendChild(hr2);grid.appendChild(ht);

  // ---- Saúde & água (anel + controles) ----
  const sh=o.health||{};const st=ovTile('sp4','heart-pulse',t('ov.healthWater'),'saude');
  const sr=el('div','ov-row2');sr.appendChild(ovRing(Math.min(100,(sh.water||0)/8*100),(sh.water||0)+'/8'));
  const scol=el('div','');scol.style.flex='1';const smini=el('div','ov-mini');
  const wp=el('button');wp.appendChild(ficon('plus'));wp.appendChild(document.createTextNode(t('ov.cup')));
  wp.onclick=async()=>{sfx('click');await fetch('/api/saude',{method:'POST',headers:H(),body:JSON.stringify({water_inc:1})});loadInicio();};
  const wm=el('button');wm.appendChild(ficon('minus'));
  wm.onclick=async()=>{await fetch('/api/saude',{method:'POST',headers:H(),body:JSON.stringify({water_inc:-1})});loadInicio();};
  smini.appendChild(wp);smini.appendChild(wm);scol.appendChild(smini);
  scol.appendChild(el('div','ov-li',(sh.sleep!=null?t('ov.sleep')+': '+sh.sleep+'h':t('ov.sleep')+': —')+(sh.mood?'   ·   '+t('ov.mood')+' '+sh.mood:'')));
  sr.appendChild(scol);st.appendChild(sr);grid.appendChild(st);

  // ---- Lembretes (concluir inline + novo) ----
  const rt=ovTile('sp4','alarm-clock',t('view.rem'),'rem');
  if(o.reminders.items.length){o.reminders.items.forEach(r=>{const row=el('div','ov-task');const ck=el('div','ck');ck.appendChild(ficon('check'));ck.title=TR('common.complete');
      ck.onclick=()=>{row.classList.add('done');sfx('click');setTimeout(()=>delU('/api/reminders/delete',{id:r.id},'/api/reminders',{text:r.text,when:r.when||'',recur:r.recur||''},loadInicio,'ent.reminder'),340);};
      row.appendChild(ck);row.appendChild(el('div','tx',r.text));
      if(r.when){const d=new Date(r.when);if(!isNaN(d))row.appendChild(el('div','when',d.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})));}
      rt.appendChild(row);});}
  else rt.appendChild(el('div','ov-li',t('ov.noReminders')));
  const radd=el('div','ov-mini');radd.style.marginTop='8px';const rb=el('button');rb.appendChild(ficon('plus'));rb.appendChild(document.createTextNode(t('ov.newReminder')));rb.onclick=()=>switchView('rem');radd.appendChild(rb);rt.appendChild(radd);
  grid.appendChild(rt);

  // ---- Gastos (total + sparkline 7 dias) ----
  const et=ovTile('sp8','wallet',t('view.exp')+' · '+esc(o.expenses.label),'exp');
  const ebig=el('div','big');ebig.innerHTML='R$ '+Number(o.expenses.total).toFixed(2)+(o.expenses.top?' <small>· '+t('ov.top')+': '+esc(o.expenses.top)+'</small>':'');et.appendChild(ebig);
  const days=o.expenses.day||[];const emx=Math.max(1,...days.map(d=>d.value));
  const sp=el('div','spark');days.forEach((d,i)=>{const b=el('div','b'+(i===days.length-1?' today':''));b.style.height=Math.max(3,d.value/emx*100)+'%';b.title='R$ '+Number(d.value).toFixed(2);b.appendChild(el('span','',d.label));sp.appendChild(b);});
  et.appendChild(sp);
  const eadd=el('form','ov-add');const ei=el('input');ei.placeholder=t('ov.quickExp');const eb=el('button');eb.type='submit';eb.appendChild(ficon('plus'));
  eadd.onsubmit=async e=>{e.preventDefault();const raw=ei.value.trim();if(!raw)return;
    const mm=raw.match(/-?\d+[.,]?\d*/);const amount=mm?parseFloat(mm[0].replace(',','.')):0;
    if(!amount){if(window.toast)toast(t('ov.quickExpHint'));return;}
    const cat=(raw.match(/#(\S+)/)||[])[1]||'geral';
    const desc=raw.replace(/#\S+/,'').replace(mm[0],'').trim()||'gasto';
    ei.value='';await fetch('/api/expenses',{method:'POST',headers:H(),body:JSON.stringify({amount,description:desc,category:cat})});loadInicio();};
  eadd.appendChild(ei);eadd.appendChild(eb);et.appendChild(eadd);grid.appendChild(et);

  // ---- Clima (agora + próximas horas) ----
  const ct=ovTile('sp4','cloud-sun',t('ov.weatherNow'),'clima');
  const cbig=el('div','big');cbig.innerHTML='…';ct.appendChild(cbig);
  const cli=el('div','ov-li',t('ov.loadingForecast'));ct.appendChild(cli);const chrs=el('div','ov-hours');ct.appendChild(chrs);grid.appendChild(ct);
  fetch('/api/weather',{headers:H()}).then(r=>r.json()).then(w=>{if(w&&w.current){cbig.innerHTML=w.current.temp+'°<small> '+esc(w.current.desc||'')+'</small>';cli.textContent=t('wx.hi')+' '+w.current.high+'° · '+t('wx.lo')+' '+w.current.low+'° · '+esc(w.location||'');
    (w.hourly||[]).slice(0,6).forEach(h=>{const hh=el('div','hh');hh.appendChild(el('div','',h.time));hh.appendChild(ficon(h.icon));const tv=el('div','');tv.innerHTML='<b>'+h.temp+'°</b>';hh.appendChild(tv);chrs.appendChild(hh);});
    if(window.lucide)lucide.createIcons();}}).catch(()=>{});

  // ---- Ações rápidas (executam de verdade) ----
  const qt=ovTile('sp4','zap',t('right.quickActions'),null,'acoes');const qm=el('div','ov-mini');
  const qb=(icon,label,fn)=>{const b=el('button');b.appendChild(ficon(icon));b.appendChild(document.createTextNode(label));b.onclick=fn;qm.appendChild(b);};
  qb('sunrise',t('cat.plano'),()=>{switchView('chat');send('Monte meu plano do dia.');});
  qb('bell-ring',t('cat.pendencias'),()=>{switchView('chat');send('O que está pendente pra hoje?');});
  qb('timer',t('cat.foco'),()=>{openPomo(25);});
  qb('newspaper',t('cat.noticias'),()=>{switchView('chat');send('Me dá as notícias de hoje.');});
  qb('bar-chart-3',t('cat.relatorio'),()=>{switchView('graf');});
  qb('zap',t('form.quickCap'),()=>{openQuickCapture();});
  qt.appendChild(qm);grid.appendChild(qt);

  // ---- Metas (só se houver) ----
  if(o.goals.length){const gt=ovTile('sp4','target',t('view.metas'),'metas');o.goals.forEach(gg=>{gt.appendChild(el('div','ov-li',esc(gg.name)+' — '+gg.pct+'%'));const bar=el('div','obar');const bi=el('i');bi.style.width=Math.min(100,Math.max(0,gg.pct))+'%';bar.appendChild(bi);gt.appendChild(bar);});grid.appendChild(gt);}

  // ---- Agenda de hoje ----
  const at=ovTile('sp4','calendar',t('ov.agendaToday'),'cal');const abig=el('div','big');abig.innerHTML=(pan.agenda||0)+' <small>'+t('ov.events')+'</small>';at.appendChild(abig);
  at.appendChild(el('div','ov-li',pan.agenda?t('ov.agendaTap'):t('ov.agendaConnect')));grid.appendChild(at);

  // ---- Atividade recente (feed) ----
  const ft=ovTile('sp8','activity',t('ov.recentAct'),'act');const feed=el('div','ov-feed');ft.appendChild(feed);grid.appendChild(ft);
  fetch('/api/activity',{headers:H()}).then(r=>r.json()).then(d=>{const items=(d.items||[]).slice(0,8);
    if(!items.length){feed.appendChild(el('div','ov-li',t('ov.noActivity')));return;}
    items.forEach(a=>{const meta=ACT_ICON[a.action]||['activity',a.action];const f=el('div','f');f.appendChild(ficon(meta[0]));f.appendChild(el('div','',t(meta[1])+': '+a.label));const w=a.created?new Date(a.created):null;f.appendChild(el('div','w',(w&&!isNaN(w))?w.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):''));feed.appendChild(f);});
    if(window.lucide)lucide.createIcons();}).catch(()=>{});

  // ---- Spotify (pronto pra quando conectar) ----
  const mt=ovTile('sp4','music',t('ov.nowPlaying'),'musica');mt.appendChild(el('div','ov-li',t('ov.loading')));grid.appendChild(mt);ovSpotify(mt);

  // ---- Astronomia & pôr do sol ----
  const ast=ovTile('sp4','moon',t('painel.astro2'),'painel','astro');const astRow=el('div','ov-astro');astRow.appendChild(el('div','ov-moon'));
  const astCol=el('div','');astCol.style.flex='1';astCol.appendChild(el('div','big','…'));astCol.appendChild(el('div','ov-li',t('ov.loadingShort')));astRow.appendChild(astCol);ast.appendChild(astRow);grid.appendChild(ast);
  fetch('/api/astro',{headers:H()}).then(r=>r.json()).then(a=>{const m=a.moon||{},s=a.sun||{};
    astCol.querySelector('.big').innerHTML=(m.illum!=null?m.illum+'% <small>iluminada</small>':'—');
    const lis=astCol.querySelectorAll('.ov-li');lis[0].textContent=(m.phase||'')+(m.waxing!=null?(m.waxing?' · '+t('ov.waxing'):' · '+t('ov.waning')):'');
    if(s.sunrise||s.sunset){const su=el('div','ov-li');su.textContent='☀ '+t('wx.sunrise')+' '+(s.sunrise||'--')+' · '+t('wx.sunset')+' '+(s.sunset||'--');astCol.appendChild(su);}}).catch(()=>{});

  // ---- Cotações ----
  const cot=ovTile('sp4','trending-up',t('ov.rates'),'painel','cotacoes');const cotBody=el('div','');cotBody.appendChild(el('div','ov-li',t('ov.loading')));cot.appendChild(cotBody);grid.appendChild(cot);
  fetch('/api/radar',{headers:H()}).then(r=>r.json()).then(d=>{const rt=(d&&d.rates)||{};cotBody.innerHTML='';
    const money=(label,val)=>{const row=el('div','ov-money');row.innerHTML='<span>'+label+'</span><b>'+val+'</b>';cotBody.appendChild(row);};
    if(rt.usd)money(t('rate.usd'),'R$ '+Number(rt.usd).toFixed(2));
    if(rt.eur)money(t('rate.eur'),'R$ '+Number(rt.eur).toFixed(2));
    if(rt.btc)money(t('rate.btc'),'R$ '+Number(rt.btc).toLocaleString('pt-BR'));
    if(!cotBody.children.length)cotBody.appendChild(el('div','ov-li',t('ov.unavailNow')));}).catch(()=>{cotBody.innerHTML='';cotBody.appendChild(el('div','ov-li',t('ov.unavailNow')));});

  // ---- Base de conhecimento (chips) ----
  const cc=o.counts;const bt=ovTile('sp4','database',t('kb.h'),'mem');const chips=el('div','ov-chips');
  [[t('chip.memories'),cc.memories],[t('chip.sources'),cc.kb],[t('chip.links'),cc.links],[t('chip.journal'),cc.journal],[t('chip.places'),cc.places],[t('chip.subs'),cc.subs],[t('chip.autos'),cc.automations]].forEach(x=>chips.appendChild(el('span','ov-chip',(x[1]||0)+' '+x[0])));
  bt.appendChild(chips);grid.appendChild(bt);

  const _hid=ovHidden();
  [...grid.querySelectorAll('.ov-card')].forEach(c=>{if(c.dataset.key&&_hid.has(c.dataset.key))c.remove();});
  ovApplyOrder(grid);
  if(window.lucide)lucide.createIcons();
  startOvPoll();
}
async function ovSpotify(mt){
  let s;try{s=await (await fetch('/api/spotify/status',{headers:H()})).json();}catch(e){s=null;}
  mt.innerHTML='';const h=el('div','h');h.innerHTML='<i data-lucide="music"></i>'+t('ov.nowPlaying');
  const go=el('span','go');go.appendChild(ficon('arrow-up-right'));go.title=TR('common.openTitle');go.onclick=()=>switchView('musica');h.appendChild(go);mt.appendChild(h);
  if(!s||!s.configured){mt.appendChild(el('div','ov-li',t('ov.spConfig')));if(window.lucide)lucide.createIcons();return;}
  if(!s.connected){const b=el('button','mchip');b.appendChild(ficon('plug'));b.appendChild(document.createTextNode(t('ov.spConnect')));b.style.marginTop='4px';b.onclick=()=>window.open('/spotify/connect','_blank');mt.appendChild(b);if(window.lucide)lucide.createIcons();return;}
  let j;try{j=await (await fetch('/api/spotify/nowplaying',{headers:H()})).json();}catch(e){j={};}
  const row=el('div','ov-sp');const img=document.createElement('img');img.className='ov-sp-art';
  if(j&&j.image)img.src=j.image;else img.style.visibility='hidden';row.appendChild(img);
  const info=el('div','ov-sp-info');info.innerHTML='<div class="t">'+esc(j&&j.name?j.name:t('ov.nothingPlaying'))+'</div><div class="a">'+esc(j&&j.artists?j.artists:'—')+'</div>';row.appendChild(info);mt.appendChild(row);
  const ctl=el('div','ov-sp-ctl');const mk=(icon,action)=>{const bb=el('button');bb.appendChild(ficon(icon));bb.onclick=async()=>{await spCtl(action);setTimeout(()=>ovSpotify(mt),700);};ctl.appendChild(bb);};
  mk('skip-back','prev');mk((j&&j.playing)?'pause':'play',(j&&j.playing)?'pause':'resume');mk('skip-forward','next');mt.appendChild(ctl);
  if(j&&j.duration){const pb=el('div','ov-sp-bar');const pi=el('i');pi.style.width=Math.min(100,j.progress/j.duration*100)+'%';pb.appendChild(pi);mt.appendChild(pb);}
  if(window.lucide)lucide.createIcons();
}
let _ovPoll=null;
function startOvPoll(){if(_ovPoll)return;_ovPoll=setInterval(()=>{
  if(curView!=='inicio'){clearInterval(_ovPoll);_ovPoll=null;return;}
  const a=document.activeElement;                       // não recarrega enquanto o usuário digita
  if(a&&a.closest&&a.closest('#inicioview')&&a.tagName==='INPUT')return;
  loadInicio();},60000);}
// --- Clima (painel holográfico estilo Weather) ---
let _wxCity='';
async function loadClima(){const body=$('#wx-body');if(!body)return;
  const inp=$('#wx-city');const city=(inp&&inp.value.trim())||_wxCity||'';
  body.innerHTML='<div class="tv-empty">'+t('ov.loading')+'</div>';
  let d;try{d=await (await fetch('/api/weather'+(city?('?city='+encodeURIComponent(city)):''),{headers:H()})).json();}catch(e){body.innerHTML='<div class="tv-empty">'+t('wx.fail')+'</div>';return;}
  if(d.error){body.innerHTML='<div class="tv-empty">'+esc(d.error)+'</div>';return;}
  _wxCity=d.location;if(inp&&!inp.value)inp.value=d.location;
  body.textContent='';const C=d.current,T=d.today||{};
  const ct=(ic,title)=>{const t=el('div','wx-ct');t.appendChild(ficon(ic));t.appendChild(document.createTextNode(title));return t;};
  // current (full width)
  const cur=el('div','wx-cur');const ic=el('div','ic');ic.appendChild(ficon(C.icon));cur.appendChild(ic);
  const info=el('div','wx-info');
  info.appendChild(el('div','wx-loc',d.location));info.appendChild(el('div','wx-temp',C.temp+'°'));
  info.appendChild(el('div','wx-desc',C.desc));
  info.appendChild(el('div','wx-hl',t('wx.feels')+' '+C.feels+'°  ·  '+t('wx.hi')+' '+C.high+'°  '+t('wx.lo')+' '+C.low+'°'));
  cur.appendChild(info);body.appendChild(cur);
  // hourly (full width)
  if((d.hourly||[]).length){const c=el('div','wx-card wide');c.appendChild(ct('clock',t('wx.nextHours')));const strip=el('div','wx-hours');
    d.hourly.forEach(h=>{const b=el('div','wx-h');b.appendChild(el('div','t',h.time));b.appendChild(ficon(h.icon));b.appendChild(el('div','d',h.temp+'°'));strip.appendChild(b);});
    c.appendChild(strip);body.appendChild(c);}
  // 10-day (span 2)
  if((d.daily||[]).length){const c=el('div','wx-card span2');c.appendChild(ct('calendar-days',t('wx.tenDay')));
    const gmin=Math.min.apply(null,d.daily.map(x=>x.min)),gmax=Math.max.apply(null,d.daily.map(x=>x.max)),span=Math.max(1,gmax-gmin);
    d.daily.forEach(x=>{const row=el('div','wx-d');row.appendChild(el('span','dn',x.day));row.appendChild(ficon(x.icon));
      row.appendChild(el('span','mn',x.min+'°'));const tr=el('span','wx-track');const i=document.createElement('i');
      i.style.left=((x.min-gmin)/span*100)+'%';i.style.right=((gmax-x.max)/span*100)+'%';tr.appendChild(i);row.appendChild(tr);
      row.appendChild(el('span','mx',x.max+'°'));c.appendChild(row);});
    body.appendChild(c);}
  // metric cards
  const uvL=u=>u<3?t('wx.uvLow'):u<6?t('wx.uvMod'):u<8?t('wx.uvHigh'):u<11?t('wx.uvVHigh'):t('wx.uvExtreme');
  const metric=(ic,title,html)=>{const c=el('div','wx-card wx-m');c.appendChild(ct(ic,title));const b=document.createElement('div');b.innerHTML=html;c.appendChild(b);body.appendChild(c);};
  metric('umbrella',t('wx.rainChance'),'<div class="big">'+(C.precip_prob||0)+'%</div><div class="bar"><i style="width:'+(C.precip_prob||0)+'%"></i></div><div class="sub">'+t('wx.upTo')+' '+(T.rain_chance||0)+'% '+t('wx.throughDay')+'</div>');
  metric('wind',t('wx.wind'),'<div class="big">'+C.wind+'<span style="font-size:15px"> km/h</span></div><div class="sub">'+C.wind_dir+' ('+C.wind_deg+'°) · '+t('wx.gusts')+' '+C.gusts+' km/h</div>');
  metric('droplets',t('wx.humidity'),'<div class="big">'+(C.humidity||0)+'%</div><div class="bar"><i style="width:'+(C.humidity||0)+'%"></i></div>');
  metric('sun',t('wx.uvIndex'),'<div class="big">'+C.uv+'</div><div class="sub">'+uvL(C.uv)+' · '+t('wx.maxToday')+' '+(T.uv_max||0)+'</div>');
  metric('sunrise',t('wx.sun'),'<div class="wx-sun"><div><div class="l">'+t('wx.sunrise')+'</div><div class="v">'+(T.sunrise||'--')+'</div></div><div style="text-align:right"><div class="l">'+t('wx.sunset')+'</div><div class="v">'+(T.sunset||'--')+'</div></div></div>');
  metric('thermometer',t('wx.feelsC'),'<div class="big">'+C.feels+'°</div><div class="sub">'+t('wx.realTemp')+' '+C.temp+'°</div>');
  metric('cloud',t('wx.cloud'),'<div class="big">'+(C.cloud||0)+'%</div><div class="bar"><i style="width:'+(C.cloud||0)+'%"></i></div>');
  metric('gauge',t('wx.pressure'),'<div class="big">'+C.pressure+'<span style="font-size:14px"> hPa</span></div>');
  window.lucide&&lucide.createIcons();}
(function(){const g=$('#wx-go');if(g)g.onclick=()=>loadClima();const i=$('#wx-city');if(i)i.addEventListener('keydown',e=>{if(e.key==='Enter')loadClima();});})();
// --- Metas (cofrinho) ---
async function loadGoals(){const box=$('#gl-list');if(!box)return;box.textContent='';
  let items=[];try{items=(await (await fetch('/api/goals',{headers:H()})).json()).items||[];}catch(e){}
  if(!items.length){box.appendChild(emptyState('target',t('empty.goalsT'),t('empty.goalsH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(g=>{const pct=Math.min(100,g.target?Math.round(g.saved/g.target*100):0);
    const c=el('div','goal');const h=el('div','gh');h.appendChild(el('span','gn',g.name));h.appendChild(el('span','gv','R$ '+Math.round(g.saved)+' / '+Math.round(g.target)+' · '+pct+'%'));c.appendChild(h);
    const bar=el('div','gbar');const i=document.createElement('i');i.style.width=pct+'%';bar.appendChild(i);c.appendChild(bar);
    const ga=el('div','ga');const inp=document.createElement('input');inp.className='tv-search';inp.type='number';inp.placeholder='R$';
    const add=el('button','mchip');add.appendChild(ficon('plus'));add.appendChild(document.createTextNode('Guardar'));
    add.onclick=async()=>{const v=parseFloat(inp.value);if(!v)return;await fetch('/api/goals/add',{method:'POST',headers:H(),body:JSON.stringify({id:g.id,amount:v})});sfx('confirm');loadGoals();};
    const wd=el('button','tv-ic');wd.appendChild(ficon('minus'));wd.onclick=async()=>{const v=parseFloat(inp.value);if(!v)return;await fetch('/api/goals/add',{method:'POST',headers:H(),body:JSON.stringify({id:g.id,amount:-v})});loadGoals();};
    const del=el('button','tv-ic');del.appendChild(ficon('trash-2'));del.onclick=async()=>{await fetch('/api/goals/delete',{method:'POST',headers:H(),body:JSON.stringify({id:g.id})});loadGoals();};
    ga.appendChild(inp);ga.appendChild(add);ga.appendChild(wd);ga.appendChild(del);c.appendChild(ga);box.appendChild(c);});
  window.lucide&&lucide.createIcons();}
(function(){const b=$('#gl-add');if(b)b.onclick=async()=>{const n=$('#gl-name').value.trim(),t=parseFloat($('#gl-target').value);if(!n||!t){toast(TR('metas.nameTargetReq'));return;}
  await fetch('/api/goals',{method:'POST',headers:H(),body:JSON.stringify({name:n,target:t})});$('#gl-name').value='';$('#gl-target').value='';sfx('confirm');loadGoals();};})();
// --- Saúde & rotina ---
async function loadSaude(){const box=$('#sa-body');if(!box)return;box.textContent='';
  let d;try{d=await (await fetch('/api/saude',{headers:H()})).json();}catch(e){return;}const t=d.today||{water:0};
  const wc=el('div','sa-card');wc.appendChild(el('div','t',TR('saude.waterToday')+' · '+(t.water||0)+' '+TR('saude.cups')));
  const wrap=el('div','sa-water');for(let k=0;k<8;k++){const dp=el('span','sa-drop'+(k<(t.water||0)?' on':''));dp.appendChild(ficon('droplet'));wrap.appendChild(dp);}
  const plus=el('button','mchip');plus.appendChild(ficon('plus'));plus.onclick=async()=>{await fetch('/api/saude',{method:'POST',headers:H(),body:JSON.stringify({water_inc:1})});sfx('click');loadSaude();};
  const minus=el('button','tv-ic');minus.appendChild(ficon('minus'));minus.onclick=async()=>{await fetch('/api/saude',{method:'POST',headers:H(),body:JSON.stringify({water_inc:-1})});loadSaude();};
  wrap.appendChild(plus);wrap.appendChild(minus);wc.appendChild(wrap);box.appendChild(wc);
  const sc=el('div','sa-card');sc.appendChild(el('div','t',TR('saude.lastSleep')));
  const si=document.createElement('input');si.className='tv-search';si.type='number';si.step='0.5';si.placeholder='horas';si.value=t.sleep!=null?t.sleep:'';si.style.maxWidth='120px';
  si.onchange=async()=>{await fetch('/api/saude',{method:'POST',headers:H(),body:JSON.stringify({sleep:parseFloat(si.value)||0})});sfx('click');};sc.appendChild(si);box.appendChild(sc);
  const mc=el('div','sa-card');mc.appendChild(el('div','t',TR('saude.moodToday')));const mm=el('div','sa-mood');
  ['😄','🙂','😐','😔','😣'].forEach(e=>{const bb=document.createElement('button');bb.textContent=e;if(t.mood===e)bb.className='on';bb.onclick=async()=>{await fetch('/api/saude',{method:'POST',headers:H(),body:JSON.stringify({mood:e})});sfx('click');loadSaude();};mm.appendChild(bb);});
  mc.appendChild(mm);box.appendChild(mc);
  if((d.history||[]).length>1){const hc=el('div','sa-card');hc.appendChild(el('div','t',TR('saude.lastDays')));
    d.history.forEach(x=>{const r=el('div','');r.style.cssText='display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)';
      r.appendChild(el('span','',x.day));r.appendChild(el('span','','💧 '+(x.water||0)+'  😴 '+(x.sleep||'-')+'h  '+(x.mood||'')));hc.appendChild(r);});box.appendChild(hc);}
  window.lucide&&lucide.createIcons();}
// --- Cofre de documentos ---
async function loadCofre(){const box=$('#cf-list');if(!box)return;box.textContent='';
  const q=($('#cf-q').value||'').trim();let items=[];
  try{items=(await (await fetch('/api/vault'+(q?('?q='+encodeURIComponent(q)):''),{headers:H()})).json()).items||[];}catch(e){}
  if(!items.length){box.appendChild(q?el('div','tv-empty','Nada encontrado.'):emptyState('folder-lock',t('empty.vaultT'),t('empty.vaultH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(it=>{const r=el('div','cf-row');r.appendChild(el('span','n',it.name));r.appendChild(el('span','sz',Math.round(it.size/1024)+' KB'));
    const open=el('button','tv-ic');open.appendChild(ficon('external-link'));open.onclick=()=>window.open('/api/vault/file?id='+it.id+'&k='+encodeURIComponent(token),'_blank');
    const del=el('button','tv-ic');del.appendChild(ficon('trash-2'));del.onclick=async()=>{await fetch('/api/vault/delete',{method:'POST',headers:H(),body:JSON.stringify({id:it.id})});loadCofre();};
    r.appendChild(open);r.appendChild(del);box.appendChild(r);});
  window.lucide&&lucide.createIcons();}
(function(){const f=$('#cf-file');if(f)f.onchange=async e=>{const file=e.target.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);
  toast('enviando…');try{const r=await fetch('/api/vault',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd});if(r.ok){sfx('confirm');loadCofre();}else{const j=await r.json().catch(()=>({}));toast(j.detail||'falhou');}}catch(_){toast('falhou');}e.target.value='';};
  const q=$('#cf-q');if(q)q.addEventListener('input',()=>{clearTimeout(q._t);q._t=setTimeout(loadCofre,300);});})();
// --- Painel (astronomia + radar do mundo, meio a meio) ---
let _pdClock=null;
function pdL(icon,text){const l=el('div','l');l.appendChild(ficon(icon));l.appendChild(document.createTextNode(text));return l;}
function tickClocks(){document.querySelectorAll('#pd-clocks .h[data-tz]').forEach(h=>{try{h.textContent=new Date().toLocaleTimeString('pt-BR',{timeZone:h.getAttribute('data-tz'),hour:'2-digit',minute:'2-digit'});}catch(e){}});}
function startClocks(){if(_pdClock)return;_pdClock=setInterval(()=>{if(curView==='painel')tickClocks();else{clearInterval(_pdClock);_pdClock=null;}},1000);tickClocks();}
function relTime(iso){if(!iso)return null;const ms=Date.now()-new Date(iso).getTime();const m=Math.round(ms/60000);
  if(m<1)return TR('time.justNow');if(m<60)return TR('time.agoPrefix')+m+' min'+TR('time.agoSuffix');const h=Math.round(m/60);if(h<24)return TR('time.agoPrefix')+h+'h'+TR('time.agoSuffix');return TR('time.agoPrefix')+Math.round(h/24)+'d'+TR('time.agoSuffix');}
async function loadBackupStatus(){const B=$('#pd-backup');if(!B)return;
  let d;try{d=await(await fetch('/api/backup/status',{headers:H()})).json();}catch(e){B.innerHTML='<div class="tv-empty">'+t('painel.statusUnavail')+'</div>';return;}
  B.textContent='';const bc=el('div','pd-card pd-card-row');
  const left=el('div','');left.style.minWidth='0';
  left.appendChild(pdL('database-backup',t('panel.encBackups')));
  const rt=relTime(d.last_at);
  const rowN=el('div','');rowN.style.cssText='font-family:var(--disp);font-size:20px;color:#eaf4fb';rowN.textContent=rt?(t('panel.last')+': '+rt):t('panel.noBackup');left.appendChild(rowN);
  const sub=el('div','sub');sub.style.cssText='color:var(--muted);font-size:12px;margin-top:4px';
  sub.textContent=d.count?(d.count+' '+TR('panel.copiesStored')+(d.last_size_kb?(' · '+d.last_size_kb+' KB'):'')+' '+TR('panel.autoDaily')):TR('panel.runsAutoDaily');
  left.appendChild(sub);bc.appendChild(left);
  const btn=el('button','mbtn2',t('panel.backupNow'));btn.style.flex='none';
  btn.onclick=async()=>{btn.disabled=true;btn.textContent=t('panel.generating');
    try{await fetch('/api/backup/run',{method:'POST',headers:H()});toast(t('toast.backupOk'));await loadBackupStatus();}
    catch(e){toast(t('toast.backupErr'));btn.disabled=false;btn.textContent=t('panel.backupNow');}};
  bc.appendChild(btn);B.appendChild(bc);window.lucide&&lucide.createIcons();}
async function loadPainel(){const A=$('#pd-astro'),R=$('#pd-radar');if(!A||!R)return;
  A.innerHTML='<div class="tv-empty">'+t('ov.loading')+'</div>';R.innerHTML='<div class="tv-empty">'+t('ov.loading')+'</div>';
  loadBackupStatus();
  const zones=[['SÃO PAULO','America/Sao_Paulo'],['NOVA YORK','America/New_York'],['LONDRES','Europe/London'],['TÓQUIO','Asia/Tokyo']];
  fetch('/api/astro',{headers:H()}).then(r=>r.json()).then(d=>{A.textContent='';const moon=d.moon||{};
    const mc=el('div','pd-card');mc.appendChild(pdL('moon',t('painel.moon')));const mrow=el('div','pd-moon');mrow.appendChild(el('div','disc'));
    const mi=el('div','');mi.appendChild(el('div','big',(moon.illum||0)+'%'));mi.appendChild(el('div','sub',(moon.phase||'')+' · '+(moon.waxing?t('painel.waxing'):t('painel.waning'))));mrow.appendChild(mi);mc.appendChild(mrow);A.appendChild(mc);
    if(d.sun&&d.sun.sunrise){const sc=el('div','pd-card');sc.appendChild(pdL('sunrise',t('wx.sun')+(d.city?(' · '+d.city):'')));const sr=el('div','pd-sun');
      sr.innerHTML='<div><div class="k">'+t('wx.sunrise')+'</div><div class="v">'+d.sun.sunrise+'</div></div><div style="text-align:right"><div class="k">'+t('wx.sunset')+'</div><div class="v">'+d.sun.sunset+'</div></div>';sc.appendChild(sr);A.appendChild(sc);}
    if(d.iss&&d.iss.lat!=null){const ic=el('div','pd-card');ic.appendChild(pdL('satellite',t('painel.iss')));
      const iv=el('div','');iv.style.cssText='font-family:var(--mono);font-size:13px;color:var(--fg)';iv.textContent=d.iss.lat+'°, '+d.iss.lng+'°  ·  '+d.iss.alt+' km de altitude';ic.appendChild(iv);A.appendChild(ic);}
    window.lucide&&lucide.createIcons();}).catch(()=>{A.innerHTML='<div class="tv-empty">'+t('painel.astroUnavail')+'</div>';});
  fetch('/api/radar',{headers:H()}).then(r=>r.json()).then(d=>{R.textContent='';
    const cc=el('div','pd-card');cc.appendChild(pdL('clock',t('painel.clocks')));const cg=el('div','pd-clocks');cg.id='pd-clocks';
    zones.forEach(z=>{const cl=el('div','pd-clock');cl.appendChild(el('span','c',z[0]));const h=el('span','h','--:--');h.setAttribute('data-tz',z[1]);cl.appendChild(h);cg.appendChild(cl);});cc.appendChild(cg);R.appendChild(cc);
    const rt=d.rates||{},rc=el('div','pd-card');rc.appendChild(pdL('trending-up',t('ov.rates')));
    const mk=(k,v)=>{const r=el('div','pd-rate');r.appendChild(el('span','',k));const b=document.createElement('b');b.textContent=v;r.appendChild(b);rc.appendChild(r);};
    if(rt.usd)mk(t('rate.usd'),'R$ '+rt.usd);if(rt.eur)mk(t('rate.eur'),'R$ '+rt.eur);if(rt.btc)mk(t('rate.btc'),'R$ '+rt.btc.toLocaleString('pt-BR'));
    if(!rt.usd&&!rt.btc)rc.appendChild(el('div','tv-empty',t('painel.ratesUnavail')));R.appendChild(rc);
    const hc=el('div','pd-card');hc.appendChild(pdL('newspaper',t('painel.headlines')));const hl=el('div','pd-hl');
    (d.headlines||[]).forEach(x=>{const a=document.createElement('a');a.href=x.url;a.target='_blank';a.rel='noopener';a.textContent=x.title;hl.appendChild(a);});
    if(!(d.headlines||[]).length)hl.appendChild(el('div','tv-empty',t('painel.noHeadlines')));hc.appendChild(hl);R.appendChild(hc);
    startClocks();window.lucide&&lucide.createIcons();}).catch(()=>{R.innerHTML='<div class="tv-empty">'+t('painel.radarUnavail')+'</div>';});
}
// --- Música (Spotify embed player) ---
let _music=[];
function playEmbed(embed,compact){const box=$('#mu-player');if(!box)return;box.classList.toggle('compact',!!compact);
  box.innerHTML='';const f=document.createElement('iframe');f.src=embed+'?utm_source=ev';f.allow='autoplay; encrypted-media; clipboard-write';f.loading='lazy';f.setAttribute('allowfullscreen','');box.appendChild(f);}
function renderMusic(){const list=$('#mu-list');if(!list)return;list.textContent='';
  if(!_music.length){list.appendChild(emptyState('music',t('empty.musicT'),t('empty.musicH')));window.lucide&&lucide.createIcons();return;}
  _music.forEach(m=>{const row=el('div','mu-row');const n=el('span','n',m.label);const k=el('span','k',m.kind);
    const del=el('button','tv-ic');del.appendChild(ficon('trash-2'));del.onclick=async(e)=>{e.stopPropagation();await fetch('/api/music/delete',{method:'POST',headers:H(),body:JSON.stringify({id:m.id})});_music=_music.filter(x=>x.id!==m.id);renderMusic();};
    row.appendChild(n);row.appendChild(k);row.appendChild(del);
    row.onclick=()=>{[...list.children].forEach(c=>c.classList&&c.classList.remove('on'));row.classList.add('on');playEmbed(m.embed,m.kind==='track'||m.kind==='episode');sfx('click');};
    list.appendChild(row);});}
async function loadMusic(){try{_music=(await (await fetch('/api/music',{headers:H()})).json()).items||[];}catch(e){_music=[];}
  renderMusic();if(_music.length&&!$('#mu-player').children.length)playEmbed(_music[0].embed,_music[0].kind==='track'||_music[0].kind==='episode');
  loadSpotify();}
// --- Spotify Web API (Premium: playlists do perfil + controle de playback) ---
let _spDevice=null,_spPlayer=null,_spSdkLoading=false;
async function loadSpotify(){const box=$('#sp-section');if(!box)return;box.textContent='';
  let st;try{st=await (await fetch('/api/spotify/status',{headers:H()})).json();}catch(e){return;}
  if(!st.configured){const h=el('div','tv-empty');h.innerHTML='Pra puxar suas playlists e controlar por voz (Premium): cole o <b>Spotify Client ID/Secret</b> em <b>Chaves de API</b> e registre a Redirect URI <code>'+esc(st.redirect_uri)+'</code> no painel do Spotify.';box.appendChild(h);return;}
  if(!st.connected){const b=el('button','mbtn');b.textContent=t('mus.connectMine');b.onclick=()=>{window.open('/spotify/connect','_blank');};box.appendChild(b);
    const h=el('div','tv-empty');h.style.marginTop='8px';h.innerHTML='Registre esta Redirect URI no seu app do Spotify: <code>'+esc(st.redirect_uri)+'</code>';box.appendChild(h);return;}
  // connected → now-playing card + device/volume + search + playlists + SDK
  box.insertAdjacentHTML('beforeend',
    '<div id="sp-np" class="sp-np"><img id="sp-art" alt=""><div class="sp-info">'
    +'<div class="sp-tt" id="sp-tt">—</div><div class="sp-ar" id="sp-ar"></div>'
    +'<div class="sp-prog"><i id="sp-prog"></i></div>'
    +'<div class="sp-ctl"><button class="vcbtn" id="sp-prev"></button><button class="vcbtn" id="sp-toggle"></button>'
    +'<button class="vcbtn" id="sp-next"></button><button class="vcbtn" id="sp-like"></button></div></div></div>');
  $('#sp-prev').appendChild(ficon('skip-back'));$('#sp-next').appendChild(ficon('skip-forward'));
  $('#sp-toggle').appendChild(ficon('play'));$('#sp-like').appendChild(ficon('heart'));
  $('#sp-prev').onclick=()=>spCtl('prev');$('#sp-next').onclick=()=>spCtl('next');
  $('#sp-toggle').onclick=()=>spCtl(_spPlaying?'pause':'resume');
  $('#sp-like').onclick=()=>spLike();
  const row=el('div','');row.style.cssText='display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap';
  const dev=document.createElement('select');dev.id='sp-dev';dev.className='tv-search';dev.style.maxWidth='190px';row.appendChild(dev);
  dev.onchange=()=>{};
  const vol=document.createElement('input');vol.type='range';vol.id='sp-vol';vol.min=0;vol.max=100;vol.value=60;vol.style.cssText='flex:1;min-width:120px;accent-color:var(--accent)';
  vol.onchange=()=>{fetch('/api/spotify/volume',{method:'POST',headers:H(),body:JSON.stringify({percent:parseInt(vol.value)})});};row.appendChild(vol);
  const dc=el('button','mchip');dc.textContent=t('mus.disconnect');dc.onclick=async()=>{await fetch('/api/spotify/disconnect',{method:'POST',headers:H()});loadSpotify();};row.appendChild(dc);
  box.appendChild(row);loadSpDevices();
  // search & play anything
  const sf=el('div','');sf.style.cssText='display:flex;gap:8px;margin-bottom:10px';
  const si=document.createElement('input');si.className='tv-search';si.placeholder='buscar e tocar (ex: Bohemian Rhapsody)';si.style.flex='1';
  const sb=el('button','mchip');sb.appendChild(ficon('search'));
  const doSearch=async()=>{const q=(si.value||'').trim();if(!q)return;const res=$('#sp-results');res.textContent='…';
    try{const items=(await (await fetch('/api/spotify/search?q='+encodeURIComponent(q),{headers:H()})).json()).items||[];res.textContent='';
      if(!items.length){res.appendChild(el('div','tv-empty',t('common.nothingFound')));return;}
      items.forEach(t=>{const row=el('div','mu-row');row.appendChild(el('span','n',t.name+' — '+t.artists));
        const q=el('button','tv-ic');q.appendChild(ficon('list-plus'));q.title=TR('mus.queueAdd');q.onclick=e=>{e.stopPropagation();fetch('/api/spotify/queue',{method:'POST',headers:H(),body:JSON.stringify({uri:t.uri})}).then(()=>{sfx('click');toast(TR('mus.queued'));});};
        row.appendChild(q);row.onclick=()=>{spPlay(t.uri);};res.appendChild(row);});}catch(e){res.textContent='';}};
  sb.onclick=doSearch;si.addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();});
  sf.appendChild(si);sf.appendChild(sb);box.appendChild(sf);
  const sres=el('div','vlist');sres.id='sp-results';sres.style.maxHeight='26vh';box.appendChild(sres);
  box.appendChild(el('div','tv-cat',t('mus.myPlaylists')));const pl=el('div','vlist');pl.style.maxHeight='34vh';box.appendChild(pl);
  try{const pls=(await (await fetch('/api/spotify/playlists',{headers:H()})).json()).items||[];
    if(!pls.length)pl.appendChild(el('div','tv-empty',t('mus.noPlaylists')));
    pls.forEach(p=>{const row=el('div','mu-row');const n=el('span','n',p.name);const k=el('span','k',p.tracks+' faixas');
      row.appendChild(n);row.appendChild(k);row.onclick=()=>spPlay(p.uri);pl.appendChild(row);});}catch(e){}
  spInitSDK();spNow();startSpPoll();}
async function spCtl(action){try{await fetch('/api/spotify/control',{method:'POST',headers:H(),body:JSON.stringify({action})});}catch(e){}sfx('click');setTimeout(spNow,600);}
async function spPlay(uri){const sel=$('#sp-dev');const dev=(sel&&sel.value)||_spDevice;
  try{const r=await (await fetch('/api/spotify/play',{method:'POST',headers:H(),body:JSON.stringify({uri,device_id:dev})})).json();if(!r.ok)toast(r.error||TR('mus.cantPlay'));else{sfx('confirm');setTimeout(spNow,700);}}catch(e){}}
let _spPlaying=false,_spTrackId=null,_spPoll=null;
async function spNow(){if(!$('#sp-np'))return;try{const j=await (await fetch('/api/spotify/nowplaying',{headers:H()})).json();
  if(!$('#sp-np'))return;_spPlaying=!!j.playing;_spTrackId=j.id||null;
  $('#sp-tt').textContent=j.name||'—';$('#sp-ar').textContent=j.artists||'';
  const art=$('#sp-art');if(j.image){art.src=j.image;art.style.display='block';}else art.style.display='none';
  const p=$('#sp-prog');if(p)p.style.width=(j.duration?Math.min(100,j.progress/j.duration*100):0)+'%';
  const tg=$('#sp-toggle');if(tg){tg.innerHTML='';tg.appendChild(ficon(_spPlaying?'pause':'play'));}
  const lk=$('#sp-like');if(lk)lk.classList.toggle('on',!!j.liked);
  const vol=$('#sp-vol');if(vol&&document.activeElement!==vol&&j.volume!=null)vol.value=j.volume;
  window.lucide&&lucide.createIcons();}catch(e){}}
function spLike(){if(!_spTrackId)return;const lk=$('#sp-like');const on=!lk.classList.contains('on');
  fetch('/api/spotify/like',{method:'POST',headers:H(),body:JSON.stringify({id:_spTrackId,on})}).then(()=>{lk.classList.toggle('on',on);sfx('click');});}
async function loadSpDevices(){try{const ds=(await (await fetch('/api/spotify/devices',{headers:H()})).json()).items||[];const sel=$('#sp-dev');if(!sel)return;sel.innerHTML='';
  const o0=document.createElement('option');o0.value='';o0.textContent='dispositivo ativo';sel.appendChild(o0);
  ds.forEach(x=>{const o=document.createElement('option');o.value=x.id;o.textContent=x.name+(x.active?' ✓':'');if(x.active)o.selected=true;sel.appendChild(o);});}catch(e){}}
function startSpPoll(){if(_spPoll)return;_spPoll=setInterval(()=>{if(curView==='musica'&&$('#sp-np'))spNow();else{clearInterval(_spPoll);_spPoll=null;}},3000);}
// --- mini-player global (pop em qualquer tela + controles do SO via MediaSession) ---
let _npPoll=null,_npPlaying=false,_npDur=0,_npProg=0,_npAt=0,_npTick2=null;
function npBar(){const i=document.querySelector('#npm-bar i');if(!i||!_npDur)return;
  let pos=_npProg+(_npPlaying?(Date.now()-_npAt):0);pos=Math.max(0,Math.min(_npDur,pos));
  i.style.width=(pos/_npDur*100)+'%';}
async function npTick(){const m=$('#np-mini');if(!m)return;
  if(localStorage.getItem('ev_np_off')==='1'){m.classList.remove('on');return;}   // desligado pelo usuário
  let j;try{j=await (await fetch('/api/spotify/nowplaying',{headers:H()})).json();}catch(e){m.classList.remove('on');return;}
  if(!j||!j.connected||!j.name){m.classList.remove('on');return;}   // esconde se desconectado/nada
  _npPlaying=!!j.playing;_npDur=j.duration||0;_npProg=j.progress||0;_npAt=Date.now();
  $('#np-mini .npm-t').textContent=j.name;$('#np-mini .npm-a').textContent=j.artists||'';
  const art=$('#npm-art');if(j.image){art.src=j.image;art.style.display='';}else art.style.display='none';
  const tg=$('#npm-tog');tg.innerHTML='';tg.appendChild(ficon(j.playing?'pause':'play'));
  m.classList.add('on');window.lucide&&lucide.createIcons();npBar();npMedia(j);}
function startNpPoll(){if(_npPoll)return;
  const p=$('#npm-prev'),n=$('#npm-next'),t=$('#npm-tog'),info=document.querySelector('#np-mini .npm-i'),bar=$('#npm-bar');
  if(p){p.innerHTML='';p.appendChild(ficon('skip-back'));p.onclick=()=>{spCtl('prev');setTimeout(npTick,600);};}
  if(n){n.innerHTML='';n.appendChild(ficon('skip-forward'));n.onclick=()=>{spCtl('next');setTimeout(npTick,600);};}
  if(t)t.onclick=()=>{spCtl(_npPlaying?'pause':'resume');setTimeout(npTick,600);};
  if(bar)bar.addEventListener('pointerup',e=>{e.stopPropagation();if(!_npDur)return;
    const r=bar.getBoundingClientRect();const frac=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
    const ms=Math.round(frac*_npDur);_npProg=ms;_npAt=Date.now();npBar();
    fetch('/api/spotify/control',{method:'POST',headers:H(),body:JSON.stringify({action:'seek',ms})}).catch(()=>{});});
  if(!_npTick2)_npTick2=setInterval(npBar,1000);   // avança a barrinha entre os polls
  if(info)info.onclick=()=>{if($('#np-mini')._moved){$('#np-mini')._moved=false;return;}switchView('musica');};
  npDraggable();
  _npPoll=setInterval(npTick,6000);npTick();}
function npDraggable(){const m=$('#np-mini');if(!m||m._dnd)return;m._dnd=true;
  try{const p=JSON.parse(localStorage.getItem('ev_np_pos')||'null');if(p){m.style.left=p.x+'px';m.style.top=p.y+'px';m.style.right='auto';m.style.bottom='auto';}}catch(e){}
  let sx,sy,ox,oy,drag=false;
  m.addEventListener('pointerdown',e=>{if(e.target.closest('.npm-c')||e.target.closest('#npm-bar'))return;   // não arrasta pelos controles nem pela barra
    const r=m.getBoundingClientRect();drag=true;m._moved=false;sx=e.clientX;sy=e.clientY;ox=r.left;oy=r.top;
    m.style.right='auto';m.style.bottom='auto';m.style.cursor='grabbing';try{m.setPointerCapture(e.pointerId);}catch(_){}});
  m.addEventListener('pointermove',e=>{if(!drag)return;
    if(Math.abs(e.clientX-sx)+Math.abs(e.clientY-sy)>4)m._moved=true;
    const x=Math.max(4,Math.min(innerWidth-m.offsetWidth-4,ox+e.clientX-sx));
    const y=Math.max(4,Math.min(innerHeight-m.offsetHeight-4,oy+e.clientY-sy));
    m.style.left=x+'px';m.style.top=y+'px';});
  const end=()=>{if(!drag)return;drag=false;m.style.cursor='grab';
    if(m._moved){const r=m.getBoundingClientRect();try{localStorage.setItem('ev_np_pos',JSON.stringify({x:Math.round(r.left),y:Math.round(r.top)}));}catch(e){}}};
  m.addEventListener('pointerup',end);m.addEventListener('pointercancel',end);}
function npMedia(j){if(!('mediaSession' in navigator))return;try{
  navigator.mediaSession.metadata=new MediaMetadata({title:j.name||'',artist:j.artists||'',album:'Spotify',
    artwork:j.image?[{src:j.image,sizes:'300x300',type:'image/jpeg'}]:[]});
  const acts={play:'resume',pause:'pause',nexttrack:'next',previoustrack:'prev'};
  for(const a in acts){try{navigator.mediaSession.setActionHandler(a,()=>{spCtl(acts[a]);setTimeout(npTick,600);});}catch(e){}}
}catch(e){}}
function spInitSDK(){if(_spPlayer||_spSdkLoading||!window.isSecureContext)return;_spSdkLoading=true;
  window.onSpotifyWebPlaybackSDKReady=()=>{try{
    _spPlayer=new Spotify.Player({name:'E.V.',getOAuthToken:cb=>{fetch('/api/spotify/token',{headers:H()}).then(r=>r.json()).then(j=>{if(j.token)cb(j.token);});},volume:0.8});
    _spPlayer.addListener('ready',({device_id})=>{_spDevice=device_id;});
    _spPlayer.addListener('not_ready',()=>{_spDevice=null;});
    // toca DENTRO da E.V. -> destrava os controles de mídia do SO (tela de bloqueio)
    _spPlayer.addListener('player_state_changed',st=>{
      if(st&&'mediaSession' in navigator){try{
        const t=st.track_window&&st.track_window.current_track;
        if(t){navigator.mediaSession.metadata=new MediaMetadata({title:t.name||'',
          artist:(t.artists||[]).map(a=>a.name).join(', '),album:(t.album&&t.album.name)||'Spotify',
          artwork:((t.album&&t.album.images)||[]).map(i=>({src:i.url,sizes:(i.width||300)+'x'+(i.height||300),type:'image/png'}))});}
        navigator.mediaSession.playbackState=st.paused?'paused':'playing';
        try{navigator.mediaSession.setPositionState({duration:(st.duration||0)/1000,position:(st.position||0)/1000,playbackRate:1});}catch(e){}
        navigator.mediaSession.setActionHandler('play',()=>_spPlayer.resume());
        navigator.mediaSession.setActionHandler('pause',()=>_spPlayer.pause());
        navigator.mediaSession.setActionHandler('nexttrack',()=>_spPlayer.nextTrack());
        navigator.mediaSession.setActionHandler('previoustrack',()=>_spPlayer.previousTrack());
        try{navigator.mediaSession.setActionHandler('seekto',e=>{if(e.seekTime!=null)_spPlayer.seek(Math.round(e.seekTime*1000));});}catch(e){}
      }catch(e){}}
      try{npTick();}catch(e){}});
    _spPlayer.connect();}catch(e){}};
  const s=document.createElement('script');s.src='https://sdk.scdn.co/spotify-player.js';s.async=true;document.head.appendChild(s);}
async function addMusic(){const u=$('#mu-url'),l=$('#mu-label');const url=(u.value||'').trim();if(!url)return;
  const r=await fetch('/api/music',{method:'POST',headers:H(),body:JSON.stringify({url,label:(l.value||'').trim()})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok){toast(j.detail||TR('map.linkUnsupported'));return;}
  u.value='';l.value='';sfx('confirm');await loadMusic();playEmbed(j.embed,false);}
$('#mu-add')&&($('#mu-add').onclick=addMusic);
$('#mu-url')&&$('#mu-url').addEventListener('keydown',e=>{if(e.key==='Enter')addMusic();});
// --- Mapa + localização (Leaflet + OSM; lugares e pontos dentro da própria E.V.) ---
let _map=null,_marker=null,_loc=null,_nearLayer=null,_savedLayer=null,_addMode=false,_pendingNear=null;
let _baseDark=null,_baseSat=null,_sat=false;
// [displayKey, icon, searchQuery] — label is i18n (map.chip.*); query stays the
// term used by nearby-search so behavior is unchanged regardless of UI language.
const MAP_CHIPS=[['map.chip.locate','locate-fixed','Onde estou'],['map.chip.subway','tram-front','Metrô'],['map.chip.train','train-front','Trem'],['map.chip.bus','bus','Ônibus'],['map.chip.pharmacy','pill','Farmácia'],['map.chip.market','shopping-cart','Mercado'],['map.chip.restaurant','utensils','Restaurante'],['map.chip.bakery','croissant','Padaria'],['map.chip.cafe','coffee','Café'],['map.chip.gas','fuel','Posto'],['map.chip.bank','landmark','Banco'],['map.chip.hospital','cross','Hospital'],['map.chip.gym','dumbbell','Academia']];
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function askEV(name,lat,lng){switchView('chat');send('me conta sobre "'+name+'", que fica perto de mim.');}
function routeBtn(name,lat,lng){const b=el('span','pop-b');b.appendChild(ficon('route'));b.appendChild(document.createTextNode(TR('map.routeHere')));b.onclick=()=>routeTo(lat,lng,name);return b;}
// Open ANY point of interest straight in Google Maps — view, directions or street.
function openGmaps(lat,lng){window.open('https://www.google.com/maps/search/?api=1&query='+lat+','+lng,'_blank','noopener');}
function openGdir(lat,lng){const o=_loc?('&origin='+_loc[0]+','+_loc[1]):'';window.open('https://www.google.com/maps/dir/?api=1'+o+'&destination='+lat+','+lng+'&travelmode=driving','_blank','noopener');}
function popBtn(icon,label,fn){const b=el('span','pop-b');b.appendChild(ficon(icon));b.appendChild(document.createTextNode(label));b.onclick=fn;return b;}
function poiActions(d,name,lat,lng){
  d.appendChild(routeBtn(name,lat,lng));                                   // rota interna (E.V.)
  d.appendChild(popBtn('external-link','Abrir no Google Maps',()=>openGmaps(lat,lng)));
  d.appendChild(popBtn('navigation','Rota no Google Maps',()=>openGdir(lat,lng)));
  d.appendChild(popBtn('eye','Ver rua',()=>openStreet(lat,lng)));
  d.appendChild(popBtn('message-circle','Perguntar à E.V.',()=>askEV(name,lat,lng)));
  window.lucide&&lucide.createIcons();return d;}
function poiPopup(name,lat,lng,dist){const d=document.createElement('div');
  d.innerHTML='<div class="pop-n">'+esc(name)+'</div>'+(dist!=null?'<div class="pop-d">~'+dist+' m '+TR('map.awayFrom')+'</div>':'');
  return poiActions(d,name,lat,lng);}
function renderMapChips(){const box=$('#map-chips');box.textContent='';
  MAP_CHIPS.forEach(([key,ic,query])=>{const b=el('button','mchip');b.type='button';b.appendChild(ficon(ic));b.appendChild(document.createTextNode(TR(key)));
    b.onclick=(e)=>{ripple(b,e);key==='map.chip.locate'?locateMe():showNearby(query);};box.appendChild(b);});window.lucide&&lucide.createIcons();}
let _routeLayer=null,_routeFT=null,_routeMode='car',_savedPlaces=[];
function fmtDur(s){const m=Math.round(s/60);return m>=60?Math.floor(m/60)+'h '+(m%60)+'min':m+' min';}
function fmtDist(m){return m>=1000?(m/1000).toFixed(1).replace('.',',')+' km':m+' m';}
function clearRoute(){if(_routeLayer){_routeLayer.remove();_routeLayer=null;}_routeFT=null;$('#map-route').classList.remove('on');}
function routeTo(lat,lng,name){if(!_loc){_routeFT=[null,[lat,lng],name||''];$('#map-status').textContent=TR('map.locatingRoute');locateMe();return;}
  drawRouteFT(_loc,[lat,lng],name||'');}
async function drawRouteFT(from,to,label){if(!from||!to)return;_routeFT=[from,to,label];
  const banner=$('#map-route');banner.classList.add('on');banner.innerHTML='';const info=el('div','rt-info','Calculando tempo...');banner.appendChild(info);
  let r=null;try{r=await (await fetch('/api/route',{method:'POST',headers:H(),body:JSON.stringify({from,to,mode:_routeMode})})).json();}catch(e){}
  if(!r||!r.ok){info.textContent=TR('map.routeFail');return;}
  if(_routeLayer)_routeLayer.remove();
  _routeLayer=L.geoJSON(r.geometry,{style:{color:ACC(),weight:5,opacity:.85}}).addTo(_map);
  try{_map.fitBounds(_routeLayer.getBounds(),{padding:[70,70]});}catch(e){}
  const mt=_routeMode==='foot'?TR('map.byFoot'):_routeMode==='bike'?TR('map.byBike'):TR('map.byCar');
  info.textContent=(label?label+' · ':'')+'~'+fmtDur(r.duration)+' · '+fmtDist(r.distance)+mt;
  [['car',TR('map.car')],['foot',TR('map.foot')],['bike',TR('map.bike')]].forEach(a=>{const b=el('button','rt-b'+(_routeMode===a[0]?' on':''),a[1]);b.onclick=()=>{_routeMode=a[0];drawRouteFT(from,to,label);};banner.appendChild(b);});
  const clr=el('button','rt-b','Limpar');clr.onclick=clearRoute;banner.appendChild(clr);window.lucide&&lucide.createIcons();}
function planCoord(v){if(v==='me')return _loc;const p=_savedPlaces.find(x=>String(x.id)===v);return p?[p.lat,p.lng]:null;}
function refreshPlanner(){const opts=[['me',TR('map.myLocation')]].concat(_savedPlaces.map(p=>[String(p.id),p.name]));
  ['plan-from','plan-to'].forEach(id=>{const s=$('#'+id);const cur=s.value;s.innerHTML='';opts.forEach(o=>{const op=document.createElement('option');op.value=o[0];op.textContent=o[1];s.appendChild(op);});if(cur)s.value=cur;});
  if($('#plan-to').value==='me'&&_savedPlaces.length)$('#plan-to').value=String(_savedPlaces[0].id);}
async function addByAddress(){const q=prompt(TR('map.addrPrompt'));if(!q)return;
  $('#map-status').textContent=TR('map.searching')+' "'+q+'"...';
  let g=null;try{g=await (await fetch('/api/geocode?q='+encodeURIComponent(q),{headers:H()})).json();}catch(e){}
  if(!g||!g.ok){$('#map-status').textContent=TR('map.addrNotFound');return;}
  const name=prompt('Nome do ponto:',(g.name||q).split(',')[0]);if(!name)return;
  const d=await (await fetch('/api/places',{method:'POST',headers:H(),body:JSON.stringify({name,lat:g.lat,lng:g.lng})})).json();
  addSavedMarker({id:d.id,name,lat:g.lat,lng:g.lng});if(_map)_map.setView([g.lat,g.lng],16);
  $('#map-status').textContent=TR('map.point')+' "'+name+'" '+TR('map.saved');}
async function showNearby(query){if(!_loc){_pendingNear=query;$('#map-status').textContent=TR('map.needLoc');locateMe();return;}
  $('#map-status').textContent=TR('map.searchingNearby1')+' "'+query+'" '+TR('map.searchingNearby2');
  let items=[];try{const r=await fetch('/api/nearby',{method:'POST',headers:H(),body:JSON.stringify({query,lat:_loc[0],lng:_loc[1]})});items=(await r.json()).items||[];}catch(e){}
  if(_nearLayer)_nearLayer.clearLayers();else _nearLayer=L.layerGroup().addTo(_map);
  const res=$('#map-results');res.innerHTML='';
  if(!items.length){$('#map-status').textContent=TR('map.notFound1')+' "'+query+'" '+TR('map.notFound2');res.classList.remove('on');return;}
  $('#map-status').textContent=items.length+' '+TR('map.resultsFor')+' "'+query+'"';
  const head=el('div','mr-h');head.appendChild(document.createTextNode(query.toUpperCase()));const x=document.createElement('b');x.textContent='fechar';x.onclick=()=>{res.classList.remove('on');if(_nearLayer)_nearLayer.clearLayers();};head.appendChild(x);res.appendChild(head);
  const bounds=[_loc];
  items.forEach(it=>{const m=L.circleMarker([it.lat,it.lng],{radius:7,weight:2,color:ACC(),fillColor:ACC(),fillOpacity:.85}).addTo(_nearLayer);
    m.bindPopup(()=>poiPopup(it.name,it.lat,it.lng,it.dist));bounds.push([it.lat,it.lng]);
    const row=el('div','mres');row.appendChild(el('div','mr-n',it.name));row.appendChild(el('div','mr-d','~'+it.dist+' m'));
    row.onclick=()=>{_map.setView([it.lat,it.lng],16);m.openPopup();};res.appendChild(row);});
  res.classList.add('on');try{_map.fitBounds(bounds,{padding:[60,60],maxZoom:16});}catch(e){}}
let _savedMarkers={};
function addSavedMarker(p){if(!_savedLayer)_savedLayer=L.layerGroup().addTo(_map);const m=L.marker([p.lat,p.lng]).addTo(_savedLayer);_savedMarkers[p.id]=m;
  m.bindPopup(()=>{const d=document.createElement('div');d.innerHTML='<div class="pop-n">'+esc(p.name)+'</div><div class="pop-d">ponto salvo</div>';
    poiActions(d,p.name,p.lat,p.lng);
    d.appendChild(popBtn('trash-2','Remover',async()=>{await fetch('/api/places/delete',{method:'POST',headers:H(),body:JSON.stringify({id:p.id})});m.remove();delete _savedMarkers[p.id];_savedPlaces=_savedPlaces.filter(x=>x.id!==p.id);}));
    window.lucide&&lucide.createIcons();return d;});}
function loadSavedPlaces(){fetch('/api/places',{headers:H()}).then(r=>r.json()).then(d=>{
  _savedPlaces=d.items||[];_savedMarkers={};if(_savedLayer)_savedLayer.clearLayers();_savedPlaces.forEach(addSavedMarker);}).catch(()=>{});}
function showSavedList(){const res=$('#map-results');res.innerHTML='';
  if(!_savedPlaces.length){$('#map-status').textContent=TR('map.noSaved');res.classList.remove('on');return;}
  const head=el('div','mr-h');head.appendChild(document.createTextNode('MEUS PONTOS ('+_savedPlaces.length+')'));const x=document.createElement('b');x.textContent='fechar';x.onclick=()=>res.classList.remove('on');head.appendChild(x);res.appendChild(head);
  _savedPlaces.forEach(p=>{const row=el('div','mres');row.appendChild(el('div','mr-n',p.name));
    const act=el('div','mr-d');const go=document.createElement('span');go.textContent='ver no mapa';go.style.cursor='pointer';go.onclick=(e)=>{e.stopPropagation();_map.setView([p.lat,p.lng],16);const mk=_savedMarkers[p.id];if(mk)mk.openPopup();};
    const rt=document.createElement('span');rt.textContent=' · rota';rt.style.cursor='pointer';rt.onclick=(e)=>{e.stopPropagation();routeTo(p.lat,p.lng,p.name);};
    const gm=document.createElement('span');gm.textContent=' · Google Maps';gm.style.cursor='pointer';gm.onclick=(e)=>{e.stopPropagation();openGmaps(p.lat,p.lng);};
    const sv=document.createElement('span');sv.textContent=' · ver rua';sv.style.cursor='pointer';sv.onclick=(e)=>{e.stopPropagation();openStreet(p.lat,p.lng);};
    act.appendChild(go);act.appendChild(rt);act.appendChild(gm);act.appendChild(sv);row.appendChild(act);
    row.onclick=()=>{_map.setView([p.lat,p.lng],16);const mk=_savedMarkers[p.id];if(mk)mk.openPopup();};res.appendChild(row);});
  res.classList.add('on');$('#map-status').textContent=_savedPlaces.length+' '+TR('map.placesSaved');}
let _accCircle=null,_fixMode=false;
function setMyLocation(lat,lng,acc){_loc=[lat,lng];
  if(_map){_map.setView(_loc,acc&&acc>1500?14:16);
    if(_marker)_marker.setLatLng(_loc);else _marker=L.circleMarker(_loc,{radius:9,weight:3,color:ACC(),fillColor:ACC(),fillOpacity:.7}).addTo(_map);
    if(_accCircle){_accCircle.remove();_accCircle=null;}
    if(acc)_accCircle=L.circle(_loc,{radius:acc,color:ACC(),weight:1,fillColor:ACC(),fillOpacity:.07}).addTo(_map);
    setTimeout(()=>_map.invalidateSize(),80);}
  fetch('/api/location',{method:'POST',headers:H(),body:JSON.stringify({lat,lng})}).catch(()=>{});
  if(_pendingNear){const q=_pendingNear;_pendingNear=null;showNearby(q);}
  if(_routeFT&&!_routeFT[0])drawRouteFT(_loc,_routeFT[1],_routeFT[2]);}
function locateMe(){const st=$('#map-status');if(!navigator.geolocation){st.textContent=TR('map.geoUnavail');return;}
  st.textContent='Localizando seu dispositivo...';
  navigator.geolocation.getCurrentPosition(p=>{const acc=Math.round(p.coords.accuracy||0);
    setMyLocation(p.coords.latitude,p.coords.longitude,acc);
    st.textContent=acc>1500?(TR('map.approxLoc1')+acc+TR('map.approxLoc2')):(TR('map.youAreHere')+(acc?' (~'+acc+' m)':'')+TR('map.pickPlaceType'));
  },()=>{st.textContent=TR('map.locFail');},{enableHighAccuracy:true,timeout:15000,maximumAge:0});}
async function fixLocation(){const q=prompt(TR('map.fixPrompt'));
  if(q===null)return;
  if(q.trim()){$('#map-status').textContent=TR('map.searching')+' "'+q+'"...';let g=null;try{g=await (await fetch('/api/geocode?q='+encodeURIComponent(q),{headers:H()})).json();}catch(e){}
    if(!g||!g.ok){$('#map-status').textContent=TR('map.addrNotFound2');return;}
    setMyLocation(g.lat,g.lng,0);$('#map-status').textContent=TR('map.locByAddr');return;}
  _fixMode=true;$('#map-status').textContent=TR('map.tapToFix');}
function loadMap(){
  if(!window.L){$('#map').innerHTML='<div class="tv-empty" style="padding:20px">'+t('map.unavail')+'</div>';return;}
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
      b.lastChild&&(b.lastChild.textContent=_sat?TR('map.mapLbl'):TR('map.sat'));};
    $('#map-street').onclick=()=>{const c=(_loc?{lat:_loc[0],lng:_loc[1]}:_map.getCenter());openStreet(c.lat,c.lng);};
    $('#map-gmaps').onclick=()=>{const c=_map.getCenter();window.open('https://www.google.com/maps/@'+c.lat+','+c.lng+','+Math.round(_map.getZoom())+'z','_blank','noopener');};
    renderMapChips();loadSavedPlaces();
    const q=$('#map-q');if(q)q.addEventListener('keydown',e=>{if(e.key==='Enter'&&q.value.trim())showNearby(q.value.trim());});
    $('#map-add').onclick=()=>{_addMode=!_addMode;$('#map-add').classList.toggle('on',_addMode);$('#map-status').textContent=_addMode?TR('map.addMode'):TR('map.youAreHere');};
    $('#map-addr').onclick=addByAddress;
    $('#map-fix').onclick=fixLocation;
    $('#map-mine').onclick=showSavedList;
    $('#map-plan').onclick=()=>{const pl=$('#map-planner');const show=pl.style.display==='none';pl.style.display=show?'flex':'none';if(show)refreshPlanner();};
    $('#plan-go').onclick=()=>{const f=planCoord($('#plan-from').value),t=planCoord($('#plan-to').value);
      if(!f){$('#map-status').textContent=TR('map.noLocSet');return;}
      if(!t){$('#map-status').textContent=TR('map.pickDest');return;}
      if($('#plan-from').value===$('#plan-to').value){$('#map-status').textContent=TR('map.pickDiff');return;}
      drawRouteFT(f,t,$('#plan-to').selectedOptions[0].textContent);};
    $('#map-ask').onclick=()=>{switchView('chat');send('E.V., o que tem de útil perto de mim agora?');};
    _map.on('click',ev=>{if(_fixMode){_fixMode=false;setMyLocation(ev.latlng.lat,ev.latlng.lng,0);$('#map-status').textContent=TR('map.locOnMap');return;}
      if(!_addMode)return;const name=prompt(TR('map.namePrompt'));if(!name)return;
      fetch('/api/places',{method:'POST',headers:H(),body:JSON.stringify({name,lat:ev.latlng.lat,lng:ev.latlng.lng})}).then(r=>r.json()).then(d=>addSavedMarker({id:d.id,name,lat:ev.latlng.lat,lng:ev.latlng.lng}));
      _addMode=false;$('#map-add').classList.remove('on');$('#map-status').textContent=TR('map.point')+' "'+name+'" '+TR('map.saved');});}
  setTimeout(()=>{if(_map)_map.invalidateSize();},120);
  if(!_loc)locateMe();}
// In-app street-level view via Mapillary (free, open imagery — no Google redirect).
// Falls back to a Google Street View link when there's no token or no coverage.
let _mlyViewer=null,_mlyLibP=null;
function loadMapillary(){if(window.mapillary)return Promise.resolve();if(_mlyLibP)return _mlyLibP;
  _mlyLibP=new Promise((res,rej)=>{
    const css=document.createElement('link');css.rel='stylesheet';css.href='https://cdn.jsdelivr.net/npm/mapillary-js@4.1.2/dist/mapillary.css';document.head.appendChild(css);
    const s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/mapillary-js@4.1.2/dist/mapillary.js';s.onload=res;s.onerror=rej;document.head.appendChild(s);});
  return _mlyLibP;}
function closeStreet(){$('#street').classList.remove('on');if(_mlyViewer){try{_mlyViewer.remove();}catch(e){}_mlyViewer=null;}}
async function openStreet(lat,lng){
  const gsv='https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='+lat+','+lng;
  let tok='';try{tok=((await (await fetch('/api/mapillary',{headers:H()})).json()).token)||'';}catch(e){}
  if(!tok){window.open(gsv,'_blank','noopener');toast(TR('street.needToken'));return;}
  const sh=$('#street-hint');$('#street').classList.add('on');sh.style.display='block';sh.textContent=TR('street.searching');
  try{
    const d=0.0007,bbox=[lng-d,lat-d,lng+d,lat+d].join(',');
    const j=await (await fetch('https://graph.mapillary.com/images?access_token='+encodeURIComponent(tok)+'&fields=id&bbox='+bbox+'&limit=1')).json();
    const img=(j.data||[])[0];
    if(!img){sh.textContent=TR('street.noCoverage');setTimeout(()=>{window.open(gsv,'_blank','noopener');closeStreet();},1300);return;}
    await loadMapillary();
    if(_mlyViewer){try{_mlyViewer.remove();}catch(e){}_mlyViewer=null;}
    $('#street-view').innerHTML='';
    _mlyViewer=new mapillary.Viewer({accessToken:tok,container:'street-view',imageId:img.id});
    sh.style.display='none';
  }catch(e){sh.textContent=TR('street.openFail');setTimeout(()=>{window.open(gsv,'_blank','noopener');closeStreet();},1300);}
}
document.addEventListener('DOMContentLoaded',()=>{const x=$('#street-x');if(x)x.onclick=closeStreet;});
$('#street-x')&&($('#street-x').onclick=closeStreet);
const ACT_ICON={'task.new':['plus','act.taskNew'],'task.done':['check-check','act.taskDone'],'task.del':['trash-2','act.taskDel'],'reminder.new':['alarm-clock','act.remNew'],'reminder.done':['bell-ring','act.remDone'],'reminder.cancel':['bell-off','act.remCancel'],'expense.new':['wallet','act.expNew'],'expense.del':['trash-2','act.expDel'],'habit.done':['repeat','act.habDone']};
async function loadAct(){try{const cat=$('#act-cat').value;
  const d=await (await fetch('/api/activity'+(cat?'?category='+encodeURIComponent(cat):''),{headers:H()})).json();
  const sel=$('#act-cat');sel.innerHTML='<option value="">'+TR('act.allCats')+'</option>'+(d.categories||[]).map(c=>'<option'+(c===cat?' selected':'')+'>'+c+'</option>').join('');
  const box=$('#actlist');box.textContent='';const items=d.items||[];
  if(!items.length){box.appendChild(emptyState('activity',t('empty.actT'),t('empty.actH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(a=>{const meta=ACT_ICON[a.action]||['activity',a.action];const row=el('div','tv-row');
    const ic=el('div','tv-ic');ic.appendChild(ficon(meta[0]));ic.style.cursor='default';
    const t=el('div','txt');t.appendChild(el('div','',TR(meta[1])+': '+a.label));
    const w=a.created?new Date(a.created):null;
    const sub=((w&&!isNaN(w))?w.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'')+(a.category?' · '+a.category:'');
    t.appendChild(subline(sub));row.appendChild(ic);row.appendChild(t);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
$('#act-cat').onchange=()=>loadAct();
async function loadSub(){try{const items=(await (await fetch('/api/recurring',{headers:H()})).json()).items||[];const box=$('#sublist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('credit-card',t('empty.subT'),t('empty.subH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(x=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',x.description));t.appendChild(subline(x.category+' · dia '+x.day));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+x.amount.toFixed(0);
    const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editSub(x);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog(TR('confirm.rmSub')))recDel('/api/recurring/delete',x.id,loadSub);};
    row.appendChild(t);row.appendChild(val);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editSub(x){openForm(t('form.editSub'),[
  {key:'amount',label:t('field.amountRs'),value:String(x.amount)},
  {key:'description',label:t('field.description'),value:x.description},
  {key:'category',label:t('field.category'),value:x.category},
  {key:'day',label:t('field.dayOfMonth'),value:String(x.day)}],
  async v=>{await fetch('/api/recurring/update',{method:'POST',headers:H(),body:JSON.stringify({id:x.id,amount:v.amount,description:v.description,category:v.category,day:v.day})});loadSub();});}
$('#subform').onsubmit=async e=>{e.preventDefault();const amount=$('#sub-amt').value.trim();if(!amount)return;
  await fetch('/api/recurring',{method:'POST',headers:H(),body:JSON.stringify({amount,description:$('#sub-desc').value.trim(),day:$('#sub-day').value})});$('#sub-amt').value='';$('#sub-desc').value='';loadSub();};
async function loadOrc(){try{const items=(await (await fetch('/api/budgets',{headers:H()})).json()).items||[];const box=$('#orclist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('piggy-bank',t('empty.orcT'),t('empty.orcH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(b=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',b.category));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+b.amount.toFixed(0)+'/mês';
    const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editOrc(b);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog(TR('confirm.rmBudget'))){await fetch('/api/budgets/delete',{method:'POST',headers:H(),body:JSON.stringify({category:b.category})});loadOrc();loadPanel();}};
    row.appendChild(t);row.appendChild(val);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editOrc(b){openForm(t('form.editBudget')+' · '+b.category,[
  {key:'amount',label:t('field.monthlyRs'),value:String(b.amount)}],
  async v=>{if(!v.amount)return;await fetch('/api/budgets',{method:'POST',headers:H(),body:JSON.stringify({category:b.category,amount:v.amount})});loadOrc();loadPanel();});}
$('#orcform').onsubmit=async e=>{e.preventDefault();const cat=$('#orc-cat').value.trim(),amount=$('#orc-amt').value.trim();if(!cat||!amount)return;
  await fetch('/api/budgets',{method:'POST',headers:H(),body:JSON.stringify({category:cat,amount})});$('#orc-cat').value='';$('#orc-amt').value='';loadOrc();};
async function loadMon(){try{const items=(await (await fetch('/api/watches',{headers:H()})).json()).items||[];const box=$('#monlist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('radar',t('empty.monT'),t('empty.monH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(w=>{const row=el('div','tv-row');const t=el('div','txt');const a=document.createElement('a');a.href=w.url;a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=w.url;t.appendChild(a);if(w.keyword)t.appendChild(subline('palavra: '+w.keyword));
    const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editMon(w);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog(TR('confirm.rmMon')))recDel('/api/watches/delete',w.id,loadMon);};
    row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editMon(w){openForm(t('form.editMon'),[
  {key:'url',label:t('field.url'),value:w.url},
  {key:'keyword',label:t('field.keyword'),value:w.keyword||''}],
  async v=>{if(!v.url)return;await fetch('/api/watches/update',{method:'POST',headers:H(),body:JSON.stringify({id:w.id,url:v.url,keyword:v.keyword})});loadMon();});}
$('#monform').onsubmit=async e=>{e.preventDefault();const url=$('#mon-url').value.trim();if(!url)return;
  await fetch('/api/watches',{method:'POST',headers:H(),body:JSON.stringify({url,keyword:$('#mon-kw').value.trim()})});$('#mon-url').value='';$('#mon-kw').value='';loadMon();};
const LOC_KIND_LABEL={script:'loc.kScript',open:'loc.kOpen',browser:'loc.kBrowser',shell:'loc.kShell'};
const LOC_STATUS_LABEL={pending:'loc.sPending',approved:'loc.sApproved',running:'loc.sRunning',done:'loc.sDone',failed:'loc.sFailed',rejected:'loc.sRejected'};
function locRow(t,withActions){const row=el('div','tv-row');const txt=el('div','txt');
  const head=el('div');head.style.display='flex';head.style.alignItems='center';head.style.gap='6px';
  if(t.risk==='high'){const b=el('span','');b.textContent=t('loc.highRisk');b.style.fontFamily='var(--mono)';b.style.fontSize='10px';b.style.letterSpacing='.06em';b.style.color='#ff6b6b';head.appendChild(b);}
  head.appendChild(document.createTextNode('['+(LOC_KIND_LABEL[t.kind]?t(LOC_KIND_LABEL[t.kind]):t.kind)+'] '+t.label));
  txt.appendChild(head);
  txt.appendChild(subline(LOC_STATUS_LABEL[t.status]?t(LOC_STATUS_LABEL[t.status]):t.status));
  if(t.result&&t.result.output)txt.appendChild(subline(String(t.result.output).slice(0,180)));
  row.appendChild(txt);
  if(withActions){const ok=el('button','tv-ic');ok.title=t('loc.approve');ok.appendChild(ficon('check'));
    ok.onclick=async()=>{await fetch('/api/local-tasks/approve',{method:'POST',headers:H(),body:JSON.stringify({id:t.id})});loadLoc();};
    const no=el('button','tv-ic');no.title=t('loc.reject');no.appendChild(ficon('x'));
    no.onclick=async()=>{await fetch('/api/local-tasks/reject',{method:'POST',headers:H(),body:JSON.stringify({id:t.id})});loadLoc();};
    row.appendChild(ok);row.appendChild(no);}
  return row;}
function locConfirmRow(c){const row=el('div','tv-row');row.style.borderColor='rgba(255,107,107,.4)';const txt=el('div','txt');
  txt.appendChild(document.createTextNode('⚠️ '+c.label));
  txt.appendChild(subline(t('loc.taskPaused1')+' #'+c.task_id+' '+t('loc.taskPaused2')));
  row.appendChild(txt);
  const ok=el('button','tv-ic');ok.title=t('loc.confirmProceed');ok.appendChild(ficon('check'));
  ok.onclick=async()=>{await fetch('/api/local-tasks/confirms/approve',{method:'POST',headers:H(),body:JSON.stringify({id:c.id})});loadLoc();};
  const no=el('button','tv-ic');no.title=t('loc.rejectAction');no.appendChild(ficon('x'));
  no.onclick=async()=>{await fetch('/api/local-tasks/confirms/reject',{method:'POST',headers:H(),body:JSON.stringify({id:c.id})});loadLoc();};
  row.appendChild(ok);row.appendChild(no);
  return row;}
async function loadLoc(){try{
  const items=(await (await fetch('/api/local-tasks',{headers:H()})).json()).items||[];
  const pend=items.filter(t=>t.status==='pending'),hist=items.filter(t=>t.status!=='pending');
  const cbox=$('#loc-confirms');cbox.textContent='';
  const confirms=(await (await fetch('/api/local-tasks/confirms?status=pending',{headers:H()})).json()).items||[];
  if(!confirms.length)cbox.appendChild(emptyState('shield-check',t('empty.locConfT'),t('empty.locConfH')));
  else confirms.forEach(c=>cbox.appendChild(locConfirmRow(c)));
  const pbox=$('#loc-pending');pbox.textContent='';
  if(!pend.length)pbox.appendChild(emptyState('shield-check',t('empty.locPendT'),t('empty.locPendH')));
  else pend.forEach(t=>pbox.appendChild(locRow(t,true)));
  const hbox=$('#loc-hist');hbox.textContent='';
  if(!hist.length)hbox.appendChild(emptyState('history',t('empty.locHistT'),t('empty.locHistH')));
  else hist.slice(0,20).forEach(t=>hbox.appendChild(locRow(t,false)));
  const scripts=(await (await fetch('/api/local-scripts',{headers:H()})).json()).items||[];
  const sbox=$('#loc-scripts');sbox.textContent='';
  if(!scripts.length)sbox.appendChild(emptyState('terminal',t('empty.locScrT'),t('empty.locScrH')));
  else scripts.forEach(s=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(document.createTextNode(s.name));t.appendChild(subline(s.command));
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));
    dl.onclick=async()=>{if(await confirmDialog(TR('confirm.rmScript')+' '+s.name+'?')){await fetch('/api/local-scripts/delete',{method:'POST',headers:H(),body:JSON.stringify({id:s.id})});loadLoc();}};
    row.appendChild(t);row.appendChild(dl);sbox.appendChild(row);});
  window.lucide&&lucide.createIcons();}catch(e){}}
$('#locscriptform').onsubmit=async e=>{e.preventDefault();const name=$('#locs-name').value.trim(),command=$('#locs-cmd').value.trim();if(!name||!command)return;
  await fetch('/api/local-scripts',{method:'POST',headers:H(),body:JSON.stringify({name,command})});$('#locs-name').value='';$('#locs-cmd').value='';loadLoc();};
setInterval(()=>{const v=$('#locview');if(v&&v.style.display!=='none')loadLoc();},4000);
async function loadLinks(){try{const items=(await (await fetch('/api/links',{headers:H()})).json()).items||[];const box=$('#lnklist');box.textContent='';
  window._lcats=[...new Set(items.map(l=>l.category))];
  if(!items.length){box.appendChild(emptyState('link',t('empty.lnkT'),t('empty.lnkH')));window.lucide&&lucide.createIcons();return;}
  const g={};items.forEach(l=>{(g[l.category]=g[l.category]||[]).push(l);});
  Object.keys(g).sort().forEach(cat=>{box.appendChild(el('div','tv-cat',cat));
    g[cat].forEach(l=>{const row=el('div','tv-row');const t=el('div','txt');const a=document.createElement('a');a.href=l.url;a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=l.name;t.appendChild(a);t.appendChild(subline(l.url));
      const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editLink(l);
      const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/links/delete',{id:l.id},'/api/links',{name:l.name,url:l.url,category:l.category},loadLinks,'ent.link');
      row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});});window.lucide&&lucide.createIcons();}catch(e){}}
function editLink(l){openForm(t('form.editLink'),[
  {key:'name',label:t('field.name'),value:l.name},
  {key:'url',label:t('field.url'),value:l.url},
  {key:'category',label:t('field.category'),value:l.category,options:window._lcats||[]}],
  async v=>{if(!v.name||!v.url)return;await fetch('/api/links/update',{method:'POST',headers:H(),body:JSON.stringify({id:l.id,name:v.name,url:v.url,category:v.category})});loadLinks();});}
$('#lnkform').onsubmit=async e=>{e.preventDefault();const name=$('#lnk-name').value.trim(),url=$('#lnk-url').value.trim(),cat=$('#lnk-cat').value.trim()||'geral';if(!name||!url)return;
  await fetch('/api/links',{method:'POST',headers:H(),body:JSON.stringify({name,url,category:cat})});$('#lnk-name').value='';$('#lnk-url').value='';loadLinks();};
async function loadHabits(){try{const items=(await (await fetch('/api/habits',{headers:H()})).json()).items||[];const box=$('#hablist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('repeat',t('empty.habT'),t('empty.habH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(h=>{const row=el('div','tv-row');const done=el('button','tv-ic');done.title=h.done_today?TR('hab.doneToday'):TR('hab.markDone');done.appendChild(ficon(h.done_today?'check-check':'check'));if(h.done_today)done.style.color='var(--fg)';
    done.onclick=async()=>{await fetch('/api/habits/done',{method:'POST',headers:H(),body:JSON.stringify({id:h.id})});loadHabits();};
    const t=el('div','txt');t.appendChild(el('div','',h.name));t.appendChild(subline(h.total+' '+TR('hab.daysWord')+(h.done_today?' · '+TR('hab.doneToday'):'')));t.appendChild(habHeat(h.days));
    const ed=el('button','tv-ic');ed.title=TR('common.renameT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editHab(h);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog(TR('confirm.rmHab')))recDel('/api/habits/delete',h.id,loadHabits);};
    row.appendChild(done);row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function habHeat(days){const set=new Set(days||[]);const wrap=el('div','heat');const today=new Date();
  for(let i=111;i>=0;i--){const d=new Date(today);d.setDate(today.getDate()-i);const ds=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');const c=el('span','hc'+(set.has(ds)?' on':''));c.title=ds;wrap.appendChild(c);}
  return wrap;}
function editHab(h){openForm(t('form.renameHab'),[
  {key:'name',label:t('field.name'),value:h.name}],
  async v=>{if(!v.name)return;await fetch('/api/habits/update',{method:'POST',headers:H(),body:JSON.stringify({id:h.id,name:v.name})});loadHabits();});}
$('#habform').onsubmit=async e=>{e.preventDefault();const name=$('#hab-name').value.trim();if(!name)return;await fetch('/api/habits',{method:'POST',headers:H(),body:JSON.stringify({name})});$('#hab-name').value='';loadHabits();};
async function loadJournal(){try{const items=(await (await fetch('/api/journal',{headers:H()})).json()).items||[];const box=$('#joulist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('notebook-pen',t('empty.jouT'),t('empty.jouH')));window.lucide&&lucide.createIcons();return;}
  items.slice().reverse().forEach(j=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',j.text));if(j.created)t.appendChild(subline(j.created.slice(0,10)));
    const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editJou(j);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/journal/delete',{id:j.id},'/api/journal',{text:j.text},loadJournal,'ent.entry');
    row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editJou(j){openForm(t('form.editEntry'),[
  {key:'text',label:t('field.text'),value:j.text,type:'textarea'}],
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
  const MONTHS=_lang==='pt'?['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']:['January','February','March','April','May','June','July','August','September','October','November','December'];
  $('#cal-title').textContent=MONTHS[calM]+' '+calY;const grid=$('#calgrid');grid.textContent='';
  (_lang==='pt'?['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']:['Sun','Mon','Tue','Wed','Thu','Fri','Sat']).forEach(d=>grid.appendChild(el('div','cal-dow',d)));
  const first=new Date(calY,calM,1).getDay(),days=new Date(calY,calM+1,0).getDate();
  const tn=new Date(),tstr=ymd(tn.getFullYear(),tn.getMonth(),tn.getDate());
  for(let i=0;i<first;i++)grid.appendChild(el('div','cal-cell empty'));
  for(let d=1;d<=days;d++){const ds=ymd(calY,calM,d);const cell=el('div','cal-cell'+(ds===tstr?' today':''));
    cell.appendChild(el('div','cal-num',String(d)));const list=(byDay[ds]||[]).slice().sort((a,b)=>a.when_iso.localeCompare(b.when_iso));
    list.slice(0,3).forEach(r=>{const lbl=(r._g&&r.all_day)?TR('cal.allDay'):r.when_iso.slice(11,16);const ev=el('div','cal-ev'+(r._g?' g':''),lbl+' '+r.text);ev.title=(r._g?'Google · ':'')+r.text;ev.onclick=e=>{e.stopPropagation();r._g?calGoogle(r):calEdit(r);};cell.appendChild(ev);});
    if(list.length>3){const mo=el('div','cal-more','+'+(list.length-3)+' mais');mo.onclick=e=>{e.stopPropagation();calList(ds,list);};cell.appendChild(mo);}
    cell.onclick=()=>calAdd(ds);grid.appendChild(cell);}}
function calFmtDay(ds){return ds.split('-').reverse().join('/');}
function calAdd(ds){openForm(t('form.newEvent')+' · '+calFmtDay(ds),[
    {key:'text',label:t('field.event'),placeholder:'...'},
    {key:'time',label:t('field.time'),value:'09:00'},
    {key:'where',label:t('field.where'),select:[{v:'ev',l:t('field.evReminder')},{v:'g',l:'Google Calendar'}],value:'ev'},
    {key:'recur',label:t('cal.repeatEv'),select:RECUR(),value:''}],
  async v=>{if(!v.text)return;
    if(v.where==='g'){toast(TR('cal.creatingGoogle'));const j=await (await fetch('/api/gcal/create',{method:'POST',headers:H(),body:JSON.stringify({summary:v.text,start:ds+'T'+(v.time||'09:00')})})).json();toast(j.ok?TR('cal.eventCreated'):(j.msg||TR('cal.createFail')));loadCal();return;}
    await fetch('/api/reminders',{method:'POST',headers:H(),body:JSON.stringify({text:v.text,when:ds+'T'+(v.time||'09:00'),recur:v.recur})});loadCal();loadRem();loadPanel();});}
function calGoogle(r){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('modal.gevent')));
  card.appendChild(el('div','mconf',r.text));
  const when=el('div','');when.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:12px;margin:4px 0 2px';
  when.textContent=r.all_day?TR('cal.allDay'):r.when_iso.replace('T',' ').slice(0,16);card.appendChild(when);
  const bar=el('div','mbar');
  const del=el('button','mbtn2',t('common.delete'));del.style.marginRight='auto';del.onclick=async()=>{m.classList.remove('on');if(await confirmDialog(t('confirm.rmGcal'))){const j=await (await fetch('/api/gcal/delete',{method:'POST',headers:H(),body:JSON.stringify({id:r.gid})})).json();toast(j.ok?TR('cal.eventDeleted'):TR('cal.deleteFail'));loadCal();}};
  bar.appendChild(del);
  if(r.link){const op=el('button','mbtn2','Abrir no Google');op.onclick=()=>window.open(r.link,'_blank');bar.appendChild(op);}
  const c=el('button','mbtn',t('common.closeBtn'));c.onclick=()=>m.classList.remove('on');bar.appendChild(c);
  card.appendChild(bar);m.appendChild(card);m.classList.add('on');}
function calEdit(r){const ds=r.when_iso.slice(0,10),tm=r.when_iso.slice(11,16)||'09:00';
  openForm(t('form.editEvent'),[
    {key:'text',label:t('field.event'),value:r.text},
    {key:'date',label:t('field.dateIso'),value:ds},
    {key:'time',label:t('field.time'),value:tm},
    {key:'recur',label:t('common.repeat'),select:RECUR(),value:r.recur||''}],
  async v=>{if(!v.text)return;await fetch('/api/reminders/update',{method:'POST',headers:H(),body:JSON.stringify({id:r.id,text:v.text,when:(v.date||ds)+'T'+(v.time||'09:00'),recur:v.recur})});loadCal();loadRem();loadPanel();},
  ()=>delU('/api/reminders/delete',{id:r.id},'/api/reminders',{text:r.text,when:r.when_iso,recur:r.recur||''},()=>{loadCal();loadRem();loadPanel();},'ent.event'));}
function calList(ds,list){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  card.appendChild(el('div','mtitle',t('cal.eventsOn')+' · '+calFmtDay(ds)));
  list.forEach(r=>{const row=el('label','mrow');row.style.cursor='pointer';
    const lbl=(r._g&&r.all_day)?TR('cal.allDay'):r.when_iso.slice(11,16);
    row.appendChild(el('span','',lbl+' · '+(r._g?'Google · ':'')+r.text));
    row.onclick=()=>{m.classList.remove('on');r._g?calGoogle(r):calEdit(r);};card.appendChild(row);});
  const bar=el('div','mbar');const c=el('button','mbtn2',t('common.closeBtn'));c.onclick=()=>m.classList.remove('on');
  const add=el('button','mbtn','Novo evento');add.onclick=()=>{m.classList.remove('on');calAdd(ds);};
  bar.appendChild(c);bar.appendChild(add);card.appendChild(bar);m.appendChild(card);m.classList.add('on');}
$('#cal-prev').onclick=()=>{calM--;if(calM<0){calM=11;calY--;}loadCal();};
$('#cal-next').onclick=()=>{calM++;if(calM>11){calM=0;calY++;}loadCal();};
function toast(msg){let t=document.getElementById('_toast');if(!t){t=el('div','');t.id='_toast';t.style.cssText='position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:var(--elev);border:1px solid var(--line-2);color:var(--fg);padding:11px 17px;border-radius:11px;font-size:13px;z-index:9999;box-shadow:0 8px 30px rgba(0,0,0,.45);max-width:82vw;text-align:center;transition:opacity .3s';document.body.appendChild(t);}
  t.textContent=msg;t.style.opacity='1';clearTimeout(t._h);t._h=setTimeout(()=>{t.style.opacity='0';},4000);}
function openEmail(){openForm(t('form.sendEmail'),[
  {key:'to',label:t('field.to'),placeholder:'name@email.com'},
  {key:'subject',label:t('field.subject')},
  {key:'body',label:t('field.message'),type:'textarea'}],
  async v=>{if(!v.to||!v.body){toast(TR('mail.fillToBody'));return;}
    toast(TR('mail.sending'));
    try{const j=await (await fetch('/api/email',{method:'POST',headers:H(),body:JSON.stringify({to:v.to,subject:v.subject,body:v.body})})).json();
      toast(j.msg||(j.ok?TR('mail.sent'):TR('mail.sendFail')));}catch(e){toast(TR('mail.noConn'));}});}
function openMsg(){openForm(t('form.tgMsg'),[
  {key:'text',label:t('field.message'),type:'textarea',placeholder:t('field.tgPh')}],
  async v=>{if(!v.text)return;
    try{const j=await (await fetch('/api/notify',{method:'POST',headers:H(),body:JSON.stringify({text:v.text})})).json();
      toast(j.msg||(j.ok?TR('msg.sent'):TR('msg.sendFail')));}catch(e){toast(TR('msg.noConn'));}});}
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
  const box=$('#explist');box.textContent='';if(!items.length){box.appendChild(emptyState('wallet',t('empty.expT'),t('empty.expH')));window.lucide&&lucide.createIcons();return;}
  items.slice().reverse().forEach(x=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',x.description));t.appendChild(subline(x.category+' · '+((x.created||'').slice(0,10))));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+x.amount.toFixed(0);
    const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editExp(x);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/expenses/delete',{id:x.id},'/api/expenses',{amount:x.amount,description:x.description,category:x.category},loadExp,'ent.expense');
    row.appendChild(t);row.appendChild(val);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function editExp(x){openForm(t('form.editExp'),[
  {key:'amount',label:t('field.amountRs'),value:String(x.amount)},
  {key:'description',label:t('field.description'),value:x.description},
  {key:'category',label:t('field.category'),value:x.category,options:window._ecats||[]}],
  async v=>{await fetch('/api/expenses/update',{method:'POST',headers:H(),body:JSON.stringify({id:x.id,amount:v.amount,description:v.description,category:v.category})});loadExp();loadPanel();});}
$('#expform').onsubmit=async e=>{e.preventDefault();const amount=$('#exp-amt').value.trim();if(!amount)return;
  await fetch('/api/expenses',{method:'POST',headers:H(),body:JSON.stringify({amount,description:$('#exp-desc').value.trim(),category:$('#exp-cat').value.trim()||'geral'})});
  $('#exp-amt').value='';$('#exp-desc').value='';loadExp();loadPanel();};
async function loadRem(){try{const items=(await (await fetch('/api/reminders',{headers:H()})).json()).items||[];const box=$('#remlist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('alarm-clock',t('empty.remT'),t('empty.remH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(r=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',r.text));
    const meta=(r.when_iso?r.when_iso.replace('T',' ').slice(0,16):'')+(r.recur?((r.when_iso?' · ':'')+recurLbl(r.recur)):'');
    if(meta)t.appendChild(subline(meta));
    const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editRem(r);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/reminders/delete',{id:r.id},'/api/reminders',{text:r.text,when:r.when_iso||'',recur:r.recur||''},loadRem,'ent.reminder');
    row.appendChild(t);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function recurShort(r){return {daily:t('recur.shortDaily'),weekly:t('recur.shortWeekly'),monthly:t('recur.shortMonthly')}[r]||r;}
function recurLbl(r){return t('recur.repeatsPrefix')+' '+recurShort(r);}
function editRem(r){openForm(t('form.editRem'),[
  {key:'text',label:t('field.remindOf'),value:r.text},
  {key:'when',label:t('field.whenIso'),value:r.when_iso||''},
  {key:'recur',label:t('common.repeat'),select:RECUR(),value:r.recur||''}],
  async v=>{if(!v.text)return;await fetch('/api/reminders/update',{method:'POST',headers:H(),body:JSON.stringify({id:r.id,text:v.text,when:v.when,recur:v.recur})});loadRem();loadCal();loadPanel();});}
$('#remform').onsubmit=async e=>{e.preventDefault();const text=$('#rem-text').value.trim();if(!text)return;
  await fetch('/api/reminders',{method:'POST',headers:H(),body:JSON.stringify({text,when:$('#rem-when').value||'',recur:$('#rem-recur').value})});$('#rem-text').value='';$('#rem-when').value='';$('#rem-recur').value='';loadRem();loadPanel();};
async function loadMem(){try{const items=(await (await fetch('/api/facts',{headers:H()})).json()).items||[];
  const cnt=$('#mem-count');if(cnt)cnt.textContent=items.length?('· '+items.length+' '+(items.length>1?TR('mem.memoriesWord'):TR('mem.memoryWord'))):'';
  const box=$('#memlist');box.textContent='';
  if(!items.length){box.appendChild(emptyState('brain',t('empty.memT'),t('empty.memH')));window.lucide&&lucide.createIcons();return;}
  items.forEach(f=>{const row=el('div','tv-row');
    const t=el('div','txt',f.fact);t.title=TR('mem.editHint');t.style.cursor='text';t.onclick=()=>startMemEdit(t,f);
    row.appendChild(t);
    const dl=el('button','tv-ic');dl.title=TR('common.forgetT');dl.appendChild(ficon('trash-2'));dl.onclick=e=>{e.stopPropagation();delU('/api/facts/delete',{id:f.id},'/api/facts',{text:f.fact},loadMem,'ent.memory');};
    row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
function startMemEdit(t,f){const orig=f.fact;const inp=document.createElement('input');inp.className='tv-search';inp.value=orig;inp.style.margin='0';inp.style.flex='1';
  t.replaceWith(inp);inp.focus();inp.select();let done=false;
  const save=async()=>{if(done)return;done=true;const v=inp.value.trim();
    if(v&&v!==orig){await fetch('/api/facts/update',{method:'POST',headers:H(),body:JSON.stringify({id:f.id,text:v})});}
    loadMem();};
  inp.onblur=save;inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();save();}else if(e.key==='Escape'){done=true;loadMem();}};}
$('#memform').onsubmit=async e=>{e.preventDefault();const text=$('#mem-text').value.trim();if(!text)return;
  await fetch('/api/facts',{method:'POST',headers:H(),body:JSON.stringify({text})});$('#mem-text').value='';loadMem();loadPanel();};
$('#mem-clear').onclick=async()=>{if(!(await confirmDialog(t('confirm.forgetAll'))))return;
  await fetch('/api/facts/clear',{method:'POST',headers:H()});loadMem();loadPanel();};
async function loadKB(){try{const d=await (await fetch('/api/kb',{headers:H()})).json();const box=$('#kblist');box.textContent='';
  if(!d.sources||!d.sources.length){box.appendChild(emptyState('book-open',t('empty.kbT'),t('empty.kbH')));window.lucide&&lucide.createIcons();return;}
  const files=new Set(d.files||[]);
  d.sources.forEach(s=>{const row=el('div','tv-row');const t=el('div','txt');
    if(/^https?:\/\//.test(s.source)){const a=document.createElement('a');a.href=s.source;a.target='_blank';a.rel='noopener';a.className='lnk';a.textContent=s.source;t.appendChild(a);}else t.appendChild(el('div','',s.source));
    const sub=el('div','');sub.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:2px';sub.textContent=s.chunks+' trechos'+(files.has(s.source)?' · arquivo':'');t.appendChild(sub);
    row.appendChild(t);
    if(files.has(s.source)){const op=el('button','tv-ic');op.title=TR('common.openTitle');op.appendChild(ficon('external-link'));op.onclick=()=>kbOpen(s.source,false);
      const dw=el('button','tv-ic');dw.title=TR('common.downloadT');dw.appendChild(ficon('download'));dw.onclick=()=>kbOpen(s.source,true);row.appendChild(op);row.appendChild(dw);}
    const dl=el('button','tv-ic');dl.title=TR('common.removeT');dl.appendChild(ficon('trash-2'));dl.onclick=async ()=>{if(await confirmDialog(TR('confirm.rmKb1')+' "'+s.source+'" '+TR('confirm.rmKb2')))kbDel(s.source);};
    row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
async function kbOpen(source,download){try{const r=await fetch('/api/kb/file?source='+encodeURIComponent(source),{headers:H()});if(!r.ok){sys(TR('kb.fileNotFound'));return;}
  const url=URL.createObjectURL(await r.blob());
  if(download){const a=document.createElement('a');a.href=url;a.download=source;document.body.appendChild(a);a.click();a.remove();}else window.open(url,'_blank');
  setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){sys(TR('kb.openFail'));}}
async function kbDel(source){await fetch('/api/kb/delete',{method:'POST',headers:H(),body:JSON.stringify({source})});loadKB();loadPanel();}
$('#kb-urlf').onsubmit=e=>{e.preventDefault();const url=$('#kb-url').value.trim();if(!url)return;
  const def=url.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,50);
  openForm(t('form.indexPage'),[{key:'name',label:t('field.nameId'),value:def},{key:'url',label:t('field.url'),value:url}],async v=>{
    if(!v.url)return;$('#kb-fmsg').textContent='indexando...';
    const j=await (await fetch('/api/kb/url',{method:'POST',headers:H(),body:JSON.stringify({url:v.url,name:v.name})})).json();
    $('#kb-fmsg').textContent=j.msg||'';$('#kb-url').value='';loadKB();loadPanel();});};
$('#kb-textf').onsubmit=async e=>{e.preventDefault();const title=$('#kb-title').value.trim()||t('kb.defaultNote');const text=$('#kb-text').value.trim();if(!text)return;$('#kb-fmsg').textContent=t('kb.indexing');
  const j=await (await fetch('/api/kb/text',{method:'POST',headers:H(),body:JSON.stringify({title,text})})).json();$('#kb-fmsg').textContent=j.msg||'';$('#kb-title').value='';$('#kb-text').value='';loadKB();loadPanel();};
$('#kb-file').onchange=e=>{const f=e.target.files[0];if(!f)return;e.target.value='';
  openForm(t('form.nameFile'),[{key:'name',label:t('field.nameId'),value:f.name}],async v=>{
    $('#kb-fmsg').textContent='enviando...';const fd=new FormData();fd.append('file',f);if(v.name)fd.append('title',v.name);
    try{const j=await (await fetch('/api/kb/upload',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();$('#kb-fmsg').textContent=j.msg||'ok';}catch(x){$('#kb-fmsg').textContent=TR('kb.uploadErr');}
    loadKB();loadPanel();});};
async function loadTasks(){try{const d=await (await fetch('/api/tasks',{headers:H()})).json();const box=$('#tasklist');box.textContent='';
  window._cats=[...new Set((d.tasks||[]).map(t=>t.category))];
  const g={};(d.tasks||[]).forEach(t=>{(g[t.category]=g[t.category]||[]).push(t);});
  if(!d.tasks||!d.tasks.length){box.appendChild(emptyState('list-checks',t('empty.tasksT'),t('empty.tasksH')));window.lucide&&lucide.createIcons();return;}
  Object.keys(g).sort().forEach(cat=>{const chd=el('div','tv-cat',cat);
    chd.ondragover=e=>{e.preventDefault();chd.classList.add('drop');};chd.ondragleave=()=>chd.classList.remove('drop');
    chd.ondrop=async e=>{e.preventDefault();chd.classList.remove('drop');const id=e.dataTransfer.getData('text/plain');
      if(id){await fetch('/api/tasks/update',{method:'POST',headers:H(),body:JSON.stringify({id:+id,category:cat})});loadTasks();loadPanel();}};
    box.appendChild(chd);
    g[cat].forEach(t=>{const row=el('div','tv-row');row.draggable=true;row.ondragstart=e=>e.dataTransfer.setData('text/plain',String(t.id));
      const done=el('button','tv-ic');done.title=TR('common.complete');done.appendChild(ficon('check'));done.onclick=()=>taskAction('complete',t.id);
      const txt=el('div','txt');const parts=t.text.split(/\s+(?=\d+[.)]\s)/);if(parts.length>1)parts.forEach(p=>txt.appendChild(el('div','',p)));else txt.appendChild(el('div','',t.text));
      const metas=[];if(t.recur)metas.push(recurLbl(t.recur));
      const overdue=t.due&&new Date(t.due)<new Date();
      if(t.due)metas.push((t.recur?TR('due.next'):(overdue?TR('due.overdue'):TR('due.due')))+fmtDue(t.due));
      if(metas.length){const s=subline(metas.join(' · '));if(overdue&&!t.recur){s.style.color='var(--fg)';s.style.fontWeight='600';}txt.appendChild(s);}
      const ed=el('button','tv-ic');ed.title=TR('common.editT');ed.appendChild(ficon('pencil'));ed.onclick=()=>editTask(t);
      const dl=el('button','tv-ic');dl.title=TR('common.deleteT');dl.appendChild(ficon('trash-2'));dl.onclick=()=>delU('/api/tasks/delete',{id:t.id},'/api/tasks',{text:t.text,category:t.category,recur:t.recur||'',due:t.due||''},loadTasks,'ent.task');
      row.appendChild(done);row.appendChild(txt);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});});
  window.lucide&&lucide.createIcons();}catch(e){}}
async function taskAction(op,id){await fetch('/api/tasks/'+op,{method:'POST',headers:H(),body:JSON.stringify({id})});loadTasks();loadPanel();}
function fmtDue(iso){const d=new Date(iso);if(isNaN(d))return iso;return d.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});}
function editTask(t){openForm(t('form.editTask'),[
  {key:'text',label:t('field.description'),value:t.text,type:'textarea'},
  {key:'category',label:t('field.category'),value:t.category,options:window._cats||[],placeholder:t('field.catPh')},
  {key:'due',label:t('field.dueOpt'),value:(t.due||'').slice(0,16),type:'datetime'},
  {key:'recur',label:t('common.repeat'),select:RECUR(),value:t.recur||''}],
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
function ckBuild(){const nav=[[t('view.chat'),()=>switchView('chat')],[t('view.tasks'),()=>switchView('tasks')],[t('view.exp'),()=>switchView('exp')],[t('view.rem'),()=>switchView('rem')],[t('view.cal'),()=>switchView('cal')],[t('view.mem'),()=>switchView('mem')],[t('view.lnk'),()=>switchView('lnk')],[t('view.hab'),()=>switchView('hab')],[t('view.jou'),()=>switchView('jou')],[t('view.sub'),()=>switchView('sub')],[t('view.orc'),()=>switchView('orc')],[t('view.mon'),()=>switchView('mon')],[t('view.kb'),()=>switchView('kb')],[t('view.brain'),()=>switchView('brain')],[t('view.loc'),()=>switchView('loc')],[t('cat.foco'),()=>openPomo(25)],[t('ck.actionTerm'),()=>openTerminal()],[t('ck.liveVoice'),()=>$('#vcopen').click()],[t('ck.focusToggle'),()=>toggleSerious()],[t('right.keys'),()=>openKeys()],[t('form.quickCap'),()=>openQuickCapture()]];
  return nav.map(n=>({k:t('ck.go'),label:n[0],desc:t('ck.open'),run:n[1]})).concat((COMMANDS||[]).map(c=>({k:'/'+c.name,label:c.name,desc:c.desc,run:()=>runCmd(c.name)})));}
let _ckSeq=0;
function ckRender(q){ckItems=ckBuild().filter(i=>(i.label+' '+i.k+' '+i.desc).toLowerCase().includes((q||'').toLowerCase())).slice(0,40);ckSel=0;CKL.textContent='';
  ckItems.forEach((i,ix)=>{const r=el('div','ck-item'+(ix===0?' sel':''));r.appendChild(el('span','ck-k',i.k));r.appendChild(el('span','',i.label));r.appendChild(el('span','ck-d',i.desc||''));r.onclick=()=>{ckClose();i.run();};CKL.appendChild(r);});
  const term=(q||'').trim();const seq=++_ckSeq;
  if(term.length>=2){
    fetch('/api/search?q='+encodeURIComponent(term),{headers:H()}).then(r=>r.json()).then(j=>{
      if(seq!==_ckSeq)return;
      (j.results||[]).forEach(it=>{
        const item={k:it.kind,label:it.text,desc:t('ck.content'),run:()=>{ckClose();if(it.view)switchView(it.view);}};
        ckItems.push(item);
        const r2=el('div','ck-item');r2.appendChild(el('span','ck-k',it.kind));r2.appendChild(el('span','',it.text));r2.appendChild(el('span','ck-d',t('ck.content')));
        r2.onclick=()=>{ckClose();item.run();};CKL.appendChild(r2);
      });
    }).catch(()=>{});
  }}
function ckOpen(){CK.classList.add('on');CKI.value='';ckRender('');setTimeout(()=>CKI.focus(),40);}
function ckClose(){CK.classList.remove('on');}
CKI.addEventListener('input',()=>ckRender(CKI.value));
CKI.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();ckSel=Math.min(ckItems.length-1,ckSel+1);}else if(e.key==='ArrowUp'){e.preventDefault();ckSel=Math.max(0,ckSel-1);}else if(e.key==='Enter'){e.preventDefault();const it=ckItems[ckSel];if(it){ckClose();it.run();}return;}else if(e.key==='Escape'){ckClose();return;}else return;
  [...CKL.children].forEach((c,i)=>c.classList.toggle('sel',i===ckSel));CKL.children[ckSel]&&CKL.children[ckSel].scrollIntoView({block:'nearest'});});
CK.onclick=e=>{if(e.target===CK)ckClose();};
window.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();CK.classList.contains('on')?ckClose():ckOpen();}});
// mobile bottom-nav + composer attach toggle
document.querySelectorAll('#bnav button[data-view]').forEach(b=>b.onclick=()=>switchView(b.dataset.view));
{const bm=$('#bnav-more');if(bm)bm.onclick=()=>openMobileMenu();const at=$('#attach');if(at)at.onclick=()=>document.body.classList.toggle('attach-open');}
setInterval(()=>{$('#s-clock').textContent=new Date().toTimeString().slice(0,8);},1000);
const GREETING='Bem-vindo de volta, Ryan. Sistemas online, tudo pronto pra você.';
let _greeted=false;  // garante saudação única por carregamento
async function validate(tok){try{return (await fetch('/api/panel',{headers:{'Authorization':'Bearer '+tok}})).status===200;}catch(e){return false;}}
function welcome(){const w=$('#welcome'),txt=$('#welcome-txt');
  if(txt)txt.textContent=GREETING;
  w.classList.remove('on');void w.offsetWidth;   // restart the entrance animations
  w.classList.add('on');sfx('boot');window.lucide&&lucide.createIcons();
  // live spoken briefing (status of the day) — shown AND spoken
  fetch('/api/briefing',{headers:H()}).then(r=>r.ok?r.json():null).then(j=>{if(j&&j.text&&txt)txt.textContent=j.text;}).catch(()=>{});
  if(!_greeted){_greeted=true;   // fala a saudação no máximo UMA vez por carregamento
    fetch('/api/greeting',{headers:H()}).then(r=>r.ok?r.blob():null).then(b=>{if(b&&b.size>0)playVoice(URL.createObjectURL(b));}).catch(()=>{});}
  setTimeout(()=>w.classList.remove('on'),4400);}
// --- standby / ambient HUD (idle) ---
let _idleT=null,_sbClock=null;const _IDLE_MS=30000;
function sbBusy(){const q=id=>{const e=document.getElementById(id);return e&&e.classList.contains('on');};
  return q('login')||q('welcome')||q('cam')||q('street')||q('modal')||(typeof vc!=='undefined'&&vc&&vc.classList.contains('on'));}
function showStandby(){const st=$('#standby');if(!st||st.classList.contains('on')||sbBusy())return;
  const upd=()=>{const d=new Date();const c=$('#sb-clock');if(c)c.textContent=d.toTimeString().slice(0,8);
    const dt=$('#sb-date');if(dt)dt.textContent=d.toLocaleDateString(_lang==='pt'?'pt-BR':'en-US',{weekday:'long',day:'numeric',month:'long'});};
  upd();_sbClock=setInterval(upd,1000);
  const t=(_counts.tasks||0),l=(_counts.reminders||0),ss=$('#sb-status');
  if(ss){if(t||l){const tw=(_lang==='pt')?(t+' tarefa'+(t!=1?'s':'')):(t+' task'+(t!=1?'s':''));
    const rw=l?((_lang==='pt')?(' e '+l+' lembrete'+(l!=1?'s':'')):(' and '+l+' reminder'+(l!=1?'s':''))):'';
    ss.textContent=(_lang==='pt')?('Você tem '+tw+rw+' pra hoje, Ryan.'):('You have '+tw+rw+' for today, Ryan.');}
  else ss.textContent=(_lang==='pt')?'Tudo tranquilo por aqui, Ryan.':'All quiet here, Ryan.';}
  st.classList.add('on');window.lucide&&lucide.createIcons();}
function hideStandby(){const st=$('#standby');if(!st||!st.classList.contains('on'))return;st.classList.remove('on');if(_sbClock){clearInterval(_sbClock);_sbClock=null;}}
function resetIdle(){if($('#standby')&&$('#standby').classList.contains('on'))hideStandby();clearTimeout(_idleT);_idleT=setTimeout(showStandby,_IDLE_MS);}
['pointerdown','keydown','wheel','touchstart','mousemove'].forEach(evn=>window.addEventListener(evn,resetIdle,{passive:true}));
resetIdle();
// --- Cérebro: grafo interativo (força) com tudo que a E.V. sabe, estilo Obsidian ---
const BRAIN_COLORS={core:'#f4f3f1',mem:'#35c8ff',tasks:'#5ee6a3',rem:'#ffb35e',people:'#ff6ec7',links:'#8f7bff',kb:'#ffe066',hab:'#4dd0e1',jou:'#ff8a65',sub:'#c792ea',orc:'#82e0aa',mon:'#ef5350',places:'#64b5f6'};
let brainLoaded=false,brainRAF=null,_TH=null;
let brainScene=null,brainCam=null,brainRenderer=null,brainRoot=null,brainCoreMesh=null;
let brainNodeMeshes=[],brainRay=null,brainDragging=false,brainDidRotate=false,brainAutoRot=true,brainLast={x:0,y:0},brainLabels=[],brainRings=[];
async function loadThree(){if(_TH)return _TH;
  _TH=await import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js');return _TH;}
function brainResize(){if(!brainRenderer)return;const wrap=$('#brain-wrap');if(!wrap)return;
  const W=wrap.clientWidth||600,H=wrap.clientHeight||400;brainRenderer.setSize(W,H,false);
  brainCam.aspect=W/H;brainCam.updateProjectionMatrix();}
window.addEventListener('resize',()=>{if(curView==='brain')brainResize();});
async function loadBrain(){
  const cv=$('#brain-canvas');if(!cv)return;
  let THREE;try{THREE=await loadThree();}catch(e){const c=$('#brain-count');if(c)c.textContent=TR('brain.unavail3d');return;}
  ensureBrainGL(THREE);
  if(!brainLoaded){
    let d;try{d=await (await fetch('/api/brain',{headers:H()})).json();}catch(e){return;}
    populateBrain(THREE,d);brainLoaded=true;
    const cnt=$('#brain-count');if(cnt)cnt.textContent=Math.max(0,(d.nodes||[]).length-1)+' neurônios · '+(d.links||[]).length+' sinapses';
  }
  brainResize();
  if(!brainRAF)brainRAF=requestAnimationFrame(brainTick);
}
function reloadBrain(){brainLoaded=false;loadBrain();}
function brainNodeMenu(node,mx,my){const m=$('#brain-menu');m.innerHTML='';
  const grp=node.group,hasRef=node.ref!==undefined&&node.ref!==null;
  m.appendChild(el('div','bm-t',node.label));
  const ob=el('button','');ob.appendChild(ficon('external-link'));ob.appendChild(document.createTextNode(t('brain.openNode')+(node.view?' ('+(VIEW_LABELS[node.view]||node.view)+')':'')));ob.onclick=()=>{m.classList.remove('on');if(node.view)switchView(node.view);};m.appendChild(ob);
  if(hasRef&&node.editable){const eb=el('button','');eb.appendChild(ficon('pencil'));eb.appendChild(document.createTextNode(t('brain.editNode')));eb.onclick=async()=>{m.classList.remove('on');
    const cur=node.full||node.label;const v=prompt(TR('brain.editPrompt'),cur);if(v==null)return;const t=v.trim();if(!t||t===cur)return;
    try{await fetch('/api/brain/edit',{method:'POST',headers:H(),body:JSON.stringify({group:grp,ref:node.ref,text:t})});}catch(e){}reloadBrain();loadPanel();};m.appendChild(eb);}
  if(hasRef){const db=el('button','bm-del');db.appendChild(ficon('trash-2'));db.appendChild(document.createTextNode(t('brain.deleteNode')));db.onclick=async()=>{m.classList.remove('on');
    if(!(await confirmDialog(t('confirm.rmBrain1')+' "'+node.label+'"? '+t('confirm.rmBrain2'))))return;
    try{await fetch('/api/brain/delete',{method:'POST',headers:H(),body:JSON.stringify({group:grp,ref:node.ref})});}catch(e){}reloadBrain();loadPanel();};m.appendChild(db);}
  const wrap=$('#brain-wrap');m.style.left=Math.max(6,Math.min(mx,wrap.clientWidth-236))+'px';m.style.top=Math.min(my+8,wrap.clientHeight-140)+'px';m.classList.add('on');window.lucide&&lucide.createIcons();}
function _hex(c){return parseInt((c||'#7d93aa').slice(1),16);}
function ensureBrainGL(THREE){
  if(brainRenderer)return;
  const cv=$('#brain-canvas'),wrap=$('#brain-wrap');const W=wrap.clientWidth||600,H=wrap.clientHeight||400;
  brainRenderer=new THREE.WebGLRenderer({canvas:cv,antialias:true,alpha:true});
  brainRenderer.setPixelRatio(Math.min(2,devicePixelRatio));brainRenderer.setSize(W,H,false);
  brainScene=new THREE.Scene();
  brainCam=new THREE.PerspectiveCamera(45,W/H,0.1,200);brainCam.position.set(0,0,34);
  brainScene.add(new THREE.AmbientLight(0x88bbff,1.4));
  const pl=new THREE.PointLight(ACC(),2,300);pl.position.set(25,30,40);brainScene.add(pl);
  brainRoot=new THREE.Group();brainScene.add(brainRoot);
  brainRay=new THREE.Raycaster();
}
// JARVIS-style holographic orb: geodesic shell + particle dust + spinning
// concentric rings + radial filaments. C_LINE/C_DUST let us recolor (gold vs cyan).
const BRAIN_R=9,C_LINE=0x35c8ff,C_DUST=0x9fe6ff;
function _addMat(THREE,o){return new THREE.MeshBasicMaterial(Object.assign({transparent:true,blending:THREE.AdditiveBlending,depthWrite:false},o));}
function makeBrain(THREE){
  brainRings=[];const out=[],R=BRAIN_R;
  // geodesic lattice shell
  out.push(new THREE.Mesh(new THREE.IcosahedronGeometry(R,3),_addMat(THREE,{color:C_LINE,wireframe:true,opacity:0.14})));
  out.push(new THREE.Mesh(new THREE.IcosahedronGeometry(R*0.66,2),_addMat(THREE,{color:C_LINE,wireframe:true,opacity:0.1})));
  // volumetric particle dust
  const N=1500,arr=new Float32Array(N*3);
  for(let i=0;i<N;i++){const c=Math.acos(2*Math.random()-1),th=Math.random()*6.2832,r=R*Math.cbrt(Math.random())*0.98;
    arr[i*3]=r*Math.sin(c)*Math.cos(th);arr[i*3+1]=r*Math.sin(c)*Math.sin(th);arr[i*3+2]=r*Math.cos(c);}
  const pg=new THREE.BufferGeometry();pg.setAttribute('position',new THREE.Float32BufferAttribute(arr,3));
  out.push(new THREE.Points(pg,new THREE.PointsMaterial({color:C_DUST,size:0.08,transparent:true,opacity:0.55,blending:THREE.AdditiveBlending,depthWrite:false})));
  // concentric rings at varied tilts — each spins on its own
  for(let k=0;k<5;k++){const ring=new THREE.Mesh(new THREE.TorusGeometry(R*(0.42+k*0.15),0.028,8,140),_addMat(THREE,{color:C_LINE,opacity:0.5}));
    ring.rotation.set(1.2*(k%3)+k*0.4,k*0.8,k*0.35);ring.userData.spin=((k%2)?1:-1)*(0.0025+k*0.0012);out.push(ring);brainRings.push(ring);}
  // radial filaments
  const sp=[];for(let i=0;i<52;i++){const c=Math.acos(2*Math.random()-1),th=Math.random()*6.2832,dx=Math.sin(c)*Math.cos(th),dy=Math.sin(c)*Math.sin(th),dz=Math.cos(c);sp.push(dx*2.2,dy*2.2,dz*2.2,dx*R,dy*R,dz*R);}
  const sg=new THREE.BufferGeometry();sg.setAttribute('position',new THREE.Float32BufferAttribute(sp,3));
  out.push(new THREE.LineSegments(sg,new THREE.LineBasicMaterial({color:C_LINE,transparent:true,opacity:0.12,blending:THREE.AdditiveBlending,depthWrite:false})));
  return out;}
function populateBrain(THREE,data){
  while(brainRoot.children.length)brainRoot.remove(brainRoot.children[0]);
  brainNodeMeshes=[];brainCoreMesh=null;brainLabels=[];
  const lbox=$('#brain-labels');if(lbox)lbox.textContent='';
  makeBrain(THREE).forEach(o=>brainRoot.add(o));
  const nodes=data.nodes||[],links=data.links||[];
  const groups=[...new Set(nodes.filter(n=>n.group!=='core').map(n=>n.group))];
  const GA={};groups.forEach((g,i)=>{const y=1-(i+0.5)/groups.length*2;const rad=Math.sqrt(Math.max(0,1-y*y)),th=i*2.399;
    GA[g]=new THREE.Vector3(Math.cos(th)*rad,y,Math.sin(th)*rad).multiplyScalar(BRAIN_R*0.9);});
  const jit=(i,s)=>{const x=Math.sin(i*127.1+s*311.7)*43758.5;return(x-Math.floor(x))*2-1;};  // deterministic
  const sph=new THREE.IcosahedronGeometry(1,2),pos={};
  nodes.forEach((n,i)=>{let p;
    if(n.group==='core')p=new THREE.Vector3(0,0,0);
    else if(n.id.startsWith('g:'))p=GA[n.group].clone();
    else{p=(GA[n.group]||new THREE.Vector3()).clone().add(new THREE.Vector3(jit(i,1),jit(i,2),jit(i,3)).multiplyScalar(2.4));p.setLength(BRAIN_R*(0.8+0.18*((jit(i,4)+1)/2)));}
    pos[n.id]=p;
    const col=_hex(BRAIN_COLORS[n.group]),rad=n.group==='core'?1.2:(n.id.startsWith('g:')?0.55:0.3);
    const m=new THREE.Mesh(sph,new THREE.MeshBasicMaterial({color:col}));m.position.copy(p);m.scale.setScalar(rad);m.userData=n;
    const halo=new THREE.Mesh(sph,new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:0.2,blending:THREE.AdditiveBlending,depthWrite:false}));
    halo.position.copy(p);halo.scale.setScalar(rad*2.4);brainRoot.add(halo);brainRoot.add(m);
    brainNodeMeshes.push(m);if(n.group==='core')brainCoreMesh=m;
    if(lbox&&n.id!=='core'&&!n.id.endsWith(':more')){const d=el('div',n.id.startsWith('g:')?'blab hub':'blab');d.textContent=n.label;lbox.appendChild(d);brainLabels.push({pos:p,el:d});}});
  const lp=[];links.forEach(l=>{const a=pos[l.source],b=pos[l.target];if(a&&b)lp.push(a.x,a.y,a.z,b.x,b.y,b.z);});
  if(lp.length){const lg=new THREE.BufferGeometry();lg.setAttribute('position',new THREE.Float32BufferAttribute(lp,3));
    brainRoot.add(new THREE.LineSegments(lg,new THREE.LineBasicMaterial({color:ACC(),transparent:true,opacity:0.13,blending:THREE.AdditiveBlending,depthWrite:false})));}
}
function brainSyncLabels(){
  if(!brainLabels||!brainLabels.length||!brainCam||!_TH)return;
  const wrap=$('#brain-wrap');if(!wrap)return;const W=wrap.clientWidth,H=wrap.clientHeight,v=new _TH.Vector3();
  for(const L of brainLabels){v.copy(L.pos).applyMatrix4(brainRoot.matrixWorld);const wz=v.z;v.project(brainCam);
    if(v.z>1||wz<-0.6){L.el.style.opacity='0';continue;}                    // behind camera / far side
    L.el.style.transform='translate(-50%,-50%) translate('+((v.x*0.5+0.5)*W)+'px,'+((-v.y*0.5+0.5)*H)+'px)';
    L.el.style.opacity=String(Math.min(0.95,0.35+(wz+0.6)/7));}             // fade toward the back
}
let brainT0=null;
function brainTick(ts){
  if(curView!=='brain'){brainRAF=null;brainT0=null;return;}
  if(brainT0===null)brainT0=ts;const t=(ts-brainT0)/1000;
  if(brainRoot){if(brainAutoRot&&!brainDragging)brainRoot.rotation.y+=0.0016;
    if(brainCoreMesh)brainCoreMesh.scale.setScalar(1.2*(1+0.12*Math.sin(t*2.2)));
    for(const r of brainRings)r.rotation.z+=r.userData.spin;}
  if(brainRenderer&&brainScene&&brainCam)brainRenderer.render(brainScene,brainCam);
  brainSyncLabels();
  brainRAF=requestAnimationFrame(brainTick);
}
function brainPick(e){if(!brainRay||!brainCam||!_TH)return null;const cv=$('#brain-canvas'),r=cv.getBoundingClientRect();
  const mv=new _TH.Vector2(((e.clientX-r.left)/r.width)*2-1,-((e.clientY-r.top)/r.height)*2+1);
  brainRay.setFromCamera(mv,brainCam);const hits=brainRay.intersectObjects(brainNodeMeshes,false);return hits.length?hits[0].object:null;}
(function initBrain3D(){
  const cv=$('#brain-canvas');if(!cv)return;
  cv.addEventListener('pointerdown',e=>{brainDragging=true;brainDidRotate=false;brainLast={x:e.clientX,y:e.clientY};
    try{cv.setPointerCapture(e.pointerId);}catch(_){}const bm=$('#brain-menu');if(bm)bm.classList.remove('on');});
  cv.addEventListener('pointermove',e=>{
    if(brainDragging&&brainRoot){const dx=e.clientX-brainLast.x,dy=e.clientY-brainLast.y;if(Math.abs(dx)+Math.abs(dy)>2)brainDidRotate=true;
      brainRoot.rotation.y+=dx*0.006;brainRoot.rotation.x=Math.max(-1.3,Math.min(1.3,brainRoot.rotation.x+dy*0.006));brainLast={x:e.clientX,y:e.clientY};return;}
    if(curView!=='brain')return;const node=brainPick(e),tip=$('#brain-tip');cv.style.cursor=node?'pointer':'grab';
    if(node&&tip){const r=cv.getBoundingClientRect();tip.style.display='block';tip.style.left=(e.clientX-r.left+14)+'px';tip.style.top=(e.clientY-r.top+10)+'px';tip.textContent=node.userData.label;}
    else if(tip)tip.style.display='none';});
  function endP(){brainDragging=false;}
  cv.addEventListener('pointerup',e=>{const rot=brainDidRotate;endP();if(rot)return;
    const node=brainPick(e);if(!node){$('#brain-menu').classList.remove('on');return;}
    const n=node.userData,r=cv.getBoundingClientRect();
    const leaf=n.id.indexOf(':')>0&&!n.id.startsWith('g:')&&n.id!=='core'&&!n.id.endsWith(':more');
    if(leaf)brainNodeMenu(n,e.clientX-r.left,e.clientY-r.top);else if(n.view)switchView(n.view);});
  cv.addEventListener('pointercancel',endP);
  cv.addEventListener('wheel',e=>{e.preventDefault();if(!brainCam)return;
    brainCam.position.z=Math.min(80,Math.max(14,brainCam.position.z*(e.deltaY<0?0.9:1.1)));},{passive:false});
})();
document.getElementById('brain-reset')?.addEventListener('click',()=>{
  brainAutoRot=true;if(brainCam)brainCam.position.set(0,0,34);if(brainRoot)brainRoot.rotation.set(0,0,0);});
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
  loadPanel();speakNewNotifs();loadPages();
  // live sync: refresh the current data view, unless a modal is open or the user is typing
  const modalOpen=$('#modal').classList.contains('on');
  const typing=['INPUT','TEXTAREA','SELECT'].includes((document.activeElement||{}).tagName);
  if(!modalOpen&&!typing&&curView&&_VLOAD[curView])_VLOAD[curView]();
}catch(e){}}
// Speak proactive alerts aloud while you're at the screen (JARVIS interjecting).
let _spokeNotif=parseInt(localStorage.getItem('ev_spoke_notif')||'0');
async function speakNewNotifs(){try{
  const items=(await (await fetch('/api/notifications',{headers:H()})).json()).items||[];
  if(!items.length)return;
  const maxId=Math.max.apply(null,items.map(n=>n.id));
  const first=_spokeNotif===0;const fresh=items.filter(n=>n.id>_spokeNotif);
  _spokeNotif=maxId;localStorage.setItem('ev_spoke_notif',String(maxId));
  if(first||!fresh.length||document.hidden)return;   // don't blurt history / when tab hidden
  const n=fresh[0];const say=((n.title||'')+(n.body?('. '+n.body):'')).trim();  // TTS strips emoji
  if(say){sfx('recv');speak(say.slice(0,240));}       // respects the VOZ toggle
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
  const rc=el('button','ip-x');rc.title=TR('receipt.logExpense');rc.appendChild(ficon('wallet'));rc.onclick=()=>receiptFromImage(f);
  const x=el('button','ip-x','×');x.title=TR('common.removeT');x.onclick=()=>setPendingImg(null);
  p.appendChild(img);p.appendChild(el('span','ip-name',f.name+TR('receipt.imgHint')));p.appendChild(rc);p.appendChild(x);p.style.display='flex';window.lucide&&lucide.createIcons();if(txt)txt.focus();}
async function receiptFromImage(file){if(!file)return;const p=thinking();setState('thinking');
  try{const fd=new FormData();fd.append('image',file);
    const j=await (await fetch('/api/receipt',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    p.remove();
    if(!j.ok){sys(j.msg||TR('receipt.noValue'));return;}
    const ok=await confirmDialog(t('confirm.logRs')+' R$ '+Number(j.amount).toFixed(2)+' — '+j.description+' (#'+j.category+')?');
    if(ok){setPendingImg(null);switchView('chat');runCmd('gasto '+Number(j.amount).toFixed(2)+' '+j.description+' #'+j.category);}
  }catch(e){p.remove();sys(TR('receipt.readFail'));}finally{setState();}}
async function sendImage(file,caption){if(!file)return;youImg(caption,URL.createObjectURL(file));const p=thinking();setState('thinking');
  try{const fd=new FormData();fd.append('image',file,file.name||'imagem.jpg');if(caption)fd.append('text',caption);fd.append('thread',thread);
    const j=await (await fetch('/api/vision',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    p.remove();ev(j.reply||TR('chat.noReply'));speak(j.reply);}catch(e){p.remove();sys(TR('img.sendFail'));}finally{setState();}}
$('#imgbtn').onclick=()=>$('#imgfile').click();
// live camera — aponta e pergunta ("olha isso")
let _camStream=null,_camFacing='environment';
function stopCam(){if(_camStream){_camStream.getTracks().forEach(t=>t.stop());_camStream=null;}}
async function startCam(){stopCam();
  try{_camStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:_camFacing}});$('#cam-video').srcObject=_camStream;}
  catch(e){$('#cam-hint').textContent=TR('cam.openFail')+((e&&e.message)||e);}}
$('#cambtn').onclick=async()=>{
  if(!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia)){sys(TR('cam.unavailable'));return;}
  $('#cam').classList.add('on');$('#cam-hint').textContent=TR('cam.openHint');await startCam();};
$('#cam-x').onclick=()=>{stopQR();stopCamLive();stopCam();$('#cam').classList.remove('on');};
$('#cam-flip').onclick=()=>{_camFacing=_camFacing==='environment'?'user':'environment';startCam();};
// --- câmera ao vivo: caixas de rosto (MediaPipe) + narração por movimento + "o que é isso" ---
let _camLive=false,_faceDet=null,_faceRAF=0,_motionPrev=null,_lastSee=0,_camBusy=false;
const _mCv=document.createElement('canvas');_mCv.width=48;_mCv.height=36;const _mCtx=_mCv.getContext('2d',{willReadFrequently:true});
function camResult(t){const r=$('#cam-result');if(!t){r.classList.remove('on');return;}r.textContent=t;r.classList.add('on');}
function camFrameBlob(cb){const v=$('#cam-video');if(!v||!v.videoWidth)return cb(null);const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);c.toBlob(cb,'image/jpeg',0.82);}
function camSee(mode){if(_camBusy)return;_camBusy=true;if(mode==='what')camResult(TR('cam.analyzing'));
  camFrameBlob(async b=>{if(!b){_camBusy=false;return;}
    try{const fd=new FormData();fd.append('image',b,'frame.jpg');fd.append('mode',mode);
      const j=await (await fetch('/api/see',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
      const t=(j.text||'').trim();if(t){camResult(t);const od=mode!=='live';if(od||voiceOn)speak(t,od);}
    }catch(e){}finally{_camBusy=false;}});}
let _objDet=null;
const OBJ_PT={person:'pessoa',cup:'copo',bottle:'garrafa','cell phone':'celular',laptop:'notebook',keyboard:'teclado',mouse:'mouse',book:'livro',chair:'cadeira','dining table':'mesa',tv:'TV',remote:'controle',clock:'relógio','potted plant':'planta',backpack:'mochila',handbag:'bolsa',car:'carro',bicycle:'bicicleta',dog:'cachorro',cat:'gato',bird:'pássaro','wine glass':'taça',fork:'garfo',knife:'faca',spoon:'colher',bowl:'tigela',banana:'banana',apple:'maçã',orange:'laranja',pizza:'pizza',cake:'bolo',scissors:'tesoura',umbrella:'guarda-chuva',couch:'sofá',bed:'cama'};
let _detInit=false,_gestDet=null,_gestLast='',_gestN=0,_gestFired=0;
const GEMOJI={Thumb_Up:'👍',Thumb_Down:'👎',Victory:'✌️',Open_Palm:'✋',Closed_Fist:'✊',Pointing_Up:'☝️',ILoveYou:'🤟'};
function handleGesture(name){$('#cam-hint').textContent=TR('cam.gesture')+(GEMOJI[name]||name);
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
// JARVIS-style targeting reticle: corner brackets that "lock on" + crosshair
// ticks + a rotating dashed ring + a HUD label. drawn over each detection.
function drawBox(ctx,bb,color,label){const x=bb.originX*ctx._sx,y=bb.originY*ctx._sy,w=bb.width*ctx._sx,h=bb.height*ctx._sy;
  const t=performance.now()/1000,pulse=0.5+0.5*Math.sin(t*3.2);
  const cl=Math.max(9,Math.min(w,h)*0.22);            // corner bracket length
  ctx.save();ctx.strokeStyle=color;ctx.shadowColor=color;ctx.shadowBlur=8;ctx.lineWidth=2;ctx.lineCap='round';
  ctx.globalAlpha=0.75+0.25*pulse;
  const corner=(cx,cy,dx,dy)=>{ctx.beginPath();ctx.moveTo(cx+dx*cl,cy);ctx.lineTo(cx,cy);ctx.lineTo(cx,cy+dy*cl);ctx.stroke();};
  corner(x,y,1,1);corner(x+w,y,-1,1);corner(x,y+h,1,-1);corner(x+w,y+h,-1,-1);
  // center crosshair ticks
  const mx=x+w/2,my=y+h/2,tk=Math.min(w,h)*0.07+3;ctx.globalAlpha=0.5+0.4*pulse;ctx.lineWidth=1.2;
  ctx.beginPath();ctx.moveTo(mx-tk,my);ctx.lineTo(mx+tk,my);ctx.moveTo(mx,my-tk);ctx.lineTo(mx,my+tk);ctx.stroke();
  // rotating dashed lock ring
  const r=Math.min(w,h)*0.5*0.62;if(r>6){ctx.globalAlpha=0.4+0.3*pulse;ctx.setLineDash([r*0.5,r*0.7]);ctx.lineDashOffset=-t*30;ctx.beginPath();ctx.arc(mx,my,r,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);}
  ctx.shadowBlur=0;ctx.globalAlpha=1;
  if(label){const lb='⌖ '+label.toUpperCase();ctx.font='700 11px ui-monospace, monospace';const tw=ctx.measureText(lb).width+12;
    ctx.fillStyle='rgba(4,7,12,.85)';ctx.fillRect(x,Math.max(0,y-19),tw,17);
    ctx.fillStyle=color;ctx.fillText(lb,x+5,Math.max(11,y-6));}
  ctx.restore();}
function faceLoop(){if(!_camLive)return;const v=$('#cam-video');
  if(v&&v.videoWidth){const ctx=ovCtx();let nf=0,no=0;const ts=performance.now();
    if(ctx&&_faceDet){try{(_faceDet.detectForVideo(v,ts).detections||[]).forEach(d=>{if(d.boundingBox){drawBox(ctx,d.boundingBox,ACC(),TR('cam.faceWord'));nf++;}});}catch(e){}}
    if(ctx&&_objDet){try{(_objDet.detectForVideo(v,ts).detections||[]).forEach(d=>{const c=(d.categories&&d.categories[0])||{};if(c.categoryName==='person')return;const nm=(_lang==='pt'?OBJ_PT[c.categoryName]:c.categoryName)||c.categoryName||TR('cam.objWord');if(d.boundingBox){drawBox(ctx,d.boundingBox,ACC(),nm);no++;}});}catch(e){}}
    if(ctx&&_gestDet&&!_camBusy){try{const gr=_gestDet.recognizeForVideo(v,ts);const g=(gr.gestures&&gr.gestures[0]&&gr.gestures[0][0])||null;const nm=(g&&g.score>0.55)?g.categoryName:'';
      if(nm&&nm!=='None'){if(nm===_gestLast)_gestN++;else{_gestLast=nm;_gestN=1;}if(_gestN===5&&performance.now()-_gestFired>2800){_gestFired=performance.now();handleGesture(nm);}}
      else{_gestLast='';_gestN=0;}}catch(e){}}
    if(ctx)$('#cam-hint').textContent=(nf?nf+' '+TR('cam.faceWord')+'(s) · ':'')+(no?no+' '+TR('cam.objWord')+'(s) · ':'')+TR('cam.liveHintSuffix');}
  if(v&&v.videoWidth){try{_mCtx.drawImage(v,0,0,48,36);const cur=_mCtx.getImageData(0,0,48,36).data;
    if(_motionPrev){let diff=0,n=0;for(let i=0;i<cur.length;i+=16){diff+=Math.abs(cur[i]-_motionPrev[i]);n++;}diff/=n;
      const now=performance.now();if(diff>18&&now-_lastSee>6500&&!_camBusy){_lastSee=now;camSee('live');}}
    _motionPrev=cur;}catch(e){}}
  _faceRAF=requestAnimationFrame(faceLoop);}
async function startCamLive(){_camLive=true;$('#cam-live').classList.add('on');$('#cam-hint').textContent=TR('cam.livePreparing');
  await initDetectors();$('#cam-hint').textContent=(_faceDet||_objDet)?TR('cam.liveOn'):TR('cam.liveOnNoDetect');
  _motionPrev=null;_lastSee=performance.now();cancelAnimationFrame(_faceRAF);faceLoop();}
function stopCamLive(){_camLive=false;const lb=$('#cam-live');if(lb)lb.classList.remove('on');cancelAnimationFrame(_faceRAF);const cv=$('#cam-fx');if(cv&&cv.getContext)cv.getContext('2d').clearRect(0,0,cv.width,cv.height);camResult('');}
$('#cam-live').onclick=()=>{_camLive?stopCamLive():startCamLive();};
$('#cam-what').onclick=()=>camSee('what');
$('#cam-tr').onclick=()=>{camResult(TR('cam.translating'));camSee('translate');};
$('#cam-food').onclick=()=>{camResult(TR('cam.estimating'));camSee('food');};
$('#cam-scan').onclick=()=>{camResult(TR('cam.readingDoc'));camFrameBlob(async b=>{if(!b)return;
  try{const fd=new FormData();fd.append('image',b,'doc.jpg');const j=await (await fetch('/api/scan',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();
    camResult(j.msg||TR('cam.ready'));speak(j.msg||'',true);loadPanel();}catch(e){camResult(TR('cam.scanFail'));}});};
// QR / código de barras (client-side, grátis, via BarcodeDetector)
let _qrScan=false,_qrDet=null,_qrRAF=0;
function stopQR(){_qrScan=false;const b=$('#cam-qr');if(b)b.classList.remove('on');cancelAnimationFrame(_qrRAF);}
async function qrLoop(){if(!_qrScan)return;const v=$('#cam-video');
  if(v&&v.videoWidth){try{const codes=await _qrDet.detect(v);if(codes&&codes.length){const val=(codes[0].rawValue||'').trim();stopQR();
    if(/^https?:\/\//i.test(val)){camResult(TR('cam.linkPrefix')+val);window.open(val,'_blank','noopener');}
    else if(val){camResult(TR('cam.codeRead')+val);speak('Código: '+val,true);}else camResult(TR('cam.cantRead'));return;}}catch(e){}}
  _qrRAF=requestAnimationFrame(qrLoop);}
$('#cam-qr').onclick=()=>{if(_qrScan){stopQR();camResult('');return;}
  if(!('BarcodeDetector' in window)){camResult(TR('cam.qrNeedChrome'));return;}
  try{if(!_qrDet)_qrDet=new BarcodeDetector();}catch(e){camResult(TR('cam.codeUnavail'));return;}
  _qrScan=true;$('#cam-qr').classList.add('on');camResult(TR('cam.qrPoint'));qrLoop();};
$('#cam-shot').onclick=()=>{const v=$('#cam-video');if(!v||!v.videoWidth){$('#cam-hint').textContent=TR('cam.waitLoad');return;}
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
async function camFace(){if(_fapiBusy)return;_fapiBusy=true;camResult(TR('cam.faceAnalyzing'));
  try{const desc=await faceDescriptor();
    if(!desc){camResult(TR('cam.faceNotClear'));return;}
    const st=await (await fetch('/api/face',{headers:H()})).json();
    if(!st.enrolled){
      if(!confirm(TR('cam.faceEnrollAsk'))){camResult('');return;}
      await fetch('/api/face',{method:'POST',headers:H(),body:JSON.stringify({descriptor:desc})});
      camResult(TR('cam.faceEnrolled'));speak('Rosto cadastrado. Da próxima vez eu te reconheço.',true);return;}
    const d=faceDist(desc,st.descriptor);
    if(d<0.52){camResult(TR('cam.faceHi'));speak('Olá, Ryan! Reconheci você.',true);}
    else{camResult(TR('cam.faceUnknown'));}
  }catch(e){camResult(TR('cam.faceUnavail'));}
  finally{_fapiBusy=false;}}
$('#cam-face').onclick=camFace;
$('#cam-face').oncontextmenu=async e=>{e.preventDefault();
  if(!confirm(TR('cam.faceEraseAsk')))return;
  await fetch('/api/face',{method:'POST',headers:H(),body:JSON.stringify({clear:true})});
  camResult('Rosto apagado. Nenhuma biometria fica guardada.');};
$('#imgfile').onchange=e=>{const f=e.target.files[0];if(f)setPendingImg(f);e.target.value='';};
(function(){const cv=$('#chatview');if(!cv)return;
  ['dragover','dragenter'].forEach(n=>cv.addEventListener(n,e=>{e.preventDefault();cv.classList.add('drag');}));
  ['dragleave','drop'].forEach(n=>cv.addEventListener(n,e=>{e.preventDefault();cv.classList.remove('drag');}));
  cv.addEventListener('drop',e=>{const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f&&f.type.startsWith('image/'))setPendingImg(f);});})();
$('#gsearch').onclick=()=>openForm(t('form.searchAll'),[{key:'q',label:t('field.search'),placeholder:t('field.searchAllPh')}],v=>{if(!v.q)return;switchView('chat');runCmd('procurar '+v.q);});
function toastUndo(msg,onUndo){let t=document.getElementById('_toast');if(!t){t=el('div','');t.id='_toast';t.style.cssText='position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:var(--elev);border:1px solid var(--line-2);color:var(--fg);padding:11px 17px;border-radius:11px;font-size:13px;z-index:9999;box-shadow:0 8px 30px rgba(0,0,0,.45);display:flex;align-items:center;gap:14px;transition:opacity .3s';document.body.appendChild(t);}
  t.textContent='';t.appendChild(document.createTextNode(msg));const b=el('button','',TR('undo.btn'));b.style.cssText='background:none;border:none;color:var(--fg);font:inherit;font-weight:700;cursor:pointer;text-decoration:underline';b.onclick=()=>{clearTimeout(t._h);t.style.opacity='0';onUndo();};t.appendChild(b);
  t.style.opacity='1';clearTimeout(t._h);t._h=setTimeout(()=>t.style.opacity='0',6000);}
async function delU(delUrl,delBody,recUrl,recBody,reload,label){await fetch(delUrl,{method:'POST',headers:H(),body:JSON.stringify(delBody)});reload();loadPanel();
  toastUndo(t(label||'ent.item')+' '+t('undo.deleted'),async()=>{await fetch(recUrl,{method:'POST',headers:H(),body:JSON.stringify(recBody)});reload();loadPanel();});}
async function startApp(){try{COMMANDS=(await (await fetch('/api/commands',{headers:H()})).json()).commands;}catch(e){}
  scopeEl.textContent=t('bnav.chat')+' · '+thread;await loadFolders();await loadHistory();await loadConfig();loadPanel();loadPages();
  initPWA();startPoll();startEvents();startNpPoll();try{spInitSDK();}catch(e){}window.lucide&&lucide.createIcons();
  switchView('inicio');}   // abre no painel de uso (Início)
function enter(){$('#login').classList.remove('on');startApp();
  // boot overlay + spoken briefing only once per browser tab — reloading shouldn't replay it
  if(!sessionStorage.getItem('ev_welcomed')){sessionStorage.setItem('ev_welcomed','1');welcome();}}
async function doLogin(){const inp=$('#login-token');const tok=((inp&&inp.value.trim())||token);if(!tok){$('#login-err').textContent=t('login.enterToken');if(inp)inp.style.display='block';return;}
  $('#login-err').textContent=t('login.checking');if(!(await validate(tok))){$('#login-err').textContent=t('login.invalid');token='';localStorage.removeItem('ev_token');if(inp)inp.style.display='block';return;}
  token=tok;localStorage.setItem('ev_token',tok);enter();}
(async function boot(){
  if(token && await validate(token)){enter();return;}          // já logado -> entra direto
  token='';const inp=$('#login-token');if(inp)inp.style.display='block';$('#login').classList.add('on');window.lucide&&lucide.createIcons();
  $('#login-btn').onclick=doLogin;if(inp)inp.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});setTimeout(()=>{$('#login-btn').focus();},60);})();

try{applyLang(_lang,true);}catch(e){}
</script></body></html>"""
