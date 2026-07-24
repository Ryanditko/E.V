# E.V. — Everything she does (complete capabilities reference)

The full, literal list of what E.V. can do. She talks to you in Brazilian
Portuguese; this reference is in English (docs convention). Commands are shown
as you type them in Telegram.

---

## 1. How you interact with her

Via the **Telegram bot** (24/7 in the cloud). Three modes, all mixable:

- **Natural chat (uses the AI):** send **text**, a **voice note** (she transcribes
  and answers in text + voice), or a **photo** (she reads/analyzes it). She keeps
  context, remembers you, and calls real tools when needed.
- **Slash commands (instant, no AI):** deterministic actions like `/tarefa`,
  `/gasto`, `/lembrete`. Full list below.
- **Interactive menu:** `/menu` opens a button-driven UI; every reply also carries
  a quick-action bar (🏠 Menu · ➕ Tarefa · ⏰ Lembrete).
- **Send a PDF** → it's indexed into her knowledge base. **Send a photo** → she
  interprets it.

She is **locked to you** (owner-only) and replies with a natural female voice.

## 2. What she does in conversation (AI)

- **Chat & advice:** answers, decisions, brainstorming, venting — with a warm,
  witty personality (you configured it in `personality.py`).
- **Long-term memory:** remembers durable facts about you and recalls the relevant
  ones (semantic search) at the right moment.
- **Commitment detection:** if you mention a deadline/appointment in chat
  ("tenho prova sexta"), she offers to create a reminder.
- **Real-world tools she calls automatically when useful:**
  - `buscar_web` — current facts, prices, events (Tavily → Brave → DuckDuckGo).
  - `consultar_noticias` — recent news (with sources).
  - `consultar_clima` — real weather forecast (open-meteo).
  - `salvar_memoria`, `criar_lembrete`, `listar_lembretes`.
  - `criar_documento` — writes a file (txt/md/pdf/docx) with content she composed
    and sends it to you (say "me manda em pdf", "faz em word"); can also save it
    to the knowledge base in the same step.
  - `ver_agenda`, `criar_evento`, `enviar_email` — once Google is connected.
- **Honesty:** if unsure, she says so and offers to search instead of inventing;
  cites sources when she used the web.

## 3. Full command reference

### General
| Command | Does |
|---------|------|
| `/menu` | Open the interactive button menu |
| `/ajuda` | List all commands |
| `/modelo` | Show AI models + today's usage; `/modelo <nome>` switches the primary model |
| `/status` | Diagnostics: uptime, DB, disk/memory, which API keys are set — plus a button to live-test the keys |
| `/silenciar <2h\|30m\|1d\|off>` | Do-not-disturb: mute proactive pings (briefing, check-in, nudges); reminders still fire |
| `/dados` | Storage control: see counts per category and wipe by category (tap-confirm) or **everything** (two-factor: tap + type `APAGAR TUDO`) |
| `/limpar` | Clear the conversation history in her memory (keeps reminders, facts, everything else) |
| `/limparchat <N>` · `/limparchat tudo` | Delete the last N (or as many as possible) visible message bubbles from the Telegram chat (only ~last 48h, Telegram limit) |
| `/foco [min] [pausa]` | Pomodoro focus timer (default 25/5) — she pings you at break and end |
| `/resumir <url>` | Fetch a page/article and return a short summary (with a save-to-KB button) |

### Tasks
| Command | Does |
|---------|------|
| `/tarefa <texto> [#categoria]` | Add a task (e.g. `/tarefa estudar #faculdade`) |
| `/tarefas [categoria]` | List tasks (grouped, or filtered) |
| `/concluir <id>` | Complete a task |

### Reminders & calendar
| Command | Does |
|---------|------|
| `/lembrete <tempo> <texto>` | One-off reminder (`10m`, `2h`, `amanhã 09:00`, `25/12 14:30`) |
| `/rotina <diario\|semanal> <HH:MM> <texto>` | Recurring reminder (daily/weekly) |
| `/rotina mensal <dia> <HH:MM> <texto>` | Monthly reminder (e.g. `mensal 5 10:00 pagar aluguel`) |
| `/lembretes` | List reminders |
| `/cancelar <id>` | Cancel a reminder |

