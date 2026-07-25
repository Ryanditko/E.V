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
    voice_fixes: tuple[tuple[str, str], ...]  # TTS-only pronunciation fixes
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
    checkin_hour: int   # local hour for a proactive check-in; <0 disables
    city: str           # for weather in the briefing (empty disables)
    news_topic: str     # topic for news in the briefing (empty disables)
    weekly_day: int     # weekday (0=Mon..6=Sun) for the weekly review; <0 disables
    weekly_hour: int    # local hour for the weekly review
    rain_hour: int      # local hour to check tomorrow's rain; <0 disables
    watch_poll_minutes: int  # how often to check web monitors
    telegram_backup: bool    # send DB backup to the owner via Telegram
    message_history_keep: int  # keep only the newest N chat messages per user
    habit_nudge_hour: int    # local hour to nudge about unmarked habits; <0 disables
    monthly_report_day: int  # day of month for the financial report; <0 disables
    monthly_report_hour: int
    # Tools
    websearch_enabled: bool
    brave_api_key: str   # optional: better web search than DuckDuckGo
    tavily_api_key: str  # optional: AI-focused web search (preferred if set)
    google_oauth_client: str
    google_accounts: tuple[str, ...]  # e.g. ("pessoal", "faculdade")
    web_token: str      # bearer token for the web interface (empty disables it)
    web_host: str       # host to bind the web server
    web_port: int       # port for the web server
    db_path: Path

    @property
    def default_account(self) -> str:
        return self.google_accounts[0] if self.google_accounts else ""

    def token_path_for(self, account: str) -> Path:
        """Per-account OAuth token file (one Google project, many accounts)."""
        return self.db_path.parent / f"google_token_{account}.json"

    def google_ready(self) -> bool:
        return bool(self.google_oauth_client and self.google_accounts)

    def google_authorized(self, account: str | None = None) -> bool:
        """True only if an OAuth token already exists for the account (i.e. the
        one-time browser authorization was done). Prevents headless servers from
        trying to open a browser on every call."""
        acc = account or self.default_account
        return bool(acc) and self.token_path_for(acc).exists()

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

        accounts_raw = os.getenv("EV_GOOGLE_ACCOUNTS", "pessoal")
        google_accounts = tuple(
            a.strip() for a in accounts_raw.split(",") if a.strip()
        )

        try:
            briefing_hour = int(os.getenv("EV_BRIEFING_HOUR", "8").strip() or "-1")
        except ValueError:
            briefing_hour = 8
        try:
            checkin_hour = int(os.getenv("EV_CHECKIN_HOUR", "").strip() or "-1")
        except ValueError:
            checkin_hour = -1
        try:
            rain_hour = int(os.getenv("EV_RAIN_HOUR", "21").strip() or "-1")
        except ValueError:
            rain_hour = -1
        try:
            weekly_day = int(os.getenv("EV_WEEKLY_DAY", "6").strip() or "-1")
        except ValueError:
            weekly_day = 6
        try:
            habit_nudge_hour = int(os.getenv("EV_HABIT_NUDGE_HOUR", "20").strip() or "-1")
        except ValueError:
            habit_nudge_hour = 20
        try:
            monthly_report_day = int(os.getenv("EV_MONTHLY_REPORT_DAY", "1").strip() or "-1")
        except ValueError:
            monthly_report_day = 1

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
            voice_rate=os.getenv("EV_VOICE_RATE", "+0%").strip(),
            voice_pitch=os.getenv("EV_VOICE_PITCH", "+0Hz").strip(),
            voice_fixes=tuple(
                tuple(p.split("=", 1))  # type: ignore[misc]
                for p in os.getenv("EV_VOICE_FIXES", "").split(";")
                if "=" in p
            ),
            embed_model=os.getenv("EV_EMBED_MODEL", "gemini-embedding-001").strip(),
            timezone=os.getenv("EV_TIMEZONE", "America/Sao_Paulo").strip(),
            reminder_poll_seconds=_get_int("EV_REMINDER_POLL_SECONDS", 30),
            briefing_hour=briefing_hour,
            checkin_hour=checkin_hour,
            city=os.getenv("EV_CITY", "").strip(),
            news_topic=os.getenv("EV_NEWS_TOPIC", "").strip(),
            weekly_day=weekly_day,
            weekly_hour=_get_int("EV_WEEKLY_HOUR", 20),
            rain_hour=rain_hour,
            watch_poll_minutes=_get_int("EV_WATCH_POLL_MINUTES", 30),
            telegram_backup=_get_bool("EV_TELEGRAM_BACKUP", True),
            message_history_keep=_get_int("EV_MESSAGE_HISTORY_KEEP", 500),
            habit_nudge_hour=habit_nudge_hour,
            monthly_report_day=monthly_report_day,
            monthly_report_hour=_get_int("EV_MONTHLY_REPORT_HOUR", 9),
            websearch_enabled=_get_bool("EV_WEBSEARCH_ENABLED", True),
            brave_api_key=os.getenv("BRAVE_API_KEY", "").strip(),
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            google_oauth_client=os.getenv("GOOGLE_OAUTH_CLIENT", "").strip(),
            google_accounts=google_accounts,
            web_token=os.getenv("EV_WEB_TOKEN", "").strip(),
            web_host=os.getenv("EV_WEB_HOST", "0.0.0.0").strip(),
            web_port=_get_int("EV_WEB_PORT", 8000),
            db_path=_PROJECT_ROOT / "ev_memory.db",
        )
