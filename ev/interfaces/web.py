"""E.V.'s web interface — use her from any browser/device.

A tiny FastAPI server that reuses the SAME brain (memory, tools, personality) as
the Telegram bot. One core, another door — the "access from anywhere" pattern.

Auth: a single bearer token (EV_WEB_TOKEN). The conversation uses conv_id="web",
so the web chat keeps its own thread, separate from Telegram, while your data
(memories, tasks, ...) stays shared.
"""

import hmac
import logging

from ..config import Config
from ..core.brain import Brain
from ..core.memory import Memory

log = logging.getLogger("ev.web")

_PAGE = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E.V.</title><style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#0d1117;color:#e6edf3}
header{padding:14px 18px;background:#161b22;border-bottom:1px solid #21262d;font-weight:600}
#log{max-width:820px;margin:0 auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{padding:10px 14px;border-radius:14px;max-width:85%;white-space:pre-wrap;line-height:1.4}
.you{align-self:flex-end;background:#1f6feb;color:#fff;border-bottom-right-radius:4px}
.ev{align-self:flex-start;background:#21262d;border-bottom-left-radius:4px}
form{position:sticky;bottom:0;display:flex;gap:8px;max-width:820px;margin:0 auto;
padding:12px 16px;background:#0d1117}
input,button{font-size:16px;border-radius:10px;border:1px solid #30363d}
#txt{flex:1;padding:11px 14px;background:#161b22;color:#e6edf3}
button{padding:11px 16px;background:#238636;color:#fff;border:none;cursor:pointer}
.sys{align-self:center;color:#8b949e;font-size:13px}
</style></head><body>
<header>🕷️ E.V.</header>
<div id="log"></div>
<form id="f"><input id="txt" placeholder="Fala com a E.V..." autocomplete="off"></input>
<button>Enviar</button></form>
<script>
let token = localStorage.getItem('ev_token');
if(!token){ token = prompt('Token de acesso da E.V.:')||''; localStorage.setItem('ev_token', token); }
const log = document.getElementById('log'), f = document.getElementById('f'), txt = document.getElementById('txt');
function add(cls, text){ const d=document.createElement('div'); d.className='msg '+cls; d.textContent=text; log.appendChild(d); window.scrollTo(0,document.body.scrollHeight); return d; }
add('sys','E.V. online. Manda uma mensagem.');
f.addEventListener('submit', async e => {
  e.preventDefault(); const m = txt.value.trim(); if(!m) return;
  add('you', m); txt.value=''; const pending = add('ev','...');
  try{
    const r = await fetch('/api/chat', {method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},
      body: JSON.stringify({message:m})});
    if(r.status===401){ pending.textContent='Token inválido. Recarregue e informe o token certo.'; localStorage.removeItem('ev_token'); return; }
    const j = await r.json(); pending.textContent = j.reply || '(sem resposta)';
  }catch(err){ pending.textContent = 'Erro de conexão: '+err; }
});
</script></body></html>"""


def create_app(config: Config, brain: Brain | None = None):
    """Build the FastAPI app. `brain` can be injected (tests); otherwise built
    from config sharing the same SQLite memory as the rest of E.V."""
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse

    memory = Memory(config.db_path)
    brain = brain or Brain(config, memory)
    app = FastAPI(title="E.V.")

    def _check(authorization: str | None) -> None:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not config.web_token or not hmac.compare_digest(token, config.web_token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _PAGE

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/api/chat")
    async def chat(request: Request) -> dict:
        _check(request.headers.get("authorization"))
        try:
            data = await request.json()
        except Exception:
            data = {}
        text = (data.get("message") or "").strip()
        if not text:
            return {"reply": "Manda alguma coisa que eu respondo. 🙂"}
        owner = str(config.owner_id) if config.owner_id is not None else "web"
        reply = await brain.respond(owner, conv_id="web", text=text)
        # Web is text-only for now; drop any queued files/actions so they don't leak.
        brain.pop_documents()
        brain.pop_actions()
        return {"reply": reply}

    return app


def run() -> None:
    import uvicorn

    config = Config.load(require_telegram=False)
    if not config.web_token:
        raise SystemExit(
            "EV_WEB_TOKEN não configurado. Defina um token no .env para ligar a interface web."
        )
    logging.basicConfig(level=logging.INFO)
    log.info("E.V. web em http://%s:%s", config.web_host, config.web_port)
    uvicorn.run(create_app(config), host=config.web_host, port=config.web_port)
