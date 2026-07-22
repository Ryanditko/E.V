"""Voz da E.V. — converte texto em áudio usando edge-tts (grátis).

Gera um MP3 em memória. A interface do Telegram envia esse MP3 como áudio.
(Não usamos ffmpeg no v1: o Telegram aceita MP3 via send_audio.)

`rate` e `pitch` deixam a voz mais "meiga"/feminina:
  - pitch  "+12Hz"  -> tom um pouco mais agudo e suave
  - rate   "-3%"    -> fala levemente mais devagar, mais carinhosa
Ajuste no .env (EV_VOICE_PITCH / EV_VOICE_RATE) até ficar do seu gosto.
"""

from __future__ import annotations

import edge_tts


async def synthesize(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> bytes:
    """Retorna os bytes de um MP3 falando `text` com a voz/tom escolhidos."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)
