"""E.V.'s web interface — a JARVIS-style operator console (voice + dashboard +
terminal + scoped conversations). Reuses the SAME brain/memory/tools as Telegram.

One self-contained page (no build) served by FastAPI. Auth: EV_WEB_TOKEN.
Conversations are scoped by folder -> conv_id = "web:<folder>" (own thread each,
shared data). Runs data commands AND interface commands (provedor/status/...).
"""

import hmac
import json
import logging

from ..config import Config
from ..core import health
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
<style>
:root{
  --ink:#0a0a0a;--panel:#0d0d0d;--elev:#141414;--surface:#101010;
  --fg:#f4f3f1;--muted:#a1a1a1;--subtle:#6b6b6b;
  --line:rgba(244,243,241,.10);--line-2:rgba(244,243,241,.20);
  --disp:'Space Grotesk',sans-serif;--body:'Inter',sans-serif;--mono:'JetBrains Mono',monospace;
}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--ink);color:var(--fg);font-family:var(--body);-webkit-font-smoothing:antialiased;overflow:hidden}
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
.folder .fi{font-family:var(--mono);font-size:11px;color:var(--subtle)}
.newf{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--subtle);border:1px dashed var(--line);border-radius:10px;padding:8px;cursor:pointer;text-align:center}
.newf:hover{color:var(--fg);border-color:var(--line-2)}
.sysbox{margin-top:auto;display:flex;flex-direction:column;gap:7px;border-top:1px solid var(--line);padding-top:12px}
.kv{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px}
.kv span{color:var(--subtle)}.kv b{font-weight:500}
.topbar{display:flex;align-items:center;gap:10px;padding:15px 22px;border-bottom:1px solid var(--line)}
.topbar .eyebrow{flex:1;margin:0}
.tbtn{font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--muted);border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:7px 12px;cursor:pointer}
.tbtn.on{color:var(--ink);background:var(--fg);border-color:var(--fg)}
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
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.act{font-size:13px;color:var(--fg);border:1px solid var(--line);background:var(--surface);border-radius:11px;padding:11px 10px;cursor:pointer;text-align:left;transition:.15s}
.act:hover{border-color:var(--line-2);transform:translateY(-1px);background:var(--elev)}
select{width:100%;font-family:var(--mono);font-size:12px;background:var(--surface);color:var(--fg);border:1px solid var(--line);border-radius:11px;padding:10px}
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
    <div class="topbar"><div class="eyebrow" id="scope">Conversa · geral</div>
      <button class="tbtn" id="term">TERMINAL</button><button class="tbtn on" id="voz">VOZ</button></div>
    <div id="log"></div>
    <form id="f"><div id="slash"></div>
      <button type="button" class="icon mic" id="mic" title="Falar"><span class="mg">🎙</span><span class="wave"><b></b><b></b><b></b><b></b></span></button>
      <div class="field"><input id="txt" placeholder="Fala com a E.V.  ·  digite / para comandos" autocomplete="off"></div>
      <button class="icon send" id="send" title="Enviar">➤</button></form>
  </main>
  <aside id="right" class="rail">
    <div class="eyebrow">Sistema</div>
    <div class="stat" data-cmd="tarefas"><span class="lbl">Tarefas</span><span class="num" data-k="tasks">0</span></div>
    <div class="stat" data-cmd="lembretes"><span class="lbl">Lembretes</span><span class="num" data-k="reminders">0</span></div>
    <div class="stat" data-cmd="gastos"><span class="lbl">Gastos · mês</span><span class="num"><span style="font-size:12px;color:var(--subtle)">R$</span><span data-k="expenses">0</span></span></div>
    <div class="stat" data-cmd="memorias"><span class="lbl">Memórias</span><span class="num" data-k="memories">0</span></div>
    <div class="stat" data-cmd="kb"><span class="lbl">Base</span><span class="num" data-k="kb">0</span></div>
    <div class="eyebrow">Ações rápidas</div>
    <div class="grid2">
      <button class="act" data-cmd="buscar">Buscar web</button><button class="act" data-cmd="noticias">Notícias</button>
      <button class="act" data-cmd="clima">Clima</button><button class="act" data-cmd="relatorio">Relatório</button>
      <button class="act" data-cmd="status">Status</button><button class="act" data-cmd="semana">Semana</button></div>
    <div class="eyebrow">Provedor de IA</div>
    <select id="prov"><option>auto</option><option>gemini</option><option>groq</option><option>openrouter</option><option>ollama</option></select>
  </aside>
