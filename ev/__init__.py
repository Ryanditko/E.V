"""E.V. — assistente pessoal de IA.

Arquitetura em duas camadas:
  - O "cérebro" (este pacote `ev`): LLM, memória, personalidade, ferramentas.
    Reutilizável por qualquer interface.
  - As "interfaces" (`ev.interfaces`): Telegram hoje; terminal/web depois.
"""

__version__ = "0.1.0"

# Faz o Python confiar na CA do trust store do SISTEMA OPERACIONAL (não só no
# bundle do certifi). Necessário atrás de proxy corporativo de inspeção TLS,
# que reassina certificados com uma CA interna. Injetado no import do pacote,
# antes de qualquer cliente HTTP (Gemini, OpenAI/Groq/OpenRouter, Telegram).
try:  # pragma: no cover
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass
