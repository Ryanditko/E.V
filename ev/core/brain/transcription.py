"""Audio transcription, OCR, image description, and receipt extraction."""

import asyncio
import logging

from google.genai import types

from ...providers import llm as providers

log = logging.getLogger("ev.brain")


class TranscriptionMixin:
    async def transcribe(self, audio: bytes, mime: str | None) -> str | None:
        """Transcribe an audio file to text (Groq Whisper). For /transcrever."""
        return await asyncio.to_thread(self._transcribe, audio, mime)

    async def ocr_image(self, image: bytes, mime: str | None) -> str | None:
        """Extract text from an image via Gemini vision (OCR)."""
        return await asyncio.to_thread(self._ocr_sync, image, mime)

    async def describe_image(self, image: bytes, mime: str | None, prompt: str) -> str:
        """One-off vision description (for live camera / 'what is this'). NOT
        persisted to any conversation. Returns '' on failure."""
        return await asyncio.to_thread(self._describe_sync, image, mime, prompt)

    def _describe_sync(self, image: bytes, mime: str | None, prompt: str) -> str:
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"),
                    types.Part.from_text(text=prompt),
                ],
                config=types.GenerateContentConfig(temperature=0.2),
            )
            return (resp.text or "").strip()
        except Exception as exc:
            log.warning("describe_image failed (%s)", exc)
            return ""

    async def extract_receipt(self, image: bytes, mime: str | None) -> dict | None:
        """Read a receipt/invoice image -> {amount, description, category} or None."""
        return await asyncio.to_thread(self._extract_receipt_sync, image, mime)

    @staticmethod
    def _parse_receipt_json(raw: str) -> dict | None:
        """Parse the vision model's JSON reply into a validated expense dict."""
        import json
        import re
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
        try:
            amount = round(float(str(d.get("valor", 0)).replace(",", ".").strip()), 2)
        except (ValueError, TypeError):
            return None
        if amount <= 0:
            return None
        desc = (str(d.get("descricao") or "").strip() or "compra")[:80]
        cat = re.sub(r"[^a-zà-ú0-9]", "",
                     str(d.get("categoria") or "geral").strip().lower()) or "geral"
        return {"amount": amount, "description": desc, "category": cat}

    def _extract_receipt_sync(self, image: bytes, mime: str | None) -> dict | None:
        prompt = (
            "Esta imagem é um comprovante, nota fiscal ou recibo. Extraia o gasto e "
            "responda APENAS um JSON, sem texto ao redor, com as chaves: "
            "\"valor\" (número — o TOTAL pago), "
            "\"descricao\" (estabelecimento ou o que foi comprado, curto), "
            "\"categoria\" (UMA palavra: mercado, comida, transporte, saude, lazer, "
            "casa, assinatura, etc). "
            "Se não for um comprovante ou não achar o total, responda {\"valor\": 0}."
        )
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"),
                    types.Part.from_text(text=prompt),
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return self._parse_receipt_json(resp.text or "")
        except Exception as exc:
            log.warning("receipt extraction (Gemini vision) failed (%s)", exc)
            return None

    def _ocr_sync(self, image: bytes, mime: str | None) -> str | None:
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"),
                    types.Part.from_text(
                        text="Extraia TODO o texto visível nesta imagem, exatamente "
                        "como está, preservando as quebras de linha. Não comente nem "
                        "resuma. Se não houver texto, responda apenas: (sem texto)"
                    ),
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return (resp.text or "").strip() or None
        except Exception as exc:
            log.warning("OCR (Gemini vision) failed (%s)", exc)
            return None

    def _transcribe(self, audio: bytes, audio_mime: str | None) -> str | None:
        """Transcribe audio via Groq Whisper (for the fallback path)."""
        if not self._config.groq_api_key:
            return None
        # Whisper detects the format from the filename extension — derive it from
        # the MIME so browser recordings (webm/mp4) and Telegram voice (ogg) work.
        ext = {
            "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4",
            "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
            "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "m4a",
        }.get((audio_mime or "").split(";")[0].strip(), "ogg")
        try:
            return providers.transcribe_groq(
                api_key=self._config.groq_api_key,
                model=self._config.groq_whisper_model,
                audio=audio,
                filename=f"audio.{ext}",
            )
        except Exception as exc:
            log.warning("Transcription (Groq Whisper) failed (%s).", exc)
            return None
