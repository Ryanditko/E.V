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


async def synthesize(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    fixes=(),
) -> bytes:
    """Return MP3 bytes speaking `text` with the chosen voice/tuning."""
    spoken = _apply_fixes(text, fixes)
    communicate = edge_tts.Communicate(spoken, voice, rate=rate, pitch=pitch)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)
