<div align="center">

# E.V.

### A personal AI assistant with a voice, a memory, and a will to never go quiet.

Two doors — **Telegram** and a **JARVIS-style web console** — one mind behind both.
Inspired by Spider-Man's E.V. (*Brand New Day*): the AI the hero built with his own
hands — loyal, warm, playful, and always on your side.

<br/>

![Python](https://img.shields.io/badge/Python-3.11+-1a1a1a?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/Web-FastAPI-1a1a1a?logo=fastapi&logoColor=white)
![Telegram](https://img.shields.io/badge/Bot-Telegram-1a1a1a?logo=telegram&logoColor=white)
![LLMs](https://img.shields.io/badge/LLMs-Gemini·Groq·OpenRouter-1a1a1a)
![SQLite](https://img.shields.io/badge/Memory-SQLite%20+%20vectors-1a1a1a?logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-185%20passing-2e7d32)
[![Deploy](https://github.com/Ryanditko/E.V/actions/workflows/deploy.yml/badge.svg)](https://github.com/Ryanditko/E.V/actions/workflows/deploy.yml)

**[Screenshots](#screenshots) · [Features](#what-she-does) · [Quick start](#quick-start) · [Architecture](#architecture) · [Deploy 24/7](#run-her-24-7) · [Docs](#documentation)**

</div>

---

> **Language note.** This documentation is in English. E.V. **talks to you in Brazilian
> Portuguese** — chat and voice — on purpose; her personality lives in `ev/personality.py`.

---

## Screenshots

Every screen in the web console — 24 tabs plus the floating action terminal and the
red-alert mode — so you can see everything she actually does, not just the highlights.

<div align="center">

**Core — chat, dashboard, terminal**

| Dashboard | Chat |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Chat](docs/screenshots/chat.png) |

| Terminal de ação | Pessoas (`/pessoas`) |
|---|---|
| ![Terminal de ação](docs/screenshots/terminal.png) | ![Pessoas](docs/screenshots/pessoas.png) |

**Modo Foco**

| Modo Foco |
|---|
| ![Modo Foco](docs/screenshots/serious-mode.png) |

**Productivity & routine**

| Tarefas | Lembretes |
|---|---|
| ![Tarefas](docs/screenshots/tasks.png) | ![Lembretes](docs/screenshots/rem.png) |

| Agenda | Diário |
|---|---|
| ![Agenda](docs/screenshots/cal.png) | ![Diário](docs/screenshots/jou.png) |

| Hábitos | Saúde |
|---|---|
| ![Hábitos](docs/screenshots/hab.png) | ![Saúde](docs/screenshots/saude.png) |

**Money**

| Gastos | Assinaturas |
|---|---|
| ![Gastos](docs/screenshots/expenses.png) | ![Assinaturas](docs/screenshots/sub.png) |

| Orçamentos | Metas |
|---|---|
| ![Orçamentos](docs/screenshots/orc.png) | ![Metas](docs/screenshots/metas.png) |

**Memory & knowledge**

| Memórias | Base de conhecimento |
|---|---|
| ![Memórias](docs/screenshots/mem.png) | ![Base de conhecimento](docs/screenshots/kb.png) |

| Links | Cofre de documentos |
|---|---|
| ![Links](docs/screenshots/lnk.png) | ![Cofre](docs/screenshots/cofre.png) |

**World & data**

| Mapa | Cérebro |
|---|---|
| ![Mapa](docs/screenshots/map.png) | ![Cérebro](docs/screenshots/brain.png) |

| Gráficos | Painel |
|---|---|
| ![Gráficos](docs/screenshots/graf.png) | ![Painel](docs/screenshots/painel.png) |

| Clima | Música |
|---|---|
| ![Clima](docs/screenshots/clima.png) | ![Música](docs/screenshots/musica.png) |

**Automation**

| Monitores web | Histórico de atividade |
|---|---|
| ![Monitores](docs/screenshots/mon.png) | ![Histórico](docs/screenshots/act.png) |

**On your phone**

| Início | Conversa | Tarefas |
|---|---|---|
| ![Dashboard mobile](docs/screenshots/mobile/dashboard.png) | ![Chat mobile](docs/screenshots/mobile/chat.png) | ![Tarefas mobile](docs/screenshots/mobile/tasks.png) |

| Gastos | Mapa | Música |
|---|---|---|
| ![Gastos mobile](docs/screenshots/mobile/expenses.png) | ![Mapa mobile](docs/screenshots/mobile/map.png) | ![Música mobile](docs/screenshots/mobile/musica.png) |

</div>

*(All data shown is fictional demo content, not a real account.)*

---

## Two doors, one mind

E.V. cleanly separates **what she is** (a reusable brain + memory) from **how you reach
her** (swappable interfaces). Every door drives the exact same brain, so a task you
create by voice on Telegram shows up in the web calendar, and a memory saved on the web
is recalled on the phone.

| | **Telegram** | **Web console** | **Terminal** |
|---|---|---|---|
| Best for | on the go, voice notes | dashboards, data, focus | quick local dev |
| Voice | send audio → audio back | record → Whisper → she speaks | — |
| Reach | anywhere | private, via your Tailscale (`https://ev.<tailnet>.ts.net`) | localhost |

---

## What she does

**Conversation & voice**
- Natural chat with a warm, witty personality; **voice in and out** (she speaks with a
 natural pt-BR voice via `edge-tts`, and transcribes your audio with **Groq Whisper**).
- Multi-provider brain that **never goes silent** — Gemini → Groq → OpenRouter → local
 Ollama; if one is rate-limited, the next answers.

**Memory & knowledge**
- **Real long-term memory** with semantic (vector) recall across conversations.
- **Knowledge base (RAG)** — drop a PDF/Word/web page; she indexes it and answers grounded
 in it, with the original file available to open or download.
- **Vision / OCR** — send a photo (a bill, a screenshot) and she reads it.

**Life, organized**
- Tasks (with **due dates + rolling recurrence**), reminders & a calendar (**daily/weekly/
 monthly recurrence**), expenses with budgets & alerts, habits with streaks, journal,
 links by category, subscriptions, and web/price monitors — full CRUD on every one.
- **Daily briefing**, weekly review, monthly financial report, proactive check-ins,
 weather & news, Pomodoro, and AI insights.

**Real tools & reach**
- Web search (**Tavily → Brave → DuckDuckGo**), web-page indexing, document generation
 (PDF/Word), **Spotify** playback control (web console), and — with setup — **Google
 Calendar & Gmail**.
- **Hands-free**: she can *run* any command herself (create/edit/delete) from chat or voice.
- **Owner-locked** to you (`EV_OWNER_ID`) and works in Telegram topic groups on mention.

**Web console extras**
- A **terminal de ação** shows her thinking → acting → result per step for a command.
- **Modo Foco** — a focus-mode visual toggle (red/high-contrast) with a
  persistent header badge.
- Proactive alerts (subscriptions due, budgets over) surface in the notification center;
  a **Cmd/Ctrl+K** searches your actual data, not just views; dashboard cards are
  draggable to reorder.

**Runs like a product**
- **CI/CD** (test-gated auto-deploy), **systemd** services, a **watchdog** that restarts
 and alerts, daily DB backups, and **private HTTPS** with zero open ports.

---

## The web console

A self-contained single-page **JARVIS-style monochrome console** (no build step) served by
FastAPI, backed by the same brain and data as Telegram.

- **Chat** with structured rendering, slash-command autocomplete and a `⌘/Ctrl-K` palette.
- **Voice** — she reads replies aloud, and takes voice input by recording audio and
 transcribing it **server-side with Whisper**, so it works in **any browser** (Firefox,
 Chrome, Safari), not just Chrome.
- **CRUD tabs** for Tasks, Expenses, Reminders, Calendar, Memories, Links, Habits, Journal,
 Subscriptions, Budgets and Monitors — create / **edit** / delete, per-tab search,
 recurrence, drag-and-drop, clickable links, PDF/Word open & download.
- Customizable quick-actions & system panels, Pomodoro, API-key manager, in-app modals,
 fully responsive.

**Private HTTPS, no open ports.** It's exposed over **Tailscale Serve** at
`https://ev.<tailnet>.ts.net` — a valid TLS cert, reachable **only** from your own
Tailscale devices, with nothing opened on the cloud firewall. The app itself binds to
`127.0.0.1`. Full runbook: **[deploy/HTTPS_TAILSCALE.md](deploy/HTTPS_TAILSCALE.md)**
(Cloudflare Tunnel alternative in [deploy/HTTPS_CLOUDFLARE.md](deploy/HTTPS_CLOUDFLARE.md)).
More: **[docs/WEB.md](docs/WEB.md)**.

---

## Quick start

> Full first-machine walkthrough (every key, Google auth, deploy): **[docs/SETUP.md](docs/SETUP.md)**.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your keys (below)

python run_telegram.py        # Telegram bot (voice + mobile)
python run_web.py             # web console at http://localhost:8000
python run_terminal.py        # terminal REPL
# or: bash start.sh
```

### Keys (all free)

Every variable and cost is in **[docs/KEYS.md](docs/KEYS.md)**. The essentials:

| Variable | Where |
|----------|-------|
| `TELEGRAM_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| `TAVILY_API_KEY` | https://app.tavily.com (better web search) |
| `EV_WEB_TOKEN` | any long random string (web login) |
| `EV_OWNER_ID` | your Telegram ID — locks the bot to you |

---

## ⌨ Commands (deterministic, no LLM, zero tokens)

Type `/` for autocomplete, or `/menu` for a button UI. A taste:

| Command | Example |
|---------|---------|
| `/lembrete <time> <text>` | `/lembrete amanhã 09:00 reunião` |
| `/rotina <diario\|semanal\|mensal> …` | recurring reminder |
| `/tarefa <text>` · `/tarefas` · `/concluir <id>` | to-do list (due dates + recurrence) |
| `/gasto <v> <desc> #cat` · `/gastos` · `/relatorio` | expenses & **current-month** report |
| `/orcamento <cat> <v>` · `/orcamentos` | budgets with 80/100% alerts |
| `/habito` · `/feito` · `/diario` | habits (streaks) & journal |
| `/lembrar <fact>` · `/memorias` · `/procurar <q>` | memory + unified search |
| `/kb` · `/kbweb <url>` · `/quiz` | knowledge base (send a PDF) + RAG quiz |
| `/agenda` · `/evento` · `/email` | Google (after setup) |
| `/foco` · `/documento` · `/exportar` · `/dados` | Pomodoro · docs · exports · data control |

Time formats: `10m`, `2h`, `1d`, `hoje 18:00`, `amanhã 09:00`, `25/12 14:30`.

---

## AI providers (all free tiers)

| Role | Provider | Model | Why |
|------|----------|-------|-----|
| Primary | **Gemini** | `gemini-flash-latest` | Smart, native audio, saves memory |
| Fallback 1 | **Groq** | `openai/gpt-oss-120b` | Fast, reliable tool calling — the workhorse |
| Fallback 2 | **OpenRouter** | `nemotron` (free) | Big-context text backstop |
| Fallback 3 | **Ollama (local)** | `llama3.1` | Never runs out of quota |
| Transcription | **Groq Whisper** | `whisper-large-v3-turbo` | Voice → text (Telegram + web) |
| Embeddings | **Gemini / Ollama** | `gemini-embedding-001` | Semantic memory + knowledge base |

Switch or force a provider at runtime with `/provedor` and `/modelo`.

---

## Architecture

One core, many doors. New interfaces reuse the brain unchanged.

```mermaid
flowchart TB
    subgraph EDGE["Access"]
        TS["Tailscale Serve · private HTTPS"]
    end
    subgraph I["Interfaces — ev/interfaces (swappable)"]
        TG["Telegram bot<br/>voice + scheduler"]
        WEB["Web console<br/>FastAPI + SPA"]
        TERM["Terminal REPL"]
    end
    subgraph C["Core — ev/core (reusable)"]
        BRAIN["Brain<br/>orchestration + RAG + fallback"]
        CMD["Commands<br/>deterministic, no-LLM"]
        MEM[("Memory<br/>SQLite + vectors")]
    end
    subgraph P["Providers — ev/providers"]
        LLM["llm · Gemini/Groq/OpenRouter/Ollama + Whisper"]
        VOICE["voice · edge-tts"]
        TOOLS["tools · web/calendar/email"]
        DOCS["documents · PDF/Word"]
    end

    TS --> WEB
    TG --> BRAIN
    WEB --> BRAIN
    WEB --> CMD
    TERM --> BRAIN
    BRAIN --> CMD
    BRAIN --> MEM
    CMD --> MEM
    BRAIN --> LLM
    BRAIN --> TOOLS
    BRAIN --> DOCS
    TG --> VOICE
    WEB --> VOICE
```

<details>
<summary><b>Message flow with automatic fallback</b></summary>

```mermaid
sequenceDiagram
    autonumber
    participant U as You
    participant I as Interface
    participant B as Brain
    participant G as Gemini
    participant Q as Groq
    participant O as OpenRouter
    participant V as edge-tts
    U->>I: message (text / audio)
    I->>B: respond()
    B->>G: generate (native audio + memory)
    alt Gemini available
        G-->>B: answer
    else rate-limited
        B->>Q: chat + tools (memory)
        alt Groq OK
            Q-->>B: answer
        else fails
            B->>O: chat (text)
            O-->>B: answer
        end
    end
    B-->>I: answer
    I->>V: synthesize voice
    V-->>I: audio
    I-->>U: text + voice
```
</details>

> Deep dive: **[docs/architecture.md](docs/architecture.md)** · extend her: **[docs/EXTENDING.md](docs/EXTENDING.md)**

---

## Run her 24/7

She's built to run like a product:

- **One-command deploy** — `bash deploy.sh` ships code + keys to the VM and restarts.
- **CI/CD** — push to `main` runs the **pytest gate**, then auto-deploys and restarts both
 services (`.github/workflows/deploy.yml`).
- **systemd** — `ev` (Telegram) and `ev-web` (web) auto-start on boot, restart on crash.
- **Watchdog** — every ~15 min, checks both services, restarts if down, alerts you on
 Telegram; also warns on low disk/memory (`.github/workflows/watchdog.yml`).
- **Backups** — the DB is sent to you on Telegram (weekly + first run).
- **Fresh VM** — `bash deploy/setup_vm.sh` installs both services in one go.

Hosting options — pick a machine that stays on:

- **Free, your hardware:** Android via Termux (**[docs/TERMUX.md](docs/TERMUX.md)**) · your
 PC as a service (**[docs/SELF_HOST.md](docs/SELF_HOST.md)**).
- **Cloud, always on:** Oracle Always Free (**[docs/DEPLOY.md](docs/DEPLOY.md)**).

---

## Project structure

```
E.V/
├── run_telegram.py · run_web.py · run_terminal.py   # entry points
├── start.sh · deploy.sh                             # local run · ship to VM
├── requirements.txt · .env.example
├── ev/
│   ├── config.py            # configuration (.env)
│   ├── personality.py       # who E.V. is (PT-BR system prompt)
│   ├── core/
│   │   ├── brain.py         # LLM + memory + tools + RAG + fallback
│   │   ├── memory.py        # SQLite: messages, facts, reminders, tasks, KB…
│   │   ├── commands.py      # deterministic slash commands (no LLM)
│   │   ├── knowledge.py     # PDF/Word/web ingestion + chunking
│   │   ├── timeparse.py     # natural-time + month-boundary helpers
│   │   └── health.py        # system + provider health checks
│   ├── providers/
│   │   ├── llm.py           # Gemini/Groq/OpenRouter/Ollama + Whisper
│   │   ├── embeddings.py    # semantic embeddings
│   │   ├── voice.py         # text → speech (edge-tts)
│   │   ├── tools.py         # web search, calendar, email
│   │   └── documents.py     # PDF/Word generation
│   └── interfaces/
│       ├── telegram_bot.py  # Telegram adapter + scheduler + automations
│       ├── web.py           # FastAPI server + single-page console
│       └── terminal.py      # terminal REPL
├── deploy/                  # setup_vm.sh · watchdog.sh · HTTPS runbooks
├── docs/                    # full documentation (index below)
└── tests/                   # 185 tests
```

---

## Testing

```bash
./.venv/bin/python -m pytest -q      # 185 passing
```

CI runs the suite as a **gate before every deploy** — a red test never ships.

---

## Documentation

| Doc | What's inside |
|-----|---------------|
| [docs/SETUP.md](docs/SETUP.md) | First-machine walkthrough (keys, Google, deploy) |
| [docs/KEYS.md](docs/KEYS.md) | Every service, variable and cost |
| [docs/WEB.md](docs/WEB.md) | The web console, endpoints, voice, HTTPS |
| [docs/architecture.md](docs/architecture.md) | Design & diagrams |
| [docs/STACK.md](docs/STACK.md) | Every tool, library & service used |
| [docs/CAPABILITIES.md](docs/CAPABILITIES.md) | Full capability reference |
| [docs/EXTENDING.md](docs/EXTENDING.md) | Add features (yourself or with an AI) |
| [docs/DEPLOY.md](docs/DEPLOY.md) · [docs/SELF_HOST.md](docs/SELF_HOST.md) · [docs/TERMUX.md](docs/TERMUX.md) | Hosting 24/7 |
| [deploy/HTTPS_TAILSCALE.md](deploy/HTTPS_TAILSCALE.md) · [deploy/HTTPS_CLOUDFLARE.md](deploy/HTTPS_CLOUDFLARE.md) | Private HTTPS |
| [docs/GOOGLE.md](docs/GOOGLE.md) · [docs/GROUPS.md](docs/GROUPS.md) | Google auth · Telegram groups |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Runbook when something breaks |

---

## Security

- **Owner-locked** to your Telegram ID; the web is behind a bearer token **and** your
 private Tailscale — not on the public internet, with plain HTTP closed.
- Secrets live only in the VM `.env` (git-ignored) and GitHub Actions secrets — never in
 the repo. The watchdog reads the Telegram token from the VM, so no token leaves it.

---

## Built with

`Python 3` · `FastAPI` + `uvicorn` · `python-telegram-bot` · `SQLite` · `edge-tts` ·
`Gemini TTS` · `Groq Whisper` · `Google Gemini` · `Groq` · `OpenRouter` · `Ollama` ·
`pypdf` · `python-docx` · `reportlab` · `Tavily/Brave/DuckDuckGo` · `Spotify Web API` +
`Web Playback SDK` · `Tailscale` · `systemd` · `GitHub Actions` · `Lucide` · `pytest`

---

<div align="center">

**Built by [Ryan](https://github.com/Ryanditko) — one core, many doors.**

</div>
