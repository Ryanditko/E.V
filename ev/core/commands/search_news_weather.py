"""Web search, own-data search, news and weather."""

from __future__ import annotations

from ...providers import tools as tools_mod


class SearchNewsWeatherMixin:
    def buscar(self, argstr: str) -> str:
        query = argstr.strip()
        if not query:
            return "Uso: /buscar <termo>. Ex: /buscar notícias de tecnologia hoje"
        return "Resultados da web:\n" + tools_mod.web_search(
            query,
            brave_key=getattr(self._config, "brave_api_key", ""),
            tavily_key=getattr(self._config, "tavily_api_key", ""),
        )

    def procurar(self, user_id: str, argstr: str) -> str:
        """Unified search across everything the user stored (not the web)."""
        term = argstr.strip()
        if not term:
            return "Uso: /procurar <termo>. Procuro em tudo que você guardou (memória, tarefas, lembretes, links, diário, documentos)."
        r = self._memory.search_all(user_id, term)
        labels = [
            ("facts", "🧠 Memórias"), ("tasks", "📋 Tarefas"),
            ("reminders", "⏰ Lembretes"), ("links", "🔗 Links"),
            ("journal", "📔 Diário"), ("expenses", "💸 Gastos"),
            ("messages", "💬 Conversas"), ("knowledge", "📄 Conhecimento"),
        ]
        lines = [f"🔎 Resultados para '{term}':"]
        found = False
        for key, label in labels:
            items = r.get(key) or []
            if not items:
                continue
            found = True
            lines.append(f"\n{label}:")
            for it in items[:5]:
                lines.append(f"- {it['text']}")
        if not found:
            return f"Nada encontrado pra '{term}' nos seus dados."
        return "\n".join(lines)

    def noticias(self, argstr: str = "") -> str:
        topic = argstr.strip() or getattr(self._config, "news_topic", "") or "Brasil"
        out = tools_mod.news(
            topic, tavily_key=getattr(self._config, "tavily_api_key", "")
        )
        parts = [f"📰 Notícias — {topic}:", out]
        tab = tools_mod.tabnews(5)
        if tab:
            parts.append("\n💻 TabNews (tech):")
            parts.append(tab)
        return "\n".join(parts)

    def clima(self, argstr: str) -> str:
        city = argstr.strip() or getattr(self._config, "city", "")
        if not city:
            return "Uso: /clima <cidade>. Ex: /clima São Paulo"
        return tools_mod.weather_forecast(city)
