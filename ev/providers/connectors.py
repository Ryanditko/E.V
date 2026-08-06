"""User-defined API connectors — fetch an allowed external HTTPS endpoint and
pull out a value. Config-driven (NO code execution).

Security: SSRF-guarded — https only, public hosts only (private/loopback/
link-local/reserved IPs are blocked), redirects disabled (a 3xx could hop to
an internal host), and response size/time capped. Secrets are substituted by
the caller (never logged here).
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.request
from urllib.parse import urlparse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Block redirects entirely — otherwise a public URL could 3xx to an internal one.
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _host_is_public(host: str) -> bool:
    """True only if every resolved IP for `host` is a public address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _tokens(path: str):
    """Parse a simple JSON path like '$.a.b[0].c' -> ['a','b',0,'c']."""
    out: list = []
    for seg in (path or "").lstrip("$").split("."):
        seg = seg.strip()
        if not seg:
            continue
        key = re.match(r"^[^\[\]]*", seg).group(0)
        if key:
            out.append(key)
        for idx in re.findall(r"\[(\d+)\]", seg):
            out.append(int(idx))
    return out


def json_path(data, path: str):
    """Extract a value from parsed JSON via a simple dotted/indexed path."""
    cur = data
    for part in _tokens(path):
        if isinstance(part, int):
            if not isinstance(cur, list) or part >= len(cur):
                return None
            cur = cur[part]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


def fetch(url: str, headers: dict | None = None, path: str = "",
          timeout: int = 8, max_bytes: int = 200_000):
    """Fetch a connector endpoint safely. Returns (value, error_message)."""
    u = urlparse(url or "")
    if u.scheme != "https":
        return None, "Só https é permitido."
    if not u.hostname or not _host_is_public(u.hostname):
        return None, "Host não permitido (endereço interno/privado bloqueado)."
    req = urllib.request.Request(
        url, headers=headers or {"User-Agent": "E.V.-connector/1.0"})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read(max_bytes + 1)
    except Exception as exc:
        return None, f"Falha ao buscar: {exc}"
    if len(raw) > max_bytes:
        return None, "Resposta grande demais."
    text = raw.decode("utf-8", "replace")
    try:
        data = json.loads(text)
    except ValueError:
        return text[:800], None  # not JSON — return raw text snippet
    val = json_path(data, path) if path else data
    return val, None
