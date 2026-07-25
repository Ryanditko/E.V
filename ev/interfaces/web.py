"""E.V.'s web interface — a JARVIS-style operator console (voice + dashboard).

One core, many doors (the OpenJarvis pattern): reuses the SAME brain/memory/tools
as Telegram. A monochrome, high-craft single-page UI (no build step) with her real
voice (edge-tts), browser voice input, a live dashboard and dynamic chat.

Auth: a single bearer token (EV_WEB_TOKEN). Conversation uses conv_id="web".
"""

import hmac
import logging

from ..config import Config
from ..core.brain import Brain
from ..core.commands import Commands
from ..core.memory import Memory
from ..providers import voice as voice_mod

log = logging.getLogger("ev.web")

_PAGE = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>E.V.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --ink:#0a0a0a; --panel:#0d0d0d; --elev:#131313; --surface:#0f0f0f;
  --fg:#f4f3f1; --muted:#a1a1a1; --subtle:#6b6b6b;
  --line:rgba(244,243,241,.10); --line-2:rgba(244,243,241,.18);
  --disp:'Space Grotesk',sans-serif; --body:'Inter',sans-serif; --mono:'JetBrains Mono',monospace;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--ink);color:var(--fg);font-family:var(--body);
  -webkit-font-smoothing:antialiased;overflow:hidden}
/* ambient: faint dot grid + slow vignette sweep */
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:radial-gradient(rgba(244,243,241,.04) 1px,transparent 1px);
  background-size:26px 26px;mask:radial-gradient(120% 90% at 50% 0%,#000,transparent 78%)}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.5;
  background:radial-gradient(60% 40% at 70% -10%,rgba(244,243,241,.06),transparent 60%)}

#app{position:relative;z-index:1;height:100%;display:grid;grid-template-columns:236px 1fr 272px}
.rail{display:flex;flex-direction:column;min-height:0}
#left{border-right:1px solid var(--line);padding:20px 18px;gap:18px}
#right{border-left:1px solid var(--line);padding:18px;gap:14px;overflow:auto}
#center{min-width:0;display:flex;flex-direction:column}

.brand{display:flex;flex-direction:column;gap:2px}
.brand .name{font-family:var(--disp);font-weight:700;font-size:26px;letter-spacing:.14em}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.28em;color:var(--subtle);text-transform:uppercase}

/* signature: the core */
.core{width:150px;height:150px;position:relative;margin:10px auto 2px}
.core .ring{position:absolute;border-radius:50%;border:1px solid var(--line-2)}
.core .ring.a{inset:0}.core .ring.b{inset:20px;border-color:var(--line)}.core .ring.c{inset:44px;border-color:var(--line-2)}
.core .arc{position:absolute;inset:0;border-radius:50%;
  background:conic-gradient(from 0deg,transparent 0 66%,rgba(244,243,241,.95) 84%,transparent 100%);
  -webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));
  mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1px));
  animation:spin 7s linear infinite}
.core .arc.two{inset:20px;animation-duration:11s;animation-direction:reverse;opacity:.55}
.core .dot{position:absolute;inset:0;margin:auto;width:9px;height:9px;border-radius:50%;background:var(--fg);
  box-shadow:0 0 22px 5px rgba(244,243,241,.45)}
@keyframes spin{to{transform:rotate(360deg)}}
body.listening .core .arc{animation-duration:1.8s}
body.thinking  .core .arc{animation-duration:2.6s}
body.listening .core .dot{animation:pulse 1s ease-in-out infinite}
@keyframes pulse{50%{transform:scale(1.9);opacity:.55}}
.state{font-family:var(--mono);font-size:10px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--muted);text-align:center}

.sysbox{margin-top:auto;display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--line);padding-top:14px}
.kv{display:flex;justify-content:space-between;align-items:center;font-family:var(--mono);font-size:11px}
.kv span{color:var(--subtle);letter-spacing:.1em}.kv b{color:var(--fg);font-weight:500}
.live{display:inline-flex;align-items:center;gap:6px}
.live::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--fg);
  box-shadow:0 0 10px 2px rgba(244,243,241,.5);animation:pulse 2s infinite}

