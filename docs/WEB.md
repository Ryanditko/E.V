# E.V. on the web (use her from any browser)

A second "door" to the same E.V. — one core, many access points. A FastAPI server
(`ev/interfaces/web.py`, entry `run_web.py`) serves a self-contained single-page
console (no build step) backed by the **same brain, memory and tools** as the
Telegram bot.

- Data (tasks, reminders, expenses, memories, KB, …) is shared with Telegram.
- Conversations are scoped into folders — each is its own thread
  (`conv_id="web:<folder>"`, nesting via `web:parent/child`); durable data stays shared.
- Auth: a single bearer token, `EV_WEB_TOKEN` (stored in the browser's localStorage).

## What's in the UI

- **Chat** with structured monochrome rendering, slash-command autocomplete, and a
  Ctrl/Cmd-K command palette.
- **Voice** — she reads replies aloud (`/api/tts`, edge-tts) and takes voice input by
  recording audio (`MediaRecorder`) and transcribing it server-side with Groq Whisper
  (`/api/stt`). Works in **any browser** (Firefox, Chrome, Safari) — tap the mic to
  start, tap again to send. Requires HTTPS (see below) for microphone access.
- **CRUD tabs** for every data type — Tarefas, Gastos, Lembretes, Agenda (calendar),
  Memórias, Links, Hábitos, Diário, Assinaturas, Orçamentos, Monitores — each with
  create / **edit** / delete and per-tab search.
- **Recurrence**: reminders and calendar events repeat daily/weekly/monthly (reuses the
  scheduler); tasks have a due date + rolling recurrence (roll forward on complete, or
  via the `roll_due_tasks` worker).
- Customizable quick-actions + "Sistema" stat panels, Pomodoro (focus + break),
  clickable links everywhere, PDF/Word open & download from the KB, API-key manager
  (`/api/keys`), in-app confirm/edit modals, favicon, full responsiveness.

## Run it locally

1. Set a strong token in `.env`:
   ```
   EV_WEB_TOKEN=<a long random string>
   EV_WEB_HOST=127.0.0.1     # 0.0.0.0 only if you intend to expose it directly
   EV_WEB_PORT=8000
   ```
2. Start it: `python run_web.py`
3. Open `http://localhost:8000` and paste the token.

Reuses the same `ev_memory.db`, so it runs alongside the Telegram bot.

## On the Oracle VM (automated)

- `deploy/setup_vm.sh` registers **both** systemd services: `ev` (Telegram) and
  `ev-web` (web, `run_web.py`, `Restart=always`, enabled on boot).
- **CI/CD**: pushing to `main` runs the pytest gate, then restarts `ev` **and** `ev-web`
  (`.github/workflows/deploy.yml`). The VM `.env` is never overwritten by CI.
- **Watchdog** (`deploy/watchdog.sh`, every ~15 min): monitors `ev` and `ev-web`,
  restarts either if down, and alerts the owner on Telegram.

## HTTPS (required for mic, and recommended in general)

The web is served privately over HTTPS via **Tailscale Serve** — reachable only from
the owner's Tailscale devices, at `https://ev.<tailnet>.ts.net`, with a valid TLS cert
and **no open ports** on Oracle. Full runbook: **`deploy/HTTPS_TAILSCALE.md`**
(alternative Cloudflare Tunnel path in `deploy/HTTPS_CLOUDFLARE.md`).

With HTTPS in place, set `EV_WEB_HOST=127.0.0.1` so the app is only reachable through
the tunnel (the plain `http://<VM_IP>:8000` surface is closed and the token no longer
travels in cleartext).

> The token is the only credential — use a long random value. Rotate it by editing
> `EV_WEB_TOKEN` in the VM `.env` and `sudo systemctl restart ev-web` (all devices
> re-login).

## Key endpoints

`/` (UI) · `/api/chat` · `/api/cmd` · `/api/stt` (voice→text) · `/api/tts` (text→voice) ·
`/api/greeting` · `/api/panel` · `/api/config` · `/api/keys` · `/api/threads` (folders) ·
`/api/history` · plus per-type CRUD under `/api/{tasks,expenses,reminders,facts,links,
habits,journal,recurring,budgets,watches,kb}` (list/create/update/delete). All require
the bearer token except the static page and favicon.
