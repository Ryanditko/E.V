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
from ..providers import voice as voice_mod

log = logging.getLogger("ev.web")

_DEFAULT_FOLDERS = ["geral", "work", "university", "personal"]

_PAGE = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>E.V.</title>
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
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--ink);color:var(--fg);font-family:var(--body);-webkit-font-smoothing:antialiased;overflow:hidden}
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
#pomo-toggle{width:62px!important;height:62px;border-radius:50%!important;font-size:20px!important;background:var(--fg)!important;color:var(--ink)!important;border:none!important}
#pomo-presets{display:flex;gap:8px}
#pomo-presets button{font-family:var(--mono);font-size:11px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
#pomo-presets button:hover{color:var(--fg);border-color:var(--line-2)}
#pomo-pip{margin-top:4px;font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:999px;padding:9px 16px;cursor:pointer}
#pomo-pip:hover{color:var(--fg);border-color:var(--line-2)}
#pomo-x{position:absolute;top:20px;right:24px;font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
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
.tabs{display:flex;gap:3px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:3px}
.tab{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--muted);border:none;background:transparent;border-radius:8px;padding:7px 13px;cursor:pointer}
.tab.on{background:var(--fg);color:var(--ink)}
#chatview{flex:1;display:flex;flex-direction:column;min-height:0}
#taskview,#kbview,#expview,#remview,#memview,#calview{flex:1;min-height:0;overflow:auto;padding:24px;display:none}
.cal-head{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:18px}
#calgrid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;max-width:940px;margin:0 auto}
.cal-dow{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--subtle);text-align:center;padding:4px}
.cal-cell{min-height:94px;border:1px solid var(--line);border-radius:10px;padding:7px;background:var(--surface);cursor:pointer;transition:border-color .15s;overflow:hidden}
.cal-cell:hover{border-color:var(--line-2)}.cal-cell.empty{background:transparent;border:none;cursor:default}
.cal-cell.today{border-color:var(--fg)}
.cal-num{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:5px}.cal-cell.today .cal-num{color:var(--fg);font-weight:600}
.cal-ev{font-size:11px;background:var(--elev);border-radius:5px;padding:2px 5px;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cal-more{font-family:var(--mono);font-size:10px;color:var(--subtle)}
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
.tv-form{display:flex;gap:8px;margin-bottom:22px;max-width:720px}
.tv-form input{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:12px 15px;color:var(--fg);font:inherit;font-size:15px}
.tv-form #task-text{flex:1}.tv-form #task-cat{width:140px;flex:none;font-family:var(--mono);font-size:13px}
.tv-form input:focus{outline:none;border-color:var(--line-2)}
.tv-cat{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--subtle);margin:20px 0 9px}
.tv-row{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;background:var(--surface);max-width:720px;transition:border-color .15s}
.tv-row:hover{border-color:var(--line-2)}.tv-row .txt{flex:1;line-height:1.4}
.tv-ic{width:34px;height:34px;flex:none;display:grid;place-items:center;border-radius:9px;border:1px solid var(--line);background:var(--elev);color:var(--muted);cursor:pointer;transition:.15s}
.tv-ic:hover{color:var(--fg);border-color:var(--line-2)}.tv-ic svg{width:16px;height:16px}
.tv-empty{color:var(--subtle);font-family:var(--mono);font-size:13px;padding:8px 2px}
#log{flex:1;min-height:0;overflow-y:auto;padding:20px 22px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:82%;padding:13px 16px;line-height:1.55;border:1px solid var(--line);border-radius:16px;animation:rise .32s cubic-bezier(.2,.7,.2,1)}
.msg.you{align-self:flex-end;background:var(--fg);color:var(--ink);border:none;border-bottom-right-radius:5px;font-weight:500}
.msg.ev{align-self:flex-start;background:var(--elev);border-bottom-left-radius:5px}
.msg.sys{align-self:center;background:transparent;border:1px dashed var(--line);color:var(--muted);font-family:var(--mono);font-size:12px}
.msg p{margin:0 0 6px}.msg p:last-child{margin:0}
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
form{display:flex;align-items:center;gap:10px;padding:14px 18px;border-top:1px solid var(--line);position:relative}
.field{flex:1;display:flex;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:2px 6px 2px 16px;transition:.2s}
.field:focus-within{border-color:var(--line-2);box-shadow:0 0 0 4px rgba(244,243,241,.05)}
#txt{flex:1;background:transparent;border:none;outline:none;color:var(--fg);font-family:var(--body);font-size:15px;padding:11px 0}
body.term #txt{font-family:var(--mono)}
.icon{width:44px;height:44px;flex:none;display:grid;place-items:center;border-radius:12px;border:1px solid var(--line);background:var(--elev);color:var(--fg);cursor:pointer;position:relative;overflow:hidden;transition:.14s}
.icon:hover{transform:translateY(-1px);border-color:var(--line-2)}.icon:active{transform:scale(.95)}
.icon.send{background:var(--fg);color:var(--ink);border:none}.icon.mic.on{background:var(--fg);color:var(--ink);border:none}
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
.mrow{display:flex;align-items:center;gap:10px;padding:9px 6px;border-top:1px solid var(--line);cursor:pointer;font-size:14px}
.mrow input{width:16px;height:16px;accent-color:var(--fg)}
.mfield{margin-bottom:13px}.mlabel{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}
.minput{width:100%;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:11px 13px;color:var(--fg);font:inherit;font-size:14px}
.minput:focus{outline:none;border-color:var(--line-2)}
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
@media(max-width:980px){#app{grid-template-columns:1fr}.rail{display:none}#slash{left:18px;right:18px}}
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
      <div class="tabs"><button class="tab on" data-view="chat">Conversa</button><button class="tab" data-view="tasks">Tarefas</button><button class="tab" data-view="exp">Gastos</button><button class="tab" data-view="rem">Lembretes</button><button class="tab" data-view="cal">Agenda</button><button class="tab" data-view="mem">Memórias</button><button class="tab" data-view="kb">Base</button></div>
      <span class="eyebrow" id="scope">geral</span><span style="flex:1"></span>
      <button class="tbtn" id="vcopen">◉ FALAR</button>
      <button class="tbtn" id="term">TERMINAL</button><button class="tbtn on" id="voz">VOZ</button></div>
    <div id="chatview">
      <div id="log"></div>
      <form id="f"><div id="slash"></div>
        <button type="button" class="icon mic" id="mic" title="Falar"><span class="mg">🎙</span><span class="wave"><b></b><b></b><b></b><b></b></span></button>
        <div class="field"><input id="txt" placeholder="Fala com a E.V.  ·  digite / para comandos" autocomplete="off"></div>
        <button class="icon send" id="send" title="Enviar">➤</button></form>
    </div>
    <div id="taskview">
      <div class="tv-h">Tarefas</div>
      <form id="taskform" class="tv-form">
        <input id="task-text" placeholder="Nova tarefa..." autocomplete="off">
        <input id="task-cat" placeholder="categoria" value="geral" autocomplete="off">
        <button class="mbtn" type="submit">Adicionar</button>
      </form>
      <div id="tasklist"></div>
    </div>
    <div id="kbview">
      <div class="tv-h">Base de conhecimento</div>
      <div class="kb-add">
        <form id="kb-urlf" class="tv-form"><input id="kb-url" placeholder="https://...  (indexar uma página)"><button class="mbtn" type="submit">Indexar URL</button></form>
        <div class="tv-form" style="align-items:center"><label class="mbtn2" for="kb-file" style="cursor:pointer">⭱ Enviar arquivo (PDF / Word / txt)</label><input id="kb-file" type="file" accept=".pdf,.docx,.txt,.md" style="display:none"><span id="kb-fmsg" class="tv-empty"></span></div>
        <form id="kb-textf"><input id="kb-title" class="minput" placeholder="Título da nota" style="margin-bottom:8px"><textarea id="kb-text" class="minput" placeholder="Cole um texto pra E.V. aprender e responder com base nele..."></textarea><button class="mbtn" type="submit" style="margin-top:8px">Adicionar texto</button></form>
      </div>
      <div class="tv-cat">Documentos indexados</div>
      <div id="kblist"></div>
    </div>
    <div id="expview">
      <div class="tv-h">Gastos</div>
      <form id="expform" class="tv-form"><input id="exp-amt" placeholder="Valor" style="width:110px;flex:none"><input id="exp-desc" placeholder="Descrição"><input id="exp-cat" placeholder="categoria" value="geral" style="width:140px;flex:none"><button class="mbtn" type="submit">Registrar</button></form>
      <div id="expchart"></div>
      <div class="tv-cat">Últimos 60 dias</div>
      <div id="explist"></div>
    </div>
    <div id="remview">
      <div class="tv-h">Lembretes</div>
      <form id="remform" class="tv-form"><input id="rem-text" placeholder="Lembrar de..."><input id="rem-when" type="datetime-local" style="flex:none"><button class="mbtn" type="submit">Criar</button></form>
      <div class="tv-cat">Em aberto</div>
      <div id="remlist"></div>
    </div>
    <div id="calview">
      <div class="cal-head"><button class="tbtn" id="cal-prev">‹</button><div class="tv-h" id="cal-title" style="margin:0;min-width:200px;text-align:center"></div><button class="tbtn" id="cal-next">›</button></div>
      <div id="calgrid"></div>
    </div>
    <div id="memview">
      <div class="tv-h">Memórias</div>
      <form id="memform" class="tv-form"><input id="mem-text" placeholder="Algo que a E.V. deve lembrar sobre você..."><button class="mbtn" type="submit">Salvar</button></form>
      <div class="tv-cat">O que a E.V. sabe</div>
      <div id="memlist"></div>
    </div>
  </main>
  <aside id="right" class="rail">
    <div class="eyebrow">Sistema <span class="mini" id="edit-stats">editar</span></div>
    <div id="stats"></div>
    <div class="eyebrow">Ações rápidas <span class="mini" id="edit-acts">editar</span></div>
    <div class="grid2" id="acts"></div>
    <div class="eyebrow">Provedor de IA</div>
    <select id="prov"><option>auto</option><option>gemini</option><option>groq</option><option>openrouter</option><option>ollama</option></select>
  </aside>
</div>
<div id="vc">
  <button id="vc-x">FECHAR</button>
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="vc-txt">Toque no microfone e fale.</div>
  <div id="vc-sub">voz ao vivo · português</div>
  <div id="vc-actions"><button class="vcbtn" id="vc-mic">🎙</button></div>
</div>
<div id="pomo">
  <button id="pomo-x">FECHAR</button>
  <div class="bigcore"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div><div class="bdot"></div></div>
  <div id="pomo-timebox"><div id="pomo-time">25:00</div><div id="pomo-label">Foco</div></div>
  <div id="pomo-ctl"><button data-m="-5">−5</button><button id="pomo-toggle">▶</button><button data-m="5">+5</button><button id="pomo-reset">reset</button></div>
  <div id="pomo-presets"><button data-set="15">15 min</button><button data-set="25">25 min</button><button data-set="50">50 min</button></div>
  <button id="pomo-pip">⧉ minimizar</button>
</div>
<div id="pomo-mini">
  <div class="pm-head"><span class="pm-grip">⋮⋮</span><span style="flex:1"></span><button class="pm-btn" id="pm-open" title="expandir">⤢</button><button class="pm-btn" id="pm-close" title="fechar">✕</button></div>
  <div class="pm-body"></div>
</div>
<div id="modal"></div>
<div id="cmdk"><div class="ck-card"><input id="ck-input" placeholder="Buscar ação ou comando...  (Esc pra fechar)" autocomplete="off"><div id="ck-list"></div></div></div>
<script>
let token=localStorage.getItem('ev_token');
if(!token){token=prompt('Token de acesso da E.V.:')||'';localStorage.setItem('ev_token',token);}
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

function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;}
const HASEMO=/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{2300}-\u{23FF}\u{20E3}]/u;
const EMOG=/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{2300}-\u{23FF}️‍\u{20E3}]/gu;
const IC={'📋':'list-checks','📝':'file-pen','✅':'check-circle-2','⏰':'alarm-clock','💰':'wallet','🧠':'brain','📄':'file-text','📰':'newspaper','☀':'sun','🌧':'cloud-rain','🩺':'activity','🔎':'search','📊':'bar-chart-3','📚':'book-open','🍅':'timer','⚠':'triangle-alert','🔕':'bell-off','🔔':'bell','🗄':'database','📅':'calendar-days','🔗':'link','📌':'pin','🌐':'globe','🎧':'headphones','📥':'download','🧽':'eraser','🧹':'trash-2','🔀':'shuffle','▶':'play','⏸':'pause','⏹':'square','💧':'droplet','🕷':'sparkles','🗓':'calendar-clock','📔':'notebook-pen','☕':'coffee'};
function stripEmoji(s){return s.replace(EMOG,'').replace(/\s{2,}/g,' ').trim();}
function iconName(s){for(const ch of s){if(IC[ch])return IC[ch];}return 'sparkles';}
function ficon(n){const i=document.createElement('i');i.setAttribute('data-lucide',n);return i;}
// structured, monochrome rendering with Lucide icons (no emoji read-out)
function renderReply(box,text){box.textContent='';const lines=(text||'').split('\n');let first=true;
  lines.forEach(ln=>{const s=ln.trim();if(!s)return;let m;
    if(first && HASEMO.test(s)){const h=el('span','h');h.appendChild(ficon(iconName(s)));h.appendChild(document.createTextNode(stripEmoji(s)));box.appendChild(h);first=false;return;}
    if((m=s.match(/^\[(.+)\]$/))){box.appendChild(el('div','cat',m[1]));return;}
    if((m=s.match(/^#(\w+)\s+(.*)$/))){const r=el('div','row');r.appendChild(el('span','id','#'+m[1]));
      const t=el('span','t');const tt=stripEmoji(m[2]);const parts=tt.split(/\s+(?=\d+[.)]\s)/);
      if(parts.length>1)parts.forEach(p=>t.appendChild(el('div','',p)));else t.textContent=tt;
      r.appendChild(t);box.appendChild(r);return;}
    if(/^(Concluir|Cancelar|Uso|Remover|Apagar):/i.test(s)||s.startsWith('/')){box.appendChild(el('div','hint',stripEmoji(s)));return;}
    box.appendChild(el('p','',stripEmoji(s)));first=false;});
  window.lucide&&lucide.createIcons();
}
function you(t){const d=el('div','msg you',t);log.appendChild(d);log.scrollTop=log.scrollHeight;}
function ev(t){const d=el('div','msg ev');renderReply(d,t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function sys(t){const d=el('div','msg sys',t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function thinking(){const d=el('div','msg ev');d.innerHTML='<span class="tp"><i></i><i></i><i></i></span>';log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ripple(b,e){const r=el('span','ripple');const q=b.getBoundingClientRect(),s=Math.max(q.width,q.height);
  r.style.width=r.style.height=s+'px';r.style.left=((e?e.clientX:q.left+q.width/2)-q.left-s/2)+'px';
  r.style.top=((e?e.clientY:q.top+q.height/2)-q.top-s/2)+'px';b.appendChild(r);setTimeout(()=>r.remove(),500);}
async function speak(t,force){if((!voiceOn&&!force)||!t)return;try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text:t})});if(!r.ok)return;new Audio(URL.createObjectURL(await r.blob())).play().catch(()=>{});}catch(e){}}

async function send(msg){if(!msg)return;you(msg);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:msg,thread})});
    if(r.status===401){p.remove();sys('Token inválido — recarregue e informe o token certo.');localStorage.removeItem('ev_token');return;}
    const j=await r.json();p.remove();ev(j.reply);speak(j.reply);loadPanel();
  }catch(e){p.remove();sys('Sem conexão com a E.V. — '+e);}finally{setState();}}