/* center */
.topbar{display:flex;align-items:center;gap:12px;padding:16px 22px;border-bottom:1px solid var(--line)}
.topbar .eyebrow{flex:1}
.chip-row{display:flex;gap:8px;flex-wrap:wrap;padding:0 22px 4px}
#log{flex:1;overflow:auto;padding:20px 22px;display:flex;flex-direction:column;gap:14px;scroll-behavior:smooth}
.msg{max-width:80%;padding:12px 16px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word;
  border:1px solid var(--line);border-radius:16px;animation:rise .34s cubic-bezier(.2,.7,.2,1)}
.msg.you{align-self:flex-end;background:var(--fg);color:var(--ink);border:none;border-bottom-right-radius:5px;font-weight:500}
.msg.ev{align-self:flex-start;background:var(--elev);border-bottom-left-radius:5px}
.msg.sys{align-self:center;background:transparent;border:1px dashed var(--line);color:var(--muted);
  font-family:var(--mono);font-size:12px;letter-spacing:.03em}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
.tp{display:inline-flex;gap:5px;align-items:center}
.tp i{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:td 1.1s infinite}
.tp i:nth-child(2){animation-delay:.15s}.tp i:nth-child(3){animation-delay:.3s}
@keyframes td{0%,60%,100%{opacity:.25;transform:translateY(0)}30%{opacity:1;transform:translateY(-3px)}}

/* command bar */
form{display:flex;align-items:center;gap:10px;padding:14px 18px;border-top:1px solid var(--line);background:linear-gradient(0deg,var(--panel),transparent)}
.field{flex:1;display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--line);
  border-radius:14px;padding:4px 6px 4px 16px;transition:border-color .2s,box-shadow .2s}
.field:focus-within{border-color:var(--line-2);box-shadow:0 0 0 4px rgba(244,243,241,.05)}
#txt{flex:1;background:transparent;border:none;outline:none;color:var(--fg);font-family:var(--body);font-size:15px;padding:9px 0}
.icon{width:42px;height:42px;flex:none;display:grid;place-items:center;border-radius:11px;border:1px solid var(--line);
  background:var(--elev);color:var(--fg);cursor:pointer;position:relative;overflow:hidden;transition:transform .12s,background .2s,border-color .2s}
.icon:hover{transform:translateY(-1px);border-color:var(--line-2)}
.icon:active{transform:translateY(0) scale(.96)}
.icon.send{background:var(--fg);color:var(--ink);border:none}
.icon.mic.on{background:var(--fg);color:var(--ink);border:none}
.wave{display:none;align-items:flex-end;gap:2px;height:16px}
.icon.mic.on .micglyph{display:none}.icon.mic.on .wave{display:flex}
.wave b{width:2.5px;height:5px;background:var(--ink);border-radius:2px;animation:wv .9s ease-in-out infinite}
.wave b:nth-child(2){animation-delay:.12s}.wave b:nth-child(3){animation-delay:.24s}.wave b:nth-child(4){animation-delay:.36s}
@keyframes wv{50%{height:15px}}
.ripple{position:absolute;border-radius:50%;background:rgba(244,243,241,.35);transform:scale(0);animation:rp .5s ease-out;pointer-events:none}
.icon.send .ripple,.icon.mic.on .ripple{background:rgba(10,10,10,.25)}
@keyframes rp{to{transform:scale(2.4);opacity:0}}

/* chips + panels */
.chip{font-family:var(--mono);font-size:11px;letter-spacing:.04em;color:var(--muted);
  border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:7px 13px;cursor:pointer;
  transition:color .2s,border-color .2s,transform .12s}
.chip:hover{color:var(--fg);border-color:var(--line-2);transform:translateY(-1px)}
#right .eyebrow{margin:6px 2px}
.stat{display:flex;align-items:baseline;justify-content:space-between;padding:11px 13px;border:1px solid var(--line);
  border-radius:12px;background:var(--surface);cursor:pointer;transition:border-color .2s,background .2s}
.stat:hover{border-color:var(--line-2);background:var(--elev)}
.stat .lbl{font-size:13px;color:var(--muted)}
.stat .num{font-family:var(--mono);font-weight:600;font-size:18px;color:var(--fg)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.act{font-family:var(--body);font-size:13px;color:var(--fg);border:1px solid var(--line);background:var(--surface);
  border-radius:11px;padding:11px 10px;cursor:pointer;text-align:left;transition:border-color .2s,transform .12s,background .2s}
.act:hover{border-color:var(--line-2);transform:translateY(-1px);background:var(--elev)}
select{width:100%;font-family:var(--mono);font-size:12px;background:var(--surface);color:var(--fg);
  border:1px solid var(--line);border-radius:11px;padding:10px}
.toggle{margin-left:auto;font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--muted);
  border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:7px 12px;cursor:pointer}
