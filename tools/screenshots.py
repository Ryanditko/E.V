#!/usr/bin/env python3
"""Reusable screenshot harness for E.V.'s web console.

Seeds a fresh, disposable SQLite DB with fictional English demo data, boots the
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

# Phone viewport for the mobile screenshot set (docs/screenshots/mobile/). The
# app's responsive layout kicks in at <=980px (see `mob()` in the frontend), so
# this triggers the mobile chrome / bottom-sheet nav. Retina scale for crisp PNGs.
MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_SCALE = 3
# The subset the README's "On your phone" section references, by filename.
MOBILE_SCREENS = ["dashboard", "chat", "tasks", "expenses", "map", "musica"]


# --- Demo data ------------------------------------------------------------
def seed_demo(db_path: Path) -> None:
    """Insert fictional English demo data across every local domain."""
    from ev.core.memory import Memory

    m = Memory(db_path)
    u = OWNER
    today = date.today()

    def iso(days_ago=0, hour=9, minute=0):
        d = datetime.now() + timedelta(days=days_ago)
        return d.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

    # Tasks (a few categories, one recurring)
    m.add_task(u, "Study calculus — chapter 4", "college")
    m.add_task(u, "Buy Ana's gift", "personal")
    m.add_task(u, "Review project report", "work")
    m.add_task(u, "Strength training", "health", recur="daily", due=iso(0, 18))
    m.add_task(u, "Pay electricity bill", "home")
    m.add_task(u, "Read 10 pages", "personal", recur="daily")

    # Reminders (future-dated)
    m.add_reminder(u, "Dentist appointment", iso(2, 14, 30))
    m.add_reminder(u, "Call the phone carrier", iso(1, 10))
    m.add_reminder(u, "Back up the computer", iso(5, 21), recur="weekly")
    m.add_reminder(u, "Alignment meeting", iso(0, 16))

    # Habits with a spread of daily logs (for the heatmap/streak)
    for hname, done_days in [
        ("Drink 2L of water", range(0, 12)),
        ("Meditate 10 min", [0, 1, 2, 4, 5, 7, 8]),
        ("Read before bed", [0, 1, 3, 4, 6, 9, 10]),
        ("Walk 30 min", [0, 2, 3, 5, 6, 8]),
    ]:
        hid = m.add_habit(u, hname)
        for dd in done_days:
            m.log_habit(hid, (today - timedelta(days=dd)).isoformat())

    # Journal
    m.add_journal(u, "Productive day — finished the report and still trained. "
                     "Tomorrow I focus on studying.")
    m.add_journal(u, "A little tired today, but kept up the habits. "
                     "Managed to read before bed.")
    m.add_journal(u, "Great chat with Ana about the end-of-year trip.")

    # Expenses (spread across categories and recent days)
    expenses = [
        (87.90, "Groceries", "food"), (32.50, "Lunch at work", "food"),
        (19.90, "Afternoon coffee", "food"), (120.00, "Pharmacy", "health"),
        (54.00, "Ride share", "transport"), (39.90, "New book", "leisure"),
        (210.00, "Electricity bill", "home"), (45.00, "Movies with friends", "leisure"),
        (28.00, "Bakery", "food"), (65.00, "Gift", "personal"),
    ]
    for amt, desc, cat in expenses:
        m.add_expense(u, amt, desc, cat)

    # Budgets (orçamentos)
    m.set_budget(u, "food", 800.0)
    m.set_budget(u, "leisure", 300.0)
    m.set_budget(u, "transport", 250.0)
    m.set_budget(u, "home", 900.0)

    # Recurring expenses (assinaturas)
    m.add_recurring(u, 39.90, "Video streaming", "leisure", 15)
    m.add_recurring(u, 21.90, "Music streaming", "leisure", 5)
    m.add_recurring(u, 29.90, "Gym membership", "health", 10)
    m.add_recurring(u, 9.90, "Cloud storage", "work", 20)

    # Goals (metas / cofrinho)
    g1 = m.add_goal(u, "End-of-year trip", 4000.0)
    m.add_to_goal(u, g1, 1750.0)
    g2 = m.add_goal(u, "New laptop", 6000.0)
    m.add_to_goal(u, g2, 2400.0)
    g3 = m.add_goal(u, "Emergency fund", 10000.0)
    m.add_to_goal(u, g3, 6800.0)

    # Links
    for cat, name, url in [
        ("dev", "Python documentation", "https://docs.python.org"),
        ("dev", "Project repository", "https://github.com"),
        ("study", "Calculus course", "https://example.edu/calculus"),
        ("leisure", "Movie watchlist", "https://example.com/movies"),
        ("work", "Metrics dashboard", "https://example.com/metrics"),
    ]:
        m.add_link(u, cat, name, url)

    # Knowledge base (notes/chunks) — no embeddings needed for the list view
    for src, chunk in [
        ("Calculus notes.pdf", "Chain rule and derivatives of composite functions."),
        ("Calculus notes.pdf", "Integration by parts and substitution."),
        ("Project summary.md", "Objectives, scope and timeline for the quarter."),
        ("Favorite recipes.txt", "Garlic and olive oil pasta, carrot cake."),
    ]:
        m.add_chunk(u, src, chunk, None)
        m.save_kb_file(u, src, src, "application/octet-stream", chunk.encode("utf-8"))

    # Facts / long-term memories
    for fact in [
        "I prefer coffee without sugar in the morning.",
        "I study engineering in evening classes.",
        "Ana's birthday is in December.",
        "I like to run on Saturday mornings.",
        "My goal for the year is to read 24 books.",
    ]:
        m.add_fact(u, fact)

    # People (relationships)
    m.add_person(u, "Ana", "Best friend, loves to travel.", birthday="12/12")
    m.add_person(u, "Bruno", "College classmate, study partner.", birthday="03/05")
    m.add_person(u, "Carla", "Sister, lives in another city.", birthday="27/08")

    # Web watches (monitores)
    m.add_watch(u, "https://example.com/deals", "discount")
    m.add_watch(u, "https://example.com/jobs", "internship")

    # Health & routine (for the saúde view + dashboard card)
    for dd in range(0, 10):
        day = (today - timedelta(days=dd)).isoformat()
        m.health_set(u, day, "water", (dd % 4) + 5)
        m.health_set(u, day, "sleep", round(6.5 + (dd % 3) * 0.5, 1))
        m.health_set(u, day, "mood", ["great", "good", "ok"][dd % 3])

    # Vault documents (cofre) — tiny fake blobs, clearly demo
    m.add_document(u, "Lease agreement.pdf", "application/pdf",
                   b"%PDF-1.4 demo", "Lease agreement — demonstration.")
    m.add_document(u, "Scanned ID.png", "image/png",
                   b"\x89PNG\r\n\x1a\n demo", "Identity document (demo).")
    m.add_document(u, "Receipt.pdf", "application/pdf",
                   b"%PDF-1.4 demo", "Payment receipt (demo).")

    # --- Data for the NEW charts (interactions, provider usage, activity,
    #     tasks created-vs-done, memory growth). Backdated via direct SQL so
    #     the time-series read realistically in the screenshot. ---
    def _ts(days_ago, hour=10, minute=0):
        d = today - timedelta(days=days_ago)
        return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"

    # Interactions: a two-week chat rhythm (you <-> E.V.)
    _pairs = [
        ("Good morning, E.V.", "Good morning! Ready for another productive day?"),
        ("What are my tasks today?", "You have 6 tasks — want me to prioritize them?"),
        ("Add a reminder to call the phone carrier", "Done! Reminder created."),
        ("How much did I spend this month?", "So far $702.20 — biggest category: home."),
        ("Summarize my day", "You completed 3 tasks and hit all your habits."),
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
        ("task.done", "task completed", 9), ("expense.new", "expense logged", 7),
        ("habit.done", "habit checked", 12), ("reminder.new", "reminder created", 5),
        ("journal.new", "journal entry", 3), ("fact.new", "memory saved", 4),
        ("link.new", "link saved", 2),
    ]:
        for _ in range(n):
            m.log_activity(u, action, label)

    # Memory growth: extra facts backdated across the period
    for fact in [
        "I work best early in the morning.", "I prefer short meetings.",
        "Goal: save up for the trip.", "I like green tea in the afternoon.",
        "I want to learn to play guitar.", "I watch documentaries on Sundays.",
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
            return "Got the image (demo)."
        return f"Sure! Here is what I found about: {text}"

    def current_model(self):
        return "gemini-flash-latest"

    async def ask(self, system, prompt):
        return "Demonstration response."

    async def transcribe(self, audio, mime):
        return "transcribed text (demo)"

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


# --- Phone mockup frame ---------------------------------------------------
def _frame_phone(png: bytes) -> bytes:
    """Composite a raw viewport screenshot into a tasteful dark phone mockup.

    Draws a rounded dark bezel around the captured screen, an iOS-style status
    bar (``9:41`` on the left; signal/wifi/battery on the right), a centered
    notch/pill and a bottom home-indicator bar. Mirrors the device-framed look
    the old mobile screenshots had before ``--mobile`` captured a raw viewport.
    Falls back to the raw PNG if PIL is unavailable.
    """
    try:
        import io

        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return png

    content = Image.open(io.BytesIO(png)).convert("RGB")
    cw, ch = content.size

    # Geometry (px; the input is already retina-scaled so use generous sizes).
    side = 18          # left/right bezel
    top = 96           # top bezel — holds the status bar + notch
    bottom = 78        # bottom bezel — holds the home indicator
    margin = 44        # page padding around the phone body
    body_r = 118       # outer body corner radius
    screen_r = 78      # inner screen corner radius

    page_bg = (6, 7, 9)
    body_bg = (13, 14, 17)
    fg = (236, 237, 242)

    body_w, body_h = cw + side * 2, ch + top + bottom
    canvas_w, canvas_h = body_w + margin * 2, body_h + margin * 2

    canvas = Image.new("RGB", (canvas_w, canvas_h), page_bg)

    # Phone body (rounded dark rectangle) on its own RGBA layer so the rounded
    # corners let the page background show through.
    body = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle([0, 0, body_w - 1, body_h - 1], radius=body_r,
                         fill=body_bg + (255,))

    # Round the screen's corners, then paste it into the body.
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1],
                                           radius=screen_r, fill=255)
    body.paste(content, (side, top), mask)

    # Status bar text + glyphs live in the top bezel, above the screen.
    def _font(size):
        for path in ("/System/Library/Fonts/Helvetica.ttc",
                     "/System/Library/Fonts/SFNSDisplay.ttf",
                     "/Library/Fonts/Arial.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    f = _font(38)
    sb_cy = top // 2                         # vertical centre of the status bar
    # Clock (left)
    bd.text((side + 46, sb_cy), "9:41", font=f, fill=fg, anchor="lm")

    # Right side: signal bars, wifi arc, battery.
    right = body_w - side - 40
    # Battery
    bat_w, bat_h = 58, 26
    bat_x1, bat_y0 = right, sb_cy - bat_h // 2
    bat_x0 = bat_x1 - bat_w
    bd.rounded_rectangle([bat_x0, bat_y0, bat_x1, bat_y0 + bat_h], radius=7,
                         outline=fg, width=3)
    bd.rounded_rectangle([bat_x1 + 3, sb_cy - 7, bat_x1 + 8, sb_cy + 7],
                         radius=2, fill=fg)
    bd.rounded_rectangle([bat_x0 + 4, bat_y0 + 4, bat_x0 + 4 + int((bat_w - 8) * 0.8),
                          bat_y0 + bat_h - 4], radius=4, fill=fg)
    # Wifi (three stacked arcs approximated with an arc glyph)
    wf_cx = bat_x0 - 40
    for i, rr in enumerate((20, 13, 6)):
        bd.arc([wf_cx - rr, sb_cy - rr + 6, wf_cx + rr, sb_cy + rr + 6],
               start=225, end=315, fill=fg, width=3)
    bd.ellipse([wf_cx - 3, sb_cy + 4, wf_cx + 3, sb_cy + 10], fill=fg)
    # Signal bars
    sig_x = wf_cx - 74
    for i, bh in enumerate((10, 16, 22, 28)):
        bx = sig_x + i * 14
        bd.rounded_rectangle([bx, sb_cy + 14 - bh, bx + 9, sb_cy + 14],
                             radius=2, fill=fg)

    # Centered notch / dynamic-island pill, straddling the top of the screen.
    pill_w, pill_h = 320, 44
    pill_x0 = (body_w - pill_w) // 2
    pill_y0 = top - pill_h // 2 - 6
    bd.rounded_rectangle([pill_x0, pill_y0, pill_x0 + pill_w, pill_y0 + pill_h],
                         radius=pill_h // 2, fill=(0, 0, 0))

    # Home indicator bar in the bottom bezel.
    hi_w, hi_h = 300, 12
    hi_x0 = (body_w - hi_w) // 2
    hi_y0 = body_h - bottom // 2 - hi_h // 2
    bd.rounded_rectangle([hi_x0, hi_y0, hi_x0 + hi_w, hi_y0 + hi_h],
                         radius=hi_h // 2, fill=(150, 152, 160))

    canvas.paste(body, (margin, margin), body)

    out = io.BytesIO()
    canvas.save(out, format="png")
    return out.getvalue()


# --- Capture --------------------------------------------------------------
def capture(port: int, names: list[str], headed: bool, mobile: bool = False) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    base = f"http://127.0.0.1:{port}/"
    results: dict[str, str] = {}
    out_dir = (_SHOTS / "mobile") if mobile else _SHOTS
    out_dir.mkdir(parents=True, exist_ok=True)

    if mobile:
        ctx_opts = dict(viewport=MOBILE_VIEWPORT, device_scale_factor=MOBILE_SCALE,
                        is_mobile=True, has_touch=True)
    else:
        ctx_opts = dict(viewport=VIEWPORT, device_scale_factor=1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(**ctx_opts)
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
                png = page.screenshot(type="png")
                if mobile:
                    png = _frame_phone(png)
                ok, note = _is_faithful(png)
                if ok:
                    (out_dir / f"{name}.png").write_bytes(png)
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
        page.fill(".eterm input", "Summarize my tasks for today")
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
    page.evaluate(f"() => switchView('{view}')")
    # brain/graf render on canvas with animations; give them extra settle time.
    page.wait_for_timeout(1800 if view in ("brain", "graf", "map") else 1000)


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
    ap.add_argument("--mobile", action="store_true",
                    help="capture the phone-viewport set into docs/screenshots/mobile/ "
                         f"(default screens: {', '.join(MOBILE_SCREENS)})")
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
    elif args.mobile:
        # The fixed "On your phone" set. map/musica are external-API screens:
        # captured for their English chrome; discarded if they fail verification.
        names = list(MOBILE_SCREENS)
    else:
        names = [n for n in SCREENS if n not in NO_VIEW
                 and (args.include_external or n not in EXTERNAL)]

    port = args.port or _free_port()
    print(f"[web] booting app on 127.0.0.1:{port} …")
    start_server(port)

    dest = "docs/screenshots/mobile/" if args.mobile else "docs/screenshots/"
    print(f"[shots] capturing {len(names)} {'mobile ' if args.mobile else ''}screen(s) -> {dest} …")
    results = capture(port, names, args.headed, mobile=args.mobile)

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
