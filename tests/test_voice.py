"""Tests for TTS-only pronunciation fixes."""

from ev.providers.voice import _apply_fixes


def test_apply_fixes_replaces_word():
    fixes = (("Ryan", "Rian"),)
    assert _apply_fixes("Oi Ryan, tudo bem?", fixes) == "Oi Rian, tudo bem?"


def test_apply_fixes_case_insensitive_whole_word():
    fixes = (("Ryan", "Rian"),)
    # matches regardless of case, but only whole words
    assert _apply_fixes("RYAN e Ryanzinho", fixes) == "Rian e Ryanzinho"


def test_apply_fixes_noop_without_fixes():
    assert _apply_fixes("texto qualquer", ()) == "texto qualquer"