.toggle.on{color:var(--ink);background:var(--fg);border-color:var(--fg)}

@media(max-width:920px){#app{grid-template-columns:1fr}.rail{display:none}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
<div id="app">
  <aside id="left" class="rail">
    <div class="brand"><div class="name">E.V.</div><div class="eyebrow">Personal Intelligence</div></div>
    <div class="core"><div class="ring a"></div><div class="ring b"></div><div class="ring c"></div>
      <div class="arc"></div><div class="arc two"></div><div class="dot"></div></div>
    <div class="state" id="state">em espera</div>
    <div class="sysbox">
      <div class="kv"><span>PROVEDOR</span><b id="s-prov">—</b></div>
      <div class="kv"><span>MODELO</span><b id="s-model">—</b></div>
      <div class="kv"><span>SESSÃO</span><b class="live">web</b></div>
      <div class="kv"><span>HORA</span><b id="s-clock">—</b></div>
    </div>
  </aside>

  <main id="center">
    <div class="topbar">
      <div class="eyebrow">Conversa</div>
      <button class="toggle on" id="voz">VOZ</button>
    </div>
    <div id="log"></div>
    <div class="chip-row" id="chips"></div>
    <form id="f">
      <button type="button" class="icon mic" id="mic" title="Falar">
        <span class="micglyph">🎙</span>
        <span class="wave"><b></b><b></b><b></b><b></b></span></button>
      <div class="field"><input id="txt" placeholder="Fala com a E.V." autocomplete="off"></div>
      <button class="icon send" id="send" title="Enviar">➤</button>
    </form>
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
      <button class="act" data-cmd="buscar">Buscar web</button>
      <button class="act" data-cmd="noticias">Notícias</button>
      <button class="act" data-cmd="clima">Clima</button>
      <button class="act" data-cmd="relatorio">Relatório</button>
      <button class="act" data-cmd="status">Status</button>
      <button class="act" data-cmd="semana">Semana</button>
    </div>
    <div class="eyebrow">Provedor de IA</div>
    <select id="prov"><option>auto</option><option>gemini</option><option>groq</option><option>openrouter</option><option>ollama</option></select>
  </aside>
</div>
<script>
let token=localStorage.getItem('ev_token');
if(!token){token=prompt('Token de acesso da E.V.:')||'';localStorage.setItem('ev_token',token);}
let voiceOn=localStorage.getItem('ev_voice')!=='off';
const H=()=>({'Content-Type':'application/json','Authorization':'Bearer '+token});
const $=s=>document.querySelector(s), log=$('#log'), txt=$('#txt'), f=$('#f'),
  micBtn=$('#mic'), vozBtn=$('#voz'), stateEl=$('#state');
function setState(s){document.body.classList.remove('listening','thinking');
  if(s)document.body.classList.add(s);
  stateEl.textContent=s==='listening'?'ouvindo':s==='thinking'?'processando':'em espera';}
vozBtn.classList.toggle('on',voiceOn);
vozBtn.onclick=()=>{voiceOn=!voiceOn;localStorage.setItem('ev_voice',voiceOn?'on':'off');vozBtn.classList.toggle('on',voiceOn);};

function add(cls,text){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;
  log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function thinking(){const d=document.createElement('div');d.className='msg ev';
  d.innerHTML='<span class="tp"><i></i><i></i><i></i></span>';log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ripple(btn,e){const r=document.createElement('span');r.className='ripple';const b=btn.getBoundingClientRect();
  const s=Math.max(b.width,b.height);r.style.width=r.style.height=s+'px';
  r.style.left=((e?e.clientX:b.left+b.width/2)-b.left-s/2)+'px';
  r.style.top=((e?e.clientY:b.top+b.height/2)-b.top-s/2)+'px';btn.appendChild(r);setTimeout(()=>r.remove(),500);}

async function speak(t){if(!voiceOn||!t)return;
  try{const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text:t})});
    if(!r.ok)return;const a=new Audio(URL.createObjectURL(await r.blob()));a.play().catch(()=>{});}catch(e){}}
