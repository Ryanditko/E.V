# E.V. — Tech stack (everything used to build her)

A complete inventory of the tools, services and libraries behind E.V. Free tiers
throughout; nothing here requires a paid plan for personal use.

## Language & runtime
- **Python 3** (11+), isolated in a `.venv` virtual environment.
- Runs 24/7 on an **Oracle Cloud Always Free** VM (Ubuntu 22.04).

## AI models (multi-provider, automatic fallback)
| Role | Service | Model |
|------|---------|-------|
| Primary chat | **Google Gemini** | `gemini-flash-latest` |
| Fallback 1 (workhorse) | **Groq** | `openai/gpt-oss-120b` |
| Fallback 2 | **OpenRouter** | free `nemotron` model |
| Fallback 3 (local) | **Ollama** | `llama3.1` (disabled on the 1 GB VM) |
| Speech-to-text | **Groq Whisper** | `whisper-large-v3-turbo` (pt-BR) |
| Embeddings | **Google Gemini** | `gemini-embedding-001` (semantic memory / RAG) |
| Text-to-speech | **edge-tts** | Microsoft neural pt-BR voice (free, no key) |

## Python libraries (`requirements.txt`)
- **Interfaces:** `python-telegram-bot` (bot), `FastAPI` + `uvicorn` + `python-multipart` (web).
- **LLM clients:** `openai` (Groq/OpenRouter, OpenAI-compatible), `google-genai` (Gemini).
- **Voice:** `edge-tts` (speech synthesis).
- **Documents:** `pypdf` (read PDF), `python-docx` (read/write Word), `reportlab` (generate PDF).
- **Google:** `google-api-python-client`, `google-auth-oauthlib` (Calendar + Gmail).
- **Web search:** `ddgs` (DuckDuckGo); Tavily & Brave via HTTP.
- **Infra/util:** `truststore` (OS trust store for TLS behind proxies), `python-dotenv`
  (`.env`), `tzdata` (timezones).
- **Tests:** `pytest`.

## Data & storage
- **SQLite** — single local file (`ev_memory.db`): messages, facts (+ vector embeddings),
  reminders, tasks, links, expenses, budgets, habits, journal, subscriptions, watches,
  knowledge chunks, KB file blobs, usage log, settings.
- Semantic recall is a lightweight in-DB vector store (cosine similarity over embeddings).

## Web frontend (no build step)
- Self-contained **HTML/CSS/vanilla JS** embedded in `web.py` (single-page app).
- **Lucide** icons (CDN); fonts **Space Grotesk**, **JetBrains Mono**, **Inter**.
- Browser APIs: **MediaRecorder** (voice capture → Whisper), Web Audio, Document
  Picture-in-Picture, Notifications.

## Search & external tools
- **Tavily → Brave → DuckDuckGo** search chain.
- **open-meteo** (weather), news via DuckDuckGo/TabNews.
- **Google Calendar & Gmail** (optional, OAuth).

## Networking & access
- **Tailscale** (`cloudflared` alternative documented) — private HTTPS to the web
  console via Tailscale Serve, valid `*.ts.net` cert, no open ports.

## Infra, deploy & operations
- **Git + GitHub** — private repo `Ryanditko/E.V`, branch `main`.
- **GitHub Actions** — CI/CD (`deploy.yml`, test-gated auto-deploy) and `watchdog.yml`
  (every ~15 min health check + auto-restart + Telegram alert).
- **systemd** — services `ev` (Telegram) and `ev-web` (web), auto-start on boot,
  `Restart=always`.
- **SSH / scp** — deploy transport; **Dependabot** — weekly dependency PRs.
- One-command scripts: `deploy.sh`, `start.sh`, `deploy/setup_vm.sh`, `deploy/watchdog.sh`.

## Development
- **Claude Code** — the AI pair-programmer used to design, build, test and operate E.V.

---
See also: [../README.md](../README.md) · [architecture.md](architecture.md) · [KEYS.md](KEYS.md) · [WEB.md](WEB.md)