async function runCmd(cmd,btn,e){const nm=cmd.trim().replace(/^\//,'').split(/\s+/)[0].toLowerCase();
  if(nm==='foco'){if(btn)ripple(btn,e);const n=cmd.match(/\d+/g)||[];openPomo(parseInt(n[0])||25,parseInt(n[1])||5);return;}
  if(btn)ripple(btn,e);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/cmd',{method:'POST',headers:H(),body:JSON.stringify({command:cmd,thread})});
    const j=await r.json();
    if(/^\/?limpar(chat)?\b/.test(cmd.trim())){log.textContent='';sys(j.reply);}
    else{p.remove();ev(j.reply);}
    loadPanel();}catch(err){p.remove();sys('Erro — '+err);}finally{setState();}}
f.onsubmit=e=>{e.preventDefault();if(slash.style.display==='block'&&slSel>=0){pickSlash();return;}
  ripple($('#send'));const m=txt.value.trim();txt.value='';hideSlash();
  if(m.startsWith('/'))runCmd(m.slice(1));else send(m);};

const CAT={tarefas:['Tarefas','list-checks'],lembretes:['Lembretes','alarm-clock'],gastos:['Gastos','wallet'],memorias:['Memórias','brain'],kb:['Base','book-open'],buscar:['Buscar web','search'],noticias:['Notícias','newspaper'],clima:['Clima','cloud-sun'],relatorio:['Relatório','bar-chart-3'],status:['Status','activity'],semana:['Semana','calendar-days'],foco:['Pomodoro','timer'],procurar:['Procurar','file-search'],calendario:['Agenda','calendar'],habitos:['Hábitos','repeat'],diario:['Diário','notebook-pen'],orcamentos:['Orçamentos','piggy-bank'],assinaturas:['Assinaturas','credit-card'],dados:['Meus dados','database'],insights:['Insights','sparkles'],quiz:['Quiz','graduation-cap']};
const SM={tasks:['Tarefas','list-checks','tarefas'],reminders:['Lembretes','alarm-clock','lembretes'],expenses:['Gastos · mês','wallet','gastos'],memories:['Memórias','brain','memorias'],kb:['Base','book-open','kb']};
let config={actions:['buscar','noticias','clima','relatorio','status','semana'],stats:['tasks','reminders','expenses','memories','kb']};let _counts={};
function renderStats(){const box=$('#stats');box.textContent='';config.stats.forEach(k=>{const m=SM[k];if(!m)return;
  const VMAP={tasks:'tasks',reminders:'rem',expenses:'exp',memories:'mem',kb:'kb'};
  const s=el('div','stat');s.onclick=()=>{if(VMAP[k])switchView(VMAP[k]);else runCmd(m[2]);};const lbl=el('span','lbl');lbl.appendChild(ficon(m[1]));lbl.appendChild(document.createTextNode(m[0]));
  const num=el('span','num');if(k==='expenses'){const rs=el('span','','R$');rs.style.cssText='font-size:12px;color:var(--subtle);margin-right:2px';num.appendChild(rs);}
  num.appendChild(document.createTextNode(_counts[k]!=null?_counts[k]:'0'));s.appendChild(lbl);s.appendChild(num);box.appendChild(s);});window.lucide&&lucide.createIcons();}
