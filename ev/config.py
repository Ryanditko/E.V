"""Central configuration for E.V. — reads everything from the environment (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load the .env sitting at the project root (one level above this package).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "sim", "y"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.isdigit() else default


@dataclass(frozen=True)
class Config:
    telegram_token: str
    gemini_api_key: str
    model: str
    # Fallbacks (optional) — empty = provider disabled
    groq_api_key: str
    groq_model: str
    groq_whisper_model: str
    openrouter_api_key: str
    openrouter_model: str
    owner_id: int | None
    voice_reply: bool
    voice: str
    voice_rate: str
    voice_pitch: str
    # Local model (Ollama) — never-runs-out safety net
    ollama_enabled: bool
    ollama_base_url: str
    ollama_model: str
    ollama_embed_model: str
    # Memory & reminders
    embed_backend: str  # "gemini" or "ollama"
    embed_model: str
    timezone: str
    reminder_poll_seconds: int
    briefing_hour: int  # local hour for the daily briefing; <0 disables
    # Tools
    websearch_enabled: bool
    google_oauth_client: str
    google_token_path: Path
    db_path: Path

    # Telegram token is only required for the Telegram interface. The terminal
    # interface can run without it (passes require_telegram=False).
    @classmethod
    def load(cls, *, require_telegram: bool = True) -> "Config":
        telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

        required = [("GEMINI_API_KEY", gemini_api_key)]
        if require_telegram:
            required.append(("TELEGRAM_TOKEN", telegram_token))
        missing = [name for name, value in required if not value]
        if missing:
            raise SystemExit(
                "Missing variables in .env: "
                + ", ".join(missing)
                + "\nCopy .env.example to .env and fill it in. See the README."
            )

        owner_raw = os.getenv("EV_OWNER_ID", "").strip()
        owner_id = int(owner_raw) if owner_raw.isdigit() else None

        token_path = os.getenv("GOOGLE_TOKEN_PATH", "google_token.json").strip()

        try:
            briefing_hour = int(os.getenv("EV_BRIEFING_HOUR", "8").strip() or "-1")
        except ValueError:
            briefing_hour = 8

        return cls(
            telegram_token=telegram_token,
            gemini_api_key=gemini_api_key,
            model=os.getenv("EV_MODEL", "gemini-flash-latest").strip(),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
            groq_whisper_model=os.getenv(
                "GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"
            ).strip(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_model=os.getenv(
                "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
            ).strip(),
            ollama_enabled=_get_bool("OLLAMA_ENABLED", True),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://localhost:11434/v1"
            ).strip(),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1").strip(),
            ollama_embed_model=os.getenv(
                "OLLAMA_EMBED_MODEL", "nomic-embed-text"
            ).strip(),
            embed_backend=os.getenv("EV_EMBED_BACKEND", "gemini").strip().lower(),
            owner_id=owner_id,
            voice_reply=_get_bool("EV_VOICE_REPLY", True),
            voice=os.getenv("EV_VOICE", "pt-BR-FranciscaNeural").strip(),
            voice_rate=os.getenv("EV_VOICE_RATE", "-3%").strip(),
            voice_pitch=os.getenv("EV_VOICE_PITCH", "+12Hz").strip(),
            embed_model=os.getenv("EV_EMBED_MODEL", "gemini-embedding-001").strip(),
            timezone=os.getenv("EV_TIMEZONE", "America/Sao_Paulo").strip(),
            reminder_poll_seconds=_get_int("EV_REMINDER_POLL_SECONDS", 30),
            briefing_hour=briefing_hour,
            websearch_enabled=_get_bool("EV_WEBSEARCH_ENABLED", True),
            google_oauth_client=os.getenv("GOOGLE_OAUTH_CLIENT", "").strip(),
            google_token_path=(_PROJECT_ROOT / token_path),
            db_path=_PROJECT_ROOT / "ev_memory.db",
        )
