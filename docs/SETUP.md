# E.V. — Full setup guide (from scratch on a new machine)

This guide gets E.V. running from zero: dependencies, every API key, Google
authorization, running, and deploying. Docs are in English; E.V. talks in PT-BR.

---

## 1. Prerequisites

- **Python 3.11+** (developed on 3.14).
- **git**.
- Optional: **Ollama** (local model, the never-runs-out fallback) — https://ollama.com
- Optional: **ffmpeg** (not required today).

## 2. Get the code

```bash
git clone https://github.com/Ryanditko/E.V.git ev
cd ev
```

## 3. Python environment and dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Note (corporate machines):** if `pip` points to a private registry and fails,
> install from the public PyPI: `pip install -i https://pypi.org/simple/ -r requirements.txt`.

## 4. Configuration (.env)

```bash
cp .env.example .env
```

Fill in the keys below. Only `TELEGRAM_TOKEN` and `GEMINI_API_KEY` are strictly
required; everything else is optional and enables more features.

| Variable | Required? | Where to get it |
|----------|-----------|-----------------|
| `TELEGRAM_TOKEN` | Yes | Telegram, talk to [@BotFather](https://t.me/BotFather): `/newbot`, copy the token |
| `GEMINI_API_KEY` | Yes | https://aistudio.google.com/apikey (use a personal Google account) |
| `EV_OWNER_ID` | Recommended | Your Telegram numeric ID. Run the bot, send `/start`, read it from the logs, paste here to lock the bot to you |
| `GROQ_API_KEY` | Optional | https://console.groq.com/keys (fast fallback + Whisper transcription) |
| `OPENROUTER_API_KEY` | Optional | https://openrouter.ai/keys (extra fallback) |
| `OLLAMA_*` | Optional | Install Ollama and `ollama pull llama3.1`; the never-runs-out local fallback |
| `GOOGLE_OAUTH_CLIENT` | Optional | Path to the OAuth client JSON (see section 6) |
| `EV_GOOGLE_ACCOUNTS` | Optional | Comma-separated account names, e.g. `pessoal,faculdade` |

Voice, timezone, briefing hour, embedding backend, etc. have sensible defaults —
see the comments in `.env.example`.

### Which models (defaults)
- Primary LLM: `gemini-flash-latest`
- Groq fallback: `openai/gpt-oss-120b`
- OpenRouter fallback: a free model (they change often; if it 404s, pick a
  current one at https://openrouter.ai/models?max_price=0)
- Embeddings: `gemini-embedding-001`

## 5. Run

```bash
python run_telegram.py     # Telegram bot (voice + mobile)
python run_web.py          # web console at http://localhost:8000 (needs EV_WEB_TOKEN)
python run_terminal.py     # Terminal REPL (text only)
```

All three share the same brain and data, and can run at once. The web console is
covered in **[WEB.md](WEB.md)**; to reach it privately over HTTPS (needed for the
browser microphone) see **[../deploy/HTTPS_TAILSCALE.md](../deploy/HTTPS_TAILSCALE.md)**.

First run: send `/start` to your bot, copy your ID from the logs into
`EV_OWNER_ID`, and restart.

## 6. Google (Calendar + email) — optional

Full step-by-step (including the exact authorization commands to run on your
personal computer) is in **[GOOGLE.md](GOOGLE.md)**. Summary below.

One Google Cloud project/OAuth client serves all your accounts.

1. **Project:** https://console.cloud.google.com -> create a project.
2. **Enable APIs:** enable **Gmail API** and **Google Calendar API**.
3. **OAuth consent screen** (aka "Google Auth Platform"): type **External**; add
   every Google account you want to use under **Test users** (personal, faculty, ...).
4. **Credentials -> Create credentials -> OAuth client ID -> Desktop app ->
   Download JSON.** Save it as `client_secret.json` in the project root.
5. In `.env`: set `GOOGLE_OAUTH_CLIENT=client_secret.json` and
   `EV_GOOGLE_ACCOUNTS=pessoal,faculdade`.
6. **Authorize each account once** (opens a browser; log in with the matching account):
   ```bash
   python authorize_google.py pessoal
   python authorize_google.py faculdade
   ```
   This caches `google_token_<account>.json` per account.

Usage: `/agenda [account]`, `/evento [account] <time> <title>`,
`/email [account] to@x.com | subject | body`. Omitting the account uses the first.

> Institutional (faculty/work) accounts may block third-party OAuth apps by admin
> policy; if so, that account cannot be authorized (nothing we can do client-side).

## 7. Deploy 24/7 (Oracle Cloud)

See [../deploy/README.md](../deploy/README.md). Summary: an Always Free VM, code
cloned, `.env` copied over, run `deploy/setup_vm.sh` (installs a `systemd` service
that starts on boot and restarts on crash). For the Google token on a headless VM,
authorize locally first, then copy `google_token_*.json` to the VM.

## 8. Files that must NOT be committed (secrets)

Already in `.gitignore`, but never share these:
`.env`, `client_secret*.json`, `google_token*.json`, `ev_memory.db`, `backups/`.

## 9. Moving to a new computer — checklist

1. `git clone` the repo, create venv, `pip install -r requirements.txt`.
2. Copy your `.env` over (or recreate it from `.env.example` + your keys).
3. Copy `client_secret.json` and `google_token_*.json` if you use Google (or
   re-run `authorize_google.py`).
4. Optionally copy `ev_memory.db` (or a file from `backups/`) to keep memory/history.
5. `python run_telegram.py`.

## 10. Tests

```bash
python -m pytest -q
```