function renderActs(){const box=$('#acts');box.textContent='';config.actions.forEach(cmd=>{const m=CAT[cmd]||[cmd,'chevron-right'];
  const b=el('button','act');b.appendChild(ficon(m[1]));b.appendChild(document.createTextNode(m[0]));
  b.onclick=e=>{if(cmd==='foco')openPomo(25);else runCmd(cmd,b,e);};box.appendChild(b);});window.lucide&&lucide.createIcons();}
async function loadPanel(){try{const r=await fetch('/api/panel',{headers:H()});if(!r.ok)return;_counts=await r.json();
  renderStats();$('#s-prov').textContent=_counts.provider;$('#s-model').textContent=_counts.model;$('#prov').value=_counts.provider;}catch(e){}}
async function loadConfig(){try{config=await (await fetch('/api/config',{headers:H()})).json();}catch(e){}renderActs();}
async function saveConfig(){try{await fetch('/api/config',{method:'POST',headers:H(),body:JSON.stringify(config)});}catch(e){}}
$('#prov').onchange=()=>runCmd('provedor '+$('#prov').value);
function openPicker(title,sub,items,selected,onSave){const m=$('#modal');m.textContent='';const card=el('div','mcard');
  const tt=el('div','mtitle',title);tt.appendChild(el('small','',sub));card.appendChild(tt);const sel=new Set(selected);
  items.forEach(it=>{const row=el('label','mrow');const cb=document.createElement('input');cb.type='checkbox';cb.checked=sel.has(it.key);
    cb.onchange=()=>cb.checked?sel.add(it.key):sel.delete(it.key);row.appendChild(cb);row.appendChild(el('span','',it.label));card.appendChild(row);});
  const bar=el('div','mbar');const c=el('button','mbtn2','Cancelar');c.onclick=()=>m.classList.remove('on');
  const sv=el('button','mbtn','Salvar');sv.onclick=()=>{onSave([...sel]);m.classList.remove('on');};bar.appendChild(c);bar.appendChild(sv);card.appendChild(bar);
  m.appendChild(card);m.classList.add('on');}
