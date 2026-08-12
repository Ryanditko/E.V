"""Local execution agent for E.V. — runs on YOUR OWN computer, not on the
server. It polls E.V. (over your Tailscale network) for tasks that you have
already approved (via the web console or the Telegram fallback) and executes
them locally, then reports the result back.

It NEVER runs anything by itself: the server only ever hands out tasks whose
status is already 'approved', and a human always made that call first. For
'browser' tasks it goes further: it drives a real, autonomous browsing agent
(goal in, LLM decides each click/type step via the server), but before any
step the model or the risk classifier flags as risky (sending a message,
posting, following, deleting...) it PAUSES and asks for a SECOND, separate
confirmation (console or Telegram) before actually doing it.

Usage:
    python3 local_agent.py

Requires EV_WEB_BASE_URL and EV_WEB_TOKEN in the .env at the project root
(the same ones the web console uses). For 'browser' tasks you also need:
    pip install playwright && playwright install chromium
The first time you use a browser task against a site that needs login
(WhatsApp Web, Instagram...), a real Chrome window opens — log in there once;
the session persists in .browser_profile/ (gitignored) for next time.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

BASE_URL = os.getenv("EV_WEB_BASE_URL", "").strip().rstrip("/")
TOKEN = os.getenv("EV_WEB_TOKEN", "").strip()
POLL_SECONDS = 5
SHELL_TIMEOUT = 120
BROWSER_PROFILE_DIR = _PROJECT_ROOT / ".browser_profile"
MAX_BROWSER_STEPS = 12
CONFIRM_TIMEOUT_SECONDS = 300
CONFIRM_POLL_SECONDS = 5


def _headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _claim() -> dict | None:
    r = requests.get(f"{BASE_URL}/api/local-tasks/claim", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json().get("task")


def _report(task_id: int, ok: bool, output: str) -> None:
    requests.post(
        f"{BASE_URL}/api/local-tasks/result",
        headers=_headers(),
        json={"id": task_id, "ok": ok, "output": {"output": output[:4000]}},
        timeout=15,
    )


def _resolve_script(name: str) -> str | None:
    r = requests.get(f"{BASE_URL}/api/local-scripts", headers=_headers(), timeout=15)
    r.raise_for_status()
    for s in r.json().get("items", []):
        if s["name"].strip().lower() == name.strip().lower():
            return s["command"]
    return None


def _run_shell(command: str) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=SHELL_TIMEOUT,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out or f"(sem saída, código {p.returncode})"
    except subprocess.TimeoutExpired:
        return False, f"comando excedeu {SHELL_TIMEOUT}s e foi cancelado"
    except Exception as exc:
        return False, f"erro ao executar: {exc}"


def _run_open(target: str) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "abrir app/arquivo/URL só está implementado no macOS por enquanto"
    try:
        p = subprocess.run(["open", target], capture_output=True, text=True, timeout=15)
        return p.returncode == 0, p.stderr or "aberto"
    except Exception as exc:
        return False, f"erro ao abrir: {exc}"


def _decide_next_action(goal: str, url: str, page_text: str, history: list,
                         high_risk: bool) -> dict:
    r = requests.post(
        f"{BASE_URL}/api/local-tasks/decide",
        headers=_headers(),
        json={
            "goal": goal, "url": url, "page_text": page_text,
            "history": history[-8:], "high_risk": high_risk,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("action") or {"action": "done", "value": "sem resposta do servidor"}


def _request_risky_confirmation(task_id: int, label: str) -> bool:
    """Pauses execution to ask for a SEPARATE, second approval before a risky
    step (send/post/follow/delete). Times out to 'refused' — never assumes
    consent when the user hasn't actively responded."""
    r = requests.post(
        f"{BASE_URL}/api/local-tasks/confirms", headers=_headers(),
        json={"task_id": task_id, "label": label[:200]}, timeout=15,
    )
    r.raise_for_status()
    cid = r.json().get("id")
    print(f"  ⚠️  ação de alto risco pausada, aguardando confirmação: {label}")
    deadline = CONFIRM_TIMEOUT_SECONDS
    while deadline > 0:
        time.sleep(CONFIRM_POLL_SECONDS)
        deadline -= CONFIRM_POLL_SECONDS
        r2 = requests.get(
            f"{BASE_URL}/api/local-tasks/confirms/status",
            headers=_headers(), params={"id": cid}, timeout=15,
        )
        status = r2.json().get("status")
        if status == "approved":
            return True
        if status == "rejected":
            return False
    return False  # timed out with no explicit answer -> treat as refused


