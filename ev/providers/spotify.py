"""Parse Spotify links/URIs into an embeddable (kind, id). No API/OAuth —
the embed player streams full tracks when the user is logged into Spotify in
the browser, else 30s previews."""
from __future__ import annotations

import re

KINDS = {"playlist", "track", "album", "artist", "show", "episode"}
_URL = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?"
    r"(playlist|track|album|artist|show|episode)/([A-Za-z0-9]+)", re.I)
_URI = re.compile(
    r"spotify:(playlist|track|album|artist|show|episode):([A-Za-z0-9]+)", re.I)


def parse(url: str):
    """Return (kind, id) for a Spotify link/URI, or None if unsupported.
    A user/profile link has no embeddable player, so it returns None."""
    m = _URL.search(url or "") or _URI.search(url or "")
    if not m:
        return None
    return m.group(1).lower(), m.group(2)


def embed_url(kind: str, ref: str) -> str:
    return f"https://open.spotify.com/embed/{kind}/{ref}"