function openForm(title,fields,onSave){const m=$('#modal');m.textContent='';const card=el('div','mcard');card.appendChild(el('div','mtitle',title));
  const inp={};fields.forEach(fd=>{const w=el('div','mfield');w.appendChild(el('label','mlabel',fd.label));
    let i;if(fd.type==='textarea'){i=document.createElement('textarea');}else{i=document.createElement('input');i.type='text';}
    i.className='minput';i.value=fd.value||'';if(fd.placeholder)i.placeholder=fd.placeholder;
    if(fd.options&&fd.options.length){const dl=document.createElement('datalist');dl.id='dl_'+fd.key;fd.options.forEach(o=>{const op=document.createElement('option');op.value=o;dl.appendChild(op);});w.appendChild(dl);i.setAttribute('list','dl_'+fd.key);}
    w.appendChild(i);card.appendChild(w);inp[fd.key]=i;});
  const bar=el('div','mbar');const c=el('button','mbtn2','Cancelar');c.onclick=()=>m.classList.remove('on');
  const s=el('button','mbtn','Salvar');s.onclick=()=>{const v={};Object.keys(inp).forEach(k=>v[k]=inp[k].value.trim());m.classList.remove('on');onSave(v);};
  bar.appendChild(c);bar.appendChild(s);card.appendChild(bar);m.appendChild(card);m.classList.add('on');
  setTimeout(()=>{const f=inp[fields[0].key];f.focus();if(f.select)f.select();},60);}
