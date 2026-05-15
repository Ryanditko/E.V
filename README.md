# E.V. - Personal AI Assistant

A local-first, privacy-focused AI assistant inspired by Spider-Man's E.D.I.T.H. Built from scratch to run entirely on your machine using Ollama.

## Features

- **100% Local**: Runs on your machine with Ollama, no cloud APIs required
- **CLI Interface**: Terminal-based interaction (Claude Code style)
- **Conversation Memory**: Maintains context within sessions
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com/) installed and running
- Recommended model: `qwen2.5:7b-instruct`

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd ev

# Install dependencies
pip install -e .

# Or with uv
uv pip install -e .
```

## Setup Ollama

```bash
# Install Ollama (see https://ollama.com/download)

# Pull the recommended model
ollama pull qwen2.5:7b-instruct

# Start Ollama server
ollama serve
```

## Usage

```bash
# Start E.V.
ev

# Or run directly
python -m ev.main
```

### Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/quit` | Exit E.V. |

## Project Structure

```
ev/
├── src/ev/
│   ├── __init__.py
│   ├── main.py           # CLI entry point and REPL
│   └── llm/
│       ├── __init__.py
│       └── ollama.py     # Ollama client
├── config/
│   └── prompts/
│       └── system.md     # System prompt for E.V.
├── pyproject.toml
└── README.md
```

## Roadmap

- [x] Phase 1: Basic CLI + LLM integration
- [ ] Phase 2: Tool system (files, shell, web search)
- [ ] Phase 3: Persistent memory (SQLite)
- [ ] Phase 4: Google Calendar/Gmail integration
- [ ] Phase 5: Browser control (Playwright)
- [ ] Phase 6: WhatsApp bot for mobile access
- [ ] Phase 7: Voice mode (optional)

## Hardware Recommendations

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 4GB | 6GB+ |
| RAM | 8GB | 16GB+ |
| Model | qwen2.5:3b | qwen2.5:7b-instruct |

## License

MIT
