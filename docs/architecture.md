# E.V. — Architecture

This document details the design decisions. For the overview, see the
[README](../README.md).

> Language: docs are in English; E.V. converses in Brazilian Portuguese
> (see `ev/personality.py`).

## Core principle: brain decoupled from interface

E.V. is split into **layers** with a strict dependency rule: outer layers know
about inner ones, never the reverse.

```mermaid
flowchart LR
    subgraph OUT["Interfaces (I/O adapters)"]
        TG["telegram_bot.py"]
        TE["terminal.py"]
    end
    subgraph CORE["Core (reusable logic)"]
        B["brain.py"]
        M["memory.py"]
    end
    subgraph PROV["Providers (external services)"]
        L["llm.py"]
        E["embeddings.py"]
        V["voice.py"]
        T["tools.py"]
    end
    TG --> B
    TE --> B
    B --> M
    B --> L
    B --> T
    M --> E
    TG --> V
```

- **Interfaces** (`ev/interfaces`): receive input and deliver output (Telegram and
  Terminal today; web later). They only call `Brain.respond()`.
- **Core** (`ev/core`): `Brain` orchestrates; `Memory` holds state. They know
  nothing about Telegram or HTTP.
- **Providers** (`ev/providers`): talk to external services (LLMs, embeddings,
  TTS, tools).
- **Cross-cutting**: `config.py` (reads `.env`) and `personality.py` (the system
  prompt).

Adding an interface = writing a new adapter that calls `Brain.respond()`. Zero
changes to the core.

## Multi-provider strategy (resilience)

Each provider's free tier is limited. Instead of relying on one, E.V. chains
providers and **falls through to the next** when one fails (rate limit, error).

```mermaid
flowchart TD
    START["respond(text/audio)"] --> GEM{"Gemini available?"}
    GEM -- yes --> GEMOK["Answer + memory (native function calling)"]
    GEM -- "no (429/error)" --> AUD{"input is audio?"}
    AUD -- yes --> WHIS["Transcribe via Groq Whisper"]
    AUD -- no --> GROQ
    WHIS --> GROQ{"Groq available?"}
    GROQ -- yes --> GROQOK["Answer + memory (OpenAI tools)"]
    GROQ -- no --> OR{"OpenRouter available?"}
    OR -- yes --> OROK["Answer (text, no memory)"]
    OR -- no --> DOWN["Friendly 'try again shortly' message"]
```

### Why Gemini is primary
It is multimodal (**hears audio natively**, no transcription step) and strong in
Portuguese. When available, it's the best path.

### Why memory also lives in Groq
In practice, Gemini's free tier can be nearly exhausted (tiny daily quotas).
Saving memory needs *function calling*, and Groq supports it too (OpenAI-compatible
API), so we replicate the tools there. Memory is therefore **reliable** even
without Gemini. OpenRouter is a plain-text backstop (no memory) — the last line
before asking the user to retry.

### Tool-calling resilience
Open models (Llama) sometimes format a tool call invalidly (`tool_use_failed`).
In that case Groq **answers without tools** instead of failing the turn — E.V.
always replies something.

## Memory (SQLite + vectors)

A single `ev_memory.db` file, plus in-process vector search over facts.

```mermaid
erDiagram
    MESSAGES {
        int id PK
        string user_id
        string role "user | model"
        string content
        string created
    }
    FACTS {
        int id PK
        string user_id
        string fact
        blob embedding "float32 vector"
        string created
    }
    REMINDERS {
        int id PK
        string user_id
        string text
        string when_iso
        int done
        string created
    }
```

- **messages**: recent conversation history (turn context).
- **facts**: long-term memory. Each fact stores an **embedding**; on each turn,
  E.V. retrieves the top-K facts most semantically similar to the current message
  (cosine similarity, computed in Python) and injects them into the system prompt.
  Falls back to "all facts" if embeddings are unavailable.
- **reminders**: reminders. A background scheduler polls for due ones and delivers
  them.

Brute-force cosine over a personal-scale fact set is more than fast enough; no
external vector DB needed.

## Reminder scheduler

```mermaid
flowchart LR
    LLM["Brain: criar_lembrete(text, when_iso)"] --> DB[("reminders")]
    SCHED["Scheduler loop (every ~30s)"] --> DB
    SCHED -->|"when_iso <= now, not done"| SEND["Send message to user"]
    SEND --> MARK["mark reminder done"]
```

The current date/time is injected into the system prompt so the model can turn
"tomorrow at 9am" into an absolute ISO 8601 timestamp. The Telegram interface runs
the scheduler as a background task and delivers due reminders to the user's chat.

## Tools

Exposed to the model via function calling (`ev/providers/tools.py`):

- **web search** — DuckDuckGo, no API key.
- **calendar / email** — Google APIs; require one-time OAuth setup by the user
  (see `.env.example`). Disabled gracefully when not configured.

## Note: TLS behind a corporate proxy

On networks with TLS inspection (a proxy that re-signs certificates with an
internal CA), Python's `certifi` fails (`CERTIFICATE_VERIFY_FAILED`) for some
hosts. E.V. injects the **OS trust store** via `truststore` in `ev/__init__.py`,
before any HTTP client — so it trusts the corporate CA (already in the system)
and works on any network. Outside a corporate proxy, it's harmless.

## Configuration

Everything comes from `.env` (via `config.py`). Fallback and tool keys are
**optional**: without them, that provider/tool is simply skipped. See `.env.example`.
