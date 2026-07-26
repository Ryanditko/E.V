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
# SQLCipher (encryption at rest) — kept out of requirements.txt so CI/local
# wheels never break; only the VM needs it. Harmless if the DB isn't encrypted.
./.venv/bin/pip install sqlcipher3-binary || echo ">> aviso: sqlcipher3-binary falhou (só necessário se EV_DB_KEY estiver setado)"

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

# Web interface service (mirrors ev.service; serves run_web.py on EV_WEB_PORT).
echo ">> Registrando o serviço systemd da interface web (ev-web)..."
sudo tee /etc/systemd/system/ev-web.service >/dev/null <<EOF
[Unit]
Description=E.V. — web interface
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJ
ExecStart=$PROJ/.venv/bin/python $PROJ/run_web.py
Restart=always
RestartSec=5
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ev-web
sudo systemctl restart ev-web

echo ""
echo "✅ E.V. instalada e rodando como serviço (liga sozinha no boot)."
echo "   Ver logs ao vivo:  sudo journalctl -u ev -f   (ou -u ev-web)"
echo "   Reiniciar:         sudo systemctl restart ev   (ou ev-web)"
echo "   Status:            sudo systemctl status ev    (ou ev-web)"
echo "   Web:               interface em EV_WEB_PORT (padrão 8000); HTTPS via deploy/HTTPS_TAILSCALE.md"