When a reminder fires it comes with quick buttons: **✅ Feito · ⏰ +10min · ⏰ +1h · 🌙 Amanhã** (snooze creates a fresh reminder).
| `/calendario` | Agenda view by day (+ Google Calendar if connected) |

### Memory
| Command | Does |
|---------|------|
| `/lembrar <fato>` | Save something to long-term memory |
| `/memorias` | List what she knows about you |
| `/esquecer <id>` | Delete a memory |

### Knowledge base & study
| Action | Does |
|--------|------|
| Send a **PDF / Word (.docx) / .txt** | She reads it and offers **Resumir** (summarize) or **Indexar na base** (index for RAG) |
| `/kb` | List documents |
| `/kbweb <url>` | Index a web page |
| `/kbrm <nome>` | Remove a document |
| `/quiz [documento]` | Generate a study question from your PDFs (answer hidden as spoiler) |
| `/exportar` | Export your data: **gastos** as CSV (Excel/Sheets) or **dados** as a PDF digest |
| `/transcrever` | Transcribe an audio (voice note or audio file) into a text file |
| `/documento <formato> <título> \| <conteúdo>` | Create a file and send it to you. Formats: `txt`, `md`, `pdf`, `docx` (or `word`); format optional (default `pdf`) |

**Creating documents (txt / Markdown / PDF / Word).** Three ways:

1. **Just ask in chat or by voice** — "escreve um resumo de X e me manda em PDF",
   "faz uma lista em word". She writes the content, generates the file and sends it.
2. **Command** — `/documento pdf Lista de compras | arroz, feijão, café` (exact
   content, no AI/tokens spent).
3. **Menu** — `/menu` → 📄 Conhecimento → 📝 Criar documento.

Every generated file arrives with a **📚 Salvar na base** button — tap it to store
that content in the knowledge base (RAG), so you can ask about it later or `/quiz`
on it. (When you ask via the AI, she can also save it in the same step.)

**Working with files, audio and images (in & out):**

- **Send a document** (PDF, Word, txt) → she reads it and shows buttons to
  **summarize** it or **index** it into the knowledge base.
- **Send an audio** (voice note or audio file), or use `/transcrever` → she
  **transcribes** it and returns the text as a `.txt` file.
- **Send a photo** → besides describing it, she offers **📄 Extrair texto (OCR)**
  to pull the text out and return it as a file (with the option to save to the KB).
- **Export your data** → `/exportar` (or 📤 Exportar no menu): expenses as **CSV**,
  or a **PDF** digest of tasks, memories, habits and journal.

### Finances
| Command | Does |
|---------|------|
| `/gasto <valor> <desc> [#cat]` | Log an expense (warns if over budget) |
| `/gastos` | Month summary by category + recent entries |
| `/gastorm <id>` | Delete an expense |
| `/relatorio` | Last month's financial report + AI comment |
| `/orcamento <cat> <valor>` | Set a monthly budget for a category |
| `/orcamentos` | Budgets vs spending (with % and 🟢🟡🔴) |
| `/orcamentorm <cat>` | Remove a budget |
| `/assinatura <valor> <desc> [dia] [#cat]` | Recurring expense (auto-logged monthly) |
| `/assinaturas` · `/assinaturarm <id>` | List / remove subscriptions |

### Habits
| Command | Does |
|---------|------|
| `/habito <nome>` | Create a habit |
| `/feito <nome>` | Mark it done today |
| `/habitos` | List habits with streaks |
| `/habitorm <nome>` | Remove a habit |

### Journal
| Command | Does |
|---------|------|
| `/diario <texto>` | Write a journal entry |
| `/diario` | Show recent entries |
| `/diariorm <id>` | Delete an entry |

### Links
| Command | Does |
|---------|------|
| `/link <categoria> \| <nome> \| <url>` | Save a link by category |
| `/links [categoria]` | List links |
| `/linkrm <id>` | Remove a link |

### Search, news & weather
| Command | Does |
|---------|------|
| `/buscar <termo>` | Web search (with sources) |
| `/procurar <termo>` | Search across YOUR data (memory, tasks, links, journal, KB...) |
| `/noticias [assunto]` | Latest news with sources + TabNews (tech) |
| `/clima [cidade]` | Real weather forecast (today + next days) |

