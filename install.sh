#!/usr/bin/env bash
#
# E.V. — friendly one-command installer for LOCAL self-hosting (this machine).
#
# Does the heavy lifting so anyone can get E.V. running with minimal fuss:
#   - checks Python 3.11+ and venv support
#   - creates .venv and installs dependencies (public PyPI via pip.conf)
#   - generates a filled .env (interactive prompts, or from env vars / flags)
#   - optionally enables the web console
#   - offers to start E.V. right away
#
# This COMPLEMENTS start.sh (the minimal launcher) and does NOT replace it.
# Server / systemd install is a separate path (deploy/setup_vm.sh) — not this.
#
# Usage:
#   bash install.sh                 # interactive wizard
#   TELEGRAM_TOKEN=... GEMINI_API_KEY=... bash install.sh   # non-interactive
#   bash install.sh --help          # full help
#
set -euo pipefail
cd "$(dirname "$0")"

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

# Colors only when writing to a real terminal.
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
  RED=$'\033[31m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; YELLOW=""; RED=""; CYAN=""; RESET=""
fi

say()  { printf '%s\n' "$*"; }
info() { printf '%s\n' "${CYAN}$*${RESET}"; }
ok()   { printf '%s\n' "${GREEN}$*${RESET}"; }
warn() { printf '%s\n' "${YELLOW}$*${RESET}" >&2; }
die()  { printf '%s\n' "${RED}$*${RESET}" >&2; exit 1; }

# Mask a secret for display: keep only the last 4 chars.
mask() {
  local v="$1"
  local n=${#v}
  if [ "$n" -le 4 ]; then
    printf '****'
  else
    printf '****%s' "${v: -4}"
  fi
}

# Detect the platform for install hints: macos | debian | termux | linux | unknown
detect_platform() {
  if [ -n "${PREFIX:-}" ] && printf '%s' "${PREFIX:-}" | grep -q "com.termux"; then
    printf 'termux'; return
  fi
  case "${OSTYPE:-}" in
    darwin*) printf 'macos'; return ;;
  esac
  case "$(uname -s 2>/dev/null || printf unknown)" in
    Darwin) printf 'macos'; return ;;
    Linux)
      if [ -f /etc/debian_version ]; then printf 'debian'; else printf 'linux'; fi
      return ;;
  esac
  printf 'unknown'
}

python_install_hint() {
  case "$(detect_platform)" in
    macos)  say "  macOS:   brew install python@3.12" ;;
    debian) say "  Debian/Ubuntu:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip" ;;
    termux) say "  Termux:  pkg install python" ;;
    *)      say "  Instale o Python 3.11+ pelo gerenciador do seu sistema (ou https://python.org)." ;;
  esac
}

# ---------------------------------------------------------------------------
# CLI flags
# ---------------------------------------------------------------------------

ASSUME_YES=0
DO_RUN=""   # empty = ask (interactive); set by future use if needed

usage() {
  cat <<'EOF'
E.V. — instalador local (self-host neste computador).

Uso:
  bash install.sh [opções]

Opções:
  -y, --yes     Aceita os padrões dos extras opcionais (não pergunta sobre
                console web etc.). Ainda pergunta as chaves obrigatórias se
                estiver no modo interativo e elas faltarem.
  -h, --help    Mostra esta ajuda.

Variáveis de ambiente (modo automatizável / CI):
  TELEGRAM_TOKEN   (obrigatória)  token do bot — @BotFather no Telegram
  GEMINI_API_KEY   (obrigatória)  chave Gemini — https://aistudio.google.com/apikey
  EV_OWNER_ID      (opcional)     seu ID do Telegram; trava o bot só pra você
  EV_WEB_TOKEN     (opcional)     token do console web; se definido, ativa a web

Exemplos:
  bash install.sh
  TELEGRAM_TOKEN=123:abc GEMINI_API_KEY=xyz bash install.sh
  TELEGRAM_TOKEN=123:abc GEMINI_API_KEY=xyz EV_WEB_TOKEN=segredo bash install.sh -y

Onde conseguir as chaves: docs/KEYS.md
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes)  ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Opção desconhecida: $1  (use --help)" ;;
  esac
  shift
done

# Interactive only when stdin is a real terminal.
INTERACTIVE=0
[ -t 0 ] && INTERACTIVE=1

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

say ""
say "${BOLD}E.V. — instalador${RESET}"
say "${DIM}Assistente pessoal · instalação local neste computador${RESET}"
say ""

# ---------------------------------------------------------------------------
# 1. Prerequisite checks: python3 present and >= 3.11, venv works
# ---------------------------------------------------------------------------

info "1/4 · Verificando pré-requisitos..."