</div>
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
// structured, monochrome rendering of E.V.'s replies (lists, ids, categories)
function renderReply(box,text){box.textContent='';const lines=(text||'').split('\n');let first=true;
  lines.forEach(ln=>{const s=ln.trim();
    if(!s){box.appendChild(el('div','',' '));return;}
    let m;
    if(first && /[\p{Emoji}]/u.test(s)){box.appendChild(el('span','h',s));first=false;return;}
    if((m=s.match(/^\[(.+)\]$/))){box.appendChild(el('div','cat',m[1]));return;}
    if((m=s.match(/^#(\w+)\s+(.*)$/))){const r=el('div','row');r.appendChild(el('span','id','#'+m[1]));r.appendChild(el('span','t',m[2]));box.appendChild(r);return;}
    if(/^(Concluir|Cancelar|Uso|Remover|Apagar):/i.test(s)||s.startsWith('/')){box.appendChild(el('div','hint',s));return;}
    box.appendChild(el('p','',s));first=false;});
}
function you(t){const d=el('div','msg you',t);log.appendChild(d);log.scrollTop=log.scrollHeight;}
function ev(t){const d=el('div','msg ev');renderReply(d,t);log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function sys(t){const d=el('div','msg sys',t);log.appendChild(d);log.scrollTop=log.scrollHeight;}
function thinking(){const d=el('div','msg ev');d.innerHTML='<span class="tp"><i></i><i></i><i></i></span>';log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ripple(b,e){const r=el('span','ripple');const q=b.getBoundingClientRect(),s=Math.max(q.width,q.height);
  r.style.width=r.style.height=s+'px';r.style.left=((e?e.clientX:q.left+q.width/2)-q.left-s/2)+'px';
  r.style.top=((e?e.clientY:q.top+q.height/2)-q.top-s/2)+'px';b.appendChild(r);setTimeout(()=>r.remove(),500);}
async function speak(t){if(!voiceOn||!t)return;try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text:t})});if(!r.ok)return;new Audio(URL.createObjectURL(await r.blob())).play().catch(()=>{});}catch(e){}}

async function send(msg){if(!msg)return;you(msg);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:msg,thread})});
    if(r.status===401){p.remove();sys('Token inválido — recarregue e informe o token certo.');localStorage.removeItem('ev_token');return;}
    const j=await r.json();p.remove();ev(j.reply);speak(j.reply);loadPanel();
  }catch(e){p.remove();sys('Sem conexão com a E.V. — '+e);}finally{setState();}}
async function runCmd(cmd,btn,e){if(btn)ripple(btn,e);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/cmd',{method:'POST',headers:H(),body:JSON.stringify({command:cmd,thread})});
    const j=await r.json();p.remove();ev(j.reply);loadPanel();}catch(err){p.remove();sys('Erro — '+err);}finally{setState();}}
f.onsubmit=e=>{e.preventDefault();if(slash.style.display==='block'&&slSel>=0){pickSlash();return;}
  ripple($('#send'));const m=txt.value.trim();txt.value='';hideSlash();
  if(m.startsWith('/'))runCmd(m.slice(1));else send(m);};
document.querySelectorAll('[data-cmd]').forEach(el=>el.addEventListener('click',e=>runCmd(el.dataset.cmd,el,e)));

