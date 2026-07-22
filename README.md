# E.V. 🕷️

Assistente pessoal de IA — voz + celular via Telegram, cérebro reutilizável.

## Arquitetura

```
Interfaces (trocáveis):  Telegram (agora) → Terminal → Web/App
        │  mesma API interna: Brain.respond(...)
Cérebro (reutilizável):  LLM (Gemini) · Memória · Personalidade · Ferramentas
```

- **`ev/`** — o cérebro. Não sabe nada de Telegram.
- **`ev/interfaces/`** — as cascas. Hoje só Telegram; terminal/web entram aqui.

| Arquivo | Papel |
|---------|-------|
| `ev/personality.py` | Quem o E.V. é (edite pra mudar o tom) |
| `ev/brain.py` | LLM + memória + ferramentas |
| `ev/memory.py` | SQLite: conversa, fatos, lembretes |
| `ev/voice.py` | Texto → áudio (edge-tts) |
| `ev/interfaces/telegram_bot.py` | Bot do Telegram |

## Setup

### 1. Dependências

```bash
cd ~/ev
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Criar o bot no Telegram

1. No Telegram, fale com **@BotFather**.
2. `/newbot` → escolha um nome e um @usuario.
3. Ele te dá um **token** — copie.

### 3. Chave do Gemini

1. Acesse https://aistudio.google.com/apikey (login Google).
2. Crie uma API key — copie.

### 4. Configurar

```bash
cp .env.example .env
# edite o .env e cole TELEGRAM_TOKEN e GEMINI_API_KEY
```

> **Dica:** rode uma vez, mande `/start` pro bot, veja seu ID nos logs e
> cole em `EV_OWNER_ID` no `.env`. Isso trava o bot só pra você.

### 5. Rodar

```bash
python run_telegram.py
```

Abra seu bot no Telegram, mande texto ou um áudio. Ele responde nos dois.

## O que já funciona (v1)

- Conversa por **texto e voz** (entende áudio, responde em texto + áudio).
- **Memória**: lembra fatos sobre você entre conversas.
- **Lembretes**: cria e lista (sem disparo agendado ainda — ver roadmap).
- **Personalidade** do E.V. editável em um arquivo.

## Roadmap

- [ ] Disparo de lembretes na hora certa (agendador).
- [ ] Ferramentas de verdade: agenda, e-mail, busca na web.
- [ ] Interface de terminal (reusa o mesmo cérebro).
- [ ] Interface web/app.
- [ ] Memória com busca vetorial (embeddings).
- [ ] `ffmpeg` opcional para responder como *voice note* nativo.