if ! command -v python3 >/dev/null 2>&1; then
  warn "Não encontrei o 'python3'. O E.V. precisa de Python 3.11 ou mais novo."
  python_install_hint
  die "Instale o Python e rode 'bash install.sh' de novo."
fi

# Robustly parse the (major, minor) version.
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || printf '0.0')"
PYMAJ="${PYVER%%.*}"
PYMIN="${PYVER##*.}"
if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 11 ]; }; then
  warn "Seu python3 é a versão ${PYVER}, mas o E.V. precisa de 3.11 ou mais novo."
  python_install_hint
  die "Atualize o Python e rode 'bash install.sh' de novo."
fi

# Make sure the venv module actually works (Debian splits it into python3-venv).
if ! python3 -c 'import venv' >/dev/null 2>&1; then
  warn "O módulo 'venv' do Python não está disponível."
  python_install_hint
  die "Instale o suporte a venv e rode 'bash install.sh' de novo."
fi

ok "  Python ${PYVER} OK."

# Reuse the project-local pip config (points at public PyPI) exactly like start.sh.
[ -f pip.conf ] && export PIP_CONFIG_FILE="$(pwd)/pip.conf"

# ---------------------------------------------------------------------------
# 2. Virtualenv + dependencies
# ---------------------------------------------------------------------------

info "2/4 · Preparando o ambiente e instalando dependências..."

if [ ! -d .venv ]; then
  say "  Criando o ambiente virtual (.venv)..."
  python3 -m venv .venv
else
  say "  Ambiente virtual (.venv) já existe."
fi

say "  Atualizando o pip..."
./.venv/bin/pip install -q --upgrade pip

say "  Instalando pacotes do requirements.txt (pode levar um tempo)..."
./.venv/bin/pip install -q -r requirements.txt

ok "  Dependências instaladas."

# ---------------------------------------------------------------------------
# 3. .env generation
# ---------------------------------------------------------------------------

info "3/4 · Configuração (.env)..."

if [ -f .env ]; then
  ok "  Um .env já existe — não vou sobrescrever. Mantendo suas configurações."
  ENV_ALREADY=1
else
  ENV_ALREADY=0

  # Precedence: (1) env vars already set in the shell, (2) interactive prompt.
  TG="${TELEGRAM_TOKEN:-}"
  GK="${GEMINI_API_KEY:-}"
  OWNER="${EV_OWNER_ID:-}"
  WEBTOK="${EV_WEB_TOKEN:-}"

  if [ "$INTERACTIVE" -eq 1 ]; then
    say ""
    say "  Vou pedir as 2 chaves obrigatórias. Onde conseguir: ${BOLD}docs/KEYS.md${RESET}"
    say ""

    if [ -z "$TG" ]; then
      say "  ${BOLD}TELEGRAM_TOKEN${RESET} — fale com o @BotFather no Telegram:"
      say "    mande /newbot, escolha um nome, e ele te dá o token."
      while [ -z "$TG" ]; do
        printf '    Cole o token do Telegram: '
        read -r TG || true
        [ -z "$TG" ] && warn "    O token é obrigatório."
      done
    fi

    if [ -z "$GK" ]; then
      say ""
      say "  ${BOLD}GEMINI_API_KEY${RESET} — pegue em https://aistudio.google.com/apikey"
      say "    (use uma conta Google pessoal; é grátis)."
      while [ -z "$GK" ]; do
        printf '    Cole a chave do Gemini: '
        read -r GK || true
        [ -z "$GK" ] && warn "    A chave é obrigatória."
      done
    fi

    if [ -z "$OWNER" ]; then
      say ""
      say "  ${BOLD}EV_OWNER_ID${RESET} (opcional) — trava o bot só pra você."
      say "    Deixe em branco por enquanto: depois é só mandar /start pro bot"
      say "    e ler seu ID nos logs. Enter pula."
      printf '    Seu ID do Telegram (opcional): '
      read -r OWNER || true
    fi
  else
    # Non-interactive: required values must come from env vars.
    MISSING=""
    [ -z "$TG" ] && MISSING="TELEGRAM_TOKEN"
    if [ -z "$GK" ]; then
      [ -n "$MISSING" ] && MISSING="$MISSING, "
      MISSING="${MISSING}GEMINI_API_KEY"
    fi
    if [ -n "$MISSING" ]; then
      warn "Modo não-interativo, mas faltando variável obrigatória: ${MISSING}."
      warn "Defina no ambiente e rode de novo, ex:"
      warn "  TELEGRAM_TOKEN=... GEMINI_API_KEY=... bash install.sh"
      die "Veja onde conseguir as chaves em docs/KEYS.md"
    fi
  fi

  # --- Optional add-ons (interactive, default no; -y takes defaults) ---
  if [ "$INTERACTIVE" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ]; then
    if [ -z "$WEBTOK" ]; then
      say ""
      printf '  Ativar o console web agora? [s/N] '
      read -r ANS || true
      case "${ANS:-}" in
        s|S|sim|Sim|y|Y|yes)
          WEBTOK="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
          ok "    Console web ativado. Depois de iniciar, acesse:"
          say "      http://localhost:8000  (token: $(mask "$WEBTOK"))"
          say "      O token completo fica salvo no .env (EV_WEB_TOKEN)."
          ;;
      esac
    fi
    say ""
    say "  ${DIM}Extras opcionais (não configuro agora, veja docs/KEYS.md):${RESET}"
    say "  ${DIM}  · Google Calendar / Gmail — OAuth documentado em docs/KEYS.md${RESET}"
    say "  ${DIM}  · Spotify (playlists/playback) — documentado em docs/KEYS.md${RESET}"
  fi

  # --- Write .env from .env.example, substituting ONLY provided keys ---
  # A python here-doc is the safest: it preserves every other line/comment
  # verbatim and handles secrets containing /, &, :, etc. without escaping.
  [ -f .env.example ] || die "Não encontrei .env.example — está no diretório certo?"

  EV_SET_TELEGRAM_TOKEN="$TG" \
  EV_SET_GEMINI_API_KEY="$GK" \
  EV_SET_EV_OWNER_ID="$OWNER" \
  EV_SET_EV_WEB_TOKEN="$WEBTOK" \
  python3 <<'PY'
