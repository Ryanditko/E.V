"""Assistant language — the single source of truth for how E.V. talks.

The same choice drives the web UI language AND the language E.V. replies/speaks
in. Stored globally in settings under the key ``assistant_lang`` (values
``"en"`` | ``"pt"``), so it applies to every interface (web + Telegram).

Default is English. Anything unknown/unset normalizes back to English.
"""

from __future__ import annotations

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "pt")
SETTING_KEY = "assistant_lang"


def normalize_lang(value: str | None) -> str:
    """Coerce any input to a supported language code, defaulting to English."""
    v = (value or "").strip().lower()
    return v if v in SUPPORTED_LANGS else DEFAULT_LANG