$('#edit-acts').onclick=()=>openPicker('Ações rápidas','Escolha os atalhos do painel.',Object.keys(CAT).map(k=>({key:k,label:CAT[k][0]})),config.actions,async l=>{config.actions=l;await saveConfig();renderActs();});
$('#edit-stats').onclick=()=>openPicker('Sistema','Escolha os indicadores exibidos.',Object.keys(SM).map(k=>({key:k,label:SM[k][0]})),config.stats,async l=>{config.stats=l;await saveConfig();renderStats();});
const PT=$('#pomo-time'),PL=$('#pomo-label'),PG=$('#pomo-toggle'),PBOX=$('#pomo-timebox'),PW=$('#pomo');
let pomo={rem:1500,total:1500,brk:300,phase:'focus',run:false,timer:null};
function pfmt(){const s=Math.max(0,pomo.rem);return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
function prender(){PT.textContent=pfmt();PG.textContent=pomo.run?'⏸':'▶';PW.classList.toggle('run',pomo.run);PW.classList.toggle('brk',pomo.phase==='break');}
function ptick(){if(!pomo.run)return;pomo.rem--;
  if(pomo.rem<=0){
    if(pomo.phase==='focus'){pomo.phase='break';pomo.total=pomo.brk;pomo.rem=pomo.brk;PL.textContent='Pausa';speak('Foco concluído, hora da pausa.',true);}
    else{pomo.rem=0;pstop();PL.textContent='Ciclo concluído';speak('Pausa concluída. Bora pro próximo ciclo.',true);}
  }prender();}
function pstart(){if(pomo.timer)clearInterval(pomo.timer);pomo.run=true;pomo.timer=setInterval(ptick,1000);prender();}
function pstop(){pomo.run=false;if(pomo.timer){clearInterval(pomo.timer);pomo.timer=null;}prender();}
function openPomo(mins,brk){mins=mins||25;brk=brk||5;pomo.phase='focus';pomo.brk=brk*60;pomo.total=mins*60;pomo.rem=mins*60;PL.textContent='Foco';PW.classList.add('on');pstart();}
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
async function delFolder(path){if(!confirm('Apagar "'+path+'" (e subpastas/conversas)? Não dá pra desfazer.'))return;
  await fetch('/api/threads/delete',{method:'POST',headers:H(),body:JSON.stringify({name:path})});
  if(thread===path||thread.startsWith(path+'/'))await switchThread('geral');else loadFolders();}
function renameFolder(path){if(path==='geral')return;const seg=path.split('/');const leaf=seg[seg.length-1];
  openForm('Renomear pasta',[{key:'name',label:'Novo nome',value:leaf}],async v=>{const nv=(v.name||'').toLowerCase().replace(/\s+/g,'-').replace(/\//g,'-');if(!nv||nv===leaf)return;
    await fetch('/api/threads/rename',{method:'POST',headers:H(),body:JSON.stringify({old:path,new:nv})});
    const np=(seg.slice(0,-1).join('/')?seg.slice(0,-1).join('/')+'/':'')+nv;
    if(thread===path||thread.startsWith(path+'/')){thread=thread.replace(path,np);localStorage.setItem('ev_thread',thread);}
    await switchThread(thread);});}
async function switchThread(name){thread=name;localStorage.setItem('ev_thread',name);scopeEl.textContent='Conversa · '+name;
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

// voice input (needs HTTPS/localhost)
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){const rec=new SR();rec.lang='pt-BR';rec.interimResults=false;
  micBtn.onclick=e=>{ripple(micBtn,e);try{micBtn.classList.add('on');setState('listening');rec.start();}catch(x){micBtn.classList.remove('on');setState();}};
  rec.onresult=e=>{micBtn.classList.remove('on');send(e.results[0][0].transcript);};
  rec.onerror=e=>{micBtn.classList.remove('on');setState();if(e.error==='not-allowed'||e.error==='service-not-allowed')sys('Microfone exige HTTPS (ou localhost). Configure o HTTPS pra usar voz aqui.');};
  rec.onend=()=>{micBtn.classList.remove('on');if(document.body.classList.contains('listening'))setState();};
}else micBtn.onclick=()=>sys('Reconhecimento de voz indisponível (use o Chrome).');

// live voice console
const vc=$('#vc'),vcTxt=$('#vc-txt'),vcMic=$('#vc-mic');
$('#vcopen').onclick=()=>{if(!SR){sys('Voz indisponível neste navegador (use o Chrome).');return;}vc.classList.add('on');vcTxt.textContent='Toque no microfone e fale.';$('#vc-sub').textContent='pasta: '+thread+' · a conversa fica salva aqui';};
$('#vc-x').onclick=()=>{vc.classList.remove('on');setState();};
if(SR){const vr=new (window.SpeechRecognition||window.webkitSpeechRecognition)();vr.lang='pt-BR';vr.interimResults=false;
  vcMic.onclick=()=>{try{vcMic.classList.add('rec');setState('listening');vcTxt.textContent='ouvindo...';vr.start();}catch(e){vcMic.classList.remove('rec');}};
  vr.onresult=async e=>{const t=e.results[0][0].transcript;vcMic.classList.remove('rec');vcTxt.textContent='"'+t+'"';setState('thinking');
    try{const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:t,thread})});const j=await r.json();
      vcTxt.textContent=j.reply||'(sem resposta)';speak(j.reply,true);loadPanel();}catch(x){vcTxt.textContent='Sem conexão com a E.V.';}finally{setState();}};
  vr.onerror=e=>{vcMic.classList.remove('rec');setState();if(e.error==='not-allowed'||e.error==='service-not-allowed')vcTxt.textContent='O microfone precisa de HTTPS (ou localhost). Configure o HTTPS pra falar por aqui.';};
  vr.onend=()=>vcMic.classList.remove('rec');}
