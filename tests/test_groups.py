"""Tests for group trigger logic (mention / reply-to-bot) and conv scoping."""

from ev.interfaces.telegram_bot import TelegramInterface

BOT = "ev_assistant_bot"
X = TelegramInterface._extract_group_query


def test_mention_triggers_and_is_stripped():
    assert X("@EV_Assistant_Bot qual a fórmula de bhaskara?", BOT, None) == \
        "qual a fórmula de bhaskara?"


def test_reply_to_bot_triggers():
    assert X("e o resto?", BOT, "EV_Assistant_Bot") == "e o resto?"


def test_reply_to_other_user_ignored():
    assert X("papo normal", BOT, "algum_amigo") is None


def test_plain_group_message_ignored():
    assert X("mensagem qualquer no grupo", BOT, None) is None


def test_mention_only_returns_none():
    assert X("@ev_assistant_bot", BOT, None) is None
