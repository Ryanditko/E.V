"""Local execution agent for E.V. — runs on YOUR OWN computer, not on the
server. It polls E.V. (over your Tailscale network) for tasks that you have
already approved (via the web console or the Telegram fallback) and executes
them locally, then reports the result back.

It NEVER runs anything by itself: the server only ever hands out tasks whose
status is already 'approved', and a human always made that call first.

Usage:
    python3 local_agent.py

Requires EV_WEB_BASE_URL and EV_WEB_TOKEN in the .env at the project root
(the same ones the web console uses).
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


def execute(task: dict) -> tuple[bool, str]:
    kind = task["kind"]
    command = (task.get("payload") or {}).get("command", "")
    if kind == "shell":
        return _run_shell(command)
    if kind in ("open", "browser"):
        return _run_open(command)
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
