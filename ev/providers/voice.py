"""E.V.'s voice — turns text into speech via edge-tts (free).

Produces an MP3 in memory. The Telegram interface sends it as audio.
(No ffmpeg in v1: Telegram accepts MP3 via send_audio.)

`rate`/`pitch` fine-tune the delivery — keep pitch at "+0Hz" for the most
natural voice (shifting pitch sounds robotic).

`fixes` are TTS-only spelling substitutions so the PT-BR voice pronounces names
correctly (e.g. "Ryan" -> "Rian"). They affect ONLY the audio, never the text
the user reads. Configure via EV_VOICE_FIXES, e.g. "Ryan=Rian;Nome=Fonetico".
"""

from __future__ import annotations

import re

import edge_tts


def _apply_fixes(text: str, fixes) -> str:
    for frm, to in fixes or ():
        text = re.sub(rf"\b{re.escape(frm)}\b", to, text, flags=re.IGNORECASE)
    return text


# Emoji / pictographic ranges the TTS would otherwise read out loud.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002300-\U000023FF\U00002B00-\U00002BFF"
    "️‍⃣•▪●■✓✔]"
)


def clean_for_speech(text: str) -> str:
    """Strip emoji and markdown so the voice doesn't read '*', '#', emoji names.

    Kept public + pure so it's testable. Applies to Telegram AND the web voice.
    """
    t = text or ""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)   # [texto](url) -> texto
    t = re.sub(r"https?://\S+", "", t)                # bare URLs
    t = _EMOJI.sub("", t)                             # emojis / bullets
    t = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", t)      # `code` -> code
    t = re.sub(r"[*_#~>|]+", "", t)                   # markdown symbols
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


async def synthesize(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    fixes=(),
) -> bytes:
    """Return MP3 bytes speaking `text` with the chosen voice/tuning."""
    spoken = _apply_fixes(clean_for_speech(text), fixes) or "..."
    communicate = edge_tts.Communicate(spoken, voice, rate=rate, pitch=pitch)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)
