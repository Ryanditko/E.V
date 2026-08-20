"""Web search, own-data search, news and weather."""

from __future__ import annotations

from ...providers import tools as tools_mod
from ..i18n import t as _t


class SearchNewsWeatherMixin:
    def buscar(self, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        query = argstr.strip()
        if not query:
            return _t(lang, "snw.buscar_usage")
        return _t(lang, "snw.web_results") + "\n" + tools_mod.web_search(
            query,
            brave_key=getattr(self._config, "brave_api_key", ""),
            tavily_key=getattr(self._config, "tavily_api_key", ""),
            lang=lang,
        )

    def procurar(self, user_id: str, argstr: str) -> str:
        """Unified search across everything the user stored (not the web)."""
        lang = self._memory.assistant_lang()
        term = argstr.strip()
        if not term:
            return _t(lang, "snw.procurar_usage")
        r = self._memory.search_all(user_id, term)
        labels = [
            ("facts", "snw.lbl_facts"), ("tasks", "snw.lbl_tasks"),
            ("reminders", "snw.lbl_reminders"), ("links", "snw.lbl_links"),
            ("journal", "snw.lbl_journal"), ("expenses", "snw.lbl_expenses"),
            ("messages", "snw.lbl_messages"), ("knowledge", "snw.lbl_knowledge"),
        ]
        lines = [_t(lang, "snw.results_for", term=term)]
        found = False
        for key, label_key in labels:
            items = r.get(key) or []
            if not items:
                continue
            found = True
            lines.append("\n" + _t(lang, label_key) + ":")
            for it in items[:5]:
                lines.append(f"- {it['text']}")
        if not found:
            return _t(lang, "snw.nothing_found", term=term)
        return "\n".join(lines)

    def noticias(self, argstr: str = "") -> str:
        lang = self._memory.assistant_lang()
        topic = argstr.strip() or getattr(self._config, "news_topic", "") or "Brasil"
        out = tools_mod.news(
            topic, tavily_key=getattr(self._config, "tavily_api_key", ""), lang=lang
        )
        parts = [_t(lang, "snw.news_title", topic=topic), out]
        tab = tools_mod.tabnews(5)
        if tab:
            parts.append(_t(lang, "snw.tabnews_tech"))
            parts.append(tab)
        return "\n".join(parts)

    def clima(self, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        city = argstr.strip() or getattr(self._config, "city", "")
        if not city:
            return _t(lang, "snw.clima_usage")
        return tools_mod.weather_forecast(city, lang=lang)