### Reviews & monitoring
| Command | Does |
|---------|------|
| `/semana` | Weekly review (tasks done, expenses, habit streaks) |
| `/insights` | AI reflection over your week's data |
| `/vigiar <url> [\| palavra]` | Monitor a page; alert on change / when a keyword appears |
| `/vigias` · `/vigiarm <id>` | List / remove monitors |

### Google (after one-time OAuth — see GOOGLE.md)
| Command | Does |
|---------|------|
| `/agenda [conta]` | Upcoming Google Calendar events |
| `/evento [conta] <tempo> <título>` | Create a calendar event |
| `/email [conta] <para> \| <assunto> \| <corpo>` | Send an email |

## 4. Automations (she acts on her own)

| When | What |
|------|------|
| Every day 08:00 | **Morning briefing**: tasks, reminders, agenda, weather, news + TabNews |
| Every day 20:00 | **Habit nudge**: reminds about habits not marked yet |
| Every day 21:00 | **Check-in** ("how was your day?") + **rain alert** for tomorrow |
| Sundays 20:00 | **Weekly review** + AI insights |
| Day 1, 09:00 | **Monthly financial report** + AI comment |
| At each reminder's time | Delivers the reminder (recurring ones reschedule themselves) |
| On each subscription's day | Auto-logs the recurring expense |
| Every ~30 min | Checks web monitors (`/vigiar`) and alerts on real changes |
| Weekly + on restart | Sends a **DB backup** to your Telegram (off-VM copy) |

All hours/days are configurable in `.env`.

## 5. What she stores (your data, local SQLite)

Conversation history (auto-pruned to the last N), long-term **facts** (with
embeddings), **reminders** (one-off + recurring), **tasks** (with categories),
**links** (by category), **expenses** + **budgets** + **subscriptions**,
**habits** (+ daily logs & streaks), **journal** entries, **knowledge base**
(document/web chunks + embeddings), **web monitors**, and usage stats/settings.
Everything is add / list / delete — you can undo anything.

## 6. AI models & resilience

- **Primary:** Gemini (`gemini-flash-latest`) — native audio + image + memory tools.
- **Fallbacks (auto):** Groq (`openai/gpt-oss-120b`, reliable tools) → OpenRouter
  (Nemotron) → **Ollama** (local, never rate-limited — if enabled on a capable host).
- **Audio transcription:** Groq Whisper. **Embeddings:** Gemini `gemini-embedding-001`.
- If a provider hits its limit, she falls through automatically — she rarely goes
  silent. `/modelo` shows what's active and today's usage.

## 7. Reliability & safety

- **Owner lock:** only you can use the bot.
- **Backups:** daily local + weekly to your Telegram (restore anytime).
- **History pruning:** keeps the DB small; facts/tasks/etc. are never pruned.
- **Honesty:** admits uncertainty, cites web sources, prefers real tools over guessing.
- **Runs 24/7** on an Oracle Always Free VM as a `systemd` service (auto-restart, boot start).

## 8. Configuration & keys

All behavior (voice, city, news topic, automation hours, models, accounts) is set
in `.env` — see [`.env.example`](../.env.example). Every service/link/key is in
[KEYS.md](KEYS.md). To add new features: [EXTENDING.md](EXTENDING.md).

## 9. Honest limits (what she can't do — yet)

- **No hands-free/always-listening voice** — Telegram can't stream your mic; voice
  is tap-to-record. A wake-word ("E.V., ...") would need a separate app on a device.
- **No sub-second real-time voice** (movie-JARVIS style) without a paid realtime API.
- **No physical-world control** (home automation, devices) — not integrated.
- **Google email/calendar** need a one-time OAuth on a personal computer.
- **Web/news quality** depends on the search provider; forecasts have normal
  meteorological uncertainty.
- **Documents:** she writes text-based files (txt/md/pdf/docx). Legacy `.doc` is
  produced as modern `.docx` (opens the same in Word/Docs). No spreadsheets/slides,
  no images or complex layout inside the generated files — plain formatted text.
- **The AI can still occasionally be wrong** on un-tooled facts — verify important
  things (she'll flag uncertainty when she can).
