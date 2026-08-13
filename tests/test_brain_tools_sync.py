"""_tool_callables (Gemini) and _openai_tools (Groq/OpenRouter) are duplicated
tool definitions that must stay in sync — this guards against desync."""

from types import SimpleNamespace

from ev.core.brain import Brain
from ev.core.memory import Memory


def test_tool_name_sets_match(tmp_path):
    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo", google_oauth_client="client.json",
        google_accounts=("pessoal",), default_account="pessoal",
        gemini_api_key="x", embed_backend="gemini", embed_model="m",
        model="gemini-flash-latest",
        groq_api_key="", openrouter_api_key="", ollama_enabled=False,
        tavily_api_key="", brave_api_key="", websearch_enabled=True,
    )
    brain = Brain(cfg, Memory(tmp_path / "t.db"))
    callable_names = set(brain._tool_callables("u"))
    schema_names = {s["function"]["name"] for s in brain._openai_tools()}
    assert callable_names == schema_names
