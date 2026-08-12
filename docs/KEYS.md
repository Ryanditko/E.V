# E.V. — all services, links and keys

Every external service E.V. can use, where to get the key, which `.env` variable
it maps to, and whether it costs anything. Fill keys in `.env` (never commit it).

## Required (E.V. won't start without these)

| Service | What for | Link | `.env` variable | Cost / card? |
|---------|----------|------|-----------------|--------------|
| **Telegram BotFather** | Create the bot, get its token | https://t.me/BotFather | `TELEGRAM_TOKEN` | Free, no card |
| **Google AI Studio** | Gemini API key (main brain + embeddings) | https://aistudio.google.com/apikey | `GEMINI_API_KEY` | Free, no card (use a personal @gmail) |

Your Telegram numeric ID (for `EV_OWNER_ID`, to lock the bot to you): message
**@userinfobot** on Telegram, or run the bot and read it from the logs after `/start`.

## Recommended fallback AI providers (free, no card)

| Service | What for | Link | `.env` variable | Cost / card? |
|---------|----------|------|-----------------|--------------|
| **Groq** | Fast fallback LLM + Whisper (audio) | https://console.groq.com/keys | `GROQ_API_KEY` | Free, no card |
| **OpenRouter** | Extra fallback LLM | https://openrouter.ai/keys | `OPENROUTER_API_KEY` | Free, no card |

## Web search (optional — better than the free default)

| Service | What for | Link | `.env` variable | Cost / card? |
|---------|----------|------|-----------------|--------------|
| **Tavily** | AI-focused web search (preferred) | https://app.tavily.com | `TAVILY_API_KEY` | Free ~1000/mo, usually no card |
| **Brave Search API** | Web search alternative | https://brave.com/search/api/ | `BRAVE_API_KEY` | Free tier may require a card / paid plans |
| **DuckDuckGo** | Default web search (fallback) | — (via `ddgs`, no key) | — | Free, no key |

Search order: Tavily → Brave → DuckDuckGo (whichever is configured).

## Google Calendar & Email (optional — needs one-time OAuth)

| Step | Link |
|------|------|
| Cloud console (create project) | https://console.cloud.google.com |
| Enable **Google Calendar API** | Console → APIs & Services → Library |
| Enable **Gmail API** | Console → APIs & Services → Library |
| OAuth consent + credentials (Desktop app) → download `client_secret.json` | Console → APIs & Services → Credentials |

`.env`: `GOOGLE_OAUTH_CLIENT=client_secret.json`, `EV_GOOGLE_ACCOUNTS=pessoal,faculdade`.
Then authorize on a PC with a browser: `python authorize_google.py pessoal`.
Full guide: [GOOGLE.md](GOOGLE.md). Free, but Google Cloud may ask for billing (card).

## Weather (no key)

| Service | What for | Link |
|---------|----------|------|
| **open-meteo** | Weather forecast + rain alerts | https://open-meteo.com |

## Mapillary (optional — street-level view on the web console's Mapa tab)

| Step | Link |
|------|------|
| Create an app, grab a client token | https://www.mapillary.com/dashboard/developers |

`.env`: `EV_MAPILLARY_TOKEN`. Free. Without it, tapping a saved place opens a Google
Street View link instead of the embedded viewer — nothing breaks.

## Spotify (optional — web console playback)

| Step | Link |
|------|------|
| Create an app (Client ID + Secret) | https://developer.spotify.com/dashboard |
| Add a redirect URI matching your web console URL + `/spotify/callback` | Dashboard → app → Settings |

`.env`: `EV_SPOTIFY_CLIENT_ID`, `EV_SPOTIFY_CLIENT_SECRET`. Then connect from the web
console (Música tab → "Conectar Spotify") — one-time OAuth per user. Free; requires a
Spotify account (Premium needed for playback control, per Spotify's own API rules).

## Gemini TTS (optional — more natural voice than edge-tts)

| `.env` variable | What for | Default |
|-----------------|----------|---------|
| `EV_GEMINI_TTS` | Set `true` to prefer Gemini's native voice over edge-tts | `false` |
| `EV_GEMINI_VOICE` | Which Gemini voice (`Kore`, `Aoede`, `Leda`, ...) | `Kore` |

Uses the same `GEMINI_API_KEY` — no separate key needed. Falls back to edge-tts
automatically on any error or quota limit.

## Hosting (run E.V. 24/7)

| Option | Link | Cost / card? |
|--------|------|--------------|
| **Oracle Cloud** (Always Free VM) | https://www.oracle.com/cloud/free/ · console: https://cloud.oracle.com | Free forever; card required at signup |
| **Ollama** (local "never runs out" model) | https://ollama.com | Free; needs a machine with RAM (not the 1GB VM) |
| **Termux** (run on Android — no card) | https://f-droid.org (install Termux + Termux:Boot) | Free, no card |

Deploy guide: [DEPLOY.md](DEPLOY.md) · phone: [TERMUX.md](TERMUX.md) · PC service: [SELF_HOST.md](SELF_HOST.md).

## Project & tooling

| Thing | Link |
|-------|------|
| **GitHub repo** | https://github.com/Ryanditko/E.V |
| **Python packages** (PyPI) | https://pypi.org |

## Current deployment (this instance)

- Host: Oracle Cloud Always Free VM (AMD micro), Ubuntu, systemd service `ev`.
- Configured providers: Gemini + Groq + OpenRouter; Tavily web search; open-meteo weather.
- Pending: Google OAuth (run `authorize_google.py` on your PC, then copy the token to the VM).

> Reminder: never commit `.env`, `client_secret*.json`, `google_token*.json`, `*.db`, or the SSH key.
