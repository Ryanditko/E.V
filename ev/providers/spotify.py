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


# --- OAuth (Authorization Code) + Web API (Premium playback) ---------------
SCOPES = ("playlist-read-private playlist-read-collaborative "
          "user-read-playback-state user-modify-playback-state "
          "user-read-currently-playing streaming")


def norm_redirect(base: str) -> str:
    """Spotify requires http loopback redirects to use 127.0.0.1 (not localhost)."""
    return (base or "").replace("http://localhost", "http://127.0.0.1").rstrip("/") + "/spotify/callback"


def auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode
    return "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": client_id, "response_type": "code",
        "redirect_uri": redirect_uri, "scope": SCOPES, "state": state,
    })


# --- shared token + API helpers (used by web endpoints and the voice tools) ---
def access_token(memory, config):
    """A valid access token from stored refresh token, refreshing if expired.
    Returns None if not connected. Persists refreshed tokens back to settings."""
    import json
    import time
    import httpx
    try:
        t = json.loads(memory.get_setting("spotify_tokens") or "{}")
    except (ValueError, TypeError):
        t = {}
    if not t.get("refresh"):
        return None
    if t.get("access") and t.get("exp", 0) > time.time() + 30:
        return t["access"]
    try:
        r = httpx.post("https://accounts.spotify.com/api/token", data={
            "grant_type": "refresh_token", "refresh_token": t["refresh"],
            "client_id": getattr(config, "spotify_client_id", ""),
            "client_secret": getattr(config, "spotify_client_secret", "")},
            timeout=15).json()
    except Exception:
        return None
    if not r.get("access_token"):
        return None
    t["access"] = r["access_token"]
    t["exp"] = time.time() + int(r.get("expires_in", 3600))
    if r.get("refresh_token"):
        t["refresh"] = r["refresh_token"]
    memory.set_setting("spotify_tokens", json.dumps(t))
    return t["access"]


def api(method: str, path: str, token: str, **kw):
    import httpx
    url = path if path.startswith("http") else ("https://api.spotify.com/v1" + path)
    return httpx.request(method, url, headers={"Authorization": "Bearer " + token},
                         timeout=15, **kw)


def find_playlist(token: str, name: str):
    """Return the URI of the user's playlist whose name best matches `name`."""
    try:
        data = api("GET", "/me/playlists?limit=50", token).json()
    except Exception:
        return None
    n = (name or "").strip().lower()
    pls = [p for p in (data.get("items") or []) if p]
    for p in pls:
        if (p.get("name") or "").strip().lower() == n:
            return p.get("uri")
    for p in pls:
        if n and n in (p.get("name") or "").strip().lower():
            return p.get("uri")
    return None


def current_track(token: str) -> str:
    try:
        r = api("GET", "/me/player/currently-playing", token)
        if r.status_code != 200:
            return ""
        d = r.json()
        it = d.get("item") or {}
        name = it.get("name") or ""
        artists = ", ".join(a.get("name", "") for a in (it.get("artists") or []))
        return f"{name} — {artists}".strip(" —")
    except Exception:
        return ""
