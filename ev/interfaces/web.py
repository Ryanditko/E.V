"""E.V.'s web interface — a full assistant dashboard (not just a chat).

Inspired by the OpenJarvis pattern (one core, many access points). Reuses the
SAME brain/memory/tools as Telegram. Adds:
  - a sidebar dashboard with her functions (tasks, reminders, expenses, memory,
    knowledge, provider) and quick actions,
  - her real voice (edge-tts) reading replies aloud,
  - voice input via the browser (needs HTTPS or localhost for mic access).

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

_PAGE = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>E.V.</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#0d1117;color:#e6edf3;height:100vh;display:flex;flex-direction:column}
header{padding:12px 16px;background:#161b22;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:12px}
header b{font-size:18px}.grow{flex:1}
button{font:inherit;border-radius:10px;border:1px solid #30363d;background:#21262d;color:#e6edf3;cursor:pointer;padding:8px 12px}
button.p{background:#238636;border:none;color:#fff}button.mic{background:#1f6feb;border:none;color:#fff}
button.mic.on{background:#da3633}
#wrap{flex:1;display:flex;min-height:0}
#side{width:240px;border-right:1px solid #21262d;padding:12px;overflow:auto;background:#0f141a}
#side h3{font-size:12px;text-transform:uppercase;color:#8b949e;margin:14px 0 6px}
.card{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:8px 10px;margin-bottom:6px;font-size:14px;cursor:pointer}
.card:hover{border-color:#388bfd}.card b{color:#58a6ff}
#side select{width:100%;padding:7px;border-radius:8px;background:#161b22;color:#e6edf3;border:1px solid #30363d}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{padding:10px 14px;border-radius:14px;max-width:88%;white-space:pre-wrap;line-height:1.45;word-wrap:break-word}
.you{align-self:flex-end;background:#1f6feb;color:#fff}
.ev{align-self:flex-start;background:#21262d}
.sys{align-self:center;color:#8b949e;font-size:13px}
form{display:flex;gap:8px;padding:12px 16px;background:#0d1117;border-top:1px solid #21262d}
#txt{flex:1;padding:11px 14px;border-radius:10px;background:#161b22;color:#e6edf3;border:1px solid #30363d;font-size:16px}
@media(max-width:640px){#side{display:none}}
</style></head><body>
<header><b>🕷️ E.V.</b><span class="grow"></span>
<button id="voz" title="Ela falar as respostas">🔊 voz: on</button>
<button id="mic" class="mic" title="Falar com ela">🎙️</button></header>
<div id="wrap">
  <aside id="side"></aside>
  <div id="main">
    <div id="log"></div>
    <form id="f"><input id="txt" placeholder="Fala com a E.V..." autocomplete="off"><button class="p">➤</button></form>
  </div>
</div>
<script>
let token = localStorage.getItem('ev_token');
if(!token){ token = prompt('Token de acesso da E.V.:')||''; localStorage.setItem('ev_token', token); }
let voiceOn = localStorage.getItem('ev_voice')!=='off';
const H = ()=>({'Content-Type':'application/json','Authorization':'Bearer '+token});
const log=document.getElementById('log'), f=document.getElementById('f'), txt=document.getElementById('txt'),
      side=document.getElementById('side'), vozBtn=document.getElementById('voz'), micBtn=document.getElementById('mic');
function add(cls,text){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
vozBtn.textContent='🔊 voz: '+(voiceOn?'on':'off');
vozBtn.onclick=()=>{voiceOn=!voiceOn;localStorage.setItem('ev_voice',voiceOn?'on':'off');vozBtn.textContent='🔊 voz: '+(voiceOn?'on':'off');};

async function speak(text){ if(!voiceOn||!text) return;
  try{ const r=await fetch('/api/tts',{method:'POST',headers:H(),body:JSON.stringify({text})});
    if(!r.ok) return; const b=await r.blob(); const a=new Audio(URL.createObjectURL(b)); a.play().catch(()=>{}); }catch(e){}
}
async function send(msg){ if(!msg) return; add('you',msg); const p=add('ev','...');
  try{ const r=await fetch('/api/chat',{method:'POST',headers:H(),body:JSON.stringify({message:msg})});
    if(r.status===401){p.textContent='Token inválido.';localStorage.removeItem('ev_token');return;}
    const j=await r.json(); p.textContent=j.reply||'(sem resposta)'; speak(j.reply); loadPanel();
  }catch(e){ p.textContent='Erro: '+e; }
}
f.onsubmit=e=>{e.preventDefault();const m=txt.value.trim();txt.value='';send(m);};

async function runCmd(command){ const p=add('ev','...');
  try{ const r=await fetch('/api/cmd',{method:'POST',headers:H(),body:JSON.stringify({command})});
    const j=await r.json(); p.textContent=j.reply||'(ok)'; }catch(e){ p.textContent='Erro: '+e; }
}
async function loadPanel(){
  try{ const r=await fetch('/api/panel',{headers:H()}); if(!r.ok) return; const d=await r.json();
    side.innerHTML='';
    const sec=(t)=>{const h=document.createElement('h3');h.textContent=t;side.appendChild(h);};
    const card=(label,cmd)=>{const c=document.createElement('div');c.className='card';c.innerHTML=label;c.onclick=()=>runCmd(cmd);side.appendChild(c);};
    sec('Resumo');
    card('📋 Tarefas <b>'+d.tasks+'</b>','tarefas');
    card('⏰ Lembretes <b>'+d.reminders+'</b>','lembretes');
    card('💰 Gastos (mês) <b>R$'+d.expenses+'</b>','gastos');
    card('🧠 Memórias <b>'+d.memories+'</b>','memorias');
    card('📄 Base <b>'+d.kb+'</b>','kb');
    sec('Ações');
    card('🔎 Buscar web','buscar');
    card('📰 Notícias','noticias');
    card('☀️ Clima','clima');
    card('📊 Relatório','relatorio');
    card('🩺 Status','status');
    sec('Provedor de IA');
    const s=document.createElement('select');
    ['auto','gemini','groq','openrouter','ollama'].forEach(p=>{const o=document.createElement('option');o.value=p;o.textContent=p;if(p===d.provider)o.selected=true;s.appendChild(o);});
    s.onchange=()=>runCmd('provedor '+s.value);
    side.appendChild(s);
    const m=document.createElement('div');m.className='card';m.style.cursor='default';m.innerHTML='modelo: <b>'+d.model+'</b>';side.appendChild(m);
  }catch(e){}
}

// voice input (browser). Needs HTTPS or localhost for mic.
const SR = window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){ const rec=new SR(); rec.lang='pt-BR'; rec.interimResults=false;
  micBtn.onclick=()=>{ try{ micBtn.classList.add('on'); rec.start(); }catch(e){ micBtn.classList.remove('on'); } };
  rec.onresult=e=>{ const t=e.results[0][0].transcript; micBtn.classList.remove('on'); txt.value=t; send(t); };
  rec.onerror=e=>{ micBtn.classList.remove('on'); if(e.error==='not-allowed'||e.error==='service-not-allowed') add('sys','O microfone precisa de HTTPS (ou localhost). Configure o HTTPS pra usar voz por aqui.'); };
  rec.onend=()=>micBtn.classList.remove('on');
}else{ micBtn.onclick=()=>add('sys','Seu navegador não suporta reconhecimento de voz (use Chrome).'); }

add('sys','E.V. online. Fala ou escreve — e usa o painel ao lado.');
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
        command = (data.get("command") or "").strip()
        args = (data.get("args") or "").strip()
        reply = commands.run(owner, command, args)
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
