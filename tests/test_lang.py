"""Assistant language: system prompt directive, the language setting, and the
brain picking the language from that setting."""

from types import SimpleNamespace

from ev.core.brain import Brain
from ev.core.lang import normalize_lang
from ev.core.memory import Memory
from ev.personality import build_system_prompt


def test_build_system_prompt_en_has_english_directive_only():
    en = build_system_prompt("en")
    assert "ALWAYS reply in **English**" in en
    assert "Fale SEMPRE" not in en


def test_build_system_prompt_pt_has_portuguese_directive_only():
    pt = build_system_prompt("pt")
    assert "Fale SEMPRE em **português do Brasil**" in pt
    assert "ALWAYS reply in **English**" not in pt


def test_build_system_prompt_defaults_to_english():
    assert build_system_prompt(None) == build_system_prompt("en")
    assert build_system_prompt("xx") == build_system_prompt("en")


def test_normalize_lang():
    assert normalize_lang("pt") == "pt"
    assert normalize_lang("EN") == "en"
    assert normalize_lang(None) == "en"
    assert normalize_lang("frobnicate") == "en"


def test_assistant_lang_setting_roundtrip(tmp_path):
    mem = Memory(tmp_path / "t.db")
    assert mem.assistant_lang() == "en"  # default when unset
    assert mem.set_assistant_lang("pt") == "pt"
    assert mem.assistant_lang() == "pt"
    # invalid values normalize back to the default
    assert mem.set_assistant_lang("nope") == "en"
    assert mem.assistant_lang() == "en"


def _brain(tmp_path):
    cfg = SimpleNamespace(
        timezone="America/Sao_Paulo", google_oauth_client="",
        google_accounts=(), gemini_api_key="x", embed_backend="gemini",
        embed_model="m", model="gemini-flash-latest", groq_api_key="",
        openrouter_api_key="", ollama_enabled=False, tavily_api_key="",
        brave_api_key="", websearch_enabled=True,
    )
    return Brain(cfg, Memory(tmp_path / "t.db"))


def test_brain_system_instruction_follows_lang_setting(tmp_path):
    brain = _brain(tmp_path)
    # unset -> English directive reaches the provider
    sys_en = brain._system_instruction("u", None)
    assert "ALWAYS reply in **English**" in sys_en
    assert "Fale SEMPRE" not in sys_en
    # switch to Portuguese -> Portuguese directive
    brain._memory.set_assistant_lang("pt")
    sys_pt = brain._system_instruction("u", None)
    assert "Fale SEMPRE em **português do Brasil**" in sys_pt
    assert "ALWAYS reply in **English**" not in sys_pt