async function send(msg){if(!msg)return;add('you',msg);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:msg})});
    if(r.status===401){p.textContent='Token inválido — recarregue e informe o token certo.';localStorage.removeItem('ev_token');setState();return;}
    const j=await r.json();p.className='msg ev';p.textContent=j.reply||'(sem resposta)';speak(j.reply);loadPanel();
  }catch(e){p.textContent='Sem conexão com a E.V. — '+e;}finally{setState();}}
f.onsubmit=e=>{e.preventDefault();ripple($('#send'));const m=txt.value.trim();txt.value='';send(m);};

async function runCmd(cmd,btn,e){if(btn)ripple(btn,e);const p=thinking();setState('thinking');
  try{const r=await fetch('/api/cmd',{method:'POST',headers:H(),body:JSON.stringify({command:cmd})});
    const j=await r.json();p.className='msg ev';p.textContent=j.reply||'(ok)';}catch(err){p.textContent='Erro — '+err;}finally{setState();}}
document.querySelectorAll('[data-cmd]').forEach(el=>el.addEventListener('click',e=>runCmd(el.dataset.cmd,el,e)));

function countTo(el,to){const from=+el.textContent||0;if(from===to){el.textContent=to;return;}
  const t0=performance.now();(function step(t){const k=Math.min(1,(t-t0)/500);
    el.textContent=Math.round(from+(to-from)*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(step);})(t0);}
async function loadPanel(){try{const r=await fetch('/api/panel',{headers:H()});if(!r.ok)return;const d=await r.json();
  ['tasks','reminders','expenses','memories','kb'].forEach(k=>{const el=document.querySelector('[data-k="'+k+'"]');if(el)countTo(el,d[k]);});
  $('#s-prov').textContent=d.provider;$('#s-model').textContent=d.model;$('#prov').value=d.provider;
}catch(e){}}
$('#prov').onchange=()=>runCmd('provedor '+$('#prov').value);

// dynamic starter chips
const CHIPS=['Como está meu dia?','Criar uma tarefa','Notícias de tecnologia','Registrar um gasto'];
const chips=$('#chips');CHIPS.forEach(c=>{const b=document.createElement('button');b.className='chip';b.textContent=c;
  b.onclick=()=>{chips.style.display='none';send(c);};chips.appendChild(b);});

// browser voice input (needs HTTPS or localhost)
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){const rec=new SR();rec.lang='pt-BR';rec.interimResults=false;
  micBtn.onclick=e=>{ripple(micBtn,e);try{micBtn.classList.add('on');setState('listening');rec.start();}catch(x){micBtn.classList.remove('on');setState();}};
  rec.onresult=e=>{micBtn.classList.remove('on');send(e.results[0][0].transcript);};
  rec.onerror=e=>{micBtn.classList.remove('on');setState();if(e.error==='not-allowed'||e.error==='service-not-allowed')add('sys','Microfone exige HTTPS (ou localhost). Configure o HTTPS para usar voz aqui.');};
  rec.onend=()=>{micBtn.classList.remove('on');if(document.body.classList.contains('listening'))setState();};
}else micBtn.onclick=()=>add('sys','Reconhecimento de voz indisponível neste navegador (use o Chrome).');

setInterval(()=>{const n=new Date();$('#s-clock').textContent=n.toTimeString().slice(0,8);},1000);
add('sys','E.V. online. Fala, escreve ou toca em uma ação.');
loadPanel();
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
        token = (auth or "").removeprefix("Bearer ").strip()
        if not config.web_token or not hmac.compare_digest(token, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")

    async def _body(request):
        try:
            return await request.json()
        except Exception:
            return {}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _PAGE

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.post("/api/chat")
    async def chat(request: Request):
        _check(request.headers.get("authorization"))
        text = ((await _body(request)).get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo. 🙂"}
        reply = await brain.respond(owner, conv_id="web", text=text)
        brain.pop_documents()
        brain.pop_actions()
        return {"reply": reply}

    @app.post("/api/cmd")
    async def cmd(request: Request):
        _check(request.headers.get("authorization"))
        data = await _body(request)
        reply = commands.run(owner, (data.get("command") or "").strip(),
                             (data.get("args") or "").strip())
        return {"reply": reply}

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
