"""Health & diagnostics — a self-check E.V. can report on demand (/status).

Pure, testable helpers for system/resource state and which API keys are
configured. Live provider pings (that hit the network) live in the brain.
"""

from __future__ import annotations

import os
import shutil


def _meminfo() -> dict:
    """Linux memory usage from /proc/meminfo (empty dict elsewhere, e.g. macOS)."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])  # kB
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        if not total:
            return {}
        used = total - avail
        return {
            "mem_total_mb": round(total / 1024),
            "mem_used_mb": round(used / 1024),
            "mem_used_pct": round(used / total * 100),
        }
    except Exception:
        return {}


def system_report(config, memory) -> dict:
    """Snapshot of the bot's system state (DB, disk, memory, load)."""
    rep: dict = {}

    # Database reachable + size.
    try:
        p = config.db_path
        rep["db_ok"] = bool(p.exists())
        rep["db_size_mb"] = round(p.stat().st_size / 1e6, 2) if p.exists() else 0.0
        # A trivial query to confirm it actually opens.
        memory.get_setting("__healthcheck__")
        rep["db_query_ok"] = True
    except Exception:
        rep["db_ok"] = rep.get("db_ok", False)
        rep["db_query_ok"] = False

    # Disk on the volume that holds the DB.
    try:
        du = shutil.disk_usage(str(config.db_path.parent))
        rep["disk_free_gb"] = round(du.free / 1e9, 2)
        rep["disk_total_gb"] = round(du.total / 1e9, 2)
        rep["disk_used_pct"] = round(du.used / du.total * 100)
    except Exception:
        pass

    mem = _meminfo()
    if mem:
        rep.update(mem)

    try:
        rep["load1"] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass

    return rep


def keys_status(config) -> list[dict]:
    """Which API keys/integrations are configured. Returns [{name, ok, note}]."""
    def item(name, ok, note=""):
        return {"name": name, "ok": bool(ok), "note": note}

    google_ok = False
    try:
        google_ok = config.google_ready() and config.google_authorized()
    except Exception:
        google_ok = False

    return [
        item("Telegram", getattr(config, "telegram_token", "")),
        item("Gemini (principal)", config.gemini_api_key),
        item("Groq (fallback + voz→texto)", config.groq_api_key),
        item("OpenRouter (fallback)", config.openrouter_api_key),
        item("Tavily (busca web)", config.tavily_api_key,
             "" if config.tavily_api_key else "opcional"),
        item("Ollama (local)", config.ollama_enabled,
             "ligado" if config.ollama_enabled else "desligado"),
        item("Google (agenda/e-mail)", google_ok,
             "" if google_ok else "não autorizado — rode authorize_google.py"),
    ]
