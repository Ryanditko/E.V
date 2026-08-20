#!/usr/bin/env python3
"""Runtime QA for E.V.'s web console — opens every view in a headless browser,
in BOTH languages, and fails if any screen throws a JavaScript error.

Why this exists: the unit tests don't execute the page's JavaScript, so a
runtime bug (e.g. an i18n `t('key')` call inside a scope that shadows the
global `t`, which blanked the Health/Activity screens) can pass tests yet break
real screens. This script drives the actual app in Chromium, switches through
every view under `en` and `pt`, and reports/【fails on】 any console error or
uncaught exception (especially `is not a function`).

It reuses the screenshot harness (`tools/screenshots.py`) for the DB-safe demo
seed + in-process app boot, so it never touches the owner's real `ev_memory.db`.

Usage
-----
    python tools/audit_views.py            # audit all views in en + pt
    python tools/audit_views.py --lang en  # a single language
    python tools/audit_views.py --headed   # watch the browser (debugging)

Exit code is non-zero if any view logged a JS error — suitable for CI.
Requires the project venv and a one-time `python -m playwright install chromium`.
"""

from __future__ import annotations

import argparse
import sys

from screenshots import (  # sibling module in tools/
    SCREENS,
    TOKEN,
    _DEMO_DB,
    _free_port,
    _rm_demo_db,
    seed_demo,
    start_server,
)


# Environment noise unrelated to the app's view code (headless Chromium has no
# DRM/EME; a couple of background polls 400 with the demo stub). These are not
# view render bugs, so they don't fail the audit.
_BENIGN = (
    "No supported keysystem",
    "Failed to load resource",
)


def _is_benign(msg: str) -> bool:
    return any(b in msg for b in _BENIGN)


def _views() -> list[str]:
    """The real switchView() keys (skip capture-only specials like __serious__)."""
    seen: dict[str, None] = {}
    for v in SCREENS.values():
        if not v.startswith("__"):
            seen.setdefault(v, None)
    return list(seen)


def audit(langs: list[str], headed: bool) -> int:
    from playwright.sync_api import sync_playwright

    # Safety: this seeds + deletes a demo DB at the checkout root. Never do that
    # on top of an existing (possibly real) ev_memory.db — run in a clean
    # checkout or a git worktree where no DB exists yet.
    if _DEMO_DB.exists():
        sys.exit(f"Refusing to run: {_DEMO_DB} already exists. Run this in a clean "
                 "checkout/worktree (it creates and deletes a disposable demo DB).")

    _rm_demo_db()
    seed_demo(_DEMO_DB)
    port = _free_port()
    start_server(port)
    base = f"http://127.0.0.1:{port}/"

    errors: list[tuple[str, str, str]] = []
    cur = {"label": "boot"}
    views = _views()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(
            f"try{{localStorage.setItem('ev_token','{TOKEN}');"
            "sessionStorage.setItem('ev_welcomed','1');}catch(e){}"
        )
        page = ctx.new_page()
        def _pageerr(e):
            if not _is_benign(str(e)):
                errors.append((cur["label"], "pageerror", str(e)[:200]))

        def _console(m):
            if m.type == "error" and not _is_benign(m.text or ""):
                errors.append((cur["label"], "console", (m.text or "")[:200]))

        page.on("pageerror", _pageerr)
        page.on("console", _console)
        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_function(
            "() => typeof switchView === 'function' && "
            "!document.querySelector('#login').classList.contains('on')",
            timeout=20000,
        )
        page.wait_for_timeout(600)

        checked = 0
        for lang in langs:
            page.evaluate("(l) => window.applyLang && applyLang(l)", lang)
            page.wait_for_timeout(400)
            for v in views:
                cur["label"] = f"{lang}:{v}"
                try:
                    page.evaluate(f"() => switchView('{v}')")
                    page.wait_for_timeout(600)
                except Exception as e:  # a switch that throws is itself a failure
                    errors.append((cur["label"], "switch", str(e)[:200]))
                checked += 1
        browser.close()

    _rm_demo_db()

    print(f"[audit] {checked} view-checks across langs {langs}")
    if errors:
        print(f"[audit] FAIL — {len(errors)} JS error(s):")
        for label, kind, msg in errors:
            print(f"  {label}  [{kind}] {msg}")
        return 1
    print("[audit] OK — every view rendered clean (no console errors) in all languages.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit every web view for JS runtime errors (en + pt).")
    ap.add_argument("--lang", default="", help="only this language (en|pt); default audits both")
    ap.add_argument("--headed", action="store_true", help="show the browser (debugging)")
    args = ap.parse_args()
    langs = [args.lang] if args.lang else ["en", "pt"]
    sys.exit(audit(langs, args.headed))


if __name__ == "__main__":
    main()
