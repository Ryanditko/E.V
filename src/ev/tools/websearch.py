from duckduckgo_search import DDGS

from ev.tools.base import Tool

class WebSearchTool(Tool): 
    "Tool for searching the web using DuckDuckGo."
    
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for current information. Use this when you need up-to-date information or facts you don't know."

    @property 
    def parameters(self) -> dict:
        return {
            "type": "object", 
            "properties": {
                "query": {
                    "type": "string", 
                    "description": "The search query"
                },
            },
            "required": ["query"]
        }

    def execute(self, query: str, max_results: int = 5) -> str:
        "Execute web search and return formatted results."
        try: 
            with DDGS() as ddgs: 
                results = list(ddgs.text(query, max_results=max_results))

            if not results: 
                return "No results found."

            # format results
            output = []
            for i, result in enumerate(results, 1):
                title = result.get("title", "No title")
                body = result.get("body", "No description")
                href = result.get("href", "")
                output.append(f"{i}. **{title}**\n {body}\n URL:{href}")

            return "\n\n".join(output)

        except Exception as e: 
            return f"Search error: {e}"