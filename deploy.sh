#!/usr/bin/env bash
#
# E.V. — one-command full deploy.
#
# Packages the code, ships YOUR secret files (.env, client_secret.json, Google
# tokens) to the VM using the SSH key, installs deps and (re)starts the service.
# One command and E.V. is fully running in the cloud.
#
#   bash deploy.sh
#
# Config (override via env if your VM/key differ):
#   EV_VM_HOST   default: ubuntu@129.158.194.108
#   EV_SSH_KEY   default: oracle_ev.key   (kept out of git)
#
# Required locally: .env filled in. Optional: client_secret.json + google_token_*.json
# (only if you use Google Calendar/email).
set -euo pipefail
cd "$(dirname "$0")"

VM="${EV_VM_HOST:-ubuntu@129.158.194.108}"
KEY="${EV_SSH_KEY:-oracle_ev.key}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new"

[ -f "$KEY" ] || { echo "ERRO: chave SSH '$KEY' não encontrada."; exit 1; }
[ -f .env ]  || { echo "ERRO: .env não encontrado (preencha as chaves — veja docs/KEYS.md)."; exit 1; }

echo ">> 1/4 Empacotando o código (sem segredos)..."
export COPYFILE_DISABLE=1  # macOS: don't add ._ xattr headers to the tar
tar czf /tmp/ev-deploy.tgz \
  --exclude=.venv --exclude=.git --exclude=backups --exclude=__pycache__ \
  --exclude='*.pyc' --exclude='*.log' --exclude="$KEY" \
  ev run_telegram.py run_terminal.py requirements.txt deploy docs tests \
  authorize_google.py README.md

echo ">> 2/4 Enviando código e suas chaves pra VM..."
scp -i "$KEY" -o StrictHostKeyChecking=accept-new /tmp/ev-deploy.tgz "$VM:~/ev-deploy.tgz" >/dev/null
$SSH "$VM" 'mkdir -p ~/ev && tar xzf ~/ev-deploy.tgz -C ~/ev'
scp -i "$KEY" .env "$VM:~/ev/.env" >/dev/null
[ -f client_secret.json ] && scp -i "$KEY" client_secret.json "$VM:~/ev/" >/dev/null || true
for f in google_token_*.json; do
  [ -f "$f" ] && scp -i "$KEY" "$f" "$VM:~/ev/" >/dev/null || true
done

echo ">> 3/4 Instalando dependências e (re)iniciando o serviço..."
$SSH "$VM" 'cd ~/ev && \
  if [ ! -d .venv ]; then bash deploy/setup_vm.sh; \
  else ./.venv/bin/pip install -q --upgrade pip && \
       ./.venv/bin/pip install -q -r requirements.txt && \
       sudo systemctl restart ev; fi'

echo ">> 4/4 Verificando..."
sleep 5
STATUS=$($SSH "$VM" 'systemctl is-active ev' || true)
echo ""
echo "Status do serviço: $STATUS"
[ "$STATUS" = "active" ] && echo "✅ E.V. rodando 24/7 em $VM" || {
  echo "⚠️ Não ficou 'active'. Veja os logs: $SSH $VM 'sudo journalctl -u ev -n 40'"; exit 1; }
