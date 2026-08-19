#!/usr/bin/env python3
"""Reusable screenshot harness for E.V.'s web console.

Seeds a fresh, disposable SQLite DB with fictional PT-BR demo data, boots the
real FastAPI web app in-process (behind uvicorn, with a lightweight stub brain
so no network / API keys are needed), then drives a headless Chromium via
Playwright to capture each screen into ``docs/screenshots/<name>.png`` — using
the exact filenames the README already references, so no README edit is needed.

Every screen is verified after capture (min file size + pixel variance) so a
blank/error page never overwrites a currently-good committed screenshot. Screens
that depend on external APIs/keys (weather, Google Calendar, map tiles, Spotify)
are skipped by default and left untouched — pass ``--include-external`` to try
them anyway (they will still be discarded if they fail verification).

All data shown is clearly-fictional demo data. Nothing here reads or touches the
owner's real ``ev_memory.db``: the DB path is derived from this checkout's root,
and this script refuses to run if that path is not inside the current tree.

Usage
-----
    # from the repo root, with the project venv:
    python tools/screenshots.py                 # regenerate the safe screen set
    python tools/screenshots.py --only tasks,mem # just a couple of screens
    python tools/screenshots.py --include-external  # also try clima/cal/map/musica
    python tools/screenshots.py --keep-db        # keep the seeded demo DB around
    python tools/screenshots.py --headed         # watch the browser (debugging)
    python tools/screenshots.py --help

Re-run it any time to refresh the shots — it is idempotent (the demo DB is
recreated from scratch on every run unless ``--keep-db`` is given).
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# --- Repo layout ----------------------------------------------------------
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent          # repo / worktree root
_SHOTS = _ROOT / "docs" / "screenshots"
_DEMO_DB = _ROOT / "ev_memory.db"    # gitignored; recreated each run

# Make `import ev...` work no matter where the script is launched from.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _rm_demo_db() -> None:
    """Delete the demo DB and its SQLite WAL/SHM sidecar files."""
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_DEMO_DB) + suffix)
        if p.exists():
            p.unlink()

# Provide dummy config via env BEFORE importing ev.config (which reads env at
# import time). Never put real keys here. EV_OWNER_ID is left empty on purpose
# so the app's owner id becomes the literal "web" (see create_app()).
_ENV_DEFAULTS = {
    "TELEGRAM_TOKEN": "x",
    "GEMINI_API_KEY": "x",
    "EV_WEB_TOKEN": "demotoken",
    "EV_OWNER_ID": "",
    "EV_WEBSEARCH_ENABLED": "0",
    "OLLAMA_ENABLED": "0",
}
for _k, _v in _ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)

TOKEN = os.environ["EV_WEB_TOKEN"]
OWNER = "web"   # config.owner_id is None (empty EV_OWNER_ID) -> owner == "web"

# The full set the README references. name -> the in-app switchView() key (or a
# custom capture action handled in capture()). Filenames deliberately match the
# committed set so the README needs no edits.
SCREENS: dict[str, str] = {
    "dashboard": "inicio",
    "chat": "chat",
    "terminal": "__terminal__",
    "tasks": "tasks",
    "rem": "rem",
    "hab": "hab",
    "jou": "jou",
    "expenses": "exp",
    "orc": "orc",
    "metas": "metas",
    "lnk": "lnk",
    "kb": "kb",
    "mem": "mem",
    "painel": "painel",
    "brain": "brain",
    "act": "act",
    "mon": "mon",
    "sub": "sub",
    "graf": "graf",
    "cofre": "cofre",
    "saude": "saude",
    "serious-mode": "__serious__",
    "brand-new-day": "__bnd__",
    # External-API-dependent — skipped unless --include-external.
    "clima": "clima",
    "cal": "cal",
    "map": "map",
    "musica": "musica",
    # No dedicated view in the current UI (people live inside the Cérebro/brain
    # graph). Never auto-captured; listed so --help/coverage is explicit.
    "pessoas": "__none__",
}

# Screens that cannot render faithfully without external keys/network. Left
# untouched by default so a blank/error page never clobbers a good screenshot.
EXTERNAL = {"clima", "cal", "map", "musica"}
NO_VIEW = {"pessoas"}

VIEWPORT = {"width": 1440, "height": 900}   # matches the existing committed set


# --- Demo data ------------------------------------------------------------
def seed_demo(db_path: Path) -> None:
    """Insert fictional PT-BR demo data across every local domain."""
    from ev.core.memory import Memory

    m = Memory(db_path)
    u = OWNER
    today = date.today()

    def iso(days_ago=0, hour=9, minute=0):
        d = datetime.now() + timedelta(days=days_ago)
        return d.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

    # Tasks (a few categories, one recurring)
    m.add_task(u, "Estudar cálculo — capítulo 4", "faculdade")
    m.add_task(u, "Comprar presente da Ana", "pessoal")
    m.add_task(u, "Revisar relatório do projeto", "trabalho")
    m.add_task(u, "Treino de força", "saúde", recur="daily", due=iso(0, 18))
    m.add_task(u, "Pagar conta de luz", "casa")
    m.add_task(u, "Ler 10 páginas", "pessoal", recur="daily")

    # Reminders (future-dated)
    m.add_reminder(u, "Consulta no dentista", iso(2, 14, 30))
    m.add_reminder(u, "Ligar para a operadora", iso(1, 10))
    m.add_reminder(u, "Backup do computador", iso(5, 21), recur="weekly")
    m.add_reminder(u, "Reunião de alinhamento", iso(0, 16))

    # Habits with a spread of daily logs (for the heatmap/streak)
    for hname, done_days in [
        ("Beber 2L de água", range(0, 12)),
        ("Meditar 10 min", [0, 1, 2, 4, 5, 7, 8]),
        ("Ler antes de dormir", [0, 1, 3, 4, 6, 9, 10]),
        ("Caminhar 30 min", [0, 2, 3, 5, 6, 8]),
    ]:
        hid = m.add_habit(u, hname)
        for dd in done_days:
            m.log_habit(hid, (today - timedelta(days=dd)).isoformat())

    # Journal
    m.add_journal(u, "Dia produtivo — terminei o relatório e ainda treinei. "
                     "Amanhã foco nos estudos.")
    m.add_journal(u, "Um pouco cansado hoje, mas mantive os hábitos. "
                     "Consegui ler antes de dormir.")
    m.add_journal(u, "Ótima conversa com a Ana sobre a viagem de fim de ano.")

    # Expenses (spread across categories and recent days)
    expenses = [
        (87.90, "Mercado", "comida"), (32.50, "Almoço no trabalho", "comida"),
        (19.90, "Café da tarde", "comida"), (120.00, "Farmácia", "saúde"),
        (54.00, "Uber", "transporte"), (39.90, "Livro novo", "lazer"),
        (210.00, "Conta de luz", "casa"), (45.00, "Cinema com amigos", "lazer"),
        (28.00, "Padaria", "comida"), (65.00, "Presente", "pessoal"),
    ]
    for amt, desc, cat in expenses:
        m.add_expense(u, amt, desc, cat)

    # Budgets (orçamentos)
    m.set_budget(u, "comida", 800.0)
    m.set_budget(u, "lazer", 300.0)
    m.set_budget(u, "transporte", 250.0)
    m.set_budget(u, "casa", 900.0)

    # Recurring expenses (assinaturas)
    m.add_recurring(u, 39.90, "Streaming de vídeo", "lazer", 15)
    m.add_recurring(u, 21.90, "Streaming de música", "lazer", 5)
    m.add_recurring(u, 29.90, "Academia", "saúde", 10)
    m.add_recurring(u, 9.90, "Armazenamento na nuvem", "trabalho", 20)

    # Goals (metas / cofrinho)
    g1 = m.add_goal(u, "Viagem de fim de ano", 4000.0)
    m.add_to_goal(u, g1, 1750.0)
    g2 = m.add_goal(u, "Notebook novo", 6000.0)
    m.add_to_goal(u, g2, 2400.0)
    g3 = m.add_goal(u, "Reserva de emergência", 10000.0)
    m.add_to_goal(u, g3, 6800.0)

    # Links
    for cat, name, url in [
        ("dev", "Documentação Python", "https://docs.python.org"),
        ("dev", "Repositório do projeto", "https://github.com"),
        ("estudos", "Curso de cálculo", "https://exemplo.edu/calculo"),
        ("lazer", "Lista de filmes", "https://exemplo.com/filmes"),
        ("trabalho", "Painel de métricas", "https://exemplo.com/metricas"),
    ]:
        m.add_link(u, cat, name, url)

    # Knowledge base (notes/chunks) — no embeddings needed for the list view
    for src, chunk in [
        ("Anotações de cálculo.pdf", "Regra da cadeia e derivadas de funções compostas."),
        ("Anotações de cálculo.pdf", "Integração por partes e substituição."),
        ("Resumo do projeto.md", "Objetivos, escopo e cronograma do trimestre."),
        ("Receitas favoritas.txt", "Macarrão ao alho e óleo, bolo de cenoura."),
    ]:
        m.add_chunk(u, src, chunk, None)
        m.save_kb_file(u, src, src, "application/octet-stream", chunk.encode("utf-8"))

    # Facts / long-term memories
    for fact in [
        "Prefiro café sem açúcar de manhã.",
        "Faço faculdade de engenharia à noite.",
        "Aniversário da Ana é em dezembro.",
        "Gosto de correr aos sábados de manhã.",
        "Meu objetivo do ano é ler 24 livros.",
    ]:
        m.add_fact(u, fact)

    # People (relationships)
    m.add_person(u, "Ana", "Melhor amiga, adora viajar.", birthday="12/12")
    m.add_person(u, "Bruno", "Colega de faculdade, dupla de estudos.", birthday="03/05")
    m.add_person(u, "Carla", "Irmã, mora em outra cidade.", birthday="27/08")

    # Web watches (monitores)
    m.add_watch(u, "https://exemplo.com/promocoes", "desconto")
    m.add_watch(u, "https://exemplo.com/vagas", "estágio")

    # Health & routine (for the saúde view + dashboard card)
    for dd in range(0, 10):
        day = (today - timedelta(days=dd)).isoformat()
        m.health_set(u, day, "water", (dd % 4) + 5)
        m.health_set(u, day, "sleep", round(6.5 + (dd % 3) * 0.5, 1))
        m.health_set(u, day, "mood", ["ótimo", "bem", "ok"][dd % 3])

    # Vault documents (cofre) — tiny fake blobs, clearly demo
    m.add_document(u, "Contrato de aluguel.pdf", "application/pdf",
                   b"%PDF-1.4 demo", "Contrato de aluguel — demonstração.")
    m.add_document(u, "RG digitalizado.png", "image/png",
                   b"\x89PNG\r\n\x1a\n demo", "Documento de identidade (demo).")
    m.add_document(u, "Comprovante.pdf", "application/pdf",
                   b"%PDF-1.4 demo", "Comprovante de pagamento (demo).")

    # --- Data for the NEW charts (interactions, provider usage, activity,
    #     tasks created-vs-done, memory growth). Backdated via direct SQL so
    #     the time-series read realistically in the screenshot. ---
    def _ts(days_ago, hour=10, minute=0):
        d = today - timedelta(days=days_ago)
        return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"

    # Interactions: a two-week chat rhythm (you <-> E.V.)
    _pairs = [
        ("Bom dia, E.V.", "Bom dia! Pronto pra mais um dia produtivo?"),
        ("Quais minhas tarefas de hoje?", "Você tem 6 tarefas — quer que eu priorize?"),
        ("Adiciona um lembrete pra ligar pra operadora", "Feito! Lembrete criado."),
        ("Quanto gastei esse mês?", "Até agora R$ 702,20 — maior categoria: casa."),
        ("Resume meu dia", "Você concluiu 3 tarefas e bateu todos os hábitos."),
    ]
    for dd in range(14, -1, -1):
        for k in range((dd % 3) + 1):
            q, a = _pairs[(dd + k) % len(_pairs)]
            m._conn.execute(
                "INSERT INTO messages (user_id, role, content, created) VALUES (?,?,?,?)",
                (u, "user", q, _ts(dd, 9 + k * 3)))
            m._conn.execute(
                "INSERT INTO messages (user_id, role, content, created) VALUES (?,?,?,?)",
                (u, "model", a, _ts(dd, 9 + k * 3, 2)))

    # Provider usage over the period (Gemini primary; others as fallback)
    for dd in range(14, -1, -1):
        day = (today - timedelta(days=dd)).isoformat()
        for _ in range((dd % 3) + 3):
            m.bump_usage("gemini", day)
        if dd % 2 == 0:
            m.bump_usage("groq", day)
        if dd % 5 == 0:
            m.bump_usage("openrouter", day)
        if dd % 7 == 0:
            m.bump_usage("ollama", day)

    # Activity log — varied action types (counts drive the "por tipo" chart)
    for action, label, n in [
        ("task.done", "tarefa concluída", 9), ("expense.new", "gasto registrado", 7),
        ("habit.done", "hábito marcado", 12), ("reminder.new", "lembrete criado", 5),
        ("journal.new", "entrada no diário", 3), ("fact.new", "memória salva", 4),
        ("link.new", "link salvo", 2),
    ]:
        for _ in range(n):
            m.log_activity(u, action, label)

    # Memory growth: extra facts backdated across the period
    for fact in [
        "Trabalho melhor de manhã cedo.", "Prefiro reuniões curtas.",
        "Meta: economizar para a viagem.", "Gosto de chá verde à tarde.",
        "Quero aprender a tocar violão.", "Assisto documentários aos domingos.",
    ]:
        m.add_fact(u, fact)
    _fids = [r[0] for r in m._conn.execute(
        "SELECT id FROM facts WHERE user_id=? ORDER BY id DESC LIMIT 6", (u,)).fetchall()]
    for offset, fid in zip([1, 3, 6, 9, 11, 13], _fids):
        m._conn.execute("UPDATE facts SET created=? WHERE id=?", (_ts(offset), fid))

    # Mark some tasks completed across recent days (created-vs-done chart)
    _tids = [r[0] for r in m._conn.execute(
        "SELECT id FROM tasks WHERE user_id=? ORDER BY id LIMIT 4", (u,)).fetchall()]
    for i, tid in enumerate(_tids):
        m._conn.execute("UPDATE tasks SET done=1, done_at=? WHERE id=?",
                        (_ts(i * 2 + 1, 17), tid))

    m._conn.commit()


# --- Stub brain (no network) ---------------------------------------------
class _StubBrain:
    """Minimal brain so the web app boots without any API keys or network.

    Mirrors the surface the web routes touch (see tests/test_web.py)."""

    def __init__(self):
        self.last = None

    async def respond(self, owner, conv_id=None, text=None, image=None, image_mime=None):
        self.last = (owner, conv_id, text)
        if image:
            return "Recebi a imagem (demo)."
        return f"Claro! Aqui está o que encontrei sobre: {text}"

    def current_model(self):
        return "gemini-flash-latest"

    async def ask(self, system, prompt):
        return "Resposta de demonstração."

    async def transcribe(self, audio, mime):
        return "texto transcrito (demo)"

    def pop_documents(self):
        return []

    def pop_actions(self):
        return []


# --- Server ---------------------------------------------------------------
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(host: str, port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"web server did not come up on {host}:{port}")


def start_server(port: int):
    """Boot create_app(cfg, brain=stub) under uvicorn in a daemon thread."""
    import uvicorn
    from ev.config import Config
    from ev.interfaces.web import create_app

    cfg = Config.load(require_telegram=False)
    app = create_app(cfg, brain=_StubBrain())
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    _wait_port("127.0.0.1", port)
    return server


# --- Verification ---------------------------------------------------------
def _is_faithful(png: bytes) -> tuple[bool, str]:
    """A screenshot is kept only if it is reasonably large AND not a flat color."""
    if len(png) < 15_000:
        return False, f"too small ({len(png)//1024} KB)"
    try:
        import io
        from PIL import Image

        im = Image.open(io.BytesIO(png)).convert("RGB")
        small = im.resize((80, 50))
        px = list(small.getdata())
        r = [p[0] for p in px]; g = [p[1] for p in px]; b = [p[2] for p in px]

        def stdev(xs):
            mean = sum(xs) / len(xs)
            return (sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5

        spread = stdev(r) + stdev(g) + stdev(b)
        if spread < 8.0:
            return False, f"looks flat (variance {spread:.1f})"
    except Exception as e:  # PIL missing / decode error -> fall back to size only
        return True, f"size ok ({len(png)//1024} KB, no pixel check: {e})"
    return True, f"ok ({len(png)//1024} KB)"


# --- Capture --------------------------------------------------------------
def capture(port: int, names: list[str], headed: bool) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    base = f"http://127.0.0.1:{port}/"
    results: dict[str, str] = {}
    _SHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport=VIEWPORT, device_scale_factor=1,
        )
        # Log in silently + skip the one-time welcome overlay, before page JS runs.
        context.add_init_script(
            f"try{{localStorage.setItem('ev_token','{TOKEN}');"
            "sessionStorage.setItem('ev_welcomed','1');}catch(e){}"
        )
        page = context.new_page()
        # No networkidle: the app opens a long-lived SSE stream + polling, so
        # the network never goes idle. Wait on app-boot signals instead.
        page.goto(base, wait_until="domcontentloaded")
        # Wait until the app has booted past the login gate.
        page.wait_for_function(
            "() => typeof switchView === 'function' && "
            "!document.querySelector('#login').classList.contains('on')",
            timeout=15000,
        )
        page.wait_for_timeout(600)

        for name in names:
            view = SCREENS[name]
            try:
                if view == "__none__":
                    results[name] = "skipped (no dedicated view in current UI)"
                    continue
                _navigate(page, name, view)
                # graf scrolls internally and is expanded in _navigate, so grab
                # the whole page to include every chart.
                png = page.screenshot(type="png", full_page=(name == "graf"))
                ok, note = _is_faithful(png)
                if ok:
                    (_SHOTS / f"{name}.png").write_bytes(png)
                    results[name] = f"regenerated — {note}"
                else:
                    results[name] = f"DISCARDED, left unchanged — {note}"
            except Exception as e:
                results[name] = f"ERROR, left unchanged — {e}"
            # Reset any special state (serious mode) before the next screen.
            try:
                page.evaluate("() => { if (typeof applySerious==='function') applySerious(false); "
                              "if (typeof applyBnd==='function') applyBnd(false); "
                              "document.querySelectorAll('.eterm').forEach(w=>w.remove()); }")
            except Exception:
                pass

        browser.close()
    return results


def _navigate(page, name: str, view: str) -> None:
    if view == "__terminal__":
        page.evaluate("() => switchView('chat')")
        page.wait_for_timeout(300)
        page.evaluate("() => openTerminal()")
        page.wait_for_selector(".eterm", timeout=5000)
        # Type a friendly prompt so the terminal shows a real exchange.
        page.fill(".eterm input", "Resuma minhas tarefas de hoje")
        page.press(".eterm input", "Enter")
        page.wait_for_timeout(1500)
        return
    if view == "__serious__":
        page.evaluate("() => switchView('inicio')")
        page.wait_for_timeout(900)
        page.evaluate("() => applySerious(true, false)")
        page.wait_for_timeout(1200)   # let the tint/sweep settle
        return
    if view == "__bnd__":
        page.evaluate("() => switchView('inicio')")
        page.wait_for_timeout(900)
        page.evaluate("() => applyBnd(true)")
        page.wait_for_timeout(1000)   # let the blue theme settle
        return
    if view == "graf":
        page.evaluate("() => switchView('graf')")
        page.wait_for_timeout(1800)   # let Chart.js draw all charts
        # #chartsview scrolls internally; expand it (and unclip parents) so a
        # full-page screenshot captures every chart, not just the first ones.
        page.evaluate("""() => {
          const cv = document.getElementById('chartsview');
          if (cv) { cv.style.height='auto'; cv.style.maxHeight='none'; cv.style.overflow='visible'; }
          for (const id of ['center','app']) {
            const el = document.getElementById(id);
            if (el) { el.style.height='auto'; el.style.overflow='visible'; }
          }
          document.body.style.height='auto'; document.body.style.overflow='visible';
          document.documentElement.style.height='auto';
        }""")
        page.wait_for_timeout(500)
        return
    page.evaluate(f"() => switchView('{view}')")
    # brain renders on canvas with animations; give it extra settle time.
    page.wait_for_timeout(1800 if view in ("brain", "map") else 1000)


# --- CLI ------------------------------------------------------------------
def _safety_check() -> None:
    from ev.config import Config
    cfg = Config.load(require_telegram=False)
    resolved = Path(cfg.db_path).resolve()
    if not str(resolved).startswith(str(_ROOT)):
        sys.exit(
            f"ABORT: resolved db_path {resolved} is OUTSIDE this checkout "
            f"({_ROOT}). Refusing to run to avoid touching real data."
        )
    real = Path("/Users/ryan.rodrigues/ev/ev_memory.db")
    if resolved == real.resolve() if real.exists() else False:
        sys.exit("ABORT: db_path points at the real user DB. Refusing to run.")
    print(f"[safe] demo DB -> {resolved}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Seed demo data + capture E.V. web screenshots into docs/screenshots/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Screens: " + ", ".join(SCREENS),
    )
    ap.add_argument("--only", default="",
                    help="comma-separated subset of screen names to capture")
    ap.add_argument("--include-external", action="store_true",
                    help="also try clima/cal/map/musica (need external keys; may be discarded)")
    ap.add_argument("--keep-db", action="store_true",
                    help="keep the seeded demo DB instead of deleting it afterwards")
    ap.add_argument("--headed", action="store_true",
                    help="run the browser visibly (debugging)")
    ap.add_argument("--port", type=int, default=0, help="web port (default: a free one)")
    args = ap.parse_args()

    _safety_check()

    # Fresh demo DB every run (unless keeping a previous one).
    if not args.keep_db:
        _rm_demo_db()
    print("[seed] inserting fictional demo data …")
    seed_demo(_DEMO_DB)

    # Which screens?
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
        bad = [n for n in names if n not in SCREENS]
        if bad:
            sys.exit(f"unknown screen(s): {', '.join(bad)}")
    else:
        names = [n for n in SCREENS if n not in NO_VIEW
                 and (args.include_external or n not in EXTERNAL)]

    port = args.port or _free_port()
    print(f"[web] booting app on 127.0.0.1:{port} …")
    start_server(port)

    print(f"[shots] capturing {len(names)} screen(s) …")
    results = capture(port, names, args.headed)

    print("\n=== coverage ===")
    for name in SCREENS:
        if name in results:
            print(f"  {name:<14} {results[name]}")
        elif name in NO_VIEW:
            print(f"  {name:<14} skipped (no dedicated view; left unchanged)")
        elif name in EXTERNAL:
            print(f"  {name:<14} skipped (external API; use --include-external)")

    if not args.keep_db:
        _rm_demo_db()
        print("\n[clean] removed demo DB")
    print("done.")


if __name__ == "__main__":
    main()
