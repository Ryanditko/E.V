#!/usr/bin/env bash
#
# E.V. — one-command LOCAL run (this machine, not the VM).
# Sets up the virtualenv, installs dependencies, checks .env, and starts the bot.
#
#   bash start.sh
#
set -euo pipefail
cd "$(dirname "$0")"

# Use the project-local pip config if present (points to public PyPI — helps on
# machines whose global pip points elsewhere). Harmless otherwise.
[ -f pip.conf ] && export PIP_CONFIG_FILE="$(pwd)/pip.conf"

[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Criei um .env a partir do modelo. Preencha as chaves (veja docs/KEYS.md)"
  echo "e rode 'bash start.sh' de novo."
  exit 1
fi

echo "E.V. iniciando localmente..."
exec ./.venv/bin/python run_telegram.py
