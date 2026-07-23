# Extending E.V. — add features without starting from scratch

This guide shows the exact, repeatable pattern to add new capabilities. It's
written so that **you or any AI coding assistant** (Claude Code, Cursor, ChatGPT)
can follow it. The codebase is intentionally consistent — new features are
copy-the-pattern, not invent-from-zero.

> Give an assistant this file plus the repo and say: "Follow docs/EXTENDING.md to
> add <feature>." That's usually enough.

## Where things live (recap)

```
ev/
├── config.py            # settings from .env (add new options here)
├── personality.py       # how E.V. talks (edit freely, no coding)
├── core/
│   ├── brain.py         # LLM orchestration + fallback + tools + RAG
│   ├── memory.py        # SQLite: tables + all data access methods
│   ├── commands.py      # deterministic slash commands (no LLM)
│   ├── timeparse.py     # time parsing for commands
│   └── knowledge.py     # document/URL ingestion
├── providers/
│   ├── llm.py           # Gemini/Groq/OpenRouter/Ollama chat + Whisper
│   ├── embeddings.py    # embeddings (Gemini/Ollama)
│   ├── voice.py         # text -> speech
│   └── tools.py         # web search, weather, news, calendar, email, fetch
└── interfaces/
    └── telegram_bot.py  # command handlers, menu, schedulers
tests/                   # pytest — add a test per feature
```

Dependency rule: interfaces → core → providers. Never import an interface from
core, or core from an interface.

## Recipe A: add a new slash command (the most common task)

Example: a `/nota` command to save quick notes. Five small steps.

**1. Storage — `ev/core/memory.py`.** Add a table to `_init_schema` and methods:

```python
# inside _init_schema executescript:
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL
);

# methods on the Memory class:
def add_note(self, user_id, text):
    cur = self._conn.execute(
        "INSERT INTO notes (user_id, text, created) VALUES (?, ?, ?)",
        (user_id, text, self._now()))
    self._conn.commit(); return int(cur.lastrowid)

def list_notes(self, user_id):
    rows = self._conn.execute(
        "SELECT id, text FROM notes WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
    return [dict(r) for r in rows]
```

**2. Command logic — `ev/core/commands.py`.** Add a method returning a PT-BR string:

```python
def nota(self, user_id, argstr):
    text = argstr.strip()
    if not text:
        return "Uso: /nota <texto>"
    nid = self._memory.add_note(user_id, text)
    return f"Nota #{nid} salva."
```

Also add it to `COMMAND_LIST` (populates the Telegram `/` menu):

```python
("nota", "Salvar uma nota: /nota comprar leite"),
```

**3. Telegram handler — `ev/interfaces/telegram_bot.py`.** Copy an existing handler:

```python
async def cmd_nota(self, update, c):
    if self._authorized(update):
        uid = str(update.effective_user.id)
        await self._cmd_out(update, self._commands.nota(uid, self._args(c)))
```

**4. Register it** in `run()` next to the others:

```python
app.add_handler(CommandHandler("nota", self.cmd_nota))
```

**5. Test — `tests/test_commands.py`.**

```python
def test_nota(tmp_path):
    c = _commands(tmp_path)
    assert "salva" in c.nota("u", "comprar leite")
```

Run `python -m pytest -q`. Done.

## Recipe B: add a scheduled/proactive automation

Automations live in `telegram_bot.py`. The `_briefing_loop` runs every 60s — add
a `_maybe_do_x(app)` method and call it there (guard with a `self._last_x` date so
it fires once). For frequent polling (like web monitors), add a separate loop in
`_post_init`'s `self._bg_tasks` list. Use `EV_*` config for hours/intervals.

## Recipe C: add a real-world tool (web/API)

Put the raw call in `ev/providers/tools.py` (use `httpx`; the OS trust store is
already injected). Then either expose it as a slash command (Recipe A) or as an
LLM tool so E.V. calls it in conversation:

- In `brain._tool_callables`, add a Python function (name, docstring, typed args).
- Mirror it in `brain._openai_tools()` (same name/params) so Groq can call it too.

## Recipe D: change behavior with NO code

- **Personality/tone:** edit `ev/personality.py`.
- **Voice, city, news, hours, models, accounts:** edit `.env` (see `.env.example`).
- **Your data:** add/remove via the bot's own commands.

## Deploy your change

Local test first: `python -m pytest -q` and `python run_telegram.py`.
Then to the server (see `docs/DEPLOY.md`): copy the code up and restart —

```bash
# from the project on your machine:
scp -i <key> -r ev <user>@<vm-ip>:~/ev/
ssh -i <key> <user>@<vm-ip> "sudo systemctl restart ev"
```

Or, if you use git on the VM: `git pull && sudo systemctl restart ev`.

## Conventions to keep

- Commands return short PT-BR strings; E.V. speaks Portuguese.
- Docs and code comments in English.
- Every data type gets add/list/delete (users expect to undo anything).
- Add a test for each new command. Keep the suite green.
- Never commit secrets (`.env`, `client_secret*.json`, `google_token*.json`, `*.db`).
