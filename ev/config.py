"""Configuração central do E.V. — lê tudo do ambiente (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carrega o .env que fica na raiz do projeto (um nível acima deste pacote).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "sim", "y"}


@dataclass(frozen=True)
class Config:
    telegram_token: str
    gemini_api_key: str
    model: str
    # Fallbacks (opcionais) — vazio = provedor desligado
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
    db_path: Path

    @classmethod
    def load(cls) -> "Config":
        telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

        missing = [
            name
            for name, value in [
                ("TELEGRAM_TOKEN", telegram_token),
                ("GEMINI_API_KEY", gemini_api_key),
            ]
            if not value
        ]
        if missing:
            raise SystemExit(
                "Faltam variáveis no .env: "
                + ", ".join(missing)
                + "\nCopie .env.example para .env e preencha. Veja o README."
            )

        owner_raw = os.getenv("EV_OWNER_ID", "").strip()
        owner_id = int(owner_raw) if owner_raw.isdigit() else None

        return cls(
            telegram_token=telegram_token,
            gemini_api_key=gemini_api_key,
            model=os.getenv("EV_MODEL", "gemini-flash-latest").strip(),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=os.getenv(
                "GROQ_MODEL", "llama-3.3-70b-versatile"
            ).strip(),
            groq_whisper_model=os.getenv(
                "GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"
            ).strip(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_model=os.getenv(
                "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
            ).strip(),
            owner_id=owner_id,
            voice_reply=_get_bool("EV_VOICE_REPLY", True),
            voice=os.getenv("EV_VOICE", "pt-BR-FranciscaNeural").strip(),
            voice_rate=os.getenv("EV_VOICE_RATE", "-3%").strip(),
            voice_pitch=os.getenv("EV_VOICE_PITCH", "+12Hz").strip(),
            db_path=_PROJECT_ROOT / "ev_memory.db",
        )