import os

# Only substitute keys the user actually provided (non-empty). Everything
# else in .env.example is preserved exactly (comments, defaults, blank lines).
overrides = {}
for key in ("TELEGRAM_TOKEN", "GEMINI_API_KEY", "EV_OWNER_ID", "EV_WEB_TOKEN"):
    val = os.environ.get("EV_SET_" + key, "")
    if val != "":
        overrides[key] = val

with open(".env.example", "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
for line in lines:
    stripped = line.lstrip()
    replaced = False
    for key, val in overrides.items():
        # Anchor on "KEY=" at the start of the (unindented) line only.
        if stripped.startswith(key + "="):
            newline = "\n" if line.endswith("\n") else ""
            out.append(f"{key}={val}{newline}")
            replaced = True
            break
    if not replaced:
        out.append(line)

with open(".env", "w", encoding="utf-8") as f:
    f.writelines(out)

print("  .env criado a partir de .env.example.")
PY

  # Masked confirmation — never echo full secrets.
  ok "  Configurado:"
  say "    TELEGRAM_TOKEN = $(mask "$TG")"
  say "    GEMINI_API_KEY = $(mask "$GK")"
  [ -n "$OWNER" ]  && say "    EV_OWNER_ID    = $OWNER"
  [ -n "$WEBTOK" ] && say "    EV_WEB_TOKEN   = $(mask "$WEBTOK")  (console web ativo)"
fi

# ---------------------------------------------------------------------------
# 4. Finish + optional run
# ---------------------------------------------------------------------------

say ""
info "4/4 · Instalação concluída!"
say ""
say "  Como iniciar o E.V.:"
say "    ${BOLD}bash start.sh${RESET}                         # bot do Telegram (atalho)"
say "    ${BOLD}./.venv/bin/python run_telegram.py${RESET}    # bot do Telegram"
say "    ${BOLD}./.venv/bin/python run_web.py${RESET}         # console web (http://localhost:8000)"
say "    ${BOLD}./.venv/bin/python run_terminal.py${RESET}    # chat no terminal"
say ""

if [ "${ENV_ALREADY:-0}" -eq 0 ] && [ -z "${EV_OWNER_ID:-}" ]; then
  say "  ${DIM}Dica: mande /start pro bot e copie seu ID dos logs pra EV_OWNER_ID no .env.${RESET}"
  say ""
fi

if [ "$INTERACTIVE" -eq 1 ]; then
  printf '  Iniciar agora? [Telegram / Web / Terminal / não] '
  read -r CHOICE || true
  case "${CHOICE:-}" in
    t|T|telegram|Telegram|TELEGRAM)
      say ""; ok "  Iniciando o bot do Telegram..."
      exec ./.venv/bin/python run_telegram.py ;;
    w|W|web|Web|WEB)
      say ""; ok "  Iniciando o console web em http://localhost:8000 ..."
      exec ./.venv/bin/python run_web.py ;;
    term|Term|terminal|Terminal|TERMINAL)
      say ""; ok "  Iniciando o chat no terminal..."
      exec ./.venv/bin/python run_terminal.py ;;
    *)
      say ""; say "  Beleza! É só rodar um dos comandos acima quando quiser. Até já. :)" ;;
  esac
else
  say "  ${DIM}(modo não-interativo — nada foi iniciado; rode um comando acima)${RESET}"
fi

exit 0
