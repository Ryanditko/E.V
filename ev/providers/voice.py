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

import asyncio
import logging
import re

import edge_tts

log = logging.getLogger("ev.voice")


def _apply_fixes(text: str, fixes) -> str:
    for frm, to in fixes or ():
        text = re.sub(rf"\b{re.escape(frm)}\b", to, text, flags=re.IGNORECASE)
    return text


# Her name is written "E.V." but spoken "Eevee" (pt-BR "Ivi") — like the Pokémon,
# never spelled out "É-Vê". Matches E.V. / E.V / E. V. / EV as a standalone token.
_NAME_SAY = re.compile(r"\bE\.?\s*V\.?(?=\b|\W|$)", re.IGNORECASE)


def say_name(text: str) -> str:
    return _NAME_SAY.sub("Ivi", text or "")


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


_PTBR_VOICES = None


async def list_ptbr_voices() -> list[dict]:
    """Real pt-BR neural voices available in edge-tts (cached). Females first."""
    global _PTBR_VOICES
    if _PTBR_VOICES is not None:
        return _PTBR_VOICES
    try:
        allv = await edge_tts.list_voices()
    except Exception:
        allv = []
    out = []
    for v in allv:
        if (v.get("Locale") or "").lower().startswith("pt-br"):
            sid = v.get("ShortName", "")
            out.append({
                "id": sid, "gender": v.get("Gender", ""),
                "name": sid.split("-")[-1].replace("Neural", "") or sid,
            })
    out.sort(key=lambda x: (x["gender"] != "Female", x["name"].lower()))
    if out:
        _PTBR_VOICES = out
    return out


async def synthesize(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    fixes=(),
) -> bytes:
    """Return MP3 bytes speaking `text` with the chosen voice/tuning."""
    spoken = _apply_fixes(say_name(clean_for_speech(text)), fixes) or "..."
    communicate = edge_tts.Communicate(spoken, voice, rate=rate, pitch=pitch)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


def _wav(pcm: bytes, rate: int = 24000) -> bytes:
    """Wrap raw PCM (mono, 16-bit) in a WAV container — Gemini TTS returns PCM."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _gemini_tts_sync(text: str, api_key: str, voice: str, model: str) -> bytes:
    """Synthesize with Gemini TTS -> WAV bytes. Raises on any failure so the
    caller can fall back to edge-tts."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    raw = resp.candidates[0].content.parts[0].inline_data.data
    if isinstance(raw, str):
        import base64
        raw = base64.b64decode(raw)
    if not raw:
        raise ValueError("Gemini TTS returned empty audio")
    return _wav(raw)


async def synth_web(config, text: str, voice: str | None = None,
                    rate: str | None = None, pitch: str | None = None,
                    fixes=None) -> tuple[bytes, str]:
    """Return (audio_bytes, mime) for the web. Uses Gemini TTS when enabled
    (mais natural); cai no edge-tts (Thalita/Francisca) em qualquer erro/quota.
    Um `voice` pt-BR explícito (preview do seletor) força o edge-tts."""
    fixes = config.voice_fixes if fixes is None else fixes
    rate = rate or config.voice_rate
    pitch = pitch or config.voice_pitch
    explicit = bool(voice)
    if getattr(config, "gemini_tts", False) and config.gemini_api_key and not explicit:
        try:
            spoken = _apply_fixes(say_name(clean_for_speech(text)), fixes) or "..."
            data = await asyncio.to_thread(
                _gemini_tts_sync, spoken, config.gemini_api_key,
                config.gemini_tts_voice, config.gemini_tts_model)
            return data, "audio/wav"
        except Exception:
            log.warning("Gemini TTS indisponível; usando edge-tts", exc_info=True)
    mp3 = await synthesize(text, voice or config.voice, rate=rate, pitch=pitch, fixes=fixes)
    return mp3, "audio/mpeg"
