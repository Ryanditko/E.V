# Extending E.V. — add features without starting from scratch

This guide shows the exact, repeatable pattern to add new capabilities. It's
written so that **you or any AI coding assistant** (Cursor, ChatGPT, etc.)
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
│   ├── brain/           # LLM orchestration package (mixins → class Brain in base.py)
│   │   ├── base.py             # class Brain(TranscriptionMixin, …); __init__
│   │   ├── ask.py              # the respond()/ask turn logic
│   │   ├── tools.py            # _tool_callables (Gemini) + _openai_tools (Groq)
│   │   ├── transcription.py    # audio → text
│   │   ├── provider_health.py  # health/availability checks
│   │   └── providers_fallback.py  # Gemini → Groq → OpenRouter → Ollama chain
│   ├── memory/          # SQLite package (mixins → class Memory in base.py)
│   │   ├── base.py             # class Memory(SchemaMixin, …); connection
│   │   ├── schema.py           # table DDL (_init_schema)
│   │   └── <domain>.py         # one file per domain: tasks, facts, links, …
│   ├── commands/        # deterministic slash commands (mixins → class Commands)
│   │   ├── base.py             # class Commands(…); COMMAND_LIST; helpers
│   │   └── <domain>.py         # one file per domain: tasks, expenses, habits, …
│   ├── timeparse.py     # time parsing for commands
│   └── knowledge.py     # document/URL ingestion
├── providers/
│   ├── llm.py           # Gemini/Groq/OpenRouter/Ollama chat + Whisper
│   ├── embeddings.py    # embeddings (Gemini/Ollama)
│   ├── voice.py         # text -> speech
│   └── tools/           # package: weather, websearch, maps, calendar, email, google_auth
└── interfaces/
    ├── telegram_bot/    # Telegram adapter package (mixins → class TelegramInterface)
    │   ├── base.py             # __init__, _post_init, run() + handler registration
    │   └── <area>.py           # routing, voice, media, pomodoro, keyboards, callbacks, …
    ├── web/             # FastAPI console package
    │   ├── app.py              # create_app() + router registration + structural routes
    │   ├── context.py          # WebContext (shared singletons)
    │   ├── frontend.py         # static _PAGE / favicon / service-worker
    │   └── routes/<domain>.py  # one APIRouter per domain, each build_router(ctx)
    └── terminal.py      # terminal REPL
tests/                   # pytest — add a test per feature
```

Every package's `__init__.py` re-exports the same public names (`Brain`, `Memory`,
`Commands`, `TelegramInterface`, the tool functions), so **import paths are
unchanged** despite the split.

Dependency rule: interfaces → core → providers. Never import an interface from
core, or core from an interface.

## Recipe A: add a new slash command (the most common task)

Example: a `/nota` command to save quick notes. Five small steps.

**1. Storage — `ev/core/memory/`.** Add the table DDL to `_init_schema` in
`ev/core/memory/schema.py`, then put the data-access methods in a domain mixin file
(e.g. a new `ev/core/memory/notes.py` defining `class NotesMixin`) and list that
mixin in `class Memory(SchemaMixin, …)` in `ev/core/memory/base.py`:

```python
# inside _init_schema (ev/core/memory/schema.py) executescript:
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL
);

# methods on the NotesMixin (ev/core/memory/notes.py):
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

**2. Command logic — `ev/core/commands/`.** Add the method to the matching domain
mixin (e.g. `ev/core/commands/tasks.py`), or a new `<domain>.py` mixin listed in
`class Commands(…)` in `ev/core/commands/base.py`. It returns a PT-BR string:

```python
def nota(self, user_id, argstr):
    text = argstr.strip()
    if not text:
        return "Uso: /nota <texto>"
    nid = self._memory.add_note(user_id, text)
    return f"Nota #{nid} salva."
```

Also add it to `COMMAND_LIST` in `ev/core/commands/base.py` (populates the Telegram
`/` menu):

```python
("nota", "Salvar uma nota: /nota comprar leite"),
```

**3. Telegram handler — `ev/interfaces/telegram_bot/`.** Add the `cmd_*` wrapper to
the `CommandsWrappersMixin` in `ev/interfaces/telegram_bot/commands_wrappers.py`,
copying an existing handler:

```python
async def cmd_nota(self, update, c):
    if self._authorized(update):
        uid = str(update.effective_user.id)
        await self._cmd_out(update, self._commands.nota(uid, self._args(c)))
```

**4. Register it** in `run()` (in `ev/interfaces/telegram_bot/base.py`) next to the
others — keep the handler registration order Document → Photo → Audio → Voice → Text
intact:

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

> **Web console equivalent.** To surface the same data in the web UI, add an
> APIRouter at `ev/interfaces/web/routes/notes.py` exposing `build_router(ctx)`
> (read `ctx.memory` / `ctx.commands`), then include the module in the router loop
> in `ev/interfaces/web/app.py`. Copy an existing `routes/<domain>.py`.

## Recipe B: add a scheduled/proactive automation

Automations live in the `BackgroundLoopsMixin`
(`ev/interfaces/telegram_bot/background_loops.py`). The `_briefing_loop` runs every
60s — add a `_maybe_do_x(app)` method and call it there (guard with a `self._last_x`
date so it fires once). For frequent polling (like web monitors), add a separate loop
in `_post_init` (`ev/interfaces/telegram_bot/base.py`) via the `self._bg_tasks` list.
Use `EV_*` config for hours/intervals.

## Recipe C: add a real-world tool (web/API)

Put the raw call in the matching submodule under `ev/providers/tools/` (or a new one,
re-exported from `ev/providers/tools/__init__.py`; use `httpx`, the OS trust store is
already injected). Then either expose it as a slash command (Recipe A) or as an
LLM tool so E.V. calls it in conversation. Both tool schemas live together in
`ev/core/brain/tools.py` and must stay in sync (a test,
`tests/test_brain_tools_sync.py`, guards this):

- In `_tool_callables`, add a Python function (name, docstring, typed args) — the
  Gemini-native path.
- Mirror it in `_openai_tools()` (same name/params) so Groq can call it too.

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