// view tabs (Conversa / Tarefas)
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>switchView(t.dataset.view));
const VIEWS={chat:'#chatview',tasks:'#taskview',exp:'#expview',rem:'#remview',cal:'#calview',mem:'#memview',kb:'#kbview'};
function switchView(v){if(!VIEWS[v])v='chat';document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.view===v));
  Object.entries(VIEWS).forEach(([k,sel])=>{const el2=$(sel);if(el2)el2.style.display=(k===v)?(k==='chat'?'flex':'block'):'none';});
  ({tasks:loadTasks,exp:loadExp,rem:loadRem,mem:loadMem,kb:loadKB,cal:loadCal}[v]||function(){})();}
let calY=null,calM=null;
function ymd(y,m,d){return y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');}
async function loadCal(){const now=new Date();if(calY==null){calY=now.getFullYear();calM=now.getMonth();}
  const items=(await (await fetch('/api/reminders',{headers:H()})).json()).items||[];
  const byDay={};items.forEach(r=>{if(r.when_iso){const d=r.when_iso.slice(0,10);(byDay[d]=byDay[d]||[]).push(r);}});
  const MONTHS=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  $('#cal-title').textContent=MONTHS[calM]+' '+calY;const grid=$('#calgrid');grid.textContent='';
  ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'].forEach(d=>grid.appendChild(el('div','cal-dow',d)));
  const first=new Date(calY,calM,1).getDay(),days=new Date(calY,calM+1,0).getDate();
  const tn=new Date(),tstr=ymd(tn.getFullYear(),tn.getMonth(),tn.getDate());
  for(let i=0;i<first;i++)grid.appendChild(el('div','cal-cell empty'));
  for(let d=1;d<=days;d++){const ds=ymd(calY,calM,d);const cell=el('div','cal-cell'+(ds===tstr?' today':''));
    cell.appendChild(el('div','cal-num',String(d)));const list=byDay[ds]||[];
    list.slice(0,3).forEach(r=>{const ev=el('div','cal-ev',r.when_iso.slice(11,16)+' '+r.text);ev.title=r.text;cell.appendChild(ev);});
    if(list.length>3)cell.appendChild(el('div','cal-more','+'+(list.length-3)+' mais'));
    cell.onclick=()=>calAdd(ds);grid.appendChild(cell);}}
function calAdd(ds){openForm('Novo lembrete · '+ds.split('-').reverse().join('/'),[{key:'text',label:'Lembrar de',placeholder:'...'},{key:'time',label:'Hora',value:'09:00'}],async v=>{
  if(!v.text)return;await fetch('/api/reminders',{method:'POST',headers:H(),body:JSON.stringify({text:v.text,when:ds+'T'+(v.time||'09:00')})});loadCal();loadPanel();});}
$('#cal-prev').onclick=()=>{calM--;if(calM<0){calM=11;calY--;}loadCal();};
$('#cal-next').onclick=()=>{calM++;if(calM>11){calM=0;calY++;}loadCal();};
async function recDel(url,id,reload){await fetch(url,{method:'POST',headers:H(),body:JSON.stringify({id})});reload();loadPanel();}
function subline(txt){const d=el('div','',txt);d.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:2px';return d;}
async function loadExp(){try{const items=(await (await fetch('/api/expenses',{headers:H()})).json()).items||[];
  const by={};let tot=0;items.forEach(x=>{by[x.category]=(by[x.category]||0)+x.amount;tot+=x.amount;});
  const ch=$('#expchart');ch.textContent='';const cats=Object.entries(by).sort((a,b)=>b[1]-a[1]);const mx=Math.max(1,...cats.map(c=>c[1]));
  cats.forEach(([c,v])=>{const row=el('div','bar-row');row.appendChild(el('div','bar-lbl',c));const tr=el('div','bar-track');const fl=el('div','bar-fill');fl.style.width=(v/mx*100)+'%';tr.appendChild(fl);row.appendChild(tr);row.appendChild(el('div','bar-val','R$'+v.toFixed(0)));ch.appendChild(row);});
  if(cats.length)ch.appendChild(el('div','tv-empty','Total (60d): R$'+tot.toFixed(2)));
  const box=$('#explist');box.textContent='';if(!items.length){box.appendChild(el('div','tv-empty','Nenhum gasto registrado.'));return;}
  items.slice().reverse().forEach(x=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',x.description));t.appendChild(subline(x.category+' · '+((x.created||'').slice(0,10))));
    const val=el('div','');val.style.cssText='font-family:var(--mono);font-weight:600';val.textContent='R$'+x.amount.toFixed(0);
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>{if(confirm('Apagar este gasto?'))recDel('/api/expenses/delete',x.id,loadExp);};
    row.appendChild(t);row.appendChild(val);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
$('#expform').onsubmit=async e=>{e.preventDefault();const amount=$('#exp-amt').value.trim();if(!amount)return;
  await fetch('/api/expenses',{method:'POST',headers:H(),body:JSON.stringify({amount,description:$('#exp-desc').value.trim(),category:$('#exp-cat').value.trim()||'geral'})});
  $('#exp-amt').value='';$('#exp-desc').value='';loadExp();loadPanel();};
async function loadRem(){try{const items=(await (await fetch('/api/reminders',{headers:H()})).json()).items||[];const box=$('#remlist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhum lembrete em aberto.'));return;}
  items.forEach(r=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',r.text));if(r.when_iso)t.appendChild(subline(r.when_iso.replace('T',' ').slice(0,16)+(r.recur?(' · '+r.recur):'')));
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>{if(confirm('Cancelar este lembrete?'))recDel('/api/reminders/delete',r.id,loadRem);};
    row.appendChild(t);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
$('#remform').onsubmit=async e=>{e.preventDefault();const text=$('#rem-text').value.trim();if(!text)return;
  await fetch('/api/reminders',{method:'POST',headers:H(),body:JSON.stringify({text,when:$('#rem-when').value||''})});$('#rem-text').value='';$('#rem-when').value='';loadRem();loadPanel();};
async function loadMem(){try{const items=(await (await fetch('/api/facts',{headers:H()})).json()).items||[];const box=$('#memlist');box.textContent='';
  if(!items.length){box.appendChild(el('div','tv-empty','Nenhuma memória ainda.'));return;}
  items.forEach(f=>{const row=el('div','tv-row');row.appendChild(el('div','txt',f.fact));
    const dl=el('button','tv-ic');dl.appendChild(ficon('trash-2'));dl.onclick=()=>{if(confirm('Apagar esta memória?'))recDel('/api/facts/delete',f.id,loadMem);};
    row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
$('#memform').onsubmit=async e=>{e.preventDefault();const text=$('#mem-text').value.trim();if(!text)return;
  await fetch('/api/facts',{method:'POST',headers:H(),body:JSON.stringify({text})});$('#mem-text').value='';loadMem();loadPanel();};
async function loadKB(){try{const d=await (await fetch('/api/kb',{headers:H()})).json();const box=$('#kblist');box.textContent='';
  if(!d.sources||!d.sources.length){box.appendChild(el('div','tv-empty','Nada na base ainda. Adicione uma URL, arquivo ou texto acima.'));return;}
  d.sources.forEach(s=>{const row=el('div','tv-row');const t=el('div','txt');t.appendChild(el('div','',s.source));
    const sub=el('div','');sub.style.cssText='color:var(--subtle);font-family:var(--mono);font-size:11px;margin-top:2px';sub.textContent=s.chunks+' trechos';t.appendChild(sub);
    const dl=el('button','tv-ic');dl.title='remover';dl.appendChild(ficon('trash-2'));dl.onclick=()=>{if(confirm('Remover "'+s.source+'" da base?'))kbDel(s.source);};
    row.appendChild(t);row.appendChild(dl);box.appendChild(row);});window.lucide&&lucide.createIcons();}catch(e){}}
async function kbDel(source){await fetch('/api/kb/delete',{method:'POST',headers:H(),body:JSON.stringify({source})});loadKB();loadPanel();}
$('#kb-urlf').onsubmit=async e=>{e.preventDefault();const url=$('#kb-url').value.trim();if(!url)return;$('#kb-fmsg').textContent='indexando...';
  const j=await (await fetch('/api/kb/url',{method:'POST',headers:H(),body:JSON.stringify({url})})).json();$('#kb-fmsg').textContent=j.msg||'';$('#kb-url').value='';loadKB();loadPanel();};
$('#kb-textf').onsubmit=async e=>{e.preventDefault();const title=$('#kb-title').value.trim()||'Nota';const text=$('#kb-text').value.trim();if(!text)return;$('#kb-fmsg').textContent='indexando...';
  const j=await (await fetch('/api/kb/text',{method:'POST',headers:H(),body:JSON.stringify({title,text})})).json();$('#kb-fmsg').textContent=j.msg||'';$('#kb-title').value='';$('#kb-text').value='';loadKB();loadPanel();};
$('#kb-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;$('#kb-fmsg').textContent='enviando '+f.name+'...';const fd=new FormData();fd.append('file',f);
  try{const j=await (await fetch('/api/kb/upload',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd})).json();$('#kb-fmsg').textContent=j.msg||'ok';}catch(x){$('#kb-fmsg').textContent='erro no upload';}
  e.target.value='';loadKB();loadPanel();};
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
      const txt=el('div','txt');const parts=t.text.split(/\s+(?=\d+[.)]\s)/);if(parts.length>1)parts.forEach(p=>txt.appendChild(el('div','',p)));else txt.textContent=t.text;
      const ed=el('button','tv-ic');ed.title='editar';ed.appendChild(ficon('pencil'));ed.onclick=()=>editTask(t);
      const dl=el('button','tv-ic');dl.title='apagar';dl.appendChild(ficon('trash-2'));dl.onclick=()=>{if(confirm('Apagar esta tarefa?'))taskAction('delete',t.id);};
      row.appendChild(done);row.appendChild(txt);row.appendChild(ed);row.appendChild(dl);box.appendChild(row);});});
  window.lucide&&lucide.createIcons();}catch(e){}}
async function taskAction(op,id){await fetch('/api/tasks/'+op,{method:'POST',headers:H(),body:JSON.stringify({id})});loadTasks();loadPanel();}
function editTask(t){openForm('Editar tarefa',[
  {key:'text',label:'Descrição',value:t.text,type:'textarea'},
  {key:'category',label:'Categoria',value:t.category,options:window._cats||[],placeholder:'ex: faculdade'}],
  async v=>{if(!v.text)return;await fetch('/api/tasks/update',{method:'POST',headers:H(),body:JSON.stringify({id:t.id,text:v.text,category:v.category||t.category})});loadTasks();loadPanel();});}
$('#taskform').onsubmit=async e=>{e.preventDefault();const text=$('#task-text').value.trim();const cat=$('#task-cat').value.trim()||'geral';
  if(!text)return;await fetch('/api/tasks',{method:'POST',headers:H(),body:JSON.stringify({text,category:cat})});$('#task-text').value='';loadTasks();loadPanel();};
// command palette (Ctrl/Cmd+K)
const CK=$('#cmdk'),CKI=$('#ck-input'),CKL=$('#ck-list');let ckItems=[],ckSel=0;
function ckBuild(){const nav=[['Conversa',()=>switchView('chat')],['Tarefas',()=>switchView('tasks')],['Gastos',()=>switchView('exp')],['Lembretes',()=>switchView('rem')],['Agenda',()=>switchView('cal')],['Memórias',()=>switchView('mem')],['Base',()=>switchView('kb')],['Pomodoro',()=>openPomo(25)],['Voz ao vivo',()=>$('#vcopen').click()]];
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
(async()=>{try{COMMANDS=(await (await fetch('/api/commands',{headers:H()})).json()).commands;}catch(e){}
  scopeEl.textContent='Conversa · '+thread;await loadFolders();await loadHistory();await loadConfig();loadPanel();
  window.lucide&&lucide.createIcons();})();
</script></body></html>"""


def create_app(config: Config, brain: Brain | None = None):
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import HTMLResponse

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

    def run_command(cmd_str: str, thread=None) -> str:
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
        if name in ("foco", "exportar", "transcrever", "documento", "resumir",
                    "quiz", "insights", "menu", "dados"):
            return f"O comando /{name} funciona no Telegram. Na web, use o chat ou o painel."
        return commands.run(owner, name, rest)  # -> "não conheço"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _PAGE

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

    @app.post("/api/cmd")
    async def cmd(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        command = (data.get("command") or "").strip()
        thread = data.get("thread")
        reply = run_command(command, thread)
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
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks")
    async def tasks_create(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        text = (data.get("text") or "").strip()
        cat = (data.get("category") or "geral").strip() or "geral"
        if text:
            memory.add_task(owner, text, cat)
        return {"tasks": memory.open_tasks(owner)}

    @app.post("/api/tasks/update")
    async def tasks_update(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        memory.update_task(owner, int(data.get("id") or 0),
                           text=(data.get("text") or None),
                           category=(data.get("category") or None))
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
        return {"sources": memory.list_sources(owner)}

    @app.post("/api/kb/url")
    async def kb_url(request: Request):
        _check(request.headers.get("authorization"))
        url = ((await _body(request)).get("url") or "").strip()
        if not url.lower().startswith("http"):
            return {"ok": False, "msg": "Informe uma URL válida (http...)."}
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_url, url, config, memory, owner)
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
        from fastapi import UploadFile
        _check(request.headers.get("authorization"))
        form = await request.form()
        f = form.get("file")
        if not isinstance(f, UploadFile):
            return {"ok": False, "msg": "Nenhum arquivo enviado."}
        name = f.filename or "arquivo"
        if not name.lower().endswith(knowledge.READABLE_EXTS):
            return {"ok": False, "msg": "Só PDF, Word (.docx) ou texto (.txt/.md)."}
        data = await f.read()
        try:
            stored, trunc = await asyncio.to_thread(
                knowledge.ingest_file, data, name, config, memory, owner)
            msg = f"'{name}': {stored} trechos" if stored else "Sem texto extraível."
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
            memory.add_reminder(owner, text, when)
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

    @app.get("/api/panel")
    async def panel(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        exp = memory.expenses_since(owner, since)
        prov = memory.get_setting("force_provider") or "auto"
        # the model that actually answers depends on the forced provider
        model = {
            "groq": config.groq_model,
            "openrouter": config.openrouter_model,
            "ollama": config.ollama_model,
        }.get(prov) or brain.current_model()
        return {
            "tasks": len(memory.open_tasks(owner)),
            "reminders": len(memory.open_reminders(owner)),
            "expenses": round(sum(e.get("amount", 0) for e in exp)),
            "memories": len(memory.all_facts(owner)),
            "kb": len(memory.list_sources(owner)),
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

    return app


def run():
    import uvicorn

    config = Config.load(require_telegram=False)
    if not config.web_token:
        raise SystemExit("EV_WEB_TOKEN não configurado no .env.")
    logging.basicConfig(level=logging.INFO)
    log.info("E.V. web em http://%s:%s", config.web_host, config.web_port)
    uvicorn.run(create_app(config), host=config.web_host, port=config.web_port)