def _apply_browser_action(page, action: str, value: str) -> None:
    if action == "goto":
        page.goto(value, wait_until="load", timeout=30000)
    elif action == "click_text":
        page.get_by_text(value, exact=False).first.click(timeout=10000)
    elif action == "type_text":
        page.keyboard.type(value)
    elif action == "press_enter":
        page.keyboard.press("Enter")
    elif action == "scroll":
        page.mouse.wheel(0, 1500)
    # 'read_more' and unknown actions: no-op, just re-observe the page.


def _page_text(page) -> str:
    try:
        return page.inner_text("body")[:6000]
    except Exception:
        return ""


def _run_browser(task: dict) -> tuple[bool, str]:
    goal = (task.get("payload") or {}).get("command", "")
    if not goal:
        return False, "tarefa de navegador sem objetivo (comando vazio)"
    high_risk = task.get("risk") == "high"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, (
            "playwright não instalado no executor local — rode "
            "'pip install playwright && playwright install chromium'"
        )
    history: list = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(BROWSER_PROFILE_DIR), headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            for step in range(MAX_BROWSER_STEPS):
                decision = _decide_next_action(
                    goal, page.url, _page_text(page), history, high_risk)
                action = decision.get("action") or "done"
                value = decision.get("value") or ""
                note = decision.get("note") or ""
                risky = bool(decision.get("risky")) or (
                    high_risk and action in ("click_text", "press_enter", "type_text"))
                print(f"  [{step + 1}/{MAX_BROWSER_STEPS}] {action}: {note or value[:80]}")
                history.append({"action": action, "value": value, "note": note})
                if action == "done":
                    return True, value or note or "objetivo concluído"
                if risky and not _request_risky_confirmation(
                    task["id"], note or f"{action}: {value}"[:200]
                ):
                    return False, "usuário recusou a confirmação de segurança da ação de alto risco"
                _apply_browser_action(page, action, value)
                time.sleep(1)
            return False, f"atingiu o limite de {MAX_BROWSER_STEPS} passos sem concluir"
        finally:
            ctx.close()


def execute(task: dict) -> tuple[bool, str]:
    kind = task["kind"]
    command = (task.get("payload") or {}).get("command", "")
    if kind == "shell":
        return _run_shell(command)
    if kind == "open":
        return _run_open(command)
    if kind == "browser":
        return _run_browser(task)
    if kind == "script":
        resolved = _resolve_script(command)
        if not resolved:
            return False, f"nenhum script cadastrado chamado '{command}'"
        return _run_shell(resolved)
    return False, f"tipo de tarefa desconhecido: {kind}"


def main() -> None:
    if not BASE_URL or not TOKEN:
        print("EV_WEB_BASE_URL e EV_WEB_TOKEN precisam estar no .env")
        sys.exit(1)
    print(f"Executor local da E.V. rodando — apontando pra {BASE_URL}")
    while True:
        try:
            task = _claim()
            if task:
                print(f"Executando tarefa #{task['id']}: [{task['kind']}] {task['label']}")
                ok, output = execute(task)
                _report(task["id"], ok, output)
                print(f"  -> {'ok' if ok else 'falhou'}: {output[:200]}")
        except requests.RequestException as exc:
            print(f"erro de rede, tentando de novo: {exc}")
        except Exception as exc:
            print(f"erro inesperado: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
