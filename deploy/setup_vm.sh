#!/usr/bin/env bash
#
# Instala a E.V. como serviço na VM (Oracle Cloud, Ubuntu ou Oracle Linux).
# Rode DE DENTRO da pasta do projeto na VM:
#     cd ~/ev && bash deploy/setup_vm.sh
#
# Pré-requisito: o arquivo .env já deve existir em ~/ev/.env (com as chaves).
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ"

if [ ! -f .env ]; then
  echo "ERRO: falta o arquivo .env em $PROJ/.env — crie-o antes (com as chaves)."
  exit 1
fi

echo ">> Instalando Python e venv..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip
fi

echo ">> Criando ambiente virtual e instalando dependências..."
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo ">> Registrando o serviço systemd..."
sudo tee /etc/systemd/system/ev.service >/dev/null <<EOF
[Unit]
Description=E.V. — assistente pessoal (Telegram)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJ
ExecStart=$PROJ/.venv/bin/python $PROJ/run_telegram.py
Restart=always
RestartSec=5
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ev
sudo systemctl restart ev

echo ""
echo "✅ E.V. instalada e rodando como serviço (liga sozinha no boot)."
echo "   Ver logs ao vivo:  sudo journalctl -u ev -f"
echo "   Reiniciar:         sudo systemctl restart ev"
echo "   Status:            sudo systemctl status ev"
