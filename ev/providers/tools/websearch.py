"""Web search, news and page-fetching tools."""

from __future__ import annotations

import logging

from ...core.i18n import t

log = logging.getLogger("ev.tools")


def fetch_text(url: str) -> str:
    """Fetch a page and return its visible text (for change monitoring)."""
    import re
    import httpx

    resp = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (E.V. assistant)"},
    )
    resp.raise_for_status()
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", resp.text)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def tabnews(max_results: int = 5) -> str:
    """Top posts from TabNews (Brazilian tech/dev community), with links."""
    import httpx

    try:
        resp = httpx.get(
            "https://www.tabnews.com.br/api/v1/contents",
            params={"strategy": "relevant", "per_page": max_results},
            headers={"User-Agent": "E.V. assistant"},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        log.warning("tabnews failed (%s)", exc)
        return ""
    lines = []
    for it in items[:max_results]:
        title, owner, slug = it.get("title"), it.get("owner_username"), it.get("slug")
        if title and owner and slug:
            lines.append(f"- {title}\n  https://www.tabnews.com.br/{owner}/{slug}")
    return "\n".join(lines)


def news(topic: str, max_results: int = 4, tavily_key: str = "",
         lang: str = "en") -> str:
    """Recent news headlines about `topic`, WITH source links. Prefers Tavily
    (fresh, last few days) when a key is set; otherwise DuckDuckGo news."""
    if tavily_key:
        try:
            import httpx

            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "query": f"últimas notícias sobre {topic}",
                    "topic": "news", "days": 3, "max_results": max_results,
                },
                headers={"Authorization": f"Bearer {tavily_key}"},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return "\n".join(
                    f"- {r.get('title', '')}\n  {r.get('url', '')}"
                    for r in results[:max_results]
                )
        except Exception as exc:
            log.warning("tavily news failed (%s); trying DuckDuckGo", exc)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            items = list(ddgs.news(topic, region="br-pt", max_results=max_results))
    except Exception as exc:
        log.warning("news failed (%s)", exc)
        return t(lang, "tool.news_error", exc=exc)
    if not items:
        return t(lang, "tool.news_none")
    return "\n".join(
        f"- {i.get('title', '')}\n  {i.get('url', '')}" for i in items
    )


def _fmt_pubdate(s: str) -> str:
    """Format a Tavily published_date (RFC-2822) as 'dd/mm/yyyy · ', or ''."""
    if not s:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%d/%m/%Y") + " · "
    except Exception:
        return ""


def tavily_search(
    query: str, api_key: str, max_results: int = 5, recent: bool = False,
    lang: str = "en",
) -> str:
    """Search via Tavily. `recent=True` switches to the news topic (last 7 days)
    for current-events queries. Includes Tavily's synthesized answer and shows
    each result's publish date so freshness is visible."""
    import httpx

    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }
    if recent:
        payload["topic"] = "news"
        payload["days"] = 7

    resp = httpx.post(
        "https://api.tavily.com/search",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    answer = (data.get("answer") or "").strip()
    if not results and not answer:
        return t(lang, "tool.web_none")
    lines = []
    if answer:
        lines.append(t(lang, "tool.web_summary", answer=answer) + "\n")
    for r in results[:max_results]:
        body = (r.get("content", "") or "")[:180]
        date = _fmt_pubdate(r.get("published_date", ""))
        lines.append(f"- {date}{r.get('title', '')}: {body} ({r.get('url', '')})")
    return "\n".join(lines)


def brave_search(query: str, api_key: str, max_results: int = 5,
                 lang: str = "en") -> str:
    """Search via the Brave Search API (better relevance; needs a key)."""
    import httpx

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results, "country": "br"},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("web", {}).get("results", [])
    if not results:
        return t(lang, "tool.web_none")
    lines = []
    for r in results[:max_results]:
        lines.append(f"- {r.get('title', '')}: {r.get('description', '')} ({r.get('url', '')})")
    return "\n".join(lines)


# Query words that signal the user wants CURRENT info (switch Tavily to news mode).
_RECENT_KW = (
    "hoje", "agora", "últimas", "ultimas", "notícia", "noticia", "notícias",
    "noticias", "atual", "atualmente", "recente", "recentes", "2026", "preço",
    "preco", "cotação", "cotacao", "dólar", "dolar", "resultado", "placar",
    "última hora", "ultima hora",
)


def _looks_recent(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in _RECENT_KW)


def web_search(
    query: str, max_results: int = 5, brave_key: str = "", tavily_key: str = "",
    lang: str = "en",
) -> str:
    """Search the web and return a concise summary. Order of preference:
    Tavily -> Brave -> DuckDuckGo (whichever is configured; free/no-key fallback)."""
    if tavily_key:
        try:
            return tavily_search(
                query, tavily_key, max_results, recent=_looks_recent(query),
                lang=lang,
            )
        except Exception as exc:
            log.warning("tavily_search failed (%s); trying next", exc)
    if brave_key:
        try:
            return brave_search(query, brave_key, max_results, lang=lang)
        except Exception as exc:
            log.warning("brave_search failed (%s); falling back to DuckDuckGo", exc)
    try:
        try:
            from ddgs import DDGS
        except ImportError:  # older package name
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    query, region="br-pt", safesearch="off", max_results=max_results
                )
            )
    except Exception as exc:
        log.warning("web_search failed (%s)", exc)
        return t(lang, "tool.web_error", exc=exc)

    if not results:
        return t(lang, "tool.web_none")

    lines = []
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        lines.append(f"- {title}: {body} ({href})")
    return "\n".join(lines)
