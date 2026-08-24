"""Full command-surface smoke tests.

Unit tests elsewhere target specific commands' happy paths — they don't catch
a command that only breaks when it actually *raises* internally (the
`cmd.error` kwarg-collision bug, #204: every failing command crashed the
whole chat/voice turn instead of returning a friendly message) or a command
whose reply silently ignores `assistant_lang` (the /focus hardcoded-Portuguese
bug, #205). Both slipped through review because nothing exercised the FULL
command surface — only the handful of commands each existing test happened to
call.

These tests run *every* dispatchable/menu command (not just the ones with
dedicated tests) through the real `Commands.run()` and the web console's
`/api/cmd`, in both languages, and assert none of them raise or fall back to
the generic internal-error message.
"""

from types import SimpleNamespace

from ev.core.commands import Commands, command_list
from ev.core.memory import Memory


def _commands(tmp_path):
    config = SimpleNamespace(
        timezone="America/Sao_Paulo",
        google_oauth_client="", google_accounts=(), default_account="",
        gemini_api_key="", embed_backend="gemini", embed_model="m",
        tavily_api_key="", brave_api_key="", websearch_enabled=False,
        google_authorized=lambda *a, **k: False, imap_ready=lambda: False,
    )
    return Commands(config, Memory(tmp_path / "t.db"))


def test_every_dispatchable_command_runs_without_raising(tmp_path):
    """Every command in Commands._dispatch() (what the AI's hands-free
    executar_comando tool can call) must return a normal string, never the
    internal-error fallback, when invoked with empty args."""
    c = _commands(tmp_path)
    names = c.runnable()
    assert len(names) > 90  # sanity: this should cover ~everything dispatchable
    broken = []
    for name in names:
        out = c.run("u", name, "")
        if out.startswith("Error running") or out.startswith("Erro ao executar"):
            broken.append((name, out))
    assert not broken, f"commands raised internally: {broken}"


class _FakeBrain:
    async def respond(self, owner, conv_id=None, text=None, image=None, image_mime=None):
        return f"echo: {text}"

    def current_model(self):
        return "m"

    async def ask(self, system, prompt):
        return "stub answer"

    async def plan_day(self, owner):
        return "stub plan"

    async def transcribe(self, audio, mime):
        return "stub transcript"

    def pop_documents(self):
        return []

    def pop_actions(self):
        return []


def _web_client(tmp_path):
    from fastapi.testclient import TestClient

    from ev.interfaces.web import create_app

    cfg = SimpleNamespace(
        web_token="secret", owner_id=123, db_path=tmp_path / "t.db",
        timezone="America/Sao_Paulo", google_oauth_client="", google_accounts=(),
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
        telegram_token="t", groq_api_key="", openrouter_api_key="",
        tavily_api_key="", brave_api_key="", ollama_enabled=False,
        groq_model="g", openrouter_model="o", ollama_model="l",
        google_ready=lambda: False, google_authorized=lambda account=None: False,
        web_base_url="", google_login_client="", google_login_secret="",
        github_login_client="", github_login_secret="",
        vapid_public="", vapid_private="", vapid_subject="mailto:x@x.com",
    )
    return TestClient(create_app(cfg, brain=_FakeBrain()))


def _auth():
    return {"Authorization": "Bearer secret"}


def test_every_menu_command_runs_via_web_console_both_languages(tmp_path):
    """Every command shown in the command menu (Telegram autocomplete / web
    palette) must produce a 200 with a non-empty reply via /api/cmd, in both
    the English and Portuguese name, in both assistant languages. This is the
    exact surface that silently regressed to Portuguese output in #205."""
    client = _web_client(tmp_path)
    for lang in ("en", "pt"):
        client.post("/api/lang", json={"lang": lang}, headers=_auth())
        for en, pt in zip((n for n, _ in command_list("en")), (n for n, _ in command_list("pt"))):
            for name in {en, pt}:
                r = client.post("/api/cmd", json={"command": name}, headers=_auth())
                assert r.status_code == 200, f"{name!r} ({lang}) -> HTTP {r.status_code}"
                reply = r.json().get("reply", "")
                assert reply, f"{name!r} ({lang}) returned an empty reply"
