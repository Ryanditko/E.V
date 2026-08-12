"""Tests for TTS-only pronunciation fixes."""

from ev.providers.voice import _apply_fixes, clean_for_speech, say_name


def test_say_name_speaks_eevee_not_letters():
    assert say_name("Sou a E.V., sua IA.") == "Sou a Ivi, sua IA."
    assert say_name("a E.V está pronta") == "a Ivi está pronta"
    assert say_name("e.v. ok") == "Ivi ok"
    assert say_name("EV agora") == "Ivi agora"
    # must NOT touch ordinary words containing e/v
    assert say_name("level up eleven event") == "level up eleven event"


def test_clean_for_speech_strips_markdown_and_emoji():
    assert clean_for_speech("**Olá** 🎉 mundo! # veja") == "Olá mundo! veja"


def test_clean_for_speech_keeps_link_text_drops_url():
    assert clean_for_speech("Veja [aqui](https://x.com) 🔗") == "Veja aqui"


def test_clean_for_speech_removes_bullets_and_asterisks():
    out = clean_for_speech("- Tarefa *importante* ✅")
    assert "*" not in out and "✅" not in out and "importante" in out


def test_apply_fixes_replaces_word():
    fixes = (("Ryan", "Rian"),)
    assert _apply_fixes("Oi Ryan, tudo bem?", fixes) == "Oi Rian, tudo bem?"


def test_apply_fixes_case_insensitive_whole_word():
    fixes = (("Ryan", "Rian"),)
    # matches regardless of case, but only whole words
    assert _apply_fixes("RYAN e Ryanzinho", fixes) == "Rian e Ryanzinho"


def test_apply_fixes_noop_without_fixes():
    assert _apply_fixes("texto qualquer", ()) == "texto qualquer"