function countTo(el,to){const from=+el.textContent||0;if(from===to){el.textContent=to;return;}const t0=performance.now();
  (function s(t){const k=Math.min(1,(t-t0)/500);el.textContent=Math.round(from+(to-from)*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(s);})(t0);}
async function loadPanel(){try{const r=await fetch('/api/panel',{headers:H()});if(!r.ok)return;const d=await r.json();
  ['tasks','reminders','expenses','memories','kb'].forEach(k=>{const e=document.querySelector('[data-k="'+k+'"]');if(e)countTo(e,d[k]);});
  $('#s-prov').textContent=d.provider;$('#s-model').textContent=d.model;$('#prov').value=d.provider;}catch(e){}}
$('#prov').onchange=()=>runCmd('provedor '+$('#prov').value);

// folders
async function loadFolders(){try{const r=await fetch('/api/threads',{headers:H()});const d=await r.json();
  const box=$('#folders');box.textContent='';
  d.threads.forEach(name=>{const f=el('div','folder'+(name===thread?' on':''));
    f.appendChild(el('span','fi','▚'));f.appendChild(el('span','',name));f.onclick=()=>switchThread(name);box.appendChild(f);});
}catch(e){}}
async function switchThread(name){thread=name;localStorage.setItem('ev_thread',name);scopeEl.textContent='Conversa · '+name;
  loadFolders();log.textContent='';await loadHistory();}
async function loadHistory(){try{const r=await fetch('/api/history?thread='+encodeURIComponent(thread),{headers:H()});const d=await r.json();
  if(!d.messages.length){sys('Pasta "'+thread+'" — comece a conversa.');return;}
  d.messages.forEach(m=>m.role==='user'?you(m.content):ev(m.content));}catch(e){}}
$('#newf').onclick=async()=>{const name=(prompt('Nome da nova pasta (ex: projetos):')||'').trim().toLowerCase().replace(/\s+/g,'-');
  if(!name)return;await fetch('/api/threads',{method:'POST',headers:H(),body:JSON.stringify({name})});await switchThread(name);};

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

setInterval(()=>{$('#s-clock').textContent=new Date().toTimeString().slice(0,8);},1000);
(async()=>{try{COMMANDS=(await (await fetch('/api/commands',{headers:H()})).json()).commands;}catch(e){}
  scopeEl.textContent='Conversa · '+thread;await loadFolders();await loadHistory();loadPanel();})();
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

    def run_command(cmd_str: str) -> str:
        """Run a slash command from the web (data + interface commands)."""
        parts = (cmd_str or "").strip().split(None, 1)
        if not parts:
            return "Digite um comando."
        name = parts[0].lstrip("/").lower()
        rest = parts[1] if len(parts) > 1 else ""
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
            forced = memory.get_setting("force_provider") or "auto"
            return f"Modelo principal: {brain.current_model()}\nProvedor: {forced}\nTrocar provedor: /provedor <nome>"
        if name == "ajuda":
            return commands.help()
        if name in ("foco", "exportar", "limparchat", "dados", "limpar",
                    "transcrever", "documento", "resumir", "quiz", "insights", "menu"):
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
        name = ((await _body(request)).get("name") or "").strip().lower()
        if name:
            fs = _folders()
            if name not in fs:
                fs.append(name)
                memory.set_setting("web_folders", json.dumps(fs))
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
        return {"reply": run_command(data.get("command") or "")}

    @app.get("/api/panel")
    async def panel(request: Request):
        _check(request.headers.get("authorization"))
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        exp = memory.expenses_since(owner, since)
        return {
            "tasks": len(memory.open_tasks(owner)),
            "reminders": len(memory.open_reminders(owner)),
            "expenses": round(sum(e.get("amount", 0) for e in exp)),
            "memories": len(memory.all_facts(owner)),
            "kb": len(memory.list_sources(owner)),
            "provider": memory.get_setting("force_provider") or "auto",
            "model": brain.current_model(),
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
