"""Provedores de fallback da E.V. — Groq e OpenRouter.

Ambos falam a API compatível com OpenAI, então um único cliente serve para
os dois (só muda base_url + chave + modelo). São a "rede de segurança":
quando o Gemini (provedor principal) bate no rate limit, a E.V. continua
conversando por aqui.

Estes provedores tratam só TEXTO. Áudio é resolvido antes, pela transcrição
via Whisper do Groq (`transcribe_groq`).
"""

from __future__ import annotations

import json
from typing import Callable

from openai import OpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def chat_openai_compat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    temperature: float = 0.4,
) -> str:
    """Chama um endpoint chat-completions compatível com OpenAI e devolve o texto.

    `messages` no formato OpenAI: [{"role": "user"|"assistant", "content": "..."}].
    """
    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=temperature,
    )
    # Alguns provedores devolvem 200 com corpo de erro (choices vazio).
    if not resp.choices:
        raise RuntimeError(f"resposta sem choices: {getattr(resp, 'model', model)}")
    return (resp.choices[0].message.content or "").strip()


def chat_with_tools(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_functions: dict[str, Callable],
    temperature: float = 0.4,
    max_rounds: int = 5,
) -> str:
    """Chat com function calling (API OpenAI). Executa as ferramentas que o
    modelo pedir e devolve a resposta final em texto.

    `tools`: schemas no formato OpenAI. `tool_functions`: nome -> função Python.
    """
    client = OpenAI(base_url=base_url, api_key=api_key)
    msgs: list[dict] = [{"role": "system", "content": system}, *messages]

    def _plain() -> str:
        """Resposta sem ferramentas (rede de segurança quando o tool-calling
        do modelo falha em formatar — comum no Llama via Groq)."""
        r = client.chat.completions.create(
            model=model, messages=msgs, temperature=temperature
        )
        if not r.choices:
            raise RuntimeError("resposta sem choices")
        return (r.choices[0].message.content or "").strip()

    for _ in range(max_rounds):
        try:
            resp = client.chat.completions.create(
                model=model, messages=msgs, tools=tools, temperature=temperature
            )
        except Exception as exc:
            # Llama às vezes emite a tool call num formato inválido -> 400
            # 'tool_use_failed'. Nesse caso, responde sem ferramentas.
            if "tool_use_failed" in str(exc) or "tool call" in str(exc).lower():
                return _plain()
            raise

        if not resp.choices:
            return _plain()
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()

        # Registra a intenção do modelo de chamar ferramentas...
        msgs.append(
            {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        # ...e executa cada uma, devolvendo o resultado ao modelo.
        for tc in msg.tool_calls:
            fn = tool_functions.get(tc.function.name)
            try:
                args = json.loads(tc.function.arguments or "{}")
                result = fn(**args) if fn else f"ferramenta {tc.function.name} desconhecida"
            except Exception as exc:  # não deixa uma ferramenta derrubar o turno
                result = f"erro ao executar: {exc}"
            msgs.append(
                {"role": "tool", "tool_call_id": tc.id, "content": str(result)}
            )

    # Esgotou as rodadas de ferramenta: pede a resposta final sem tools.
    return _plain()


def transcribe_groq(
    *, api_key: str, model: str, audio: bytes, filename: str = "audio.ogg"
) -> str:
    """Transcreve áudio usando o Whisper hospedado no Groq (grátis)."""
    client = OpenAI(base_url=GROQ_BASE_URL, api_key=api_key)
    resp = client.audio.transcriptions.create(
        model=model,
        file=(filename, audio),
    )
    return (resp.text or "").strip()
